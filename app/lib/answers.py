"""Guided question answers, worked out from the tables with no AI. Each says when there is too little data."""
from dataclasses import dataclass, field

import pandas as pd

from lib import charts, data
from lib.rules import MIN_SAMPLE, SETTINGS, latest_figure, pct_text, rising_verdict


@dataclass
class Answer:
    status: str
    lines: list = field(default_factory=list)
    chart: object = None
    table: object = None


def rate_series(measure, organism, country, source="all"):
    """All-isolates and outbreak-adjusted rows for one group, ready for a trend chart."""
    title = lambda r: f"{country}, {int(r['year'])}"
    return {"All isolates": charts.with_hover(data.rate_rows(measure, False, source, organism=organism, country=country), title),
            "Outbreak-adjusted": charts.with_hover(data.rate_rows(measure, True, source, organism=organism, country=country), title)}


def latest_line(measure, organism, country, adjusted=False, source="all"):
    yearly, pooled = data.latest_inputs(measure, organism, country, adjusted, source)
    figure = latest_figure(yearly, pooled, data.latest_data_year())
    if figure is None:
        n = int(yearly["n"].max()) if len(yearly) else 0
        return f"Latest figure: none usable, because no year or pooled period reaches {MIN_SAMPLE} isolates (largest year: {n:,})."
    return f"Latest figure ({figure['label']}): {figure['text']}, among sequenced isolates."


def rising_question(measure, organism, country):
    """Is this resistance rising in this organism and country?"""
    label = data.measure_label(measure)
    verdict = rising_verdict(data.rising_row(measure, organism, country))
    adjusted = rising_verdict(data.rising_row(measure, organism, country, adjusted=True))
    lines = [f"**{label}, all isolates:** {verdict['text']}", f"**{label}, outbreak-adjusted:** {adjusted['text']}"]
    if measure[0] == "last_resort" and measure[2] == "acquired":
        wider = (measure[0], measure[1], "any_excl_intrinsic")
        lines.append(f"**{data.measure_label(wider)}:** {rising_verdict(data.rising_row(wider, organism, country))['text']}")
    lines.append(latest_line(measure, organism, country))
    lines.append("Read this as genotypic resistance among sequenced isolates, not as national prevalence.")
    return Answer(verdict["status"], lines, charts.trend(rate_series(measure, organism, country), data.provisional_start()))


def outbreak_question(measure, organism, country):
    """Is this a trend, or could it be one outbreak?"""
    label = data.measure_label(measure)
    full, adjusted = (rising_verdict(data.rising_row(measure, organism, country, adjusted=a)) for a in (False, True))
    lines = [f"**All isolates:** {full['text']}", f"**Outbreak-adjusted:** {adjusted['text']}"]
    pair = (full["status"], adjusted["status"])
    if "too_little" in pair:
        status, reading = "too_little", "There is too little data in at least one view to separate a trend from outbreaks."
    elif pair == ("rising", "rising"):
        status, reading = "rising", "Both views flag it, so it does not depend on counting every isolate in a cluster."
    elif pair == ("rising", "not_flagged"):
        status, reading = "not_flagged", "Only the all-isolates view flags it, so clustered isolates may account for the signal."
    else:
        status, reading = adjusted["status"], "The all-isolates view does not flag it."
    return Answer(status, [f"{label}: {reading}", *lines], charts.trend(rate_series(measure, organism, country), data.provisional_start()))


def first_seen_rows(gene, organism="ALL"):
    families = data.load("first_seen", gene=gene, organism=organism, level="family")
    return families if len(families) else data.load("first_seen", gene=gene, organism=organism, level="gene")


def gene_question(gene, organism="ALL"):
    """When did this gene reach each country?"""
    rows = first_seen_rows(gene, organism)
    if rows.empty:
        return Answer("too_little", [f"{gene} has no records for this choice among sequenced isolates."])
    established = rows[rows["established_year"].notna()].sort_values(["established_year", "country"])
    lines = [f"{gene} is on record in {rows['country'].nunique()} countries and established in {established['country'].nunique()}, among sequenced isolates. "
             "Established means at least 3 isolates from at least 2 clusters."]
    if len(established):
        first_year = int(established["established_year"].min())
        earliest = ", ".join(established.loc[established["established_year"] == first_year, "country"])
        lines.append(f"Earliest established: {first_year}, in {earliest}. This shows when sequenced samples show it, not when it truly arrived.")
    fig, outside = charts.spread_timeline(rows)
    if outside:
        lines.append(f"{outside} countries have a raw earliest record before this chart's range. Raw dates include errors, so they lead with the established year.")
    table = rows.sort_values(["established_year", "first_year", "country"])[["country", "established_year", "first_year", "isolates", "clusters"]]
    return Answer("ok", lines, fig, table)


def new_genes_question(country):
    """What has newly appeared here recently?"""
    rows = data.load("early_warnings", country=country)
    shown = rows[~rows["new_sequencing"]]
    if rows.empty:
        return Answer("too_little", [f"No early warnings for {country}. This can also mean little recent sequencing."])
    if shown.empty:
        return Answer("too_little", [f"{country} has {len(rows)} new appearances, but all come where sequencing has only just begun, so every gene looks new."])
    lines = [f"{len(shown)} new appearances in {country} among sequenced isolates, leaving out {len(rows) - len(shown)} where sequencing has only just begun. "
             "Some have older lone records, shown in the table as earlier records."]
    table = shown.sort_values(["organism_label", "gene"])[["organism_label", "gene", "level", "established_year", "recent_isolates", "recent_clusters", "earlier_records"]]
    return Answer("ok", lines, charts.early_warning_timeline(shown), table)


def enough_data_question(organism, country):
    """Is there enough data for this organism and country?"""
    rows = data.coverage(organism=organism, country=country)
    if rows.empty:
        return Answer("too_little", [f"No sequenced isolates for this organism in {country}."])
    usable = rows[rows["isolates"] >= MIN_SAMPLE]
    usable_recent = usable[~usable["provisional"]]
    lines = [f"{int(rows['isolates'].sum()):,} sequenced isolates over {len(rows)} years. {len(usable)} years reach the minimum of {MIN_SAMPLE}, "
             f"and {len(usable_recent)} of those are outside the provisional period."]
    needed = SETTINGS["rising_min_years"]
    status = "ok" if len(usable_recent) >= needed else "too_little"
    lines.append("That is enough years for a trend check." if status == "ok" else f"That is too few years for a trend check, which needs at least {needed}.")
    chart = charts.count_bars(rows.sort_values("year"), "year", "isolates", provisional_from=data.provisional_start())
    return Answer(status, lines, chart)


def hotspot_question(organism, country):
    """Are any drug classes flagged as unusually high here?"""
    rows = data.load("hotspots", organism=organism, country=country)
    held = rows[rows["persistent"] & rows["reason"].isin(["high", "both"])]
    if held.empty:
        return Answer("too_little", [f"No persistent hotspots for this organism in {country}. This can also mean too little data to compare."])
    latest = held.sort_values("year").groupby("drug_class", as_index=False).tail(1).sort_values("drug_class")
    table = pd.DataFrame({"Drug class": latest["drug_class"], "Year": latest["year"],
                          "Here": [rate_text(r) for r in latest.to_dict("records")], "All other countries, same year": [f"{r['rest_rate'] * 100:.1f}% (n = {int(r['rest_n']):,})" for r in latest.to_dict("records")]})
    lines = [f"{len(latest)} drug classes are high here in a year and the year next to it, compared with all other countries, among sequenced isolates. "
             "With so many comparisons, some flags will occur by chance."]
    return Answer("ok", lines, None, table)


def rate_text(row):
    return pct_text(row["rate"], row["n"], row["ci_low"], row["ci_high"], row["positives"], row["provisional"])
