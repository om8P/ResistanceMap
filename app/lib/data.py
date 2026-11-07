"""Cached readers for results/ and config/. The app reads nothing else, so it runs with Docker stopped.

The dataset is the six core organisms (results/) or one imported pathogen (results/imported/<organism>/),
chosen in the sidebar. Cached readers take the results folder as an argument, so switching never mixes them."""
import json
from pathlib import Path

import pandas as pd
import streamlit as st

from lib.rules import ROOT, table_name

RESULTS = ROOT / "results"
IMPORTED_RESULTS = RESULTS / "imported"
CONFIG = ROOT / "config"
CORE = "core"
DATASET_KEY = "dataset"

LAST_RESORT_MEASURES = [("last_resort", "CARBAPENEM", "acquired"), ("last_resort", "CARBAPENEM", "any_excl_intrinsic"),
                        ("last_resort", "COLISTIN", "acquired"), ("last_resort", "COLISTIN", "any_excl_intrinsic"),
                        ("last_resort", "CARBAPENEM+COLISTIN", "acquired"), ("last_resort", "CARBAPENEM+COLISTIN", "any_excl_intrinsic")]
DRUG_LABEL = {"CARBAPENEM": "Carbapenem", "COLISTIN": "Colistin", "CARBAPENEM+COLISTIN": "Carbapenem and colistin in one isolate"}
MECHANISM_LABEL = {"acquired": "acquired genes", "any_excl_intrinsic": "any mechanism except intrinsic", "mutation": "point mutations",
                   "disrupted": "disrupted genes", "intrinsic": "intrinsic genes"}


def import_status(organism):
    path = IMPORTED_RESULTS / organism / "status.json"
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def imported_rows():
    path = CONFIG / "imported.csv"
    return pd.read_csv(path, dtype=str, keep_default_na=False) if path.exists() else pd.DataFrame(columns=["organism", "label", "taxon"])


def imported_datasets():
    """Imported pathogens whose import finished, as id to label."""
    rows = imported_rows()
    return {r.organism: r.label for r in rows.itertuples() if (import_status(r.organism) or {}).get("state") == "done"}


def dataset():
    chosen = st.session_state.get(DATASET_KEY, CORE)
    return chosen if chosen == CORE or chosen in imported_datasets() else CORE


def is_imported():
    return dataset() != CORE


def results_root():
    return str(RESULTS if dataset() == CORE else IMPORTED_RESULTS / dataset())


@st.cache_data(max_entries=128, show_spinner=False)
def _read(root, name, filters):
    pushed = [(k, "in", list(v)) if isinstance(v, tuple) else (k, "==", v) for k, v in filters] or None
    return pd.read_parquet(Path(root) / f"{name}.parquet", filters=pushed)


def load(name, **filters):
    """Read a result table of the chosen dataset, with equality or `in` filters pushed down to Parquet."""
    clean = tuple(sorted((k, tuple(v) if isinstance(v, (list, tuple, set)) else v) for k, v in filters.items() if v is not None))
    return _read(results_root(), name, clean)


@st.cache_data(show_spinner=False)
def _load_json(root, name):
    return json.loads((Path(root) / f"{name}.json").read_text())


def load_json(name):
    return _load_json(results_root(), name)


def has_result(name):
    return (Path(results_root()) / name).exists()


@st.cache_data(show_spinner=False)
def _organisms(chosen):
    frame = pd.read_csv(CONFIG / "organisms.csv") if chosen == CORE else imported_rows().query("organism == @chosen")
    frame = frame.sort_values("label")
    return dict(zip(frame["organism"], frame["label"]))


def organisms():
    """Organism id to display label, in name order, for the chosen dataset."""
    return _organisms(dataset())


def core_organisms():
    return _organisms(CORE)


def coverage(**filters):
    """Coverage rows with a known country and year. Isolates missing either stay only in overall totals."""
    frame = load("coverage", **filters)
    frame = frame[frame["country"].notna() & frame["year"].notna()].copy()
    frame["year"] = frame["year"].astype(int)
    frame["provisional"] = frame["provisional"].astype(bool)
    return frame


def countries():
    return _countries(results_root())


@st.cache_data(show_spinner=False)
def _countries(root):
    return sorted(coverage()["country"].unique())


def latest_data_year():
    return _latest_data_year(results_root())


@st.cache_data(show_spinner=False)
def _latest_data_year(root):
    return int(coverage()["year"].max())


def provisional_start():
    return _provisional_start(results_root())


@st.cache_data(show_spinner=False)
def _provisional_start(root):
    frame = coverage()
    years = frame.loc[frame["provisional"], "year"]
    return int(years.min()) if len(years) else int(frame["year"].max()) + 1


def drug_classes():
    return _drug_classes(results_root())


@st.cache_data(show_spinner=False)
def _drug_classes(root):
    """Classes from prevalence. Colistin is left out here because the last-resort measures cover it."""
    frame = pd.read_parquet(Path(root) / "prevalence.parquet", columns=["drug_class"])
    return sorted(set(frame["drug_class"]) - {"COLISTIN"})


def measure_label(measure):
    table, value, mechanism = measure
    if table == "last_resort":
        return f"{DRUG_LABEL[value]}: {MECHANISM_LABEL[mechanism]}"
    return value.replace("_", " ").capitalize()


def measures():
    return LAST_RESORT_MEASURES + [("prevalence", value, None) for value in drug_classes()]


def rate_rows(measure, adjusted=False, source="all", pooled=False, **filters):
    """Rows for one resistance measure, from `prevalence` or `last_resort`, in the chosen view."""
    table, value, mechanism = measure
    if source != "all":
        filters["epi_type"] = source
    if table == "last_resort":
        filters.update(drug=value, mechanism=mechanism)
    else:
        filters["drug_class"] = value
    return load(table_name(table, adjusted, source, pooled), **filters)


def rising_row(measure, organism, country, adjusted=False, source="all"):
    """The `rising` row for one measure as a dict, or None when there is no row."""
    table, value, mechanism = measure
    kind, key = ("last_resort", f"{value}:{mechanism}") if table == "last_resort" else ("drug_class", value)
    filters = {"organism": organism, "country": country, "kind": kind, "value": key}
    if source != "all":
        filters["epi_type"] = source
    frame = load(table_name("rising", adjusted, source), **filters)
    return frame.iloc[0].to_dict() if len(frame) else None


def latest_inputs(measure, organism, country, adjusted=False, source="all"):
    """Yearly and pooled rows for `rules.latest_figure`. Source views have no pooled rows."""
    yearly = rate_rows(measure, adjusted, source, organism=organism, country=country)
    pooled = None if source != "all" else rate_rows(measure, adjusted, pooled=True, organism=organism, country=country)
    return yearly, pooled


def field_fill():
    return _field_fill(results_root())


@st.cache_data(show_spinner=False)
def _field_fill(root):
    """Share filled for each source field, weighted by rows across organisms."""
    profile = load_json("data_profile")["organisms"]
    totals, rows = {}, 0
    for item in profile.values():
        rows += item["rows"]
        for field, values in item["fill"].items():
            totals[field] = totals.get(field, 0) + values["pct_filled"] * item["rows"]
    return {field: value / rows for field, value in totals.items()}


@st.cache_data(show_spinner=False)
def ncbi_organisms():
    """Organism groups NCBI Pathogen Detection tracks (config/ncbi_organisms.csv)."""
    return pd.read_csv(CONFIG / "ncbi_organisms.csv")


@st.cache_data(show_spinner=False)
def disease_list():
    """Hand-checked disease to possible pathogen rows (config/disease_pathogens.csv)."""
    return pd.read_csv(CONFIG / "disease_pathogens.csv")


@st.cache_data(show_spinner=False)
def search_index():
    """The core search index. Search covers the core dataset; imported pathogens are listed by name."""
    return pd.read_parquet(RESULTS / "search_index.parquet")
