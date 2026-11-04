"""Country report contents and its downloadable Markdown file. Numbers come from results/ only."""
import pandas as pd

from lib import data
from lib.rules import MIN_SAMPLE, NOTICE, latest_figure, near_universal, pct_text, rising_verdict, table_name

LAST_RESORT_DRUGS = ["CARBAPENEM", "COLISTIN"]


def _last_resort(country, adjusted, source):
    rows = []
    organisms = data.organisms()
    present = set(data.coverage(country=country)["organism"])
    for organism, label in organisms.items():
        if organism not in present:
            continue
        for drug in LAST_RESORT_DRUGS:
            measure = ("last_resort", drug, "acquired")
            figure = latest_figure(*data.latest_inputs(measure, organism, country, adjusted, source), data.latest_data_year())
            verdict = rising_verdict(data.rising_row(measure, organism, country, adjusted, source))
            rows.append({"Organism": label, "Drug (acquired genes)": drug.capitalize(), "Period": figure["label"] if figure else "none usable",
                         "Latest figure": figure["text"] if figure else f"too few isolates (minimum {MIN_SAMPLE})", "Trend": verdict["text"]})
    return pd.DataFrame(rows)


def _rising(country, adjusted, source):
    filters = {"country": country, "kind": "drug_class"}
    if source != "all":
        filters["epi_type"] = source
    rows = data.load(table_name("rising", adjusted, source), **filters)
    rows = rows[rows["rising"].fillna(False).astype(bool)].sort_values(["organism_label", "value"])
    threats, universal = [], []
    for row in rows.to_dict("records"):
        item = {"Organism": row["organism_label"], "Drug class": row["value"], "Trend": rising_verdict(row)["text"]}
        (universal if near_universal(row) else threats).append(item)
    return pd.DataFrame(threats), pd.DataFrame(universal)


def _hotspots(country, adjusted):
    rows = data.load("hotspots_adjusted" if adjusted else "hotspots", country=country)
    rows = rows[rows["persistent"]]
    if rows.empty:
        return pd.DataFrame()
    rows = rows.sort_values("year").groupby(["organism", "drug_class"], as_index=False).tail(1).sort_values(["organism_label", "drug_class"])
    return pd.DataFrame({"Organism": rows["organism_label"], "Drug class": rows["drug_class"], "Year": rows["year"], "Reason": rows["reason"],
                         "Here": [pct_text(r["rate"], r["n"], r["ci_low"], r["ci_high"], r["positives"], r["provisional"]) for r in rows.to_dict("records")]})


def _warnings(country):
    rows = data.load("early_warnings", country=country)
    rows = rows[~rows["new_sequencing"]].sort_values(["organism_label", "gene"])
    return pd.DataFrame({"Organism": rows["organism_label"], "Gene": rows["gene"], "Established": rows["established_year"], "Recent isolates": rows["recent_isolates"],
                         "Recent clusters": rows["recent_clusters"], "Earlier records": rows["earlier_records"]})


def _quality(country):
    rows = data.coverage(country=country)
    total = int(data.load("coverage", country=country)["isolates"].sum())
    usable = rows[rows["isolates"] >= MIN_SAMPLE]
    provisional = int(rows.loc[rows["provisional"], "isolates"].sum())
    return {"isolates": total, "undated": total - int(rows["isolates"].sum()), "groups": len(rows), "usable_groups": len(usable), "provisional_isolates": provisional,
            "last_year": int(rows["year"].max()) if len(rows) else None, "rows": rows}


def build(country, adjusted=False, source="all"):
    threats, universal = _rising(country, adjusted, source)
    return {"country": country, "adjusted": adjusted, "source": source, "quality": _quality(country), "last_resort": _last_resort(country, adjusted, source),
            "rising": threats, "near_universal": universal, "hotspots": _hotspots(country, adjusted), "warnings": _warnings(country)}


def _section(title, frame, empty):
    if frame is None or frame.empty:
        return f"## {title}\n\n{empty}\n"
    head = "| " + " | ".join(frame.columns) + " |"
    rule = "|" + "---|" * len(frame.columns)
    body = ["| " + " | ".join(str(v) for v in row) + " |" for row in frame.itertuples(index=False)]
    return f"## {title}\n\n" + "\n".join([head, rule, *body]) + "\n"


def to_markdown(report):
    quality = report["quality"]
    view = "outbreak-adjusted" if report["adjusted"] else "all isolates"
    source = "" if report["source"] == "all" else f", {report['source']} isolates only (isolates with no recorded type left out)"
    return "\n".join([
        f"# ResistanceMap country report: {report['country']}", "",
        f"**{NOTICE}**", "",
        f"View: {view}{source}. Source: NCBI Pathogen Detection, prepared tables in ResistanceMap.", "",
        "## Data quality", "",
        f"{quality['isolates']:,} sequenced isolates across {quality['groups']} organism and year groups, of which {quality['usable_groups']} reach the minimum of {MIN_SAMPLE}. "
        f"{quality['undated']:,} isolates have no usable year, so they are left out of yearly figures. "
        f"{quality['provisional_isolates']:,} isolates are from provisional years, which are still incomplete. Latest year on record: {quality['last_year']}.", "",
        _section("Last-resort drugs", report["last_resort"], "No isolates for these organisms."),
        _section("Drug classes flagged as rising", report["rising"], "None flagged. This does not show that resistance is stable or falling."),
        _section("Near-universal classes, probably intrinsic genes (not threats)", report["near_universal"], "None."),
        _section("Persistent hotspots, latest year", report["hotspots"], "None flagged. Some flags occur by chance, and small samples cannot flag."),
        _section("Early warnings", report["warnings"], "None, leaving out places where sequencing has only just begun."),
    ])
