import pandas as pd
import streamlit as st

from lib import data, ui
from lib.rules import pct_text

ui.header("Evidence panel", "What the data shows for a gene, for readers who know the clinical context. It does not choose a drug.")
st.error("Not for clinical use. A gene does not prove that a drug will fail, and its absence does not prove that a drug will work. "
         "Antibiotics are listed by name only, as evidence, with no order of preference. Treatment decisions need local antibiograms and WHO or national guidance.")
left, middle, right = st.columns(3)
organism = ui.organism_picker("ev_organism", left)
country = ui.country_picker("ev_country", middle)
genes_here = data.load("first_seen", organism=organism, country=country, level="family")
genes_here = genes_here[~genes_here["point_mutation"]].sort_values("gene")
lab = data.load("gene_lab_agreement", organism=organism, level="family")
options = sorted(set(lab["gene"]))
if not options:
    st.warning("No lab results for this organism.")
    st.stop()
default = next((g for g in ("blaNDM", "blaKPC", "mcr-1") if g in options), options[0])
gene = right.selectbox("Gene family", options, index=options.index(default), key="ev_gene")

coverage = data.coverage(organism=organism, country=country)
st.subheader("Data age")
if coverage.empty:
    st.write(f"No sequenced isolates of this organism from {country}.")
else:
    latest = int(coverage["year"].max())
    latest_row = coverage[coverage["year"] == latest].iloc[0]
    st.write(f"{int(coverage['isolates'].sum()):,} sequenced isolates from {country} with a usable year. Latest year on record: {latest} ({int(latest_row['isolates']):,} isolates"
             f"{', provisional' if latest_row['provisional'] else ''}).")

st.subheader(f"Gene families detected in {country}")
if genes_here.empty:
    st.write("None on record for this organism.")
else:
    summary = data.load("gene_summary", family=list(genes_here["gene"]))
    classes = summary.groupby("family")["drug_class"].agg(lambda v: ", ".join(sorted(set(v.dropna())))).to_dict()
    with st.expander(f"{len(genes_here)} families, in name order"):
        ui.table(pd.DataFrame({"Gene family": genes_here["gene"], "Drug class": genes_here["gene"].map(classes).fillna("not mapped"), "Isolates": genes_here["isolates"], "Clusters": genes_here["clusters"],
                               "Established": genes_here["established_year"], "Earliest record": genes_here["first_year"]}))

st.subheader(f"Gene and lab agreement: {gene}")
st.caption(f"Across all countries, not specific to {country}. Lab results exist for only 24,803 isolates, more of them environmental than clinical, so they are not a random sample.")
rows = lab[lab["gene"] == gene].copy()
rows["name"] = [a.capitalize() if w != w or w is None or w.lower() == a.lower() else f"{w} (recorded as {a})" for w, a in zip(rows["who_name"], rows["antibiotic"])]
rows = rows.sort_values("name")
frame = pd.DataFrame({"Antibiotic": rows["name"], "WHO AWaRe group": rows["aware_category"].fillna("not listed"), "Tested": rows["tested"],
                      "Lab-resistant, with the gene": [pct_text(r["with_gene_rate"], r["with_gene"], r["with_gene_ci_low"], r["with_gene_ci_high"], r["with_gene_resistant"]) for r in rows.to_dict("records")],
                      "Lab-resistant, without the gene": [pct_text(r["without_gene_rate"], r["without_gene"], r["without_gene_ci_low"], r["without_gene_ci_high"], r["without_gene_resistant"]) for r in rows.to_dict("records")]})
st.table(frame.set_index("Antibiotic"))
st.caption("Sorted by antibiotic name. This table is fixed, so it cannot be reordered by rate. Low figures do not mean a drug looks effective: they come from small, selected samples.")

st.subheader("Where to look for treatment guidance")
st.markdown("- [The WHO AWaRe antibiotic book](https://www.who.int/publications/i/item/9789240062382)\n"
            "- [WHO AWaRe classification, 2023](https://www.who.int/publications/i/item/WHO-MHP-HPS-EML-2023.04)\n"
            "- Your hospital or regional antibiogram, which reflects local lab-tested resistance\n- National treatment guidelines")
ui.no_switch_note("Gene and lab agreement")
