"""Tests for OBS catalog API parsing."""

from decimal import Decimal

from src.scrapers.obs.catalog import _parse_hip, _parse_sale_status, _parse_sale_price, _parse_ut_time


def test_parse_sold_hip():
    raw = {
        "sale_id": "142",
        "in_out_status": "I",
        "horse_type": "2",
        "foaling_year": "2023",
        "hip_number": "2",
        "horse_name": "",
        "color": "B",
        "sex": "C",
        "foaling_date": "02/13/2023",
        "sire_name": "Basin",
        "dam_name": "Callie's Candy",
        "dam_sire": "Declaration of War",
        "property_line_1": "Triple C Sales, Agent",
        "consignor_sort": "Triple C Sales",
        "consignor_name": "Triple C Sales, Agent",
        "foaling_area": "KY",
        "barn_number": "15",
        "session_number": "1",
        "buyer_name": "RM 18 Stables",
        "hammer_price": "55000.00",
        "rna_summary_indicator": "N",
        "post_sale_indicator": "N",
        "ut_time": "10.2",
        "ut_expected_date": "03/06/2025",
        "ut_actual_date": "03/06/2025",
        "ut_set": "171",
        "ut_distance": " 1/8",
        "ut_group": "3",
        "has_photo": "1",
        "has_video": "1",
        "has_walk_video": "1",
        "photo_link": "https://obscatalog.com/2025/142/2p.jpg?v=123",
        "video_link": "https://obscatalog.com/2025/142/2.mp4?v=123",
        "walk_video_link": "https://obscatalog.com/2025/142/2w.mp4?v=123",
        "pedigree_pdf_link": "https://obscatalog.com/2025/142/2.pdf?v=123",
        "display_props": {
            "is_hip_out": False,
            "is_hip_not_through_ring_yet": False,
            "is_hip_sold": True,
            "is_rna": False,
            "has_walk_video": True,
            "hammer_price": "$55,000",
        },
    }

    hip = _parse_hip(raw)

    assert hip.hip_number == 2
    assert hip.horse_name is None  # empty string → None
    assert hip.sex == "C"
    assert hip.colour == "B"
    assert hip.year_of_birth == 2023
    assert hip.sire == "Basin"
    assert hip.dam == "Callie's Candy"
    assert hip.dam_sire == "Declaration of War"
    assert hip.consignor == "Triple C Sales, Agent"
    assert hip.state_bred == "KY"
    assert hip.under_tack_distance == "1/8"
    assert hip.under_tack_time == Decimal("10.2")
    assert hip.under_tack_date == "03/06/2025"
    assert hip.sale_price == 55000
    assert hip.sale_status == "sold"
    assert hip.buyer == "RM 18 Stables"
    assert hip.has_photo is True
    assert hip.has_video is True
    assert hip.has_walk_video is True
    assert hip.video_url == "https://obscatalog.com/2025/142/2.mp4?v=123"
    assert hip.walk_video_url == "https://obscatalog.com/2025/142/2w.mp4?v=123"


def test_parse_rna_hip():
    raw = {
        "sale_id": "142",
        "hip_number": "1",
        "horse_name": "",
        "color": "B",
        "sex": "F",
        "foaling_year": "2023",
        "foaling_date": "02/19/2023",
        "sire_name": "Silver State",
        "dam_name": "Calamity Jane",
        "dam_sire": "Cowboy Cal",
        "consignor_name": "GOP Racing Stable Corp.",
        "consignor_sort": "GOP Racing Stable Corp.",
        "foaling_area": "KY",
        "barn_number": "18",
        "session_number": "1",
        "buyer_name": "RNA",
        "hammer_price": -30000,
        "rna_summary_indicator": "Y",
        "ut_time": "10.3",
        "ut_distance": " 1/8",
        "ut_actual_date": "03/06/2025",
        "has_photo": "1",
        "has_video": "1",
        "has_walk_video": "1",
        "display_props": {
            "is_hip_out": False,
            "is_hip_sold": False,
            "is_rna": True,
        },
    }

    hip = _parse_hip(raw)

    assert hip.sale_status == "RNA"
    assert hip.sale_price is None  # Negative → None
    assert hip.buyer == "RNA"


def test_parse_out_hip():
    raw = {
        "sale_id": "142",
        "hip_number": "3",
        "in_out_status": "O",
        "horse_name": "",
        "color": "B",
        "sex": "C",
        "foaling_year": "2023",
        "sire_name": "Good Magic",
        "dam_name": "Some Dam",
        "dam_sire": "Some Sire",
        "consignor_name": "Consignor A",
        "consignor_sort": "Consignor A",
        "foaling_area": "FL",
        "hammer_price": None,
        "ut_time": None,
        "ut_distance": None,
        "ut_actual_date": None,
        "has_photo": "0",
        "has_video": "0",
        "has_walk_video": "0",
        "display_props": {
            "is_hip_out": True,
            "is_hip_sold": False,
            "is_rna": False,
        },
    }

    hip = _parse_hip(raw)

    assert hip.sale_status == "out"
    assert hip.sale_price is None
    assert hip.under_tack_time is None


def test_parse_sale_status():
    assert _parse_sale_status({"display_props": {"is_hip_sold": True}}) == "sold"
    assert _parse_sale_status({"display_props": {"is_rna": True}}) == "RNA"
    assert _parse_sale_status({"display_props": {"is_hip_out": True}}) == "out"
    assert _parse_sale_status({"in_out_status": "O", "display_props": {}}) == "out"
    assert _parse_sale_status({"display_props": {"is_hip_not_through_ring_yet": True}}) == "pending"


def test_parse_sale_price():
    assert _parse_sale_price({"hammer_price": "55000.00"}) == 55000
    assert _parse_sale_price({"hammer_price": -30000}) is None  # RNA
    assert _parse_sale_price({"hammer_price": None}) is None
    assert _parse_sale_price({"hammer_price": "0"}) is None
    assert _parse_sale_price({}) is None


def test_parse_ut_time():
    assert _parse_ut_time("10.2") == Decimal("10.2")
    assert _parse_ut_time("  21.1  ") == Decimal("21.1")
    assert _parse_ut_time(None) is None
    assert _parse_ut_time("") is None
    assert _parse_ut_time("   ") is None
