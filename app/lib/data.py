"""Cached readers for results/ and config/. The app reads nothing else, so it runs with Docker stopped."""
import json

import pandas as pd
import streamlit as st

from lib.rules import ROOT, table_name

RESULTS = ROOT / "results"
CONFIG = ROOT / "config"

LAST_RESORT_MEASURES = [("last_resort", "CARBAPENEM", "acquired"), ("last_resort", "CARBAPENEM", "any_excl_intrinsic"),
                        ("last_resort", "COLISTIN", "acquired"), ("last_resort", "COLISTIN", "any_excl_intrinsic"),
                        ("last_resort", "CARBAPENEM+COLISTIN", "acquired"), ("last_resort", "CARBAPENEM+COLISTIN", "any_excl_intrinsic")]
DRUG_LABEL = {"CARBAPENEM": "Carbapenem", "COLISTIN": "Colistin", "CARBAPENEM+COLISTIN": "Carbapenem and colistin in one isolate"}
MECHANISM_LABEL = {"acquired": "acquired genes", "any_excl_intrinsic": "any mechanism except intrinsic", "mutation": "point mutations",
                   "disrupted": "disrupted genes", "intrinsic": "intrinsic genes"}


@st.cache_data(max_entries=128, show_spinner=False)
def _read(name, filters):
    pushed = [(k, "in", list(v)) if isinstance(v, tuple) else (k, "==", v) for k, v in filters] or None
    return pd.read_parquet(RESULTS / f"{name}.parquet", filters=pushed)


def load(name, **filters):
    """Read a result table, with equality or `in` filters pushed down to Parquet."""
    clean = tuple(sorted((k, tuple(v) if isinstance(v, (list, tuple, set)) else v) for k, v in filters.items() if v is not None))
    return _read(name, clean)


@st.cache_data(show_spinner=False)
def load_json(name):
    return json.loads((RESULTS / f"{name}.json").read_text())


@st.cache_data(show_spinner=False)
def organisms():
    """Organism id to display label, in name order."""
    frame = pd.read_csv(CONFIG / "organisms.csv").sort_values("label")
    return dict(zip(frame["organism"], frame["label"]))


def coverage(**filters):
    """Coverage rows with a known country and year. Isolates missing either stay only in overall totals."""
    frame = load("coverage", **filters)
    frame = frame[frame["country"].notna() & frame["year"].notna()].copy()
    frame["year"] = frame["year"].astype(int)
    frame["provisional"] = frame["provisional"].astype(bool)
    return frame


@st.cache_data(show_spinner=False)
def countries():
    return sorted(coverage()["country"].unique())


@st.cache_data(show_spinner=False)
def latest_data_year():
    return int(coverage()["year"].max())


@st.cache_data(show_spinner=False)
def provisional_start():
    frame = coverage()
    return int(frame.loc[frame["provisional"], "year"].min())


@st.cache_data(show_spinner=False)
def drug_classes():
    """Classes from prevalence. Colistin is left out here because the last-resort measures cover it."""
    frame = pd.read_parquet(RESULTS / "prevalence.parquet", columns=["drug_class"])
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


@st.cache_data(show_spinner=False)
def field_fill():
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
    return pd.read_parquet(RESULTS / "search_index.parquet")
