#!/usr/bin/env python3
"""Initialize the database: create tables and seed known sale records."""

import sys
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import OBS_CATALOG_IDS, SQLITE_URL
from src.db import create_tables, get_session_factory
from src.models import Sale

# Known 2025 OBS sales for seeding
SEED_SALES = [
    Sale(
        sale_id="obs_march_2025",
        company="OBS",
        sale_name="OBS March 2YO in Training 2025",
        year=2025,
        location="Ocala, FL",
        catalog_sale_id="142",
    ),
    Sale(
        sale_id="obs_spring_2025",
        company="OBS",
        sale_name="OBS Spring 2YO in Training 2025",
        year=2025,
        location="Ocala, FL",
        catalog_sale_id="144",
    ),
    Sale(
        sale_id="obs_june_2025",
        company="OBS",
        sale_name="OBS June 2YO & HRA 2025",
        year=2025,
        location="Ocala, FL",
        catalog_sale_id="145",
    ),
    Sale(
        sale_id="obs_march_2026",
        company="OBS",
        sale_name="OBS March 2YO in Training 2026",
        year=2026,
        location="Ocala, FL",
        catalog_sale_id="149",
    ),
]


def main(db_url: str | None = None):
    url = db_url or SQLITE_URL
    print(f"Initializing database at: {url}")

    engine = create_tables(
        __import__("sqlalchemy").create_engine(url, echo=True)
    )
    SessionFactory = get_session_factory(engine)

    with SessionFactory() as session:
        for sale in SEED_SALES:
            existing = session.get(Sale, sale.sale_id)
            if existing is None:
                session.add(sale)
                print(f"  Seeded: {sale.sale_id}")
            else:
                print(f"  Already exists: {sale.sale_id}")
        session.commit()

    print("Done.")


if __name__ == "__main__":
    # Accept optional DB URL as first argument
    url = sys.argv[1] if len(sys.argv) > 1 else None
    main(url)
