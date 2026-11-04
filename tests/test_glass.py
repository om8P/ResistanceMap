"""Hand-checked cases for src/glass.py, on a small file in the real download layout."""
import pandas as pd
import pytest

import glass as G

FILE = """Filters
Region filter: {region}
Infection type filter: Bloodstream
Bacterial pathogen filter: {pathogen}
Antibiotic filter: Imipenem

Data for time series
"Year","Specimen","PathogenName","AbTargets","Min","Q1","Median","Q3","Max"
2022,"BLOOD","{pathogen}","Imipenem",0,40.5,69.5,86.25,100


Data for line plots for individual CTAs
"Iso3","CountryTerritoryArea","WHORegionName","Year","Specimen","PathogenName","AbTargets","TotalSpecimenIsolates","InterpretableAST","Resistant","PercentResistant"
"ARG","Argentina","Region of the Americas",2022,"BLOOD","{pathogen}","Imipenem",7385,40,20,50
"BHR","Bahrain","Eastern Mediterranean Region",2022,"BLOOD","{pathogen}","Imipenem",633,29,10,34.48
"""
MAPPING = pd.DataFrame([{"glass_pathogen": "Acinetobacter spp.", "glass_antibiotic": "Imipenem", "organism": "Acinetobacter",
                         "our_table": "last_resort", "our_value": "CARBAPENEM", "match_note": None}])


def text(region="All", pathogen="Acinetobacter spp."):
    return FILE.format(region=region, pathogen=pathogen)


def test_parse_reads_filters_and_both_sections():
    filters, summary, country = G.parse_file(text())
    assert filters == {"region": "All", "pathogen": "Acinetobacter spp.", "antibiotic": "Imipenem"}
    assert summary["Median"].tolist() == [69.5]
    assert country["Iso3"].tolist() == ["ARG", "BHR"]


def test_wilson_matches_the_hand_value():
    low, high = G.wilson(5, 10)
    assert low == pytest.approx(0.2366, abs=1e-4)
    assert high == pytest.approx(0.7634, abs=1e-4)


def test_under_minimum_keeps_counts_and_leaves_the_rate_empty():
    countries, _ = G.build([text()], MAPPING, 30)
    rows = countries.set_index("iso3")
    assert rows.loc["ARG", "rate"] == pytest.approx(0.5)
    assert pd.isna(rows.loc["BHR", "rate"]) and pd.isna(rows.loc["BHR", "ci_low"])
    assert rows.loc["BHR", "tested"] == 29 and rows.loc["BHR", "resistant"] == 10


def test_unmapped_pairs_are_dropped():
    countries, regions = G.build([text(), text(pathogen="Escherichia coli")], MAPPING, 30)
    assert set(countries["pathogen"]) == {"Acinetobacter spp."}
    assert set(regions["pathogen"]) == {"Acinetobacter spp."}


def test_countries_come_only_from_the_all_regions_file():
    countries, regions = G.build([text(), text(region="Region of the Americas")], MAPPING, 30)
    assert len(countries) == 2
    assert set(regions["who_region"]) == {G.GLOBAL, "Region of the Americas"}


def test_a_file_with_no_country_rows_is_handled():
    empty = text().split(G.COUNTRY_TITLE)[0]
    countries, regions = G.build([text(), empty.replace("Region filter: All", "Region filter: African Region")], MAPPING, 30)
    assert len(countries) == 2 and len(regions) == 2
