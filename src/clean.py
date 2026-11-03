"""Build the isolates table: standard country and year, one row per isolate.

Rows with a missing location or year are kept and flagged. Counts go to
results/pipeline_summary.json.

Usage: spark-submit src/clean.py [--organism NAME]
"""
import argparse
import csv
import json
from pathlib import Path

from pyspark.sql import SparkSession, Window
from pyspark.sql import functions as F

from profile_data import add_date_labels, is_empty, is_placeholder, is_real

ROOT = Path(__file__).resolve().parent.parent
PARQUET = ROOT / "data" / "parquet"
ORGANISMS = ROOT / "config" / "organisms.csv"
COUNTRIES = ROOT / "config" / "countries.csv"
SUMMARY = ROOT / "results" / "pipeline_summary.json"
# Earlier dates are artefacts: 1900-01-01 defaults, and years read as Excel day counts (2021 becomes 1905-07-13).
EARLIEST_YEAR = 1910
TEXT_COLUMNS = ["host", "isolation_source", "epi_type"]


def read_organisms():
    with open(ORGANISMS, encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def read_countries(spark):
    with open(COUNTRIES, encoding="utf-8", newline="") as source:
        rows = [(row["raw_location"].lower(), row["country"], row["iso3"]) for row in csv.DictReader(source)]
    return spark.createDataFrame(rows, ["location_key", "country", "iso3"])


def add_location(frame, countries):
    """Standardise the text before the colon, and flag what cannot be placed."""
    raw = F.trim(F.split(F.regexp_replace("geo_loc_name", '"', ""), ":").getItem(0))
    joined = (frame.withColumn("raw_location", raw)
              .withColumn("location_key", F.lower(raw))
              .join(F.broadcast(countries), "location_key", "left")
              .drop("location_key"))
    flag = (F.when(is_empty("geo_loc_name"), "missing")
            .when(is_placeholder("geo_loc_name"), "placeholder")
            .when(F.col("country").isNull(), "unrecognised"))
    placed = F.col("location_flag").isNull()
    return (joined.withColumn("location_flag", flag)
            .withColumn("country", F.when(placed, F.col("country")))
            .withColumn("iso3", F.when(placed, F.col("iso3"))))


def add_year(frame, latest_year):
    """Add year, leaving it empty with a year_flag when no single valid year exists."""
    labelled = add_date_labels(frame)
    start = F.col("year").cast("int")
    created = F.regexp_extract("target_creation_date", r"^(\d{4})", 1).cast("int")
    flag = (F.when(~is_real("collection_date"), "missing")
            .when(F.col("date_format") == "range_multi_year", "multi_year_range")
            .when(F.col("date_format") == "other", "unparsed")
            .when((start < EARLIEST_YEAR) | (start > latest_year), "out_of_range")
            .when(created.isNotNull() & (start > created), "after_upload"))
    return (labelled.withColumn("year_flag", flag)
            .withColumn("year", F.when(F.col("year_flag").isNull(), start).cast("int"))
            .drop("date_format"))


def latest_upload_year(frame):
    created = F.regexp_extract("target_creation_date", r"^(\d{4})", 1)
    return frame.filter(created != "").agg(F.max(created.cast("int"))).first()[0]


def keep_one_per_isolate(frame):
    """Keep the newest record for each biosample, so repeat runs give the same row."""
    order = Window.partitionBy("biosample_acc").orderBy(
        F.col("target_creation_date").desc_nulls_last(), F.col("target_acc").desc_nulls_last())
    return frame.withColumn("_rank", F.row_number().over(order)).filter("_rank = 1").drop("_rank")


def duplicate_counts(frame):
    groups = (frame.groupBy("biosample_acc")
              .agg(F.count("*").alias("rows"),
                   F.size(F.collect_set(F.coalesce(F.col("AMR_genotypes_core"), F.lit("")))).alias("gene_lists"))
              .filter("rows > 1"))
    totals = groups.agg(F.count("*"), F.sum("rows"), F.sum(F.when(F.col("gene_lists") > 1, 1).otherwise(0))).first()
    return {
        "duplicate_groups": totals[0],
        "duplicate_rows_removed": (totals[1] or 0) - totals[0],
        "duplicate_groups_with_different_genes": totals[2] or 0,
    }


def attach_clusters(isolates, clusters):
    """Add cluster_id, preferring the row for the same target_acc, then the lowest PDS_acc."""
    candidates = (clusters.filter(F.col("biosample_acc").isNotNull())
                  .select("biosample_acc", F.col("target_acc").alias("cluster_target"), "PDS_acc")
                  .join(isolates.select("biosample_acc", "target_acc"), "biosample_acc"))
    same_target = F.when(F.col("cluster_target") == F.col("target_acc"), 0).otherwise(1)
    order = Window.partitionBy("biosample_acc").orderBy(same_target, F.col("PDS_acc"))
    best = (candidates.withColumn("_rank", F.row_number().over(order)).filter("_rank = 1")
            .select("biosample_acc", F.col("PDS_acc").alias("cluster_id")))
    return isolates.join(best, "biosample_acc", "left")


def clean_organism(frame, clusters, countries, latest_year):
    """Return the cleaned isolates and the counts behind them."""
    valid = frame.filter(F.col("biosample_acc").isNotNull())
    counts = {"rows_in": frame.count(), "rows_dropped_no_biosample": frame.count() - valid.count()}
    counts.update(duplicate_counts(valid))

    isolates = attach_clusters(add_year(add_location(keep_one_per_isolate(valid), countries), latest_year), clusters)
    for column in TEXT_COLUMNS:
        isolates = isolates.withColumn(column, F.when(is_real(column), F.regexp_replace(column, '"', "")))
    return isolates, counts


def flag_counts(isolates, column):
    return {str(row[column]): row["count"] for row in isolates.groupBy(column).count().collect()}


def update_summary(organism, section, values):
    summary = json.loads(SUMMARY.read_text()) if SUMMARY.exists() else {"organisms": {}}
    summary["organisms"].setdefault(organism, {})[section] = values
    SUMMARY.write_text(json.dumps(summary, indent=2, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organism", help="Clean one organism only")
    args = parser.parse_args()

    spark = SparkSession.builder.appName("clean").config("spark.sql.shuffle.partitions", "16").getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    countries = read_countries(spark)

    for row in read_organisms():
        organism = row["organism"]
        if args.organism and organism != args.organism:
            continue
        frame = spark.read.parquet(str(PARQUET / "amr" / organism))
        clusters = spark.read.parquet(str(PARQUET / "clusters" / organism))
        isolates, counts = clean_organism(frame, clusters, countries, latest_upload_year(frame))
        output = isolates.select(
            "biosample_acc", "target_acc", F.lit(row["label"]).alias("organism_label"), "country", "iso3",
            "raw_location", "location_flag", "year", "year_flag", "collection_date", *TEXT_COLUMNS, "cluster_id",
            "amrfinder_analysis_type", "AMR_genotypes_core")
        path = PARQUET / "isolates" / f"organism={organism}"
        output.write.mode("overwrite").parquet(str(path))

        written = spark.read.parquet(str(path)).cache()
        unrecognised = (written.filter(F.col("location_flag") == "unrecognised").groupBy("raw_location").count()
                        .orderBy(F.desc("count"), "raw_location").limit(30).collect())
        counts.update(
            isolates_kept=written.count(),
            location_flags=flag_counts(written, "location_flag"),
            unrecognised_locations={r["raw_location"]: r["count"] for r in unrecognised},
            year_flags=flag_counts(written, "year_flag"),
            isolates_in_cluster=written.filter(F.col("cluster_id").isNotNull()).count(),
            isolates_with_no_core_genes=written.filter(F.col("AMR_genotypes_core").isNull()).count(),
        )
        update_summary(organism, "clean", counts)
        written.unpersist()
        print(f"cleaned {organism}: {counts['rows_in']} rows in, {counts['isolates_kept']} kept", flush=True)
    spark.stop()


if __name__ == "__main__":
    main()
