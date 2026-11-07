import json

import pandas as pd
import streamlit as st

from lib import charts, data, ui
from lib.answers import gene_question
from lib.rules import field_status

ui.header("Gene profile", "Search a gene to see its drug class, timeline, countries and sources.")


@st.cache_data(show_spinner=False)
def gene_options():
    summary = data.load("gene_summary")
    return sorted(set(summary["gene"]) | set(summary["family"].dropna()))


left, right = st.columns(2)
options = gene_options()
gene = left.selectbox("Gene or gene family", options, index=options.index("blaNDM") if "blaNDM" in options else 0, key="gene_name")
organism = ui.organism_picker("gene_organism", right, include_all=True)

summary = data.load("gene_summary")
rows = summary[(summary["family"] == gene) | (summary["gene"] == gene)]
exact = rows[rows["gene"] == gene]
facts = rows.iloc[0] if len(rows) else None
if facts is not None:
    classes = ", ".join(sorted(set(rows["drug_class"].dropna()))) or "not mapped"
    subclasses = ", ".join(sorted(set(rows["drug_subclass"].dropna()))) or "none listed"
    st.markdown(f"**Drug class:** {classes}  \n**Subclass:** {subclasses}  \n**Organisms:** {', '.join(sorted({o for v in rows['organisms'].dropna() for o in v.split(' | ')}))}  \n"
                f"**Exact gene names in this family:** {rows['gene'].nunique()}")

answer = gene_question(gene, organism)
for line in answer.lines:
    st.write(line)
ui.chart(answer.chart, "No records for this gene and organism.")
if answer.table is not None:
    st.subheader("Isolates by country")
    ui.chart(charts.isolates_by_country(answer.table, f"Sequenced isolates with {gene} (count, not a rate)"))
    st.caption("Counts follow how much each country sequences, so they are not rates. Countries in name order.")
    with st.expander("Table of first detection"):
        frame = answer.table.rename(columns={"country": "Country", "established_year": "Established", "first_year": "Earliest record", "isolates": "Isolates", "clusters": "Clusters"})
        ui.table(frame)

if len(rows):
    st.subheader("Sources")
    fill = data.field_fill()
    fields = {"top_epi_type": ("epi_type", "Isolate type"), "top_host": ("host", "Host"), "top_isolation_source": ("isolation_source", "Isolation source")}
    columns = st.columns(len(fields))
    for column, (name, (field, title)) in zip(columns, fields.items()):
        status = field_status(fill.get(field, 0))
        if status == "hide":
            column.caption(f"{title} is hidden, because only {fill[field]:.0f}% of isolates have it.")
            continue
        totals = {}
        for raw in rows[name].dropna():
            for item in json.loads(raw):
                totals[item["value"]] = totals.get(item["value"], 0) + item["isolates"]
        frame = pd.DataFrame(sorted(totals.items()), columns=[title, "Isolates"])
        column.dataframe(frame, hide_index=True, width="stretch")
        if status == "label":
            column.caption(f"Sparse field: only {fill[field]:.0f}% of isolates have it.")
    st.caption("Listed values come from each exact gene's most common entries, added up, so totals are partial. In name order. Sources describe what was sequenced.")
ui.no_switch_note("Gene history")
