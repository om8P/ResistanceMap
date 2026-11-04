"""Compare first-seen dates with published gene history, and reconcile table totals.

Writes results/sanity_checks.json. Published dates come from the sources listed below.

Usage: spark-submit src/sanity_checks.py
"""
import json

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

from analytics import ALL_ORGANISMS, RESULTS
from clean import PARQUET

OLD_RECORDS_SHOWN = 25
PUBLISHED = {
    "blaNDM": {
        "gene_filter": "blaNDM",
        "family": "blaNDM",
        "published_year": 2008,
        "history": "First described by Yong et al. (Antimicrob Agents Chemother, December 2009), from a Klebsiella "
                   "pneumoniae isolate found in 2008 in a Swedish patient who had been treated in New Delhi, India.",
        "sources": ["https://en.wikipedia.org/wiki/New_Delhi_metallo-beta-lactamase_1",
                    "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3204651/"],
        "assessment": "Broadly consistent. With the support rule the earliest established year is 2009, in India, "
                      "which fits the published 2008 discovery and link to India.",
        "oddities": [
            "1943 and 1968 (Slovakia, SAMEA116823128 and SAMEA117931159) predate any report of the gene by decades. "
            "Treated as date errors in the source metadata, not checked with the submitters.",
            "1984 (China, SAMN31881052) carries both blaNDM-13 and mcr-1.1 in a human urine sample. Likely a date error.",
            "The 2005 records have no country and are labelled as lab passages or transformants, so they do not come "
            "from patients and do not affect any country's first-seen year.",
            "2007 (Germany, SAMN03366525, Acinetobacter) could be a real isolate from before the discovery. Not verified.",
            "The first_year column still shows these raw dates, so the app must lead with established_year.",
        ],
    },
    "mcr-1": {
        "gene_filter": "mcr-1",
        "family": "mcr-1",
        "published_year": 2015,
        "retrospective_from": 1980,
        "history": "First described by Liu et al. (Lancet Infect Dis 2016;16:161-168, online November 2015), from "
                   "E. coli in animals, meat and patients in China. Later retrospective work reports it in Chinese "
                   "chicken E. coli from the 1980s. Sources were read as summaries, not the original letter.",
        "sources": ["https://pesquisa.bvsalud.org/sms/resource/pt/mdl-26603172",
                    "https://pmc.ncbi.nlm.nih.gov/articles/PMC5347679"],
        "assessment": "Broadly consistent. The earliest established year is 2004, in China. Records from before 2015 "
                      "are expected, because the gene circulated before it was described and later studies looked "
                      "back through stored isolates.",
        "oddities": [
            "1975 (China, SAMN07983309, chicken) is earlier than the 1980s usually cited. The accession sits near other "
            "Chinese chicken records (SAMN079832xx), so it may come from a retrospective survey, but the date is not "
            "confirmed. Unresolved.",
            "1984 (China, SAMN31881052) is the same record that also lists blaNDM-13, so its date is doubtful. It should "
            "not be read as support for the 1980s reports.",
            "The source for the 1980s date was read in summary only, and summaries disagree slightly on the survey's "
            "start, so the original letter should be checked before citing it in the report.",
        ],
    },
}


def first_seen_summary(seen, family):
    rows = seen.filter((F.col("organism") == ALL_ORGANISMS) & (F.col("level") == "family") & (F.col("gene") == family))
    def earliest(column):
        year = rows.agg(F.min(column)).first()[0]
        return {"year": year, "countries": sorted(r["country"] for r in rows.filter(F.col(column) == year).collect())}

    return {
        "countries_on_record": rows.count(),
        "countries_established": rows.filter(F.col("established_year").isNotNull()).count(),
        "earliest_record": earliest("first_year"),
        "earliest_established": earliest("established_year"),
    }


def records_before(genes, isolates, prefix, year):
    """Records dated before the given year, with what is needed to judge them."""
    match = (F.col("gene") == prefix) | F.col("gene").startswith(prefix + "-") | F.col("gene").startswith(prefix + ".")
    details = isolates.select("biosample_acc", "organism", "collection_date", "host", "isolation_source")
    old = (genes.filter(match & (F.col("year") < year)).join(details, ["biosample_acc", "organism"])
           .select("biosample_acc", "gene", "organism", "country", "year", "collection_date", "host", "isolation_source")
           .orderBy("year", "biosample_acc"))
    return old.count(), [row.asDict() for row in old.limit(OLD_RECORDS_SHOWN).collect()]


def by_year(genes, prefix, first, last):
    match = (F.col("gene") == prefix) | F.col("gene").startswith(prefix + "-") | F.col("gene").startswith(prefix + ".")
    rows = (genes.filter(match & F.col("year").between(first, last)).groupBy("year")
            .agg(F.countDistinct("biosample_acc").alias("n")).orderBy("year").collect())
    return {str(r["year"]): r["n"] for r in rows}


def reconcile(spark, isolates):
    cover = spark.read.parquet(str(RESULTS / "coverage.parquet"))
    checks = {
        "isolates_in_table": isolates.count(),
        "isolates_in_coverage": cover.agg(F.sum("isolates")).first()[0],
    }
    usable = cover.filter(F.col("country").isNotNull() & F.col("year").isNotNull())
    keys = ["organism", "country", "year"]
    for name in ["prevalence", "last_resort"]:
        table = spark.read.parquet(str(RESULTS / f"{name}.parquet"))
        groups = table.select(keys + ["n"]).distinct()
        joined = usable.join(groups, keys, "full")
        checks[f"{name}_groups_differing_from_coverage"] = joined.filter(
            F.col("n").isNull() | F.col("isolates").isNull() | (F.col("n") != F.col("isolates"))).count()
        for suffix in ["", "_adjusted"]:
            view = spark.read.parquet(str(RESULTS / f"{name}{suffix}.parquet"))
            checks[f"{name}{suffix}_rows_positives_above_n"] = view.filter(F.col("positives") > F.col("n")).count()
            checks[f"{name}{suffix}_rows_rate_shown_under_minimum"] = view.filter(
                F.col("rate").isNotNull() & ~F.col("meets_min_sample")).count()
    checks["passed"] = (checks["isolates_in_table"] == checks["isolates_in_coverage"]
                        and not any(v for k, v in checks.items() if k.endswith(("_coverage", "_above_n", "_minimum"))
                                    and k != "isolates_in_coverage"))
    return checks


def main():
    spark = SparkSession.builder.appName("sanity").config("spark.sql.shuffle.partitions", "16").getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    isolates = spark.read.parquet(str(PARQUET / "isolates"))
    genes = spark.read.parquet(str(PARQUET / "isolate_genes"))
    seen = spark.read.parquet(str(RESULTS / "first_seen.parquet"))

    result = {"genes": {}, "reconciliation": reconcile(spark, isolates)}
    for name, known in PUBLISHED.items():
        before = known.get("retrospective_from", known["published_year"])
        total, records = records_before(genes, isolates, known["gene_filter"], known["published_year"])
        result["genes"][name] = {
            "published": {k: v for k, v in known.items() if k not in ("gene_filter", "family", "assessment", "oddities")},
            "in_data": first_seen_summary(seen, known["family"]),
            "assessment": known["assessment"],
            "oddities": known["oddities"],
            "records_before_published_year": total,
            "records_before_retrospective_start": records_before(genes, isolates, known["gene_filter"], before)[0],
            "oldest_records": records,
            "isolates_by_year_around_publication": by_year(genes, known["gene_filter"], known["published_year"] - 6,
                                                           known["published_year"] + 3),
        }
    (RESULTS / "sanity_checks.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    print(json.dumps(result["reconciliation"]), flush=True)
    spark.stop()


if __name__ == "__main__":
    main()
