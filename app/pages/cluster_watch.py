import pandas as pd
import streamlit as st

from lib import charts, data, ui

LIMIT = 120
ui.header("Cluster watch", "Recent genetic clusters seen in more than one country. This describes the past and shows no routes.")
left, middle, right = st.columns(3)
organism = ui.organism_picker("cw_organism", left, include_all=True)
only_new = middle.toggle("Only new clusters", value=True, key="cw_new", help="First recorded inside the last 3 data years.")
only_acquired = right.toggle("Only with an acquired last-resort gene", value=True, key="cw_acquired")

rows = data.load("cluster_watch")
if organism != "ALL":
    rows = rows[rows["organism"] == organism]
if only_new:
    rows = rows[rows["new_since_window"]]
if only_acquired:
    rows = rows[rows["acquired_last_resort"]]
rows = rows.sort_values(["first_year", "cluster_id"])
shown = rows.head(LIMIT)
ui.chart(charts.cluster_bars(shown, "First to last year on record, per cluster"), "No clusters for this choice.")
st.caption(f"{len(rows):,} clusters match" + (f"; the {LIMIT} with the earliest first year are drawn" if len(rows) > LIMIT else "") + ". Ordered by first year. "
           "A cluster seen in two countries shares closely related isolates. The data cannot show how or whether it moved between them.")
if len(rows):
    ui.table(pd.DataFrame({"Cluster": rows["cluster_id"], "Organism": rows["organism_label"], "First year": rows["first_year"], "Last year": rows["last_year"], "Isolates": rows["isolates"],
                           "Recent isolates": rows["recent_isolates"], "Seen in": rows["countries"], "Countries": rows["country_count"], "Last-resort genes": rows["last_resort_genes"], "Provisional": rows["provisional"]}))
ui.no_switch_note("Cluster watch")
