import pandas as pd
import streamlit as st

from lib import data, search, ui
from lib.rules import MIN_SAMPLE

ui.header("Search", "Is a pathogen, serovar, strain or disease covered here, and how good is the data?")

labels = data.organisms()
ncbi = data.ncbi_organisms()
diseases = data.disease_list()
index = data.search_index()
coverage = data.load("coverage")
summary = data.load_json("pipeline_summary")
profile = data.load_json("data_profile")["organisms"]

query = st.text_input("Search", key="search_query", placeholder="For example: Klebsiella, Typhimurium, ST131, 573, typhoid, pneumonia")


def ncbi_label(organism):
    return labels.get(organism, organism.replace("_", " "))


def open_page(organism, page, key):
    if st.button(f"Open {page[1]}", key=f"open_{page[0]}_{key}"):
        st.session_state[page[2]] = organism
        st.switch_page(f"pages/{page[0]}.py")


def card(organism, key):
    facts = search.organism_card(organism, coverage, summary, MIN_SAMPLE)
    years = f"{facts['first_year']} to {facts['last_year']}" if facts["first_year"] else "no usable years"
    st.markdown(f"**{labels[organism]}**: {facts['isolates']:,} sequenced isolates from {facts['countries']} countries, collection years {years}. "
                f"{facts['groups_at_minimum']:,} of {facts['groups']:,} country and year groups reach the minimum of {MIN_SAMPLE} isolates, "
                f"so rates show only for those. Gene catalog match: {facts['catalog_match_pct']}% ({facts['gene_rows']:,} gene entries).")
    left, right = st.columns(2)
    with left:
        open_page(organism, ("map_trends", "map and trends", "map_organism"), key)
    with right:
        open_page(organism, ("about", "data coverage", "ab_organism"), key)


if not query.strip():
    st.write(f"Covered here: {', '.join(labels.values())}. NCBI Pathogen Detection tracks {len(ncbi)} organism groups in all; "
             "the others are not imported. Viruses and parasites are not covered.")
    st.stop()

found = search.search(query, labels, ncbi, diseases, index)

if found["organisms"]:
    st.subheader("Organisms")
    for organism in found["organisms"]:
        card(organism, organism)

if len(found["diseases"]):
    st.subheader("Diseases")
    st.warning("Possible pathogens, not a diagnosis. A disease can have many causes, including ones not listed or not covered here. "
               "This list was written by hand from public fact sheets.")
    for name, rows in found["diseases"].groupby("disease", sort=False):
        st.markdown(f"#### {name}")
        listed = rows[rows["organism"].notna()]
        if not len(listed):
            st.info(f"{rows.iloc[0]['note']}. Source: {rows.iloc[0]['source']}.")
            continue
        table = []
        for _, row in listed.iterrows():
            organism = row["organism"]
            if organism in labels:
                isolates = int(coverage.loc[coverage["organism"] == organism, "isolates"].sum())
                status = f"In this tool: {isolates:,} sequenced isolates"
            else:
                status = "Tracked by NCBI, not imported here"
            table.append({"Possible pathogen": ncbi_label(organism), "Status": status,
                          "Note": row["note"] if isinstance(row["note"], str) else "", "Source": row["source"]})
        ui.table(pd.DataFrame(table))

    # One block for the whole search, so diseases that share a word (such as both pneumonias) are not counted twice.
    terms = list(dict.fromkeys(t for _, rows in found["diseases"].groupby("disease", sort=False) for t in search.disease_terms(rows.iloc[0])))
    recorded = search.recorded_disease(terms, index)
    if len(recorded):
        st.markdown("#### Recorded in the data")
        lines = []
        for organism, part in recorded.groupby("organism"):
            fill = profile[organism]["search_fill"]["host_disease"]["pct_filled"]
            total = int(coverage.loc[coverage["organism"] == organism, "isolates"].sum())
            lines.append(f"- **{labels[organism]}:** {int(part['isolates'].sum()):,} of {total:,} isolates record a matching value "
                         f"(the field is filled for {fill:.1f}% of this organism's source rows)")
        st.markdown("The free-text `host_disease` field, where submitters filled it in, matching any of: "
                    f"{', '.join(terms)}.\n" + "\n".join(lines))
        with st.expander("Matching values"):
            shown = recorded.sort_values("isolates", ascending=False).head(30)
            ui.table(pd.DataFrame({"Organism": shown["organism"].map(labels), "Recorded value": shown["value"],
                                   "Isolates": shown["isolates"], "Countries": shown["countries"]}))
        st.caption("Submitters word this field freely and most leave it empty, so these counts are a floor, not how often the disease occurs. "
                   "A recorded value is what the submitter wrote, not a confirmed cause.")

if len(found["index"]):
    st.subheader("Names, serovars, strains and IDs")
    hits = found["index"]
    years = [f"{int(a)} to {int(b)}" if pd.notna(a) else "no usable years" for a, b in zip(hits["first_year"], hits["last_year"])]
    ui.table(pd.DataFrame({"Organism": hits["organism"].map(labels), "Field": hits["field"].map(search.INDEX_FIELDS),
                           "Value": hits["value"], "Isolates": hits["isolates"], "Countries": hits["countries"], "Years": years}))
    st.caption("Coverage only. Resistance rates are worked out per organism, not per serovar or strain. "
               "Strains are listed only where seen at least 5 times, as most are one-off lab IDs.")
    for organism in hits["organism"].unique():
        if organism not in found["organisms"]:
            card(organism, f"index_{organism}")

if found["tracked"]:
    st.subheader("Tracked by NCBI, not imported here")
    st.write(", ".join(ncbi_label(o) for o in found["tracked"]) + ". NCBI Pathogen Detection has data for these, but this tool has not imported it, so there are no figures for them here.")

if found["not_covered"]:
    st.info("No match. This tool covers six bacteria, and NCBI Pathogen Detection tracks bacteria and a few fungi, not viruses or parasites.")
    if found["suggestions"]:
        st.write("Did you mean:")
        for suggestion in found["suggestions"]:
            if st.button(suggestion, key=f"suggest_{suggestion}"):
                st.session_state["search_query"] = suggestion
                st.rerun()
