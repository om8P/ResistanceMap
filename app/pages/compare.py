import pandas as pd
import streamlit as st

from lib import charts, data, glass, ui
from lib.rules import latest_figure, pct_text, rising_verdict

ui.header("Compare countries", "A few countries side by side, in name order. Differences can reflect what each country sequences.")
top_left, top_right = st.columns([2, 1])
all_countries = data.countries()
chosen = top_left.multiselect("Countries, up to 6", all_countries, default=[c for c in ["Germany", "India", "United Kingdom"] if c in all_countries], max_selections=6, key="cc_countries")
organism = ui.organism_picker("cc_organism", top_right)
left, middle, right = st.columns(3)
measure = ui.measure_picker("cc_measure", left)
_, source = ui.view_controls("cc", middle, adjust=False)
adjusted = right.toggle("Outbreak-adjusted", key="cc_adjusted", help="Counts each outbreak cluster once per organism, country and year.")
ui.view_note(adjusted, source)
chosen = sorted(chosen)
if not chosen:
    st.info("Choose at least one country.")
    st.stop()

panels = {}
figures = []
for country in chosen:
    rows = data.rate_rows(measure, adjusted, source, organism=organism, country=country)
    panels[country] = charts.with_hover(rows, lambda r: f"{r['country']}, {int(r['year'])}")
    figure = latest_figure(*data.latest_inputs(measure, organism, country, adjusted, source), data.latest_data_year())
    verdict = rising_verdict(data.rising_row(measure, organism, country, adjusted, source))
    figures.append({"Country": country, "Isolates of this organism": int(data.load("coverage", organism=organism, country=country)["isolates"].sum()),
                    "Period": figure["label"] if figure else "none usable", "Latest figure": figure["text"] if figure else "too few isolates (minimum 30)", "Trend": verdict["text"]})

ui.chart(charts.trend_panels(panels, data.provisional_start(), f"{data.measure_label(measure)}, {data.organisms()[organism]}"))
st.caption("All panels use the same axes. Bands are Wilson 95% intervals, gaps are years under the minimum, and shading marks provisional years.")
ui.table(pd.DataFrame(figures))
ui.caveats(organism, measure)

if (measure[0] == "last_resort" and measure[1] != "CARBAPENEM+COLISTIN") or measure == ("prevalence", "QUINOLONE", None):
    st.subheader("WHO GLASS for the same countries")
    st.caption("Credit: WHO. GLASS shows lab-confirmed resistance in bloodstream infections, against genes in sequenced isolates here, so these are different measures. GLASS lists only countries meeting its reporting threshold.")
    rows = []
    for country in chosen:
        series, _ = glass.series(organism, country, measure[1])
        for name, part in series.items():
            usable = part[part["rate"].notna()].sort_values("year")
            if len(usable):
                row = usable.iloc[-1]
                rows.append({"Country": country, "GLASS antibiotic": name.replace("GLASS: ", ""), "Year": int(row["year"]), "Lab-confirmed, bloodstream": pct_text(row["rate"], row["n"], row["ci_low"], row["ci_high"], row["positives"])})
    if rows:
        ui.table(pd.DataFrame(rows))
    else:
        st.write("No matching WHO GLASS figures for these countries and this organism.")
