import pandas as pd
import streamlit as st

from lib import charts, data, glass, ui
from lib.answers import rate_text
from lib.rules import latest_figure, rising_verdict

ui.header("Last-resort drugs", "How are carbapenem and colistin resistance changing?")
MECHANISMS = {"CARBAPENEM": ["acquired", "any_excl_intrinsic", "mutation", "disrupted", "intrinsic"], "COLISTIN": ["acquired", "any_excl_intrinsic", "mutation", "disrupted", "intrinsic"],
              "CARBAPENEM+COLISTIN": ["acquired", "any_excl_intrinsic"]}
one, two, three, four, five = st.columns(5)
organism = ui.organism_picker("lr_organism", one)
drug = two.selectbox("Drug", list(MECHANISMS), format_func=data.DRUG_LABEL.get, key="lr_drug")
mechanism = three.selectbox("Mechanism", MECHANISMS[drug], format_func=data.MECHANISM_LABEL.get, key="lr_mechanism")
adjusted, source = ui.view_controls("lr", four, adjust=False)
adjusted = five.toggle("Outbreak-adjusted", key="lr_adjusted", help="Counts each outbreak cluster once per organism, country and year.")
measure = ("last_resort", drug, mechanism)
label = data.measure_label(measure)
view = st.radio("View", ["Trends", "Country by year", "Spread of genes", "Beside WHO GLASS"], horizontal=True, key="lr_view", label_visibility="collapsed")
ui.view_note(adjusted, source)
organism_label = data.organisms()[organism]

if view == "Trends":
    country = ui.country_picker("lr_country")
    rows = data.rate_rows(measure, False, source, organism=organism, country=country)
    held = data.rate_rows(measure, True, source, organism=organism, country=country)
    series = {"All isolates": charts.with_hover(rows, lambda r: f"{country}, {int(r['year'])}"), "Outbreak-adjusted": charts.with_hover(held, lambda r: f"{country}, {int(r['year'])}")}
    ui.chart(charts.trend(series, data.provisional_start(), f"{label}, {organism_label}, {country}"))
    st.caption("Bands are Wilson 95% intervals. Gaps are years under the minimum of 30 isolates. Shaded years are provisional.")
    ui.caveats(organism, measure)
    yearly, pooled = data.latest_inputs(measure, organism, country, adjusted, source)
    figure = latest_figure(yearly, pooled, data.latest_data_year())
    st.markdown(f"**Latest figure{' (' + figure['label'] + ')' if figure else ''}:** {figure['text'] if figure else 'too few isolates in every year and period.'}")
    if figure and figure["pooled"]:
        st.info(f"No recent single year reaches the minimum, so this uses a pooled period: {figure['label']}.")
    st.markdown(f"**Trend:** {rising_verdict(data.rising_row(measure, organism, country, adjusted, source))['text']}")
    table = series["All isolates"].sort_values("year")
    with st.expander("Table of yearly figures"):
        ui.table(pd.DataFrame({"Year": table["year"], "All isolates": [rate_text(r) for r in table.to_dict("records")]}))

elif view == "Country by year":
    rows = data.rate_rows(measure, adjusted, source, organism=organism)
    usable = rows[rows["rate"].notna()]
    if usable.empty:
        ui.chart(None)
    else:
        kept = rows[rows["country"].isin(usable["country"]) & (rows["year"] >= usable["year"].min())]
        kept = charts.with_hover(kept, lambda r: f"{r['country']}, {int(r['year'])}")
        ui.chart(charts.rate_heatmap(kept, "year", "country", f"{label}, {organism_label}"))
        st.caption(f"{rows['country'].nunique() - usable['country'].nunique()} countries with no year at the minimum of 30 isolates are left out. Countries in name order.")
        ui.legend_note()
    ui.caveats(organism, measure)

elif view == "Spread of genes":
    single = "COLISTIN" if drug == "COLISTIN" else "CARBAPENEM"
    summary = data.load("gene_summary")
    subclass = summary["drug_subclass"].fillna("")
    found = summary[subclass.str.contains(single) & ~summary["family"].fillna("").str.contains("OXA-51")]
    sizes = found.groupby("family")["isolates"].sum()
    families = sorted(sizes.index)
    acquired_type = sizes[sizes.index.str.startswith(("bla", "mcr"))]
    default = sorted(acquired_type.sort_values(ascending=False).head(5).index)
    chosen = st.multiselect("Gene families", families, default=default, max_selections=5, key=f"lr_families_{single}")
    rows = data.load("first_seen", level="family", organism=organism, gene=chosen) if chosen else pd.DataFrame()
    if len(rows):
        rows = rows[~rows["point_mutation"]]
    ui.chart(charts.countries_established(rows, f"Countries with each gene family established, {organism_label}") if len(rows) else None, "No established gene families for this choice.")
    st.caption("Established means at least 3 isolates from at least 2 clusters. This counts where sequencing has found the gene, not where it truly is. The intrinsic OXA-51 family and point mutations are left out. "
               "Families in name order; the five bla or mcr families with the most isolates are selected first. The outbreak and source switches do not apply here.")

else:
    country = ui.country_picker("lr_glass_country")
    if drug == "CARBAPENEM+COLISTIN":
        st.warning("WHO GLASS has no figure for both drugs in one isolate. Choose carbapenem or colistin.")
    else:
        series, notes = glass.series(organism, country, drug)
        ours = data.rate_rows(measure, adjusted, source, organism=organism, country=country)
        if not series:
            st.warning(f"WHO GLASS has no matching figures for this organism, drug and country. GLASS shows only countries meeting its reporting threshold, and has no USA rows.")
        else:
            ours = ours[ours["year"].between(2010, data.latest_data_year())]
            everything = {f"Ours: {data.MECHANISM_LABEL[mechanism]}": charts.with_hover(ours, lambda r: f"{country}, {int(r['year'])}"), **series}
            ui.chart(charts.trend(everything, data.provisional_start(), f"{data.DRUG_LABEL[drug]}, {organism_label}, {country}", y_title="% resistant, on each source's own measure"))
            st.warning("These are different measures and should not be read as one number. WHO GLASS shows lab-confirmed resistance in bloodstream infections. Ours shows genes in sequenced isolates. Credit for GLASS figures: WHO.")
            for note in notes:
                st.caption(note)
    ui.caveats(organism, measure)
