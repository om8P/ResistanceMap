"""Display rules in one place, so no page can show a percentage without its count. No Streamlit here."""
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SETTINGS = json.loads((ROOT / "config" / "settings.json").read_text())
MIN_SAMPLE = SETTINGS["min_sample"]
EVIDENCE_WORDS = "among sequenced isolates · genotypic resistance"
GLASS_WORDS = "WHO GLASS · lab-confirmed resistance in bloodstream infections"
NOTICE = ("Not for clinical use. Figures show genotypic resistance among sequenced isolates. They reflect what labs "
          "chose to sequence, not all infections, and are not national prevalence.")


def missing(value):
    return value is None or (isinstance(value, float) and math.isnan(value)) or value != value


def confidence(ci_low, ci_high):
    """Confidence level from the width of the Wilson interval, or None when there is no rate."""
    if missing(ci_low) or missing(ci_high):
        return None
    width = (ci_high - ci_low) * 100
    if width <= SETTINGS["confidence_stronger_points"]:
        return "stronger"
    return "moderate" if width <= SETTINGS["confidence_moderate_points"] else "weak"


def too_few_text(n):
    n = 0 if missing(n) else int(n)
    return f"too few isolates (n = {n:,}, minimum {MIN_SAMPLE})"


def pct_text(rate, n, ci_low=None, ci_high=None, positives=None, provisional=False):
    """The only way a percentage becomes text: always with its count and confidence level."""
    if missing(rate):
        return too_few_text(n)
    counts = f"{int(positives):,} of {int(n):,}" if not missing(positives) else f"n = {int(n):,}"
    parts = [f"{rate * 100:.1f}% ({counts}"]
    level = confidence(ci_low, ci_high)
    if level:
        parts.append(f", 95% CI {ci_low * 100:.1f} to {ci_high * 100:.1f}, {level} confidence")
    parts.append(", provisional)" if provisional else ")")
    return "".join(parts)


def hover_text(title, rate, n, ci_low=None, ci_high=None, positives=None, provisional=False, measure=EVIDENCE_WORDS):
    """Chart hover text: sample count and what the number measures, on every point."""
    return f"<b>{title}</b><br>{pct_text(rate, n, ci_low, ci_high, positives, provisional)}<br>{measure}"


def table_name(base, adjusted=False, source="all", pooled=False):
    """Result table for a view. Pooled rows have no source version, and hotspots have neither."""
    name = base
    if source != "all":
        if pooled or base not in ("prevalence", "last_resort", "rising"):
            raise ValueError(f"No source view for {base}{' pooled' if pooled else ''}")
        name += "_by_source"
    if pooled:
        if base not in ("prevalence", "last_resort"):
            raise ValueError(f"No pooled view for {base}")
        name += "_pooled"
    if adjusted:
        name += "_adjusted"
    return name


def _usable(rows):
    return rows[rows["rate"].notna()] if len(rows) else rows


def latest_figure(yearly, pooled=None, latest_year=None):
    """Latest usable figure for one group. A pooled row is used only when no recent single year is big enough.

    Recent means the last 3 data years, the length of a pooled period. Returns None when nothing is usable.
    """
    yearly_ok = _usable(yearly)
    pooled_ok = _usable(pooled) if pooled is not None else None
    year_row = yearly_ok.sort_values("year").iloc[-1] if len(yearly_ok) else None
    period_row = pooled_ok.sort_values("period_end").iloc[-1] if pooled_ok is not None and len(pooled_ok) else None
    if latest_year is None and len(yearly):
        latest_year = int(yearly["year"].max())
    recent = year_row is not None and latest_year is not None and year_row["year"] >= latest_year - 2
    use_pooled = period_row is not None and not recent and (year_row is None or period_row["period_end"] > year_row["year"])
    row = period_row if use_pooled else year_row
    if row is None:
        return None
    if use_pooled:
        start, end = int(row["period_start"]), int(row["period_end"])
        label = f"pooled {start} to {end}" if start != end else f"pooled {end}"
    else:
        label = str(int(row["year"]))
    provisional = bool(row["provisional"])
    return {"label": label, "pooled": bool(use_pooled), "rate": row["rate"], "n": row["n"], "positives": row["positives"],
            "ci_low": row["ci_low"], "ci_high": row["ci_high"], "provisional": provisional,
            "text": pct_text(row["rate"], row["n"], row["ci_low"], row["ci_high"], row["positives"], provisional)}


def rising_verdict(row):
    """Plain wording for one `rising` row, or None row when it is missing. Never says stable or falling."""
    if row is None or missing(row.get("enough_years")) or not row.get("enough_years"):
        used = "" if row is None or missing(row.get("years_used")) else f" Only {int(row['years_used'])} years reach the minimum sample."
        return {"status": "too_little", "text": f"Too little data to judge a trend: it needs at least {SETTINGS['rising_min_years']} years "
                                                f"with {MIN_SAMPLE} or more isolates.{used}"}
    window = f"{int(row['window_from'])} to {int(row['window_to'])}"
    evidence = (f"{window}, {int(row['years_used'])} usable years, {int(row['positives']):,} of {int(row['n']):,} isolates, "
                f"slope {row['slope_points_per_year']:+.2f} points per year" + ("" if missing(row["z"]) else f", z {row['z']:.2f}"))
    if row["rising"]:
        status, text = "rising", f"Flagged as rising ({evidence})."
    else:
        status, text = "not_flagged", f"Not flagged as rising ({evidence}). This check looks only for a rise, so it does not show it is stable or falling."
    with_provisional = row.get("rising_with_provisional")
    if with_provisional is not None and not missing(with_provisional):
        if with_provisional and not row["rising"]:
            text += " It is flagged once provisional years are included, and those years are incomplete."
        elif row["rising"] and not with_provisional:
            text += " It is not flagged once provisional years are included."
    return {"status": status, "text": text}


def near_universal(row):
    """True when a class is in nearly every isolate, usually from intrinsic genes such as fosA in Klebsiella."""
    if row is None or missing(row.get("n")) or not row.get("n"):
        return False
    return row["positives"] / row["n"] >= SETTINGS["near_universal_rate"]


def field_status(pct_filled):
    """Whether a sparse source field is shown: 'ok', 'label' or 'hide'."""
    if pct_filled < SETTINGS["sparse_hide_pct"]:
        return "hide"
    return "label" if pct_filled < SETTINGS["sparse_label_pct"] else "ok"
