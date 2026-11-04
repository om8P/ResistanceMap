"""WHO GLASS figures, kept separate from our rates. Comparison only, never merged."""
from lib import data
from lib.rules import GLASS_WORDS, hover_text


def rows_for(organism, country, value):
    return data.load("glass", organism=organism, country=country, our_value=value)


def series(organism, country, value):
    """GLASS trend series by antibiotic, with `rate` empty under its own minimum, plus any match notes."""
    rows = rows_for(organism, country, value)
    if rows.empty:
        return {}, []
    rows = rows.copy()
    rows["n"] = rows["tested"]
    rows["positives"] = rows["resistant"]
    rows["provisional"] = False
    rows.loc[~rows["meets_min_sample"], ["rate", "ci_low", "ci_high"]] = float("nan")
    rows["hover"] = [hover_text(f"{country}, {int(r['year'])}, {r['antibiotic']}", r["rate"], r["n"], r["ci_low"], r["ci_high"], r["positives"], False, GLASS_WORDS) for r in rows.to_dict("records")]
    result = {f"GLASS: {name}": part for name, part in sorted(rows.groupby("antibiotic")) if part["rate"].notna().any()}
    notes = sorted({note for note in rows["match_note"].dropna() if note})
    return result, notes
