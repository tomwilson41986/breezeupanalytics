"""Validate time-related mappings across the entire pipeline.

Covers:
  - OBS API → OBSHip field mapping
  - OBS legacy → _derive_ut_distance thresholds
  - FT API → FTHip field mapping (including under_tack_distance)
  - CSV header normalisation (Python upload script)
  - Consistency between Python and JS header normalisation
  - parseS3Hip / parseHip field mapping (documented expectations)
  - Edge cases: boundary times, missing values, malformed input
"""

from decimal import Decimal

import pytest


# ── OBS catalog time parsing ────────────────────────────────────

from src.scrapers.obs.catalog import _parse_ut_time as obs_parse_ut_time


class TestOBSParseUtTime:
    def test_normal_time(self):
        assert obs_parse_ut_time("10.2") == Decimal("10.2")

    def test_quarter_mile_time(self):
        assert obs_parse_ut_time("21.1") == Decimal("21.1")

    def test_three_eighths_time(self):
        assert obs_parse_ut_time("34.0") == Decimal("34.0")

    def test_whitespace_stripped(self):
        assert obs_parse_ut_time("  10.2  ") == Decimal("10.2")

    def test_none_returns_none(self):
        assert obs_parse_ut_time(None) is None

    def test_empty_string_returns_none(self):
        assert obs_parse_ut_time("") is None

    def test_whitespace_only_returns_none(self):
        assert obs_parse_ut_time("   ") is None

    def test_non_numeric_returns_none(self):
        assert obs_parse_ut_time("out") is None
        assert obs_parse_ut_time("G") is None
        assert obs_parse_ut_time("N/A") is None


# ── OBS legacy distance derivation ──────────────────────────────

from src.scrapers.obs.legacy_results import _derive_ut_distance


class TestDeriveUtDistance:
    """Validate time-to-distance threshold mapping for legacy OBS data."""

    def test_none_returns_none(self):
        assert _derive_ut_distance(None) is None

    # 1/8 mile: typical 9-12s, threshold ≤15s
    def test_fast_eighth(self):
        assert _derive_ut_distance(Decimal("9.4")) == "1/8"

    def test_typical_eighth(self):
        assert _derive_ut_distance(Decimal("10.2")) == "1/8"

    def test_slow_eighth(self):
        assert _derive_ut_distance(Decimal("12.0")) == "1/8"

    def test_boundary_eighth_at_15(self):
        """15.0s is at the boundary — should map to 1/8."""
        assert _derive_ut_distance(Decimal("15.0")) == "1/8"

    # 1/4 mile: typical 20-24s, threshold ≤27s
    def test_fast_quarter(self):
        assert _derive_ut_distance(Decimal("20.0")) == "1/4"

    def test_typical_quarter(self):
        assert _derive_ut_distance(Decimal("21.1")) == "1/4"

    def test_slow_quarter(self):
        assert _derive_ut_distance(Decimal("24.0")) == "1/4"

    def test_boundary_quarter_at_15_1(self):
        """15.1s should map to 1/4 (just above 1/8 threshold)."""
        assert _derive_ut_distance(Decimal("15.1")) == "1/4"

    def test_boundary_quarter_at_27(self):
        """27.0s is at the boundary — should map to 1/4."""
        assert _derive_ut_distance(Decimal("27.0")) == "1/4"

    # 3/8 mile: typical 31-36s, threshold >27s
    def test_fast_three_eighths(self):
        assert _derive_ut_distance(Decimal("31.0")) == "3/8"

    def test_typical_three_eighths(self):
        assert _derive_ut_distance(Decimal("34.0")) == "3/8"

    def test_boundary_three_eighths_at_27_1(self):
        """27.1s should map to 3/8 (just above 1/4 threshold)."""
        assert _derive_ut_distance(Decimal("27.1")) == "3/8"


# ── FT time parsing ─────────────────────────────────────────────

from src.scrapers.fasig_tipton.catalog import (
    _parse_ut_time as ft_parse_ut_time,
    _parse_ut_distance as ft_parse_ut_distance,
)


class TestFTParseUtTime:
    def test_normal_time(self):
        assert ft_parse_ut_time("10.2") == Decimal("10.2")

    def test_numeric_input(self):
        assert ft_parse_ut_time(10.2) == Decimal("10.2")

    def test_zero_returns_none(self):
        assert ft_parse_ut_time(0) is None
        assert ft_parse_ut_time("0") is None

    def test_negative_returns_none(self):
        assert ft_parse_ut_time(-5) is None

    def test_none_returns_none(self):
        assert ft_parse_ut_time(None) is None


class TestFTParseUtDistance:
    """Validate FT distance parsing — checks explicit API field, then derives from time."""

    def test_explicit_distance_from_api(self):
        horse = {"under_tack_show_distance": "1/8", "under_tack_show_time": "10.2"}
        assert ft_parse_ut_distance(horse) == "1/8"

    def test_explicit_distance_quarter(self):
        horse = {"under_tack_show_distance": "1/4", "under_tack_show_time": "21.0"}
        assert ft_parse_ut_distance(horse) == "1/4"

    def test_derives_eighth_from_time(self):
        horse = {"under_tack_show_time": "10.2"}
        assert ft_parse_ut_distance(horse) == "1/8"

    def test_derives_quarter_from_time(self):
        horse = {"under_tack_show_time": "21.0"}
        assert ft_parse_ut_distance(horse) == "1/4"

    def test_derives_three_eighths_from_time(self):
        horse = {"under_tack_show_time": "34.0"}
        assert ft_parse_ut_distance(horse) == "3/8"

    def test_no_time_no_distance_returns_none(self):
        horse = {}
        assert ft_parse_ut_distance(horse) is None

    def test_empty_distance_derives_from_time(self):
        horse = {"under_tack_show_distance": "", "under_tack_show_time": "10.2"}
        assert ft_parse_ut_distance(horse) == "1/8"


# ── OBS hip parsing — full field mapping ─────────────────────────

from src.scrapers.obs.catalog import _parse_hip as obs_parse_hip


class TestOBSHipTimeFields:
    """Validate that OBS API fields map correctly to OBSHip time attributes."""

    def test_time_field_mapping(self):
        raw = {
            "sale_id": "142",
            "hip_number": "10",
            "ut_time": "10.2",
            "ut_distance": " 1/8",
            "ut_actual_date": "03/06/2025",
            "ut_set": "5",
            "ut_group": "2",
            "display_props": {"is_hip_sold": True},
            "hammer_price": "50000",
        }
        hip = obs_parse_hip(raw)
        assert hip.under_tack_time == Decimal("10.2")
        assert hip.under_tack_distance == "1/8"  # leading space stripped
        assert hip.under_tack_date == "03/06/2025"
        assert hip.under_tack_set == "5"
        assert hip.under_tack_group == "2"

    def test_missing_time_fields(self):
        raw = {
            "sale_id": "142",
            "hip_number": "10",
            "ut_time": None,
            "ut_distance": None,
            "ut_actual_date": None,
            "display_props": {"is_hip_out": True},
        }
        hip = obs_parse_hip(raw)
        assert hip.under_tack_time is None
        assert hip.under_tack_distance is None
        assert hip.under_tack_date is None

    def test_empty_distance_becomes_none(self):
        raw = {
            "sale_id": "142",
            "hip_number": "10",
            "ut_time": "10.2",
            "ut_distance": "  ",
            "display_props": {},
        }
        hip = obs_parse_hip(raw)
        assert hip.under_tack_distance is None

    def test_quarter_mile_distance(self):
        raw = {
            "sale_id": "142",
            "hip_number": "10",
            "ut_time": "21.1",
            "ut_distance": "1/4",
            "display_props": {},
        }
        hip = obs_parse_hip(raw)
        assert hip.under_tack_time == Decimal("21.1")
        assert hip.under_tack_distance == "1/4"

    def test_three_eighths_distance(self):
        raw = {
            "sale_id": "142",
            "hip_number": "10",
            "ut_time": "34.0",
            "ut_distance": "3/8",
            "display_props": {},
        }
        hip = obs_parse_hip(raw)
        assert hip.under_tack_time == Decimal("34.0")
        assert hip.under_tack_distance == "3/8"


# ── FT hip parsing — full field mapping ──────────────────────────

from src.scrapers.fasig_tipton.catalog import _parse_hip as ft_parse_hip


class TestFTHipTimeFields:
    """Validate that FT API fields map correctly to FTHip time attributes."""

    def test_time_field_mapping(self):
        raw = {
            "hip": 10,
            "under_tack_show_time": 10.2,
            "under_tack_show_distance": "1/8",
            "under_tack_show_day": "2025-05-15",
            "under_tack_show_surface": "Dirt",
            "purchaser": "Buyer A",
            "price": "50000.00",
        }
        hip = ft_parse_hip(raw, "ft_midlantic_2025")
        assert hip.under_tack_time == Decimal("10.2")
        assert hip.under_tack_distance == "1/8"
        assert hip.under_tack_date == "2025-05-15"
        assert hip.under_tack_surface == "Dirt"

    def test_derives_distance_when_missing(self):
        raw = {
            "hip": 10,
            "under_tack_show_time": 10.2,
            "purchaser": "OUT",
        }
        hip = ft_parse_hip(raw, "ft_midlantic_2025")
        assert hip.under_tack_time == Decimal("10.2")
        assert hip.under_tack_distance == "1/8"  # derived from time

    def test_no_time_no_distance(self):
        raw = {
            "hip": 10,
            "purchaser": "OUT",
        }
        hip = ft_parse_hip(raw, "ft_midlantic_2025")
        assert hip.under_tack_time is None
        assert hip.under_tack_distance is None


# ── CSV header normalisation ────────────────────────────────────

# Import from upload script
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from upload_live_sale_times import normalize_header


class TestNormalizeHeader:
    """Validate CSV header normalisation handles all expected formats."""

    def test_hip_hash(self):
        """'Hip #' must normalise to 'hip_number' — was producing 'hip_'."""
        assert normalize_header("Hip #") == "hip_number"

    def test_hip_plain(self):
        assert normalize_header("Hip") == "hip_number"

    def test_hip_number(self):
        assert normalize_header("Hip Number") == "hip_number"

    def test_hip_no(self):
        assert normalize_header("Hip No") == "hip_number"

    def test_distance(self):
        assert normalize_header("Distance") == "distance"

    def test_ut_time(self):
        assert normalize_header("UT Time") == "ut_time"

    def test_go_time_with_parens(self):
        """'Go Time (s)' should produce 'go_time_s' not 'go_time_(s)'."""
        result = normalize_header("Go Time (s)")
        assert "(" not in result
        assert ")" not in result
        assert result == "go_time_s"

    def test_distance_with_slash(self):
        """'1/8 Time' should produce '18_time' not '1/8_time'."""
        result = normalize_header("1/8 Time")
        assert "/" not in result

    def test_trailing_underscores_stripped(self):
        """Headers ending in special chars should not have trailing underscores."""
        result = normalize_header("Test #")
        assert not result.endswith("_")

    def test_leading_underscores_stripped(self):
        result = normalize_header("# Test")
        assert not result.startswith("_")

    def test_double_underscores_collapsed(self):
        result = normalize_header("Go  Time")
        assert "__" not in result


# ── Consistency: Python normaliser matches JS behaviour ──────────
# These tests document the expected output for common headers,
# ensuring both Python and JS produce the same result.

class TestNormalizerConsistency:
    """Document expected normalisation results — must match JS normaliseHeader()."""

    EXPECTED = {
        "Hip": "hip_number",
        "Hip #": "hip_number",
        "Hip Number": "hip_number",
        "Hip No": "hip_number",
        "Distance": "distance",
        "UT Time": "ut_time",
        "Go Time": "go_time",
        "Go Time (s)": "go_time_s",
        "1/8 Time": "18_time",
        "Sire": "sire",
        "Dam": "dam",
        "Sex": "sex",
        "Consignor": "consignor",
    }

    @pytest.mark.parametrize("header,expected", EXPECTED.items())
    def test_normalisation(self, header, expected):
        assert normalize_header(header) == expected


# ── Legacy results time parsing ──────────────────────────────────

from src.scrapers.obs.legacy_results import _parse_ut_time as legacy_parse_ut_time


class TestLegacyParseUtTime:
    def test_normal(self):
        assert legacy_parse_ut_time("10.2") == Decimal("10.2")

    def test_whitespace(self):
        assert legacy_parse_ut_time("  21.1  ") == Decimal("21.1")

    def test_empty(self):
        assert legacy_parse_ut_time("") is None

    def test_none(self):
        assert legacy_parse_ut_time(None) is None

    def test_out_string(self):
        """Legacy pages show 'out' in the time column for withdrawn hips."""
        assert legacy_parse_ut_time("out") is None

    def test_non_numeric(self):
        assert legacy_parse_ut_time("G") is None
        assert legacy_parse_ut_time("N/A") is None


# ── sync_under_tack time parsing ─────────────────────────────────

from scripts.sync_under_tack import _parse_ut_time as sync_parse_ut_time


class TestSyncParseUtTime:
    """Validate the sync script's own time parser returns float (not Decimal)."""

    def test_normal(self):
        result = sync_parse_ut_time("10.2")
        assert result == 10.2
        assert isinstance(result, float)

    def test_none(self):
        assert sync_parse_ut_time(None) is None

    def test_empty(self):
        assert sync_parse_ut_time("") is None

    def test_non_numeric(self):
        assert sync_parse_ut_time("G") is None


# ── Valid distance values ────────────────────────────────────────

VALID_DISTANCES = {"1/8", "1/4", "3/8"}


class TestValidDistances:
    """Ensure all distance derivation paths produce valid distance strings."""

    @pytest.mark.parametrize("time_val,expected_dist", [
        (Decimal("9.0"), "1/8"),
        (Decimal("10.2"), "1/8"),
        (Decimal("15.0"), "1/8"),
        (Decimal("15.1"), "1/4"),
        (Decimal("21.0"), "1/4"),
        (Decimal("27.0"), "1/4"),
        (Decimal("27.1"), "3/8"),
        (Decimal("34.0"), "3/8"),
    ])
    def test_obs_legacy_distances_are_valid(self, time_val, expected_dist):
        result = _derive_ut_distance(time_val)
        assert result == expected_dist
        assert result in VALID_DISTANCES

    @pytest.mark.parametrize("time_str,expected_dist", [
        ("10.2", "1/8"),
        ("21.0", "1/4"),
        ("34.0", "3/8"),
    ])
    def test_ft_derived_distances_are_valid(self, time_str, expected_dist):
        horse = {"under_tack_show_time": time_str}
        result = ft_parse_ut_distance(horse)
        assert result == expected_dist
        assert result in VALID_DISTANCES
