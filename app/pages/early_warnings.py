import pandas as pd
import streamlit as st

from lib import charts, data, ui

ui.header("Early warnings", "What has newly appeared, and how strong is the evidence?")
left, middle, right = st.columns(3)
organism = ui.organism_picker("ew_organism", left, include_all=True)
level = middle.selectbox("Level", ["family", "gene"], format_func=lambda v: {"family": "Gene family", "gene": "Exact gene"}[v], key="ew_level")
show_new = right.toggle("Include new sequencing", value=False, key="ew_new", help="Places with under 30 earlier isolates, where every gene looks new because sequencing has just begun.")

rows = data.load("early_warnings", level=level)
if organism != "ALL":
    rows = rows[rows["organism"] == organism]
hidden = int(rows["new_sequencing"].sum())
if not show_new:
    rows = rows[~rows["new_sequencing"]]

ui.chart(charts.early_warning_timeline(rows, "New appearances by country and year"), "No early warnings for this choice.")
st.caption(f"Larger markers mean more recent isolates. Countries in name order. All of these years are provisional, so counts may still change. "
           + (f"{hidden} rows from places where sequencing has only just begun are hidden." if not show_new and hidden else ""))
if len(rows):
    rows = rows.sort_values(["country", "organism_label", "gene"])
    st.subheader("Evidence")
    ui.table(pd.DataFrame({"Country": rows["country"], "Organism": rows["organism_label"], "Gene": rows["gene"], "Established": rows["established_year"], "Earliest record": rows["first_year"],
                           "Recent isolates": rows["recent_isolates"], "Recent clusters": rows["recent_clusters"], "Earlier records": rows["earlier_records"],
                           "Earlier isolates of this organism": rows["baseline_isolates"], "New sequencing": rows["new_sequencing"], "First in country, any organism": rows["first_in_country_any_organism"]}))
    st.caption("Early warning means established in the last 3 data years, with at least 3 isolates from at least 2 clusters. Earlier records are older lone records, so some genes are not truly new. Point mutations are left out.")
ui.no_switch_note("Early warnings")
