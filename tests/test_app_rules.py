"""Hand-checked cases for the app's display rules. Runs on the host, with no Spark."""
import sys
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("streamlit")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
from lib import rules  # noqa: E402

NAN = float("nan")


def year_row(year, rate, n=100, positives=50, provisional=False):
    return {"year": year, "rate": rate, "n": n, "positives": positives, "ci_low": None if rate != rate else rate - 0.05, "ci_high": None if rate != rate else rate + 0.05, "provisional": provisional}


def period_row(start, end, rate, n=100, positives=50):
    return {"period_start": start, "period_end": end, "rate": rate, "n": n, "positives": positives, "ci_low": rate - 0.05, "ci_high": rate + 0.05, "provisional": False}


def test_percent_always_has_its_count():
    text = rules.pct_text(0.6, 960, 0.568, 0.631, 576, True)
    assert text == "60.0% (576 of 960, 95% CI 56.8 to 63.1, stronger confidence, provisional)"


def test_empty_rate_never_becomes_a_percent():
    text = rules.pct_text(NAN, 23, NAN, NAN, 16)
    assert text == "too few isolates (n = 23, minimum 30)" and "%" not in text


@pytest.mark.parametrize("low,high,level", [(0.40, 0.50, "stronger"), (0.40, 0.65, "moderate"), (0.40, 0.66, "weak"), (NAN, NAN, None)])
def test_confidence_comes_from_interval_width(low, high, level):
    assert rules.confidence(low, high) == level


def test_hover_says_what_is_measured():
    text = rules.hover_text("India, 2023", 0.6, 960, 0.568, 0.631, 576)
    assert "among sequenced isolates" in text and "genotypic resistance" in text and "576 of 960" in text


@pytest.mark.parametrize("args,name", [(("prevalence",), "prevalence"), (("prevalence", True), "prevalence_adjusted"), (("rising", False, "clinical"), "rising_by_source"),
                                       (("last_resort", True, "clinical"), "last_resort_by_source_adjusted"), (("last_resort", True, "all", True), "last_resort_pooled_adjusted"),
                                       (("hotspots", True), "hotspots_adjusted")])
def test_table_choice(args, name):
    assert rules.table_name(*args) == name
    assert (rules.ROOT / "results" / f"{name}.parquet").exists()


@pytest.mark.parametrize("args", [("prevalence", False, "clinical", True), ("hotspots", False, "clinical"), ("rising", False, "all", True)])
def test_views_without_a_table_are_refused(args):
    with pytest.raises(ValueError):
        rules.table_name(*args)


def test_recent_year_is_kept_over_pooled():
    yearly = pd.DataFrame([year_row(2025, 0.84), year_row(2026, NAN, 23, 16, True)])
    pooled = pd.DataFrame([period_row(2023, 2025, 0.6, 1262, 756)])
    figure = rules.latest_figure(yearly, pooled, 2026)
    assert figure["label"] == "2025" and not figure["pooled"]


def test_pooled_only_when_recent_years_are_too_small_and_is_labelled():
    yearly = pd.DataFrame([year_row(2012, 0.4), year_row(2024, NAN, 12, 3), year_row(2025, NAN, 15, 4)])
    pooled = pd.DataFrame([period_row(2023, 2025, 0.25, 40, 10)])
    figure = rules.latest_figure(yearly, pooled, 2026)
    assert figure["label"] == "pooled 2023 to 2025" and figure["pooled"] and "10 of 40" in figure["text"]


def test_old_year_is_used_when_pooled_is_not_newer():
    yearly = pd.DataFrame([year_row(2012, 0.4)])
    pooled = pd.DataFrame([period_row(2010, 2012, 0.5)])
    assert rules.latest_figure(yearly, pooled, 2026)["label"] == "2012"


def test_nothing_usable_gives_none():
    assert rules.latest_figure(pd.DataFrame([year_row(2025, NAN, 5, 1)]), None, 2026) is None


def rising_row(**changes):
    row = {"enough_years": True, "years_used": 8, "rising": False, "rising_with_provisional": False, "n": 1610, "positives": 918, "slope_points_per_year": 0.0565, "z": 0.085, "window_from": 2013, "window_to": 2022}
    return {**row, **changes}


def test_missing_rising_row_says_too_little():
    assert rules.rising_verdict(None)["status"] == "too_little"


def test_not_enough_years_says_too_little():
    verdict = rules.rising_verdict(rising_row(enough_years=False, years_used=3))
    assert verdict["status"] == "too_little" and "Only 3 years" in verdict["text"]


def test_not_rising_is_never_called_stable():
    verdict = rules.rising_verdict(rising_row())
    assert verdict["status"] == "not_flagged" and verdict["text"].startswith("Not flagged as rising") and "looks only for a rise" in verdict["text"]


def test_provisional_only_flag_is_labelled():
    assert "flagged once provisional years are included" in rules.rising_verdict(rising_row(rising_with_provisional=True))["text"]


def test_near_universal():
    assert rules.near_universal({"n": 1610, "positives": 1607}) and not rules.near_universal({"n": 1610, "positives": 918})


def test_field_status():
    assert [rules.field_status(v) for v in (1.47, 33.5, 80)] == ["hide", "label", "ok"]
