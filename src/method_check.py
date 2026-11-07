"""Check whether the AMRFinder analysis method could distort rates or trends.

Compares methods within the same organism, year and drug class, so that a change in the
years covered cannot explain a gap. Labs choose methods, so a gap can still come from which
isolates were analysed each way. This reports a check and corrects nothing.

Writes results/method_check.json.

Usage: spark-submit src/method_check.py
"""
import json

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

from analytics import RESULTS, load_settings, split_drugs, windows, usable
from clean import PARQUET
from datasets import core_organisms

METHOD = "amrfinder_analysis_type"
TOP_GAPS = 5


def method_shares(isolates):
    """Isolates per organism, year and method, with each method's share of that year."""
    counted = isolates.filter(F.col("year").isNotNull()).groupBy("organism", "year", METHOD).agg(F.count("*").alias("n"))
    totals = counted.groupBy("organism", "year").agg(F.sum("n").alias("year_total"))
    return counted.join(totals, ["organism", "year"]).withColumn("share", F.col("n") / F.col("year_total"))


def method_rates(isolates, genes, min_sample):
    """Rate per organism, year, method and drug class, for method groups that meet the minimum."""
    known = isolates.filter(F.col("year").isNotNull())
    totals = (known.groupBy("organism", "year", METHOD).agg(F.count("*").alias("n")).filter(F.col("n") >= min_sample))
    drugs = split_drugs(genes).select("biosample_acc", "organism", "drug_class").distinct()
    targets = drugs.select("organism", "drug_class").distinct()
    positives = (drugs.join(known.select("biosample_acc", "organism", "year", METHOD), ["biosample_acc", "organism"])
                 .groupBy("organism", "year", METHOD, "drug_class").agg(F.count("*").alias("positives")))
    return (totals.join(targets, "organism").join(positives, ["organism", "year", METHOD, "drug_class"], "left")
            .withColumn("positives", F.coalesce(F.col("positives"), F.lit(0)))
            .withColumn("rate", F.col("positives") / F.col("n")))


def within_year_gaps(rates):
    """The gap between the highest and lowest method rate, per organism, year and drug class."""
    return (rates.groupBy("organism", "year", "drug_class")
            .agg(F.countDistinct(METHOD).alias("methods"), F.max("rate").alias("_high"), F.min("rate").alias("_low"))
            .filter(F.col("methods") >= 2)
            .withColumn("gap_points", 100 * (F.col("_high") - F.col("_low"))).drop("_high", "_low"))


def share_shift(shares, first_year, last_year):
    """Each organism's largest change in a method's share over the window, using years in it."""
    rows = shares.filter(F.col("year").between(first_year, last_year)).collect()
    result = {}
    for organism in sorted({r["organism"] for r in rows}):
        years = sorted({r["year"] for r in rows if r["organism"] == organism})
        methods = sorted({str(r[METHOD]) for r in rows if r["organism"] == organism})
        table = {(r["year"], str(r[METHOD])): r["share"] for r in rows if r["organism"] == organism}
        result[organism] = {
            "first_year": years[0],
            "last_year": years[-1],
            "share_first_year": {m: round(table.get((years[0], m), 0), 3) for m in methods},
            "share_last_year": {m: round(table.get((years[-1], m), 0), 3) for m in methods},
            "largest_change_points": round(100 * max(abs(table.get((years[-1], m), 0) - table.get((years[0], m), 0))
                                                     for m in methods), 1),
        }
    return result


def main():
    spark = SparkSession.builder.appName("method").config("spark.sql.shuffle.partitions", "16").getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    settings = load_settings()
    core = core_organisms()
    isolates = spark.read.parquet(str(PARQUET / "isolates")).filter(F.col("organism").isin(core)).cache()
    genes = spark.read.parquet(str(PARQUET / "isolate_genes")).filter(F.col("organism").isin(core))
    bounds = windows(settings, usable(isolates).agg(F.max("year")).first()[0])
    first, last = bounds["rising_from"], bounds["rising_to"]

    gaps = within_year_gaps(method_rates(isolates, genes, settings["min_sample"])).filter(F.col("year").between(first, last))
    median = F.percentile_approx("gap_points", 0.5)
    summary = (gaps.groupBy("organism", "drug_class").agg(median.alias("median_gap_points"), F.count("*").alias("years_compared"))
               .filter(F.col("years_compared") >= settings["rising_min_years"]).collect())
    largest = {}
    for organism in sorted({r["organism"] for r in summary}):
        rows = sorted((r for r in summary if r["organism"] == organism), key=lambda r: -r["median_gap_points"])[:TOP_GAPS]
        largest[organism] = [{"drug_class": r["drug_class"], "median_gap_points": round(r["median_gap_points"], 1),
                              "years_compared": r["years_compared"]} for r in rows]

    result = {
        "window": [first, last],
        "method_counts": {str(r[METHOD]): r["count"] for r in isolates.groupBy(METHOD).count().collect()},
        "share_shift": share_shift(method_shares(isolates), first, last),
        "largest_within_year_gaps": largest,
        "note": "Gaps compare methods within one organism, year and class, needing at least "
                f"{settings['min_sample']} isolates per method. Labs choose methods, so a gap may reflect which "
                "isolates were analysed each way. A trend is most at risk where both the share shift and the gap are large.",
    }
    (RESULTS / "method_check.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result["share_shift"])[:1500], flush=True)
    spark.stop()


if __name__ == "__main__":
    main()
