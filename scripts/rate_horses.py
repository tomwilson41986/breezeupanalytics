#!/usr/bin/env python3
"""
Horse Ratings by Distance Group
================================
Reads breeze-up data from a CSV/TSV file, groups horses by "Distance UT",
ranks them on five metrics with equal weight, and produces a rating
between 10 (worst) and 100 (best).

Ranking metrics (all within each Distance UT group):
  - Time UT        : lower is better  (rank 1 = fastest)
  - Time GO        : lower is better  (rank 1 = fastest)
  - Stride Length UT: higher is better (rank 1 = longest)
  - Stride Length GO: higher is better (rank 1 = longest)
  - diff           : higher is better  (rank 1 = biggest positive diff)

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


RANK_COLS = {
    # column_name: ascending (True = lower is better → rank ascending)
    "Time UT": True,
    "Time GO": True,
    "Stride Length UT": False,
    "Stride Length GO": False,
    "diff": False,
}

RATING_MIN = 10
RATING_MAX = 100


def load_data(path: Path) -> pd.DataFrame:
    """Load CSV or TSV (auto-detected) into a DataFrame."""
    text = path.read_text()
    sep = "\t" if "\t" in text.split("\n")[0] else ","
    df = pd.read_csv(path, sep=sep, on_bad_lines="warn")
    # Normalise column names: strip whitespace
    df.columns = df.columns.str.strip()
    return df


def compute_ratings(df: pd.DataFrame) -> pd.DataFrame:
    """Add per-distance-group ranks and a composite rating (10–100)."""
    # Coerce metric columns to numeric; non-numeric → NaN
    for col in RANK_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Drop rows where ALL ranking columns are missing (empty horses)
    metric_mask = df[list(RANK_COLS)].notna().any(axis=1)
    df = df.copy()
    df["_has_data"] = metric_mask

    rank_col_names: list[str] = []

    for col, ascending in RANK_COLS.items():
        rank_name = f"Rank {col}"
        rank_col_names.append(rank_name)
        # Rank within each Distance UT group; NaN metrics get NaN rank
        df[rank_name] = df.groupby("Distance UT")[col].rank(
            method="min", ascending=ascending, na_option="keep"
        )

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

    # Round rating to 1 decimal place
    df["Rating"] = df["Rating"].round(1)

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
