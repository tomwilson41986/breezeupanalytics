"""Tests for the OBS ingest pipeline."""

from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.models import Asset, Base, Lot, Sale
from src.scrapers.obs.catalog import OBSHip, OBSSale
from src.scrapers.obs.ingest import ingest_sale, _make_sale_id, _expand_sex, _parse_date


def _make_db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _make_test_sale() -> OBSSale:
    return OBSSale(
        sale_id="142",
        sale_code="O625",
        sale_name="2025 March 2YO in Training Sale",
        sale_short_name="25 Mar",
        year=2025,
        sale_category="2yo",
        start_date="2025-03-11 04:00:00",
        end_date="2025-03-13 04:00:00",
        previous_year_sale_id="137",
        next_sale_id="144",
        previous_sale_id="140",
        hips=[
            OBSHip(
                sale_id="142", hip_number=1, horse_name=None, sex="F",
                colour="B", year_of_birth=2023, foaling_date="02/19/2023",
                sire="Silver State", dam="Calamity Jane", dam_sire="Cowboy Cal",
                consignor="GOP Racing Stable Corp.", consignor_sort="GOP Racing Stable Corp.",
                state_bred="KY", barn_number="18", session_number="1",
                under_tack_distance="1/8", under_tack_time=Decimal("10.3"),
                under_tack_date="03/06/2025", under_tack_set="1", under_tack_group="1",
                sale_price=None, sale_status="RNA", buyer="RNA",
                hammer_price_raw="-30000",
                has_photo=True, has_video=True, has_walk_video=True,
                photo_url="https://obscatalog.com/2025/142/1p.jpg",
                video_url="https://obscatalog.com/2025/142/1.mp4",
                walk_video_url="https://obscatalog.com/2025/142/1w.mp4",
                pedigree_pdf_url="https://obscatalog.com/2025/142/1.pdf",
            ),
            OBSHip(
                sale_id="142", hip_number=2, horse_name=None, sex="C",
                colour="B", year_of_birth=2023, foaling_date="02/13/2023",
                sire="Basin", dam="Callie's Candy", dam_sire="Candy Ride (ARG)",
                consignor="Triple C Sales, Agent", consignor_sort="Triple C Sales",
                state_bred="KY", barn_number="15", session_number="1",
                under_tack_distance="1/8", under_tack_time=Decimal("10.2"),
                under_tack_date="03/06/2025", under_tack_set="171", under_tack_group="3",
                sale_price=55000, sale_status="sold", buyer="RM 18 Stables",
                hammer_price_raw="55000.00",
                has_photo=True, has_video=True, has_walk_video=True,
                photo_url="https://obscatalog.com/2025/142/2p.jpg",
                video_url="https://obscatalog.com/2025/142/2.mp4",
                walk_video_url="https://obscatalog.com/2025/142/2w.mp4",
                pedigree_pdf_url="https://obscatalog.com/2025/142/2.pdf",
            ),
        ],
    )


def test_make_sale_id():
    sale = _make_test_sale()
    assert _make_sale_id(sale) == "obs_march_2025"


def test_expand_sex():
    assert _expand_sex("C") == "Colt"
    assert _expand_sex("F") == "Filly"
    assert _expand_sex("G") == "Gelding"
    assert _expand_sex(None) is None
    assert _expand_sex("") is None


def test_parse_date():
    d = _parse_date("03/06/2025")
    assert d is not None
    assert d.year == 2025
    assert d.month == 3
    assert d.day == 6
    assert _parse_date(None) is None
    assert _parse_date("") is None


def test_ingest_creates_sale_and_lots():
    db = _make_db()
    obs_sale = _make_test_sale()

    sale = ingest_sale(obs_sale, db)

    assert sale.sale_id == "obs_march_2025"
    assert sale.company == "OBS"
    assert sale.year == 2025

    lots = db.query(Lot).filter(Lot.sale_id == sale.sale_id).all()
    assert len(lots) == 2

    hip1 = db.get(Lot, "obs_march_2025_1")
    assert hip1 is not None
    assert hip1.sire == "Silver State"
    assert hip1.sex == "Filly"
    assert hip1.sale_status == "RNA"
    assert hip1.sale_price is None
    assert hip1.buyer is None  # "RNA" buyer should be stored as None
    assert hip1.under_tack_time == Decimal("10.3")

    hip2 = db.get(Lot, "obs_march_2025_2")
    assert hip2 is not None
    assert hip2.sire == "Basin"
    assert hip2.sex == "Colt"
    assert hip2.sale_status == "sold"
    assert hip2.sale_price == 55000
    assert hip2.buyer == "RM 18 Stables"


def test_ingest_creates_assets():
    db = _make_db()
    obs_sale = _make_test_sale()

    ingest_sale(obs_sale, db)

    # Hip 2 has all 4 media types
    assets = db.query(Asset).filter(Asset.lot_id == "obs_march_2025_2").all()
    asset_types = {a.asset_type for a in assets}
    assert asset_types == {"breeze_video", "walk_video", "photo", "pedigree_page"}

    video_asset = next(a for a in assets if a.asset_type == "breeze_video")
    assert video_asset.source_url == "https://obscatalog.com/2025/142/2.mp4"
    assert video_asset.downloaded_at is None  # Not downloaded yet


def test_ingest_upsert_is_idempotent():
    db = _make_db()
    obs_sale = _make_test_sale()

    ingest_sale(obs_sale, db)
    ingest_sale(obs_sale, db)  # Run again

    lots = db.query(Lot).all()
    assert len(lots) == 2  # No duplicates

    assets = db.query(Asset).all()
    assert len(assets) == 8  # 4 per hip, no duplicates
