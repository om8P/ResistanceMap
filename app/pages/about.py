import pandas as pd
import streamlit as st

from lib import charts, data, ui
from lib.rules import MIN_SAMPLE, field_status

ui.header("About the data", "Where the figures come from and what they cannot show.")
st.error("Not for clinical use. This tool shows what sequenced samples contain. It does not say which drug to give.")

profile = data.load_json("data_profile")["organisms"]
labels = data.organisms()
everything = data.load("coverage")
coverage = data.coverage()
total = int(everything["isolates"].sum())
shares = everything.groupby("country")["isolates"].sum()
no_country = int(everything.loc[everything["country"].isna(), "isolates"].sum())
no_year = int(everything.loc[everything["year"].isna(), "isolates"].sum())

st.subheader("What it measures")
st.markdown(f"""
- **Genotypic resistance among sequenced isolates:** the share of isolates carrying at least one gene for a drug class. Isolates with no resistance genes stay in the denominator.
- **Minimum sample:** percentages are hidden under {MIN_SAMPLE} isolates in a group.
- **Confidence:** Wilson 95% interval. Stronger means up to 10 points wide, moderate up to 25, weak above that.
- **Outbreak-adjusted:** each cluster counts once per organism, country and year.
- **Provisional:** {data.provisional_start()} on. Samples are uploaded long after collection, so these years are incomplete.
""")

st.subheader("Coverage")
organism = st.selectbox("Organism", ["ALL", *labels], format_func=lambda v: {"ALL": "All organisms", **labels}[v], key="ab_organism")
part = coverage if organism == "ALL" else coverage[coverage["organism"] == organism]
per = part.groupby(["country", "year"], as_index=False)["isolates"].sum()
keep = per.loc[per["isolates"] >= MIN_SAMPLE, "country"].unique()
first = int(per.loc[per["isolates"] >= MIN_SAMPLE, "year"].min()) if len(keep) else 2000
shown = per[per["country"].isin(keep) & (per["year"] >= max(first, 2000))]
ui.chart(charts.count_heatmap(shown, "year", "country", "isolates", "Sequenced isolates by country and year"))
st.caption(f"Countries in name order. {per['country'].nunique() - len(keep)} countries with no year at the minimum are left out. Colour is on a log scale. "
           + "".join(f"{name} holds {shares[name] / total:.1%} of isolates ({int(shares[name]):,} of {total:,}). " for name in ["USA", "India"] if name in shares)
           + f"{no_country / total:.1%} have no usable country and {no_year / total:.1%} no usable year, so they are not on this chart. "
           f"{int((coverage['isolates'] >= MIN_SAMPLE).sum()):,} of {len(coverage):,} organism, country and year groups reach the minimum.")

st.subheader("Data quality by organism")
rows = []
for key in sorted(profile, key=lambda k: labels.get(k, k)):
    fill = profile[key]["fill"]
    delay = profile[key]["upload_delay"]
    rows.append({"Organism": labels.get(key, key), "Source rows": f"{profile[key]['rows']:,}", "Collection date filled": f"{fill['collection_date']['pct_filled']:.1f}%",
                 "Location filled": f"{fill['geo_loc_name']['pct_filled']:.1f}%", "Isolate type filled": f"{fill['epi_type']['pct_filled']:.1f}%",
                 "Lab results filled": f"{fill['AST_phenotypes']['pct_filled']:.1f}%", "Years to 90% uploaded": str(delay.get("years_to_complete") or "not reached")})
ui.table(pd.DataFrame(rows))
fills = data.field_fill()
labelled = sorted(k for k, v in fills.items() if field_status(v) == "label")
hidden = sorted(k for k, v in fills.items() if field_status(v) == "hide")
st.caption(f"Fields under 50% filled, labelled as sparse where used: {', '.join(labelled) or 'none'}. Fields under 10% filled, hidden as a breakdown: {', '.join(hidden) or 'none'}.")

st.subheader("Limits")
st.markdown("""
- The data reflects what labs chose to sequence, not all infections. It is not national prevalence.
- Having a gene does not prove a drug will fail.
- Location is mostly country level, and 40 to 55% of real dates are year only, so results stay yearly.
- Raw dates include errors, such as `blaNDM` in 1943, so timelines lead with the established year.
- Intrinsic genes (`fosA`, `blaSHV` in Klebsiella) put some classes near 100%, so those classes cannot flag as high.
- `blaKPC` with no subclass (749 rows) slightly undercounts carbapenem.
- Clustered isolates are not independent, so z scores in the all-isolates view run high. Check the adjusted view.
- Many country and year comparisons mean some hotspots will flag by chance.
- Analysis methods can differ by about 20 points within a year for some Salmonella and E. coli classes. Staph aureus shifted most in method mix, so its trends carry a caveat.
- Lab results cover 24,803 isolates, more of them environmental than clinical, so they are not a random sample.
""")

st.subheader("Sources")
st.markdown("""
- **NCBI Pathogen Detection:** isolate resistance genes and metadata for six organisms, plus the gene catalog and cluster lists.
- **WHO GLASS:** lab-confirmed resistance in bloodstream infections, 2018 to 2023, for countries meeting its reporting threshold (32 here, no USA). Comparison only, never merged into our rates. Credit: WHO.
- **WHO AWaRe classification:** antibiotic group labels. Credit: WHO.
""")

st.subheader("Someone else's estimates: GRAM")
st.markdown("""
The Global Research on Antimicrobial Resistance (GRAM) project estimated the burden of bacterial antimicrobial resistance. These are its modelled figures, not results from this tool:
- In 2021: 1.14 million deaths attributable (95% UI 1.00 to 1.28 million) and 4.71 million associated (4.23 to 5.19 million).
- Forecast for 2050: 1.91 million attributable (1.56 to 2.26 million) and 8.22 million associated (6.85 to 9.65 million).

Credit: GBD 2021 Antimicrobial Resistance Collaborators, [The Lancet, 2024; 404: 1199 to 1226](https://doi.org/10.1016/S0140-6736(24)01867-1).
""")

st.subheader("Checks")
if not data.has_result("sanity_checks.json"):
    st.write("The reconciliation checks run on the six core organisms only. For an imported pathogen, see its isolate and coverage counts above.")
    st.stop()
sanity = data.load_json("sanity_checks")
reconciliation = sanity["reconciliation"]
st.write(f"Isolates in the main table and in coverage: {reconciliation['isolates_in_table']:,} and {reconciliation['isolates_in_coverage']:,}. "
         f"Prevalence groups that differ from coverage: {reconciliation['prevalence_groups_differing_from_coverage']}. Rates shown under the minimum: {reconciliation['prevalence_rows_rate_shown_under_minimum']}.")
