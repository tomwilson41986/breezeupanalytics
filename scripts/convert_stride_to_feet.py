#!/usr/bin/env python3
"""
Convert Stride Length from metres to feet.

Reads stride CSV data, adds 'Stride Length UT (ft)' and 'Stride Length GO (ft)'
columns by multiplying the metre values by 3.28084, and writes the result back.

Usage
-----
    python scripts/convert_stride_to_feet.py data/ratings/obsMarch\ stride.csv
    python scripts/convert_stride_to_feet.py data/ratings/input.csv --output data/ratings/output.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

METRES_TO_FEET = 3.28084


def convert_stride_to_feet(df: pd.DataFrame) -> pd.DataFrame:
    """Add Stride Length (ft) columns converted from metre columns."""
    df = df.copy()

    for label in ("UT", "GO"):
        src_col = f"Stride Length {label}"
        dst_col = f"Stride Length {label} (ft)"
        if src_col in df.columns:
            df[src_col] = pd.to_numeric(df[src_col], errors="coerce")
            df[dst_col] = (df[src_col] * METRES_TO_FEET).round(2)

    return df


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Add Stride Length (ft) columns to stride CSV data"
    )
    parser.add_argument("input", type=Path, help="Path to input CSV file")
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Path for output CSV (default: overwrites input)",
    )
    args = parser.parse_args(argv)

    if not args.input.exists():
        print(f"Error: {args.input} not found", file=sys.stderr)
        sys.exit(1)

    text = args.input.read_text()
    sep = "\t" if "\t" in text.split("\n")[0] else ","
    df = pd.read_csv(args.input, sep=sep, on_bad_lines="warn")
    df.columns = df.columns.str.strip()

    df = convert_stride_to_feet(df)

    output_path = args.output or args.input
    df.to_csv(output_path, index=False)
    print(f"Converted {len(df)} rows → {output_path}")

    # Show a sample of the new columns
    sample = df[["Hip", "Stride Length UT", "Stride Length UT (ft)",
                  "Stride Length GO", "Stride Length GO (ft)"]].dropna().head(5)
    print("\nSample:")
    print(sample.to_string(index=False))


if __name__ == "__main__":
    main()
