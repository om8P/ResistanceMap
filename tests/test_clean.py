"""Hand-checked cases for src/clean.py."""
import pytest
from pyspark.sql.types import StringType, StructField, StructType

import clean as C


def table(spark, **columns):
    names = list(columns)
    schema = StructType([StructField(name, StringType()) for name in names])
    return spark.createDataFrame(list(zip(*columns.values())), schema)


@pytest.fixture
def countries(spark):
    return C.read_countries(spark)


@pytest.mark.parametrize("raw, country, iso3", [
    ("USA: Western Region", "USA", "USA"),
    ("India", "India", "IND"),
    ("Berlgium", "Belgium", "BEL"),
    ("Czech republic", "Czechia", "CZE"),
    ("England, Devon", "United Kingdom", "GBR"),
    ("Perú: Lima", "Peru", "PER"),
    ("Taiwan", "Taiwan", "TWN"),
    ("China: Hong Kong", "China", "CHN"),
])
def test_countries_are_standardised(spark, countries, raw, country, iso3):
    row = C.add_location(table(spark, geo_loc_name=[raw]), countries).first()
    assert (row["country"], row["iso3"], row["location_flag"]) == (country, iso3, None)


@pytest.mark.parametrize("raw, flag", [
    (None, "missing"),
    ("", "missing"),
    ("not collected", "placeholder"),
    ("missing: third party data", "placeholder"),
    ("Germany/Libya", "unrecognised"),
    ("Baltic Sea", "unrecognised"),
    ("USSR", "unrecognised"),
    ("Korea", "unrecognised"),
    ("OUTPATIENT", "unrecognised"),
])
def test_unplaceable_locations_are_flagged_and_kept(spark, countries, raw, flag):
    rows = C.add_location(table(spark, geo_loc_name=[raw]), countries).collect()
    assert len(rows) == 1
    assert (rows[0]["country"], rows[0]["location_flag"]) == (None, flag)


@pytest.mark.parametrize("date, created, year, flag", [
    ("2013", "2014-01-01", 2013, None),
    ("2013-05", "2014-01-01", 2013, None),
    ("2013-05-09", "2014-01-01", 2013, None),
    ("2019-09-26T10:00:04Z", "2020-01-01", 2019, None),
    ("2021-05-01/2021-09-30", "2022-01-01", 2021, None),
    ("2015/2018", "2020-01-01", None, "multi_year_range"),
    ("May 2015", "2020-01-01", None, "unparsed"),
    ("missing", "2020-01-01", None, "missing"),
    (None, "2020-01-01", None, "missing"),
    ("1018", "2020-01-01", None, "out_of_range"),
    ("1900-01-01", "2020-01-01", None, "out_of_range"),
    ("1905-07-13", "2020-01-01", None, "out_of_range"),
    ("1917", "2020-01-01", 1917, None),
    ("2919", "2020-01-01", None, "out_of_range"),
    ("2022", "2020-01-01", None, "after_upload"),
    ("2013", None, 2013, None),
])
def test_year_rules(spark, date, created, year, flag):
    frame = table(spark, collection_date=[date], target_creation_date=[created])
    row = C.add_year(frame, 2026).first()
    assert (row["year"], row["year_flag"]) == (year, flag)


def test_one_row_per_isolate_keeps_newest_whatever_the_input_order(spark):
    records = [("S1", "PDT1", "2020-01-01"), ("S1", "PDT3", "2021-01-01"), ("S1", "PDT2", "2021-01-01"),
               ("S2", "PDT4", None)]
    for ordered in (records, list(reversed(records))):
        frame = spark.createDataFrame(ordered, ["biosample_acc", "target_acc", "target_creation_date"])
        rows = {r["biosample_acc"]: r["target_acc"] for r in C.keep_one_per_isolate(frame).collect()}
        assert rows == {"S1": "PDT3", "S2": "PDT4"}


def test_duplicate_counts_report_groups_that_differ(spark):
    frame = table(spark, biosample_acc=["S1", "S1", "S1", "S2", "S2", "S3"],
                  AMR_genotypes_core=['"a"', '"b"', '"a"', '"c"', '"c"', None])
    assert C.duplicate_counts(frame) == {"duplicate_groups": 2, "duplicate_rows_removed": 3,
                                         "duplicate_groups_with_different_genes": 1}


def test_cluster_prefers_same_target_then_lowest_id(spark):
    isolates = table(spark, biosample_acc=["S1", "S2", "S3"], target_acc=["T1", "T2", "T3"])
    clusters = table(spark, biosample_acc=["S1", "S1", "S2", "S2", None],
                     target_acc=["T9", "T1", "T8", "T7", "T3"],
                     PDS_acc=["PDS1", "PDS2", "PDS5", "PDS4", "PDS9"])
    rows = {r["biosample_acc"]: r["cluster_id"] for r in C.attach_clusters(isolates, clusters).collect()}
    assert rows == {"S1": "PDS2", "S2": "PDS4", "S3": None}


def test_clean_keeps_zero_gene_isolates_and_drops_only_missing_ids(spark, countries):
    frame = table(spark, biosample_acc=["S1", "S2", "S2", None],
                  target_acc=["T1", "T2", "T3", "T4"],
                  geo_loc_name=["India", "USA", "USA", "USA"],
                  collection_date=["2020", "2021", "2021", "2021"],
                  target_creation_date=["2021-01-01", "2022-01-01", "2023-01-01", "2023-01-01"],
                  host=["Homo sapiens", "missing", "missing", None],
                  isolation_source=[None] * 4, epi_type=[None] * 4,
                  AMR_genotypes_core=[None, '"sul1"', '"sul1"', '"sul1"'])
    clusters = table(spark, biosample_acc=["S1"], target_acc=["T1"], PDS_acc=["PDS1"])
    isolates, counts = C.clean_organism(frame, clusters, countries, 2026)
    rows = {r["biosample_acc"]: r for r in isolates.collect()}
    assert set(rows) == {"S1", "S2"}
    assert rows["S1"]["AMR_genotypes_core"] is None
    assert rows["S1"]["host"] == "Homo sapiens" and rows["S2"]["host"] is None
    assert rows["S2"]["target_acc"] == "T3"
    assert rows["S1"]["cluster_id"] == "PDS1"
    assert counts["rows_in"] == 4
    assert counts["rows_dropped_no_biosample"] == 1
    assert counts["duplicate_rows_removed"] == 1
