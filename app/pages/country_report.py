import streamlit as st

from lib import charts, data, report, ui
from lib.rules import table_name

ui.header("Country report", "What should someone in this country know, and how far can the data be trusted?")
left, middle, right = st.columns(3)
country = ui.country_picker("cr_country", left)
adjusted, source = ui.view_controls("cr", middle, adjust=False)
adjusted = right.toggle("Outbreak-adjusted", key="cr_adjusted", help="Counts each outbreak cluster once per organism, country and year.")
ui.view_note(adjusted, source)

built = report.build(country, adjusted, source)
quality = built["quality"]
st.download_button("Download this report (Markdown)", report.to_markdown(built), file_name=f"resistancemap_{country.replace(' ', '_').lower()}.md", mime="text/markdown", key="cr_download")

st.subheader("Data quality")
st.write(f"{quality['isolates']:,} sequenced isolates across {quality['groups']} organism and year groups, of which {quality['usable_groups']} reach the minimum of 30. "
         f"{quality['undated']:,} isolates have no usable year, so they are left out of yearly figures. {quality['provisional_isolates']:,} isolates are from provisional years. Latest year on record: {quality['last_year']}.")
per_year = quality["rows"].groupby("year", as_index=False)["isolates"].sum().sort_values("year")
per_year = per_year[per_year["year"] >= 2000]
ui.chart(charts.count_bars(per_year, "year", "isolates", f"Sequenced isolates by year, {country}", provisional_from=data.provisional_start()), "No isolates from 2000 on.")

st.subheader("Last-resort drugs")
organisms = data.organisms()
panels = {}
for organism in sorted(set(quality["rows"]["organism"]), key=organisms.get):
    for drug in report.LAST_RESORT_DRUGS:
        rows = data.rate_rows(("last_resort", drug, "acquired"), adjusted, source, organism=organism, country=country)
        if rows["rate"].notna().any():
            panels[f"{organisms[organism]}: {drug.capitalize()}"] = charts.with_hover(rows, lambda r: f"{country}, {int(r['year'])}")
ui.chart(charts.trend_panels(panels, data.provisional_start(), "Acquired genes, by organism and drug") if panels else None, "No organism and drug here reaches the minimum of 30 isolates in any year.")
ui.table(built["last_resort"])
st.caption("A pooled period appears only when no recent single year reaches the minimum.")

st.subheader("Drug classes flagged as rising")
if built["rising"].empty:
    st.write("None flagged. This does not show that resistance is stable or falling.")
else:
    ui.table(built["rising"])
if not built["near_universal"].empty:
    with st.expander(f"Near-universal classes, probably intrinsic genes ({len(built['near_universal'])})"):
        st.write("These classes are in nearly every isolate, so they are not treated as threats, even where a small rise is flagged.")
        ui.table(built["near_universal"])

filters = {"country": country}
if source != "all":
    filters["epi_type"] = source
classes = data.load(table_name("prevalence", adjusted, source), **filters)
usable = classes[classes["rate"].notna()]
if len(usable):
    year = int(usable.loc[usable["year"] < data.provisional_start(), "year"].max() if (usable["year"] < data.provisional_start()).any() else usable["year"].max())
    in_year = classes[(classes["year"] == year) & classes["drug_class"].isin(usable.loc[usable["year"] == year, "drug_class"])]
    in_year = charts.with_hover(in_year, lambda r: f"{r['organism_label']}, {r['drug_class']}, {year}")
    st.subheader("Drug classes by organism")
    ui.chart(charts.rate_heatmap(in_year, "drug_class", "organism_label", f"{country}, {year}", cell_px=46))
    st.caption("Latest year outside the provisional period with usable figures. Classes and organisms in name order.")
    ui.near_universal_note()

st.subheader("Persistent hotspots, latest year")
if built["hotspots"].empty:
    st.write("None flagged. Some flags occur by chance, and small samples cannot flag.")
else:
    ui.table(built["hotspots"])
st.subheader("Early warnings")
if built["warnings"].empty:
    st.write("None, leaving out places where sequencing has only just begun.")
else:
    ui.chart(charts.early_warning_timeline(data.load("early_warnings", country=country).query("not new_sequencing")))
    ui.table(built["warnings"])
ui.caveats("Staphylococcus_aureus" if "Staphylococcus_aureus" in set(quality["rows"]["organism"]) else None, ("last_resort", "CARBAPENEM", "acquired"))
