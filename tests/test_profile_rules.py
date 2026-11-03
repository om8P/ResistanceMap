"""Hand-checked cases for the rules in src/profile_data.py."""
import pytest
from pyspark.sql import functions as F
from pyspark.sql.types import StringType, StructField, StructType

import profile_data as P


def table(spark, **columns):
    """Build a string table from equal-length column lists, allowing None."""
    names = list(columns)
    schema = StructType([StructField(name, StringType()) for name in names])
    return spark.createDataFrame(list(zip(*columns.values())), schema)


@pytest.mark.parametrize("value", ["missing", "missing: third party data", "not collected", "Not Provided",
                                   "restricted access", "not available: not collected", '"NULL"', "NONE"])
def test_placeholders_are_not_real(spark, value):
    row = table(spark, c=[value]).select(P.is_placeholder("c").alias("p"), P.is_real("c").alias("r")).first()
    assert row["p"] is True and row["r"] is False


@pytest.mark.parametrize("value", [None, "", "  ", '""'])
def test_empty_is_neither_real_nor_placeholder(spark, value):
    row = table(spark, c=[value]).select(P.is_empty("c").alias("e"), P.is_placeholder("c").alias("p"),
                                         P.is_real("c").alias("r")).first()
    assert row["e"] is True and row["p"] is False and row["r"] is False


@pytest.mark.parametrize("value", ["USA", "India: Delhi", '"ampC=HMM"', "2015", "Homo sapiens", "missing person ward"])
def test_real_values_are_kept(spark, value):
    assert table(spark, c=[value]).select(P.is_real("c").alias("r")).first()["r"] is True


@pytest.mark.parametrize("value, expected, year", [
    ("2013", "YYYY", "2013"),
    ("2013-05", "YYYY-MM", "2013"),
    ("2013-05-09", "YYYY-MM-DD", "2013"),
    ("2019-09-26T10:00:04Z", "timestamp", "2019"),
    ("2021-05-01/2021-09-30", "range_same_year", "2021"),
    ("2015/2018", "range_multi_year", "2015"),
    ("May 2015", "other", ""),
])
def test_date_labels(spark, value, expected, year):
    row = P.label_dates(table(spark, collection_date=[value])).first()
    assert (row["date_format"], row["year"]) == (expected, year)


def test_yearly_counts_keep_timestamps_and_drop_multi_year_ranges(spark):
    frame = table(spark, collection_date=["2019", "2019-09-26T10:00:04Z", "2015/2018", "2021-05-01/2021-09-30",
                                          "May 2015", "missing", None])
    result = P.date_profile(frame)
    assert result["isolates_per_year"] == {"2019": 2, "2021": 1}
    assert result["formats"] == {"YYYY": 1, "timestamp": 1, "range_multi_year": 1, "range_same_year": 1, "other": 1}


def test_countries_exclude_placeholders_and_group_regions(spark):
    frame = table(spark, geo_loc_name=["India: Delhi", "India", "USA", "missing: third party data", "not collected",
                                       None])
    result = P.country_profile(frame, 6)
    assert result["top"] == {"India": 2, "USA": 1}
    assert result["india_count"] == 2
    assert result["india_pct_of_rows"] == 33.33


def test_gene_audit_counts_isolates_with_no_core_genes(spark):
    frame = table(spark,
                  AMR_genotypes_core=['"blaTEM-1,sul1"', '"ampC=HMM"', None, "NULL", '""'],
                  AMR_genotypes=['"blaTEM-1,sul1,mdsA"', '"ampC=HMM"', '"mdsA,mdsB"', None, '""'])
    result = P.gene_audit(frame, 5)
    assert result["core_no_genes"] == 3
    assert result["core_no_genes_pct"] == 60.0
    assert result["core_no_genes_but_any_genes"] == 1
    assert result["any_no_genes"] == 2
    assert result["core_gene_count_first_10"] == {1: 1, 2: 1}


def test_analysis_coverage_separates_no_genes_from_not_analysed(spark):
    frame = table(spark,
                  AMR_genotypes_core=['"sul1"', None, None, None],
                  number_core_amr_genes=["1", "0", "2", "0"],
                  amrfinder_version=["4.0", "4.0", "4.0", None],
                  amrfinder_applied=["1", "1", "1", None],
                  amrfinder_analysis_type=["COMBINED", "COMBINED", "NUCLEOTIDE", "NUCLEOTIDE"])
    result = P.analysis_coverage(frame)
    assert result["not_analysed_rows"] == 1
    assert result["no_core_but_gene_count_above_zero"] == 1
    assert result["by_analysis_type"]["COMBINED"] == {"rows": 2, "pct_no_core_genes": 50.0}
    assert result["by_analysis_type"]["NUCLEOTIDE"] == {"rows": 2, "pct_no_core_genes": 100.0}


def test_upload_delay_finds_provisional_years(spark):
    # Latest upload is 2026, so the measured cohort is collection years 2016 to 2021.
    # Of the 10 cohort rows: 2 at lag 0, 7 at lag 1, 1 at lag 3, so 90% is reached at lag 1.
    collected = ["2018"] * 2 + ["2018"] * 7 + ["2018"] + ["2026", "2010", "2020"]
    created = ["2018-03-01"] * 2 + ["2019-03-01"] * 7 + ["2021-03-01"] + ["2026-01-01", "2024-01-01", "2019-01-01"]
    result = P.upload_delay(table(spark, collection_date=collected, target_creation_date=created))
    assert result["latest_upload_year"] == 2026
    assert result["cohort_collection_years"] == [2016, 2021]
    assert result["cohort_rows"] == 10
    assert result["cumulative_pct_by_lag_years"][0] == 20.0
    assert result["cumulative_pct_by_lag_years"][1] == 90.0
    assert result["years_to_complete"] == 1
    assert result["provisional_from_year"] == 2026
    assert result["rows_created_before_collected"] == 1


def test_upload_delay_reports_none_when_target_not_reached(spark):
    collected = ["2018"] * 2 + ["2026"]
    created = ["2025-01-01"] * 2 + ["2026-01-01"]
    result = P.upload_delay(table(spark, collection_date=collected, target_creation_date=created))
    assert result["years_to_complete"] is None
    assert result["provisional_from_year"] is None
