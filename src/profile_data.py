"""Measure data quality by organism and save results/data_profile.json.

Usage: spark-submit src/profile_data.py [--organism NAME]
"""
import argparse
import json
import time
from pathlib import Path

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

from datasets import core_organisms, results_dir
from ingest import clean_name, read_tsv

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "data" / "raw" / "manifest.json"
PARQUET = ROOT / "data" / "parquet"
PROFILE = results_dir() / "data_profile.json"

FILL_COLUMNS = ["collection_date", "geo_loc_name", "host", "isolation_source", "epi_type", "lat_lon",
                "AST_phenotypes", "AMR_genotypes_core"]
# Fields for pathogen search, kept apart from FILL_COLUMNS so the app's fill summaries do not change.
SEARCH_COLUMNS = ["scientific_name", "serovar", "strain", "host_disease", "taxid", "species_taxid"]
# Values can carry a reason after a colon, such as "missing: third party data".
PLACEHOLDER = (r"^(missing|not[ _]collected|not[ _]applicable|not[ _]provided|not[ _]available|not[ _]determined"
               r"|unknown|unspecified|n/?a|none|null|restricted access|-|\.)(\s*:.*)?$")
DATE_FORMATS = {"YYYY": r"^\d{4}$", "YYYY-MM": r"^\d{4}-\d{2}$", "YYYY-MM-DD": r"^\d{4}-\d{2}-\d{2}$",
                "timestamp": r"^\d{4}-\d{2}-\d{2}T"}
TOP_COUNTRIES = 15
# Upload delay is measured on collection years this many years before the latest upload,
# because newer years have not had time to finish uploading.
DELAY_COHORT = (5, 10)
DELAY_MAX_YEARS = 5
COMPLETE_PCT = 90


def normal(column):
    """Lower-case text with the literal quotes that quoting-off leaves behind removed."""
    return F.lower(F.trim(F.regexp_replace(F.col(column), '"', "")))


def is_empty(column):
    return F.col(column).isNull() | (normal(column) == "")


def is_placeholder(column):
    return ~is_empty(column) & normal(column).rlike(PLACEHOLDER)


def is_real(column):
    return ~is_empty(column) & ~normal(column).rlike(PLACEHOLDER)


def percent(part, total):
    return round(100 * part / total, 2) if total else None


def top_values(frame, condition, column, limit=10):
    rows = (frame.filter(condition).groupBy(column).count()
            .orderBy(F.desc("count"), column).limit(limit).collect())
    return {str(row[column]): row["count"] for row in rows}


def fill_rates(frame, total, columns=FILL_COLUMNS, distinct=False):
    """Percent real, placeholder and empty for each column the features rely on."""
    exprs = []
    for column in columns:
        exprs.append(F.sum(F.when(is_real(column), 1).otherwise(0)).alias(f"{column}|real"))
        exprs.append(F.sum(F.when(is_placeholder(column), 1).otherwise(0)).alias(f"{column}|placeholder"))
    counts = frame.agg(*exprs).first().asDict()

    rates = {}
    for column in columns:
        real, placeholder = counts[f"{column}|real"], counts[f"{column}|placeholder"]
        rates[column] = {
            "pct_filled": percent(real, total),
            "pct_placeholder": percent(placeholder, total),
            "pct_empty": percent(total - real - placeholder, total),
            "top_placeholders": top_values(frame, is_placeholder(column), column, 5),
        }
        if distinct:
            rates[column]["distinct_real"] = frame.filter(is_real(column)).select(normal(column)).distinct().count()
    return rates


def label_dates(frame):
    """Add date_format and year columns to rows with a real collection_date."""
    return add_date_labels(frame.filter(is_real("collection_date")))


def add_date_labels(frame):
    """Add date_format and year columns, keeping every row."""
    start = F.regexp_extract("collection_date", r"^(\d{4})", 1)
    end = F.regexp_extract("collection_date", r"/(\d{4})", 1)
    label = F.lit("other")
    for name, pattern in DATE_FORMATS.items():
        label = F.when(F.col("collection_date").rlike(pattern), name).otherwise(label)
    label = (F.when(F.col("collection_date").contains("/") & (start != "") & (start == end), "range_same_year")
             .when(F.col("collection_date").contains("/") & (start != "") & (end != ""), "range_multi_year")
             .otherwise(label))
    return frame.withColumn("date_format", label).withColumn("year", start)


def single_year_rows(labelled):
    """A multi-year range has no single year, so it is left out of yearly counts."""
    return labelled.filter(F.col("year").rlike(r"^\d{4}$") & ~F.col("date_format").isin("range_multi_year", "other"))


def date_profile(frame):
    labelled = label_dates(frame)
    formats = {row["date_format"]: row["count"] for row in labelled.groupBy("date_format").count().collect()}
    dated = single_year_rows(labelled)
    per_year = {row["year"]: row["count"] for row in dated.groupBy("year").count().orderBy("year").collect()}
    return {
        "formats": formats,
        "other_examples": top_values(labelled, F.col("date_format") == "other", "collection_date", 10),
        "multi_year_range_examples": top_values(labelled, F.col("date_format") == "range_multi_year",
                                                "collection_date", 5),
        "isolates_per_year": per_year,
    }


def upload_delay(frame):
    """Measure how long isolates take to appear, to decide which recent years are provisional."""
    created = F.regexp_extract("target_creation_date", r"^(\d{4})", 1)
    rows = (single_year_rows(label_dates(frame)).filter(created != "")
            .withColumn("created_year", created.cast("int"))
            .withColumn("collected_year", F.col("year").cast("int"))
            .withColumn("lag", F.col("created_year") - F.col("collected_year")))
    latest = rows.agg(F.max("created_year")).first()[0]
    if latest is None:
        return None

    first, last = latest - DELAY_COHORT[1], latest - DELAY_COHORT[0]
    cohort = rows.filter(F.col("collected_year").between(first, last) & (F.col("lag") >= 0))
    by_lag = {row["lag"]: row["count"] for row in cohort.groupBy("lag").count().collect()}
    total = sum(by_lag.values())

    cumulative, running, years_to_complete = {}, 0, None
    for lag in range(DELAY_MAX_YEARS + 1):
        running += by_lag.get(lag, 0)
        cumulative[lag] = percent(running, total)
        if years_to_complete is None and total and 100 * running / total >= COMPLETE_PCT:
            years_to_complete = lag
    return {
        "latest_upload_year": latest,
        "cohort_collection_years": [first, last],
        "cohort_rows": total,
        "cumulative_pct_by_lag_years": cumulative,
        "complete_pct_target": COMPLETE_PCT,
        # None means the target was not reached within DELAY_MAX_YEARS.
        "years_to_complete": years_to_complete,
        "provisional_from_year": None if years_to_complete is None else latest - years_to_complete + 1,
        "rows_created_before_collected": rows.filter(F.col("lag") < 0).count(),
    }


def country_profile(frame, total):
    countries = (frame.filter(is_real("geo_loc_name"))
                 .withColumn("country", F.trim(F.split(F.regexp_replace("geo_loc_name", '"', ""), ":").getItem(0)))
                 .groupBy("country").count().orderBy(F.desc("count"), "country").collect())
    india = sum(row["count"] for row in countries if row["country"].lower() == "india")
    return {
        "distinct_values": len(countries),
        "top": {row["country"]: row["count"] for row in countries[:TOP_COUNTRIES]},
        "india_count": india,
        "india_pct_of_rows": percent(india, total),
    }


def gene_audit(frame, total):
    """Show how isolates with no resistance genes appear in the file."""
    core, every = "AMR_genotypes_core", "AMR_genotypes"
    no_core = ~is_real(core)
    genes = (frame.filter(is_real(core))
             .withColumn("gene_count", F.size(F.split(F.regexp_replace(core, '"', ""), ","))))
    histogram = {row["gene_count"]: row["count"]
                 for row in genes.groupBy("gene_count").count().orderBy("gene_count").limit(10).collect()}
    no_core_rows = frame.filter(no_core).count()
    return {
        "core_no_genes": no_core_rows,
        "core_no_genes_pct": percent(no_core_rows, total),
        "core_no_genes_but_any_genes": frame.filter(no_core & is_real(every)).count(),
        "any_no_genes": frame.filter(~is_real(every)).count(),
        "core_no_gene_values": top_values(frame, no_core, core, 10),
        "commonest_short_core_values": top_values(frame, is_real(core) & (F.length(core) <= 25), core, 10),
        "core_gene_count_first_10": histogram,
    }


def analysis_coverage(frame):
    """Check that an empty gene value means analysed with no genes, not never analysed."""
    no_core = ~is_real("AMR_genotypes_core")
    not_analysed = F.col("amrfinder_version").isNull() | (F.coalesce(F.col("amrfinder_applied"), F.lit("")) != "1")
    core_count = F.coalesce(F.col("number_core_amr_genes"), F.lit("0"))
    by_type = (frame.groupBy("amrfinder_analysis_type")
               .agg(F.count("*").alias("rows"), F.sum(F.when(no_core, 1).otherwise(0)).alias("no_core")).collect())
    return {
        "not_analysed_rows": frame.filter(not_analysed).count(),
        "no_core_but_gene_count_above_zero": frame.filter(no_core & (core_count != "0")).count(),
        "by_analysis_type": {str(row["amrfinder_analysis_type"]): {
            "rows": row["rows"], "pct_no_core_genes": percent(row["no_core"], row["rows"])} for row in by_type},
    }


def profile_organism(spark, organism, record):
    frame = spark.read.parquet(str(PARQUET / "amr" / organism))
    total = frame.count()
    return {
        "pdg_version": record["pdg_version"],
        "source_file": record["amr"]["file"],
        "rows": total,
        "distinct_biosample_acc": frame.select("biosample_acc").distinct().count(),
        "fill": fill_rates(frame, total),
        "search_fill": fill_rates(frame, total, SEARCH_COLUMNS, distinct=True),
        "dates": date_profile(frame),
        "upload_delay": upload_delay(frame),
        "countries": country_profile(frame, total),
        "gene_audit": gene_audit(frame, total),
        "analysis_coverage": analysis_coverage(frame),
    }


def denominator_check(spark, organism, record):
    """Compare the AMR file with the Metadata file to see if isolates are left out."""
    amr = spark.read.parquet(str(PARQUET / "amr" / organism))
    raw = read_tsv(spark, ROOT / record["metadata"]["path"])
    metadata = raw.toDF(*[clean_name(c) for c in raw.columns])

    left = amr.select("target_acc").filter(F.col("target_acc").isNotNull()).distinct()
    right = metadata.select("target_acc").filter(F.col("target_acc").isNotNull()).distinct()
    only_metadata = right.join(left, "target_acc", "left_anti")
    extra = metadata.join(only_metadata, "target_acc", "inner")
    return {
        "metadata_file": record["metadata"]["file"],
        "amr_rows": amr.count(),
        "metadata_rows": metadata.count(),
        "in_both": right.join(left, "target_acc", "inner").count(),
        "only_in_metadata": only_metadata.count(),
        "only_in_amr": left.join(right, "target_acc", "left_anti").count(),
        "only_in_metadata_with_core_genes": (extra.filter(is_real("AMR_genotypes_core")).count()
                                             if "AMR_genotypes_core" in metadata.columns else None),
        "columns_only_in_metadata": sorted(set(metadata.columns) - set(amr.columns)),
        "columns_only_in_amr": sorted(set(amr.columns) - set(metadata.columns)),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organism", help="Profile one organism only")
    args = parser.parse_args()

    manifest = json.loads(MANIFEST.read_text())
    profile = json.loads(PROFILE.read_text()) if PROFILE.exists() else {"organisms": {}, "denominator_check": {}}
    spark = SparkSession.builder.appName("profile").config("spark.sql.shuffle.partitions", "16").getOrCreate()
    spark.sparkContext.setLogLevel("WARN")

    core = core_organisms()
    for organism, record in manifest["organisms"].items():
        if (args.organism and organism != args.organism) or (not args.organism and organism not in core):
            continue
        started = time.time()
        profile["organisms"][organism] = profile_organism(spark, organism, record)
        if "metadata" in record:
            profile["denominator_check"][organism] = denominator_check(spark, organism, record)
        PROFILE.write_text(json.dumps(profile, indent=2))
        print(f"profiled {organism}: {profile['organisms'][organism]['rows']} rows in {time.time() - started:.0f}s",
              flush=True)
    spark.stop()


if __name__ == "__main__":
    main()
