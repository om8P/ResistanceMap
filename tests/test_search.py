"""Hand-checked cases for pathogen and disease search. Runs on the host, with no Spark."""
import sys
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("streamlit")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
from lib import search  # noqa: E402

from download import parse_listing  # noqa: E402

LABELS = {"Klebsiella": "Klebsiella", "Salmonella": "Salmonella", "Staphylococcus_aureus": "Staph aureus"}
NCBI = pd.DataFrame({"organism": ["Klebsiella", "Klebsiella_oxytoca", "Salmonella", "Staphylococcus_aureus",
                                  "Haemophilus_influenzae", "Vibrio_cholerae"]})
DISEASES = pd.DataFrame([
    ("Typhoid fever", "typhoid;enteric fever", "Salmonella", "", "WHO"),
    ("Salmonellosis", "non-typhoidal salmonella", "Salmonella", "", "WHO"),
    ("Hospital pneumonia", "pneumonia", "Klebsiella", "", "CDC"),
    ("Hospital pneumonia", "pneumonia", "Staphylococcus_aureus", "", "CDC"),
    ("Cholera", None, "Vibrio_cholerae", "", "WHO"),
    ("Influenza", "flu", None, "Caused by a virus", "WHO"),
], columns=["disease", "synonyms", "organism", "note", "source"])


def index_row(organism, field, value, isolates, countries=1, first=2010, last=2020):
    return {"organism": organism, "field": field, "value": value, "key": value.lower(), "isolates": isolates,
            "countries": countries, "first_year": first, "last_year": last}


INDEX = pd.DataFrame([
    index_row("Salmonella", "serovar", "Typhimurium", 500, 40),
    index_row("Salmonella", "serovar", "Typhi", 300, 30),
    index_row("Salmonella", "scientific_name", "Salmonella enterica", 900, 50),
    index_row("Klebsiella", "scientific_name", "Klebsiella pneumoniae", 800, 60),
    index_row("Klebsiella", "taxid", "573", 800, 60),
    index_row("Klebsiella", "strain", "ST258", 12),
    index_row("Salmonella", "host_disease", "Typhoid fever", 40),
    index_row("Salmonella", "host_disease", "Enteric Fever", 10),
    index_row("Salmonella", "host_disease", "non-typhoidal salmonellosis", 7),
    index_row("Klebsiella", "host_disease", "Pneumonia", 25),
    index_row("Klebsiella", "host_disease", "Bloodstream Infection", 30),
])


def run(query):
    return search.search(query, LABELS, NCBI, DISEASES, INDEX)


def test_organism_by_name_and_prefix():
    assert run("Klebsiella")["organisms"] == ["Klebsiella"]
    found = run("klebs")
    assert found["organisms"] == ["Klebsiella"] and found["tracked"] == ["Klebsiella_oxytoca"]


def test_species_name_finds_its_organism_and_index_rows():
    found = run("Klebsiella pneumoniae")
    assert found["organisms"] == ["Klebsiella"]
    assert list(found["index"]["value"]) == ["Klebsiella pneumoniae"]


def test_serovar_exact_match_first():
    hits = run("Typhimurium")["index"]
    assert hits.iloc[0]["value"] == "Typhimurium" and hits.iloc[0]["isolates"] == 500
    assert "Typhi" not in set(hits["value"])


def test_taxid_and_strain_match_exactly():
    assert list(run("573")["index"]["field"]) == ["taxid"]
    assert list(run("st258")["index"]["value"]) == ["ST258"]
    assert not len(run("57")["index"])


def test_disease_by_synonym_lists_every_pathogen():
    rows = run("pneumonia")["diseases"]
    assert set(rows["organism"]) == {"Klebsiella", "Staphylococcus_aureus"}


def test_disease_needs_whole_words():
    assert list(run("typhoid")["diseases"]["disease"].unique()) == ["Typhoid fever"]


def test_virus_is_named_as_not_covered_and_bacterium_name_is_kept_apart():
    found = run("influenza")
    assert list(found["diseases"]["disease"]) == ["Influenza"] and found["diseases"]["organism"].isna().all()
    assert found["tracked"] == ["Haemophilus_influenzae"]
    assert not found["not_covered"]


def test_tracked_but_not_imported():
    found = run("cholera")
    assert found["tracked"] == ["Vibrio_cholerae"] and found["organisms"] == []


def test_misspelling_gets_a_suggestion():
    found = run("klebsiela")
    assert found["not_covered"] and found["suggestions"][0] == "Klebsiella"


def test_unknown_query_is_not_covered():
    found = run("zzqqx")
    assert found["not_covered"] and found["suggestions"] == []


def test_recorded_disease_counts_whole_word_values():
    terms = search.disease_terms(DISEASES.iloc[0])
    rows = search.recorded_disease(terms, INDEX)
    assert set(rows["value"]) == {"Typhoid fever", "Enteric Fever"} and rows["isolates"].sum() == 50


def test_organism_card_counts():
    coverage = pd.DataFrame({"organism": ["Klebsiella"] * 4, "country": ["India", "India", "Peru", None],
                             "year": [2019, 2020, 2020, 2020], "isolates": [40, 10, 31, 5]})
    summary = {"organisms": {"Klebsiella": {"genes": {"catalog_match_pct": 99.9, "gene_rows": 1000}}}}
    card = search.organism_card("Klebsiella", coverage, summary, 30)
    assert card == {"isolates": 86, "countries": 2, "first_year": 2019, "last_year": 2020, "groups": 3,
                    "groups_at_minimum": 2, "catalog_match_pct": 99.9, "gene_rows": 1000}


def test_ncbi_listing_is_parsed():
    listing = '<a href="../">..</a><a href="Klebsiella/">Klebsiella/</a><a href="BioProject_Hierarchy/">x</a>' \
              '<a href="Vibrio_cholerae/">x</a><a href="README.txt">x</a>'
    assert parse_listing(listing) == ["Klebsiella", "Vibrio_cholerae"]


def test_disease_list_names_only_known_organisms():
    diseases = pd.read_csv(ROOT / "config" / "disease_pathogens.csv")
    ncbi = set(pd.read_csv(ROOT / "config" / "ncbi_organisms.csv")["organism"])
    assert set(diseases["organism"].dropna()) <= ncbi
    assert diseases["source"].notna().all()
