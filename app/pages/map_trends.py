import pandas as pd
import streamlit as st

from lib import charts, data, ui
from lib.answers import rate_series, rate_text
from lib.rules import rising_verdict, table_name

ui.header("Map and trends", "Where is this resistance, and how has it changed over time?")
left, middle, right, far = st.columns(4)
organism = ui.organism_picker("map_organism", left)
measure = ui.measure_picker("map_measure", middle)
adjusted, source = ui.view_controls("map", right, adjust=False)
adjusted = far.toggle("Outbreak-adjusted", key="map_adjusted", help="Counts each outbreak cluster once per organism, country and year.")
view = st.radio("View", ["Map", "Country by year", "Trends", "Hotspots", "Organism by drug class"], horizontal=True, key="map_view", label_visibility="collapsed")
ui.view_note(adjusted, source)
label = data.measure_label(measure)

if view == "Map":
    rows = data.rate_rows(measure, adjusted, source, organism=organism)
    ui.chart(charts.world_map(rows, f"{label}, {data.organisms()[organism]}", start_year=data.provisional_start() - 1))
    ui.legend_note()
    ui.caveats(organism, measure)
    st.caption("The map shows single years. Use the country report for pooled periods where one year is too small.")

elif view == "Country by year":
    rows = data.rate_rows(measure, adjusted, source, organism=organism)
    usable = rows[rows["rate"].notna()]
    if usable.empty:
        ui.chart(None)
    else:
        kept = rows[rows["country"].isin(usable["country"]) & (rows["year"] >= usable["year"].min())]
        kept = charts.with_hover(kept, lambda r: f"{r['country']}, {int(r['year'])}")
        ui.chart(charts.rate_heatmap(kept, "year", "country", f"{label}, {data.organisms()[organism]}"))
        st.caption(f"{rows['country'].nunique() - usable['country'].nunique()} countries with no year at the minimum of 30 isolates are left out. Countries in name order.")
        ui.legend_note()
    ui.caveats(organism, measure)

elif view == "Trends":
    country = ui.country_picker("map_country")
    series = rate_series(measure, organism, country, source)
    ui.chart(charts.trend(series, data.provisional_start(), f"{label}, {data.organisms()[organism]}, {country}"))
    st.caption("Bands are Wilson 95% intervals. Gaps are years under the minimum of 30 isolates. Shaded years are provisional.")
    ui.caveats(organism, measure)
    full = rising_verdict(data.rising_row(measure, organism, country, False, source))
    held = rising_verdict(data.rising_row(measure, organism, country, True, source))
    st.markdown(f"**All isolates:** {full['text']}\n\n**Outbreak-adjusted:** {held['text']}")
    table = series["All isolates"].sort_values("year")
    with st.expander("Table of yearly figures"):
        ui.table(pd.DataFrame({"Year": table["year"], "All isolates": [rate_text(r) for r in table.to_dict("records")]}))

elif view == "Hotspots":
    st.caption("This view uses the drug class chosen below, not the resistance measure above.")
    rows = data.load("hotspots_adjusted" if adjusted else "hotspots", organism=organism)
    only = st.toggle("Only persistent hotspots", value=True, key="map_persistent", help="High in this year and the calendar year before or after.")
    if only:
        rows = rows[rows["persistent"]]
    classes = sorted(rows["drug_class"].unique())
    if not classes:
        st.warning("No hotspots for this choice.")
    else:
        drug_class = st.selectbox("Drug class", classes, key="map_hot_class")
        part = charts.with_hover(rows[rows["drug_class"] == drug_class], lambda r: f"{r['country']}, {int(r['year'])}")
        ui.chart(charts.rate_heatmap(part, "year", "country", f"Flagged years: {drug_class}, {data.organisms()[organism]}"))
        st.caption("A hotspot's lower confidence limit is more than 10 points above all other countries in the same year, or the class is rising there. "
                   "Pale cells are not flagged. With so many comparisons, some flags occur by chance. Countries in name order, with no ranking.")
        if source != "all":
            ui.no_switch_note("Hotspots")
        part = part.sort_values(["country", "year"])
        ui.table(pd.DataFrame({"Country": part["country"], "Year": part["year"], "Reason": part["reason"], "Persistent": part["persistent"],
                               "Here": [rate_text(r) for r in part.to_dict("records")],
                               "All other countries": [f"{r['rest_rate'] * 100:.1f}% (n = {int(r['rest_n']):,})" if r["rest_rate"] == r["rest_rate"] else "not compared" for r in part.to_dict("records")]}))
    ui.near_universal_note()

else:
    st.caption("This view covers every drug class, so the organism and resistance measure above do not apply.")
    country = ui.country_picker("map_org_country")
    year_rows = data.coverage(country=country)
    years = sorted(year_rows.loc[year_rows["isolates"] >= 30, "year"].unique(), reverse=True)
    if not years:
        st.warning(f"No organism in {country} reaches the minimum of 30 isolates in any year.")
    else:
        stable = [y for y in years if y < data.provisional_start()]
        year = st.selectbox("Year", years, index=years.index(stable[0]) if stable else 0, key="map_org_year")
        filters = {"country": country, "year": int(year)}
        if source != "all":
            filters["epi_type"] = source
        rows = data.load(table_name("prevalence", adjusted, source), **filters)
        usable = rows[rows["rate"].notna()]
        rows = rows[rows["drug_class"].isin(usable["drug_class"])]
        if rows.empty:
            ui.chart(None)
        else:
            rows = charts.with_hover(rows, lambda r: f"{r['organism_label']}, {r['drug_class']}, {int(r['year'])}")
            ui.chart(charts.rate_heatmap(rows, "drug_class", "organism_label", f"Drug classes by organism, {country}, {int(year)}", cell_px=46))
            st.caption("Carbapenem sits inside Beta-lactam here, so use the last-resort measures for it. Classes and organisms in name order.")
            ui.near_universal_note()
