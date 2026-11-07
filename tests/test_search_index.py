"""Hand-checked cases for src/search_index.py. Needs Spark, so it runs in the container."""
import pytest

pytest.importorskip("pyspark")
from pyspark.sql.types import IntegerType, StringType, StructField, StructType  # noqa: E402

import search_index as S  # noqa: E402

RAW_COLUMNS = ["biosample_acc", "target_acc", *S.FIELDS]


def raw_table(spark, rows):
    schema = StructType([StructField(c, StringType()) for c in RAW_COLUMNS])
    return spark.createDataFrame(rows, schema)


def isolate_table(spark, rows):
    schema = StructType([StructField("biosample_acc", StringType()), StructField("target_acc", StringType()),
                         StructField("country", StringType()), StructField("year", IntegerType())])
    return spark.createDataFrame(rows, schema)


@pytest.fixture
def tables(spark):
    raw = raw_table(spark, [
        ("S1", "T1", "Salmonella enterica", "Typhimurium", "LT2", "gastroenteritis", "90371", "28901"),
        ("S2", "T2", "Salmonella enterica", '"Typhimurium"', "LT2", "missing", "90371", "28901"),
        ("S3", "T3", "Salmonella enterica", "typhimurium ", "X1", None, "90371", "28901"),
        ("S4", "T4", "Salmonella enterica", "Enteritidis", "LT2", "Gastroenteritis", "149539", "28901"),
        ("S5", "T5", "Salmonella enterica", "Typhimurium", "LT2", None, "90371", "28901"),
        ("S1", "T9", "Salmonella enterica", "Dropped", "LT2", None, "1", "28901"),
    ])
    isolates = isolate_table(spark, [("S1", "T1", "USA", 2019), ("S2", "T2", "India", 2021),
                                     ("S3", "T3", "USA", 2020), ("S4", "T4", None, None)])
    return raw, isolates


def rows(frame):
    return {(r["field"], r["key"]): r.asDict() for r in frame.collect()}


def test_counts_only_kept_isolates_and_merges_spellings(tables):
    found = rows(S.index_rows(*tables, "Salmonella", True, 3))
    typhimurium = found[("serovar", "typhimurium")]
    assert typhimurium["isolates"] == 3 and typhimurium["countries"] == 2
    assert (typhimurium["first_year"], typhimurium["last_year"]) == (2019, 2021)
    assert ("serovar", "dropped") not in found and ("taxid", "1") not in found


def test_placeholders_are_left_out_and_case_is_merged(tables):
    found = rows(S.index_rows(*tables, "Salmonella", True, 3))
    assert found[("host_disease", "gastroenteritis")]["isolates"] == 2
    assert ("host_disease", "missing") not in found


def test_strain_gate(tables):
    found = rows(S.index_rows(*tables, "Salmonella", True, 3))
    assert found[("strain", "lt2")]["isolates"] == 3 and ("strain", "x1") not in found
    closed = rows(S.index_rows(*tables, "Salmonella", False, 3))
    assert not any(field == "strain" for field, _ in closed)
