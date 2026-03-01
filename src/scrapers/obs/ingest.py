"""Ingest pipeline: fetch OBS sale JSON and populate the database.

Takes parsed OBSSale/OBSHip dataclasses from the scraper and upserts them
into the sale, lot, and asset tables.
"""

import logging
from datetime import date, datetime

from sqlalchemy.orm import Session

from src.models import Asset, Lot, Sale
from src.scrapers.obs.catalog import OBSHip, OBSSale

logger = logging.getLogger(__name__)


def _parse_date(date_str: str | None, fmt: str = "%m/%d/%Y") -> date | None:
    """Parse a date string, returning None on failure."""
    if not date_str or not date_str.strip():
        return None
    try:
        return datetime.strptime(date_str.strip(), fmt).date()
    except ValueError:
        return None


def _parse_datetime(dt_str: str | None) -> datetime | None:
    """Parse a datetime string like '2025-03-11 04:00:00'."""
    if not dt_str or not dt_str.strip():
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(dt_str.strip(), fmt)
        except ValueError:
            continue
    return None


def _make_sale_id(obs_sale: OBSSale) -> str:
    """Generate our internal sale_id from OBS data. e.g. 'obs_march_2025'."""
    name = obs_sale.sale_name.lower()
    if "march" in name or "mar" in obs_sale.sale_short_name.lower():
        month = "march"
    elif "spring" in name or "apr" in name:
        month = "spring"
    elif "june" in name or "jun" in name or "july" in name or "jul" in name:
        month = "june"
    elif "winter" in name:
        month = "winter"
    elif "october" in name or "oct" in name:
        month = "october"
    else:
        month = obs_sale.sale_short_name.strip().replace(" ", "_").lower()
    return f"obs_{month}_{obs_sale.year}"


def _make_lot_id(sale_id: str, hip_number: int) -> str:
    return f"{sale_id}_{hip_number}"


def _expand_sex(code: str | None) -> str | None:
    """Expand OBS sex codes to full words."""
    if not code:
        return None
    return {"C": "Colt", "F": "Filly", "G": "Gelding", "R": "Ridgling"}.get(
        code.strip().upper(), code
    )


def _filter_sale_status(status: str) -> str | None:
    """Only store statuses that match our check constraint."""
    if status in ("sold", "RNA", "out", "withdrawn"):
        return status
    return None  # "pending" etc. stored as NULL


def ingest_sale(obs_sale: OBSSale, db: Session) -> Sale:
    """Upsert a sale and all its lots + asset records into the database.

    Returns the Sale ORM object.
    """
    sale_id = _make_sale_id(obs_sale)
    logger.info("Ingesting sale %s (%s, %d hips)", sale_id, obs_sale.sale_name, len(obs_sale.hips))

    # Upsert sale
    sale = db.get(Sale, sale_id)
    if sale is None:
        sale = Sale(
            sale_id=sale_id,
            company="OBS",
            sale_name=obs_sale.sale_name,
            year=obs_sale.year,
            start_date=_parse_datetime(obs_sale.start_date).date() if _parse_datetime(obs_sale.start_date) else None,
            end_date=_parse_datetime(obs_sale.end_date).date() if _parse_datetime(obs_sale.end_date) else None,
            location="Ocala, FL",
            catalog_url=f"https://obssales.com/catalog/#{obs_sale.sale_id}",
            catalog_sale_id=obs_sale.sale_id,
        )
        db.add(sale)
    else:
        sale.sale_name = obs_sale.sale_name
        sale.start_date = _parse_datetime(obs_sale.start_date).date() if _parse_datetime(obs_sale.start_date) else sale.start_date
        sale.end_date = _parse_datetime(obs_sale.end_date).date() if _parse_datetime(obs_sale.end_date) else sale.end_date
        sale.catalog_sale_id = obs_sale.sale_id

    db.flush()

    # Track stats
    stats = {"created": 0, "updated": 0, "assets": 0}

    for obs_hip in obs_sale.hips:
        lot_id = _make_lot_id(sale_id, obs_hip.hip_number)

        lot = db.get(Lot, lot_id)
        if lot is None:
            lot = Lot(lot_id=lot_id, hip_number=obs_hip.hip_number, sale_id=sale_id)
            db.add(lot)
            stats["created"] += 1
        else:
            stats["updated"] += 1

        # Update all fields (upsert semantics)
        lot.horse_name = obs_hip.horse_name
        lot.sex = _expand_sex(obs_hip.sex)
        lot.colour = obs_hip.colour
        lot.year_of_birth = obs_hip.year_of_birth
        lot.sire = obs_hip.sire
        lot.dam = obs_hip.dam
        lot.dam_sire = obs_hip.dam_sire
        lot.consignor = obs_hip.consignor
        lot.state_bred = obs_hip.state_bred
        lot.under_tack_distance = obs_hip.under_tack_distance
        lot.under_tack_time = obs_hip.under_tack_time
        lot.under_tack_date = _parse_date(obs_hip.under_tack_date)
        lot.sale_price = obs_hip.sale_price
        lot.sale_status = _filter_sale_status(obs_hip.sale_status)
        lot.buyer = obs_hip.buyer if obs_hip.buyer != "RNA" else None

        db.flush()

        # Upsert asset records for media
        _upsert_assets(lot_id, obs_hip, db)
        stats["assets"] += sum([obs_hip.has_video, obs_hip.has_walk_video,
                                obs_hip.has_photo, bool(obs_hip.pedigree_pdf_url)])

    db.commit()
    logger.info("Ingest complete: %d created, %d updated, %d assets tracked",
                stats["created"], stats["updated"], stats["assets"])
    return sale


def _upsert_assets(lot_id: str, obs_hip: OBSHip, db: Session):
    """Create asset rows for each available media type if not already tracked."""
    media_map = [
        ("breeze_video", obs_hip.video_url, obs_hip.has_video),
        ("walk_video", obs_hip.walk_video_url, obs_hip.has_walk_video),
        ("photo", obs_hip.photo_url, obs_hip.has_photo),
        ("pedigree_page", obs_hip.pedigree_pdf_url, bool(obs_hip.pedigree_pdf_url)),
    ]

    for asset_type, url, available in media_map:
        if not available or not url:
            continue

        existing = (
            db.query(Asset)
            .filter(Asset.lot_id == lot_id, Asset.asset_type == asset_type)
            .first()
        )
        if existing is None:
            db.add(Asset(lot_id=lot_id, asset_type=asset_type, source_url=url))
        elif existing.source_url != url:
            existing.source_url = url  # URL changed (cache buster updated)
