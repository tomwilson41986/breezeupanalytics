#!/usr/bin/env python3
"""
Horse Ratings by Distance Group
================================
Reads breeze-up data from a CSV/TSV file, groups horses by "Distance UT",
ranks them on five metrics with equal weight, and produces a rating
between 10 (worst) and 100 (best).

Ranking metrics (all within each Distance UT group):
  - Time UT              : lower is better  (rank 1 = fastest)
  - Time GO              : lower is better  (rank 1 = fastest)
  - Stride Length UT (ft): higher is better (rank 1 = longest)
  - Stride Length GO (ft): higher is better (rank 1 = longest)
  - diff                 : higher is better  (rank 1 = biggest positive diff)

Usage
-----
    python scripts/rate_horses.py data/ratings/input.csv
    python scripts/rate_horses.py data/ratings/input.csv --output data/ratings/rated.csv
    python scripts/rate_horses.py data/ratings/input.tsv          # auto-detects tab-separated
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from convert_stride_to_feet import convert_stride_to_feet


RANK_COLS = {
    # column_name: ascending (True = lower is better → rank ascending)
    "Time UT": True,
    "Time GO": True,
    "Stride Length UT (ft)": False,
    "Stride Length GO (ft)": False,
    "diff": False,
}

# Known standard distances (ft). Nearby values are snapped to these.
STANDARD_DISTANCES = [205, 404.32]
DISTANCE_SNAP_TOLERANCE = 5  # ft – values within this range snap to the standard

RATING_MIN = 10
RATING_MAX = 100


def _snap_distance(val, standards=STANDARD_DISTANCES, tol=DISTANCE_SNAP_TOLERANCE):
    """Snap a distance value to the nearest standard if within tolerance."""
    if pd.isna(val):
        return val
    for std in standards:
        if abs(val - std) <= tol:
            return std
    return val


def load_data(path: Path) -> pd.DataFrame:
    """Load CSV or TSV (auto-detected) into a DataFrame."""
    text = path.read_text()
    sep = "\t" if "\t" in text.split("\n")[0] else ","
    df = pd.read_csv(path, sep=sep, on_bad_lines="warn")
    # Normalise column names: strip whitespace
    df.columns = df.columns.str.strip()
    return df


def _sanitise_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Replace negative or clearly erroneous metric values with NaN."""
    metric_cols = ["Time UT", "Time GO",
                   "Stride Length UT", "Stride Length GO",
                   "Stride Length UT (ft)", "Stride Length GO (ft)",
                   "Stride Frequency UT", "Stride Frequency GO",
                   "diff"]
    for col in metric_cols:
        if col not in df.columns:
            continue
        numeric = pd.to_numeric(df[col], errors="coerce")
        # Negative times, stride lengths, or frequencies are invalid
        if col != "diff":
            df.loc[numeric < 0, col] = pd.NA
        # Recompute diff where underlying values were scrubbed
        if col in ("Stride Length UT", "Stride Length GO",
                    "Stride Length UT (ft)", "Stride Length GO (ft)"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def compute_ratings(df: pd.DataFrame) -> pd.DataFrame:
    """Add per-distance-group ranks and a composite rating (10–100)."""
    df = df.copy()

    # Snap distances to standard groups so near-misses aren't isolated
    df["Distance UT"] = pd.to_numeric(df["Distance UT"], errors="coerce")
    df["Distance UT"] = df["Distance UT"].apply(_snap_distance)

    # Sanitise obviously bad metric values (negative times, strides, etc.)
    df = _sanitise_metrics(df)

    # Recompute diff after sanitisation (GO stride may have been NaN'd)
    if "Stride Length GO (ft)" in df.columns and "Stride Length UT (ft)" in df.columns:
        df["diff"] = pd.to_numeric(df.get("diff"), errors="coerce")
        # Where stride GO was scrubbed, diff is also invalid
        go_bad = df["Stride Length GO (ft)"].isna() | df["Stride Length UT (ft)"].isna()
        df.loc[go_bad, "diff"] = pd.NA

    # Coerce metric columns to numeric; non-numeric → NaN
    for col in RANK_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Only rate horses that have BOTH stride and time data
    required_cols = list(RANK_COLS.keys())
    metric_mask = df[required_cols].notna().all(axis=1)
    df["_has_data"] = metric_mask

    rank_col_names: list[str] = []

    for col, ascending in RANK_COLS.items():
        rank_name = f"Rank {col}"
        rank_col_names.append(rank_name)
        # Rank within each Distance UT group; NaN metrics get NaN rank
        df[rank_name] = df.groupby("Distance UT")[col].rank(
            method="min", ascending=ascending, na_option="keep"
        )

    # Null out ranks for horses missing any required data (stride + time)
    for rc in rank_col_names:
        df.loc[~df["_has_data"], rc] = pd.NA

    # Composite score = mean of ranks (lower mean rank → better horse)
    df["Mean Rank"] = df[rank_col_names].mean(axis=1)

    # Scale within each Distance UT group: best mean rank → 100, worst → 10
    def scale_group(g: pd.DataFrame) -> pd.Series:
        valid = g["Mean Rank"].dropna()
        if len(valid) <= 1:
            # Only one horse with data → give them 100
            return g["Mean Rank"].map(lambda v: RATING_MAX if pd.notna(v) else pd.NA)
        best = valid.min()
        worst = valid.max()
        if best == worst:
            return g["Mean Rank"].map(lambda v: RATING_MAX if pd.notna(v) else pd.NA)
        # Invert: low mean rank → high rating
        scaled = RATING_MIN + (RATING_MAX - RATING_MIN) * (worst - g["Mean Rank"]) / (worst - best)
        return scaled.where(g["Mean Rank"].notna(), other=pd.NA)

    df["Rating"] = df.groupby("Distance UT", group_keys=False).apply(
        lambda g: scale_group(g)
    )

    # Round rating to 1 decimal place (use pd.to_numeric to handle NA safely)
    df["Rating"] = pd.to_numeric(df["Rating"], errors="coerce").round(1)

    # Clean up helper column
    df.drop(columns=["_has_data"], inplace=True)

    return df


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Rate breeze-up horses by distance group")
    parser.add_argument("input", type=Path, help="Path to input CSV/TSV file")
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Path for rated output CSV (default: <input>_rated.csv)",
    )
    args = parser.parse_args(argv)

    if not args.input.exists():
        print(f"Error: {args.input} not found", file=sys.stderr)
        sys.exit(1)

    df = load_data(args.input)
    df = convert_stride_to_feet(df)
    df = compute_ratings(df)

    output_path = args.output or args.input.with_name(args.input.stem + "_rated.csv")
    df.to_csv(output_path, index=False)
    print(f"Rated {len(df)} horses → {output_path}")

    # Print summary per distance group
    for dist, group in df.groupby("Distance UT"):
        rated = group["Rating"].dropna()
        if rated.empty:
            continue
        print(f"\n  Distance UT = {dist}  ({len(rated)} rated horses)")
        top = group.nsmallest(3, "Mean Rank")[["Hip", "Rating", "Mean Rank"]]
        for _, row in top.iterrows():
            print(f"    Hip {int(row['Hip']):>4d}  Rating: {row['Rating']:5.1f}")


if __name__ == "__main__":
    main()
