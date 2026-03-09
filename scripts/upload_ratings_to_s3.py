#!/usr/bin/env python3
"""Upload rated CSV data to S3 as ratings.json for a given sale.

Reads the rated CSV output from rate_horses.py, converts it to a JSON
object keyed by hip number, and uploads to S3 at:
    data/{sale_key}/ratings.json

Usage:
    python scripts/upload_ratings_to_s3.py obs_march_2026 data/ratings/obs_march_2026_rated.csv

Environment variables:
    BREEZEUP_AWS_ACCESS_KEY_ID
    BREEZEUP_AWS_SECRET_ACCESS_KEY
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

import pandas as pd

# Reuse S3 upload from sync_to_s3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.sync_to_s3 import s3_put

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
)
logger = logging.getLogger("upload_ratings")


def rated_csv_to_json(path: Path) -> dict:
    """Convert a rated CSV to a JSON dict keyed by hip number."""
    text = path.read_text()
    sep = "\t" if "\t" in text.split("\n")[0] else ","
    df = pd.read_csv(path, sep=sep, on_bad_lines="warn")
    df.columns = df.columns.str.strip()

    ratings = {}
    for _, row in df.iterrows():
        hip = row.get("Hip")
        if pd.isna(hip):
            continue
        hip_key = str(int(hip))

        entry = {}
        # Core rating
        if pd.notna(row.get("Rating")):
            entry["rating"] = round(float(row["Rating"]), 1)
        if pd.notna(row.get("Mean Rank")):
            entry["meanRank"] = round(float(row["Mean Rank"]), 2)

        # Distance group
        if pd.notna(row.get("Distance UT")):
            entry["distanceUT"] = str(row["Distance UT"])

        # Stride lengths (feet)
        if pd.notna(row.get("Stride Length UT (ft)")):
            entry["strideLengthUT"] = round(float(row["Stride Length UT (ft)"]), 2)
        if pd.notna(row.get("Stride Length GO (ft)")):
            entry["strideLengthGO"] = round(float(row["Stride Length GO (ft)"]), 2)

        # Stride frequencies
        if pd.notna(row.get("Stride Frequency UT")):
            entry["strideFreqUT"] = round(float(row["Stride Frequency UT"]), 2)
        if pd.notna(row.get("Stride Frequency GO")):
            entry["strideFreqGO"] = round(float(row["Stride Frequency GO"]), 2)

        # Times
        if pd.notna(row.get("Time UT")):
            entry["timeUT"] = round(float(row["Time UT"]), 2)
        if pd.notna(row.get("Time GO")):
            entry["timeGO"] = round(float(row["Time GO"]), 2)

        # Diff
        if pd.notna(row.get("diff")):
            entry["diff"] = round(float(row["diff"]), 2)

        # Individual ranks
        rank_mappings = {
            "Rank Time UT": "rankTimeUt",
            "Rank Time GO": "rankTimeGo",
            "Rank Stride Length UT (ft)": "rankStrideLengthUt",
            "Rank Stride Length GO (ft)": "rankStrideLengthGo",
            "Rank diff": "rankDiff",
        }
        for rank_col, camel in rank_mappings.items():
            if pd.notna(row.get(rank_col)):
                entry[camel] = int(row[rank_col])

        ratings[hip_key] = entry

    return ratings


def main():
    if len(sys.argv) < 3:
        print("Usage: upload_ratings_to_s3.py <sale_key> <rated_csv_path>", file=sys.stderr)
        sys.exit(1)

    sale_key = sys.argv[1]
    csv_path = Path(sys.argv[2])

    if not csv_path.exists():
        logger.error("File not found: %s", csv_path)
        sys.exit(1)

    # Verify AWS credentials
    if not os.environ.get("BREEZEUP_AWS_ACCESS_KEY_ID"):
        logger.error("BREEZEUP_AWS_ACCESS_KEY_ID not set")
        sys.exit(1)

    ratings = rated_csv_to_json(csv_path)
    logger.info("Parsed %d hip ratings from %s", len(ratings), csv_path)

    payload = json.dumps(ratings, indent=2).encode()
    s3_key = f"data/{sale_key}/ratings.json"
    s3_put(s3_key, payload)
    logger.info("Uploaded ratings for %d hips to s3://%s", len(ratings), s3_key)


if __name__ == "__main__":
    main()
