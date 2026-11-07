"""ResistanceMap. Reads prepared files in results/, so it works with Docker stopped."""
import streamlit as st

from lib import data
from lib.rules import NOTICE

st.set_page_config(page_title="ResistanceMap", layout="wide")

imported = data.imported_datasets()
if imported:
    options = [data.CORE, *imported]
    labels = {data.CORE: "Six core organisms", **{k: f"Imported: {v}" for k, v in imported.items()}}
    st.sidebar.selectbox("Dataset", options, format_func=labels.get, key=data.DATASET_KEY)

if data.is_imported():
    # Pages built around fixed core examples (Klebsiella in India, GLASS, guided questions) are left out.
    pages = {
        "Explore": [
            st.Page("pages/map_trends.py", title="Map and trends", default=True),
            st.Page("pages/early_warnings.py", title="Early warnings"),
            st.Page("pages/gene_profile.py", title="Gene profile"),
        ],
        "Reference": [st.Page("pages/about.py", title="About the data")],
    }
    st.sidebar.info("Imported pathogen: only the general pages are shown. Switch the dataset back for search and the other pages.")
else:
    pages = {
        "Explore": [
            st.Page("pages/map_trends.py", title="Map and trends", default=True),
            st.Page("pages/search.py", title="Search"),
            st.Page("pages/early_warnings.py", title="Early warnings"),
            st.Page("pages/last_resort.py", title="Last-resort drugs"),
            st.Page("pages/gene_profile.py", title="Gene profile"),
            st.Page("pages/cluster_watch.py", title="Cluster watch"),
        ],
        "Countries": [
            st.Page("pages/country_report.py", title="Country report"),
            st.Page("pages/compare.py", title="Compare countries"),
        ],
        "Answers": [
            st.Page("pages/guided.py", title="Guided questions"),
            st.Page("pages/evidence.py", title="Evidence panel"),
        ],
        "Reference": [st.Page("pages/about.py", title="About the data")],
    }
page = st.navigation(pages)
st.sidebar.caption(NOTICE)
page.run()
