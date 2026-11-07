"""Build results/search_index.parquet for pathogen search.

One row per organism, search field and value: how many kept isolates carry the
value, in how many countries, and over which years. Only isolates kept by
clean.py count, joined back to the raw rows for the fields clean.py drops.

Strain is indexed only for organisms whose strain field is filled well enough
(results/data_profile.json, search_fill), and only for values seen often enough.

Usage: spark-submit src/search_index.py [--organism NAME]
"""
import argparse
import json

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

from analytics import load_settings, output_dir, write_table
from datasets import read_organisms
from profile_data import PARQUET, PROFILE, SEARCH_COLUMNS, is_real

FIELDS = ["scientific_name", "serovar", "strain", "host_disease", "taxid", "species_taxid"]
assert set(FIELDS) <= set(SEARCH_COLUMNS)


def search_settings(settings):
    search = settings["search"]
    return search["strain_min_fill_pct"], search["strain_min_isolates"]


def index_rows(raw, isolates, organism, strain_allowed, strain_min_isolates):
    """Index rows for one organism. `raw` has the search fields; `isolates` has the kept rows."""
    kept = isolates.select("biosample_acc", "target_acc", "country", "year")
    joined = raw.select("biosample_acc", "target_acc", *FIELDS).join(kept, ["biosample_acc", "target_acc"])
    parts = []
    for field in FIELDS:
        if field == "strain" and not strain_allowed:
            continue
        value = F.trim(F.regexp_replace(F.col(field), '"', ""))
        part = (joined.filter(is_real(field))
                .select(value.alias("value"), F.lower(value).alias("key"), "biosample_acc", "country", "year")
                .groupBy("key")
                .agg(F.min("value").alias("value"), F.countDistinct("biosample_acc").alias("isolates"),
                     F.countDistinct("country").alias("countries"),
                     F.min("year").cast("int").alias("first_year"), F.max("year").cast("int").alias("last_year")))
        if field == "strain":
            part = part.filter(F.col("isolates") >= strain_min_isolates)
        parts.append(part.select(F.lit(organism).alias("organism"), F.lit(field).alias("field"),
                                 "value", "key", "isolates", "countries", "first_year", "last_year"))
    result = parts[0]
    for part in parts[1:]:
        result = result.unionByName(part)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organism", help="Index one organism only, into data/dev_results/ or RESULTS_DIR")
    args = parser.parse_args()

    spark = (SparkSession.builder.appName("search_index").config("spark.sql.shuffle.partitions", "16")
             .config("spark.hadoop.mapreduce.fileoutputcommitter.marksuccessfuljobs", "false").getOrCreate())
    spark.sparkContext.setLogLevel("WARN")
    min_fill, min_isolates = search_settings(load_settings())
    profile = json.loads(PROFILE.read_text())["organisms"]

    frames = []
    for row in read_organisms(args.organism):
        organism = row["organism"]
        if args.organism and organism != args.organism:
            continue
        strain_fill = profile[organism]["search_fill"]["strain"]["pct_filled"]
        raw = spark.read.parquet(str(PARQUET / "amr" / organism))
        isolates = spark.read.parquet(str(PARQUET / "isolates" / f"organism={organism}"))
        frames.append(index_rows(raw, isolates, organism, strain_fill >= min_fill, min_isolates))
        print(f"{organism}: strain {'indexed' if strain_fill >= min_fill else 'left out'} ({strain_fill}% filled)",
              flush=True)
    result = frames[0]
    for frame in frames[1:]:
        result = result.unionByName(frame)
    write_table(result.orderBy("organism", "field", "key"), "search_index", output_dir(args.organism))
    spark.stop()


if __name__ == "__main__":
    main()
