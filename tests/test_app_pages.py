"""Opens every page and checks known answers against results/. Runs on the host, with no Spark or Docker."""
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("streamlit")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
from streamlit.testing.v1 import AppTest  # noqa: E402

from lib import answers, charts, data, report  # noqa: E402

PAGES = sorted(p.name for p in (ROOT / "app" / "pages").glob("*.py"))
CARBAPENEM = ("last_resort", "CARBAPENEM", "acquired")


def open_page(name, **values):
    page = AppTest.from_file(str(ROOT / "app" / "pages" / name), default_timeout=120).run()
    for key, value in values.items():
        page.session_state[key] = value
    if values:
        page.run()
    assert not page.exception, f"{name}: {[e.value for e in page.exception]}"
    return page


def test_all_eleven_pages_exist():
    assert len(PAGES) == 11


@pytest.mark.parametrize("name", PAGES)
def test_page_opens(name):
    open_page(name)


@pytest.mark.parametrize("view", ["Country by year", "Trends", "Hotspots", "Organism by drug class"])
def test_map_views(view):
    open_page("map_trends.py", map_view=view)


@pytest.mark.parametrize("view", ["Country by year", "Spread of genes", "Beside WHO GLASS"])
def test_last_resort_views(view):
    open_page("last_resort.py", lr_view=view)


def test_adjusted_and_clinical_switches():
    open_page("map_trends.py", map_adjusted=True, map_source="clinical", map_view="Trends")
    open_page("country_report.py", cr_adjusted=True, cr_source="clinical")
    open_page("compare.py", cc_adjusted=True, cc_source="clinical")


@pytest.mark.parametrize("question", ["When did this gene reach each country?", "Is this a trend, or could it be one outbreak?", "What has newly appeared here recently?",
                                      "Is there enough data here?", "Are any drug classes unusually high here?"])
def test_guided_questions(question):
    open_page("guided.py", gq_question=question)


def test_rare_country_says_too_little():
    answer = answers.rising_question(CARBAPENEM, "Klebsiella", "Afghanistan")
    assert answer.status == "too_little" and "Too little data" in answer.lines[0]


def test_india_klebsiella_carbapenem_answer():
    answer = answers.rising_question(CARBAPENEM, "Klebsiella", "India")
    text = " ".join(answer.lines)
    assert answer.status == "not_flagged"
    assert "Not flagged as rising (2013 to 2022, 8 usable years, 918 of 1,610 isolates, slope +0.06 points per year, z 0.08)" in text
    assert "any mechanism except intrinsic" in text and "slope +0.89 points per year, z 1.42" in text and "flagged once provisional years are included" in text
    assert answer.chart is not None


def test_blandm_timeline_is_in_order_of_first_detection():
    answer = answers.gene_question("blaNDM")
    assert "on record in 123 countries and established in 105" in answer.lines[0]
    established = answer.table["established_year"].dropna().tolist()
    assert established == sorted(established) and established[0] == 2009
    order = list(answer.chart.layout.yaxis.categoryarray)
    assert len(order) == 123


def test_hover_text_on_rate_charts():
    series = answers.rate_series(CARBAPENEM, "Klebsiella", "India")
    fig = charts.trend(series, 2023)
    shown = [t for trace in fig.data if trace.text is not None for t in trace.text if isinstance(t, str)]
    assert shown and all("among sequenced isolates" in t and "genotypic resistance" in t for t in shown)
    world = charts.world_map(data.rate_rows(CARBAPENEM, organism="Klebsiella"))
    assert all("genotypic resistance" in t for trace in world.data for t in trace.text)


def test_map_marks_too_few_apart_from_zero():
    fig = charts.world_map(data.rate_rows(CARBAPENEM, organism="Klebsiella"))
    too_few, rates = fig.data
    assert too_few.colorscale[0][1] == charts.TOO_FEW and rates.zmin == 0
    assert set(too_few.locations).isdisjoint(rates.locations) and len(fig.frames) > 5


def test_figures_match_results():
    table = pd.read_parquet(ROOT / "results" / "last_resort.parquet", filters=[("organism", "==", "Klebsiella"), ("country", "==", "India"), ("drug", "==", "CARBAPENEM"), ("mechanism", "==", "acquired"), ("year", "==", 2025)])
    row = report.build("India")["last_resort"]
    row = row[(row["Organism"] == "Klebsiella") & (row["Drug (acquired genes)"] == "Carbapenem")].iloc[0]
    assert row["Period"] == "2025" and f"{int(table['positives'][0])} of {int(table['n'][0])}" in row["Latest figure"]


def test_fosfomycin_is_not_a_threat():
    built = report.build("India")
    klebsiella = built["rising"][built["rising"]["Organism"] == "Klebsiella"]
    assert "FOSFOMYCIN" not in set(klebsiella["Drug class"])
    assert "FOSFOMYCIN" in set(built["near_universal"]["Drug class"])


def test_report_file_carries_the_notice_and_counts():
    text = report.to_markdown(report.build("India"))
    assert "Not for clinical use" in text and "among sequenced isolates" in text and "% (" in text


def test_every_percent_in_the_report_has_a_count():
    text = report.to_markdown(report.build("India"))
    for match in re.finditer(r"\d+\.\d%", text):
        after = text[match.end():match.end() + 3]
        assert after.startswith(" ("), f"percent with no count near: {text[max(0, match.start() - 30):match.end() + 20]}"


def test_banned_wording_is_absent():
    banned = ["use this", "worst", "spread from", "recommend", "first-line", "best option", "most effective", "treat with", "ranking of"]
    for path in (ROOT / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        for phrase in banned:
            assert phrase not in text, f"{phrase!r} in {path.name}"


@pytest.mark.parametrize("query, expected", [
    ("typhoid", "Possible pathogens, not a diagnosis"),
    ("Typhimurium", "Coverage only"),
    ("influenza", "Caused by a virus"),
    ("klebsiela", "Did you mean"),
    ("cholera", "Tracked by NCBI, not imported here"),
])
def test_search_answers(query, expected):
    page = open_page("search.py", search_query=query)
    text = " ".join(str(e.value) for e in [*page.markdown, *page.info, *page.warning, *page.caption, *page.subheader, *page.get("table")])
    text += " ".join(b.label for b in page.button)
    assert expected in text, query


def test_search_typhoid_counts_match_index():
    page = open_page("search.py", search_query="typhoid")
    index = data.search_index()
    recorded = index[(index["field"] == "host_disease") & (index["organism"] == "Salmonella")
                     & index["key"].str.contains(r"(?<!\w)(?:typhoid|enteric fever|paratyphoid)(?!\w)", regex=True)]
    text = " ".join(m.value for m in page.markdown)
    assert f"{int(recorded['isolates'].sum()):,} of" in text
