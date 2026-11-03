"""Build the isolate_genes table: one row per isolate and gene, with drug class.

Each gene entry takes one lookup, and match_source records which. Point
mutations try the mutation table, the allele, then the disrupted gene. Other
entries try the allele, the family-level row, then all rows of the family.

Usage: spark-submit src/genes.py [--organism NAME]
"""
import argparse

from pyspark.sql import SparkSession, Window
from pyspark.sql import functions as F

from clean import PARQUET, read_organisms, update_summary

TOP_UNMAPPED = 20
FAMILY_LEVEL_EXCLUDED = ["POINT_DISRUPT", "AMR-SUSCEPTIBLE"]
INACTIVE_CLASS = "NONE"


def parse_entries(isolates):
    """Split the gene list into one row per gene, with the suffix as gene_type."""
    entries = (isolates.filter(F.col("AMR_genotypes_core").isNotNull())
               .withColumn("_entry", F.explode(F.split(F.regexp_replace("AMR_genotypes_core", '"', ""), ",")))
               .withColumn("_entry", F.trim("_entry"))
               .filter(F.col("_entry") != ""))
    suffix = F.regexp_extract("_entry", r"=(.*)$", 1)
    return (entries.withColumn("gene", F.regexp_extract("_entry", r"^([^=]*)", 1))
            .withColumn("gene_type", F.when(suffix == "", "COMPLETE").otherwise(suffix))
            .drop("_entry", "AMR_genotypes_core"))


def own_taxon_rows(rows, key, taxon):
    """Keep rows for this taxon if a key has any, otherwise rows open to all taxa."""
    listed = F.array_contains(F.split(F.col("whitelisted_taxa"), r"\s*,\s*"), taxon)
    usable = rows.withColumn("_own", F.coalesce(listed, F.lit(False))).filter(F.col("_own") | F.col("whitelisted_taxa").isNull())
    order = Window.partitionBy(key).orderBy(F.col("_own").desc())
    return usable.withColumn("_rank", F.rank().over(order)).filter("_rank = 1").drop("_rank", "_own")


def distinct_drug_lists(column):
    return F.collect_set(F.array_sort(F.split(F.coalesce(F.col(column), F.lit("")), "/")))


def shared_drugs(column):
    """Keep only the drugs every row lists, or nothing if they share none."""
    first = F.element_at(F.col(column), 1)
    shared = F.array_join(F.array_sort(F.aggregate(F.col(column), first, lambda kept, x: F.array_intersect(kept, x))), "/")
    return F.when(shared != "", shared)


def one_row_per_key(rows, key):
    """Collapse to one row per key, so blaNDM stays carbapenem and blaOXA gets no subclass."""
    grouped = rows.groupBy(key).agg(distinct_drug_lists("class").alias("_classes"),
                                    distinct_drug_lists("subclass").alias("_subclasses"))
    return grouped.select(F.col(key).alias("_key"), shared_drugs("_classes").alias("drug_class"),
                          shared_drugs("_subclasses").alias("drug_subclass"))


def build_steps(catalog, mutations, taxon):
    """Return the lookup tables, each with one row per key."""
    amr = catalog.filter(F.col("type") == "AMR")
    allele = amr.filter(F.col("allele").isNotNull())
    family_level = amr.filter(F.col("allele").isNull() & ~F.col("subtype").isin(FAMILY_LEVEL_EXCLUDED))
    disrupt = amr.filter(F.col("subtype") == "POINT_DISRUPT")
    # An inactive enzyme says nothing about the rest of its family.
    active = amr.filter(F.coalesce(F.col("class"), F.lit("")) != INACTIVE_CLASS)
    return {
        "mutation": one_row_per_key(mutations.filter(F.col("taxgroup") == taxon), "standard_mutation_symbol"),
        "allele": one_row_per_key(own_taxon_rows(allele, "allele", taxon), "allele"),
        "family": one_row_per_key(own_taxon_rows(family_level, "gene_family", taxon), "gene_family"),
        "family_ambiguous": one_row_per_key(own_taxon_rows(active, "gene_family", taxon), "gene_family"),
        "disrupt": one_row_per_key(own_taxon_rows(disrupt, "gene_family", taxon), "gene_family"),
    }


def resolve(keys, steps):
    """Give each (gene, gene_type) key its first matching lookup, or mark it unmapped."""
    is_point = F.col("gene_type") == "POINT"
    prefix = F.regexp_extract("gene", r"^([^_]+)", 1)
    orders = [
        (is_point, [("mutation", F.col("gene")), ("allele", F.col("gene")), ("disrupt", prefix)]),
        (~is_point, [("allele", F.col("gene")), ("family", F.col("gene")), ("family_ambiguous", F.col("gene"))]),
    ]
    found = []
    for condition, order in orders:
        remaining = keys.filter(condition)
        for source, key in order:
            with_key = remaining.withColumn("_key", key)
            hits = with_key.join(F.broadcast(steps[source]), "_key").drop("_key")
            found.append(hits.withColumn("match_source", F.lit(source)))
            remaining = with_key.join(F.broadcast(steps[source].select("_key")), "_key", "left_anti").drop("_key")
        found.append(remaining.withColumn("drug_class", F.lit(None).cast("string"))
                     .withColumn("drug_subclass", F.lit(None).cast("string"))
                     .withColumn("match_source", F.lit("unmapped")))
    result = found[0]
    for part in found[1:]:
        result = result.unionByName(part)
    return result


def annotate(isolates, catalog, mutations, taxon):
    """Return isolate_genes rows, and how many exact repeats were removed."""
    parsed = parse_entries(isolates)
    entries = parsed.dropDuplicates(["biosample_acc", "gene", "gene_type"])
    repeats = parsed.count() - entries.count()
    keys = entries.select("gene", "gene_type").distinct()
    resolved = resolve(keys, build_steps(catalog, mutations, taxon))
    return entries.join(F.broadcast(resolved), ["gene", "gene_type"]), repeats


def gene_summary(genes, repeats):
    total = genes.count()
    by_source = {row["match_source"]: row["count"] for row in genes.groupBy("match_source").count().collect()}
    unmapped = by_source.get("unmapped", 0)
    top = (genes.filter(F.col("match_source") == "unmapped").groupBy("gene", "gene_type").count()
           .orderBy(F.desc("count"), "gene").limit(TOP_UNMAPPED).collect())
    return {
        "gene_rows": total,
        "repeats_removed": repeats,
        "by_match_source": by_source,
        "catalog_match_pct": round(100 * (total - unmapped) / total, 3) if total else None,
        "rows_without_drug_class": genes.filter(F.col("drug_class").isNull()).count(),
        "rows_without_drug_subclass": genes.filter(F.col("drug_subclass").isNull()).count(),
        "rows_inactive_allele": genes.filter(F.col("drug_class") == INACTIVE_CLASS).count(),
        "top_unmapped": {f"{row['gene']} ({row['gene_type']})": row["count"] for row in top},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organism", help="Process one organism only")
    args = parser.parse_args()

    spark = SparkSession.builder.appName("genes").config("spark.sql.shuffle.partitions", "16").getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    catalog = spark.read.parquet(str(PARQUET / "reference" / "gene_catalog")).cache()
    mutations = spark.read.parquet(str(PARQUET / "reference" / "point_mutations")).cache()

    for row in read_organisms():
        organism = row["organism"]
        if args.organism and organism != args.organism:
            continue
        isolates = spark.read.parquet(str(PARQUET / "isolates" / f"organism={organism}"))
        genes, repeats = annotate(isolates, catalog, mutations, row["taxon"])
        path = PARQUET / "isolate_genes" / f"organism={organism}"
        genes.select("biosample_acc", "gene", "gene_type", "drug_class", "drug_subclass", "match_source",
                     "organism_label", "country", "iso3", "year", "cluster_id").write.mode("overwrite").parquet(str(path))

        summary = gene_summary(spark.read.parquet(str(path)), repeats)
        update_summary(organism, "genes", summary)
        print(f"genes {organism}: {summary['gene_rows']} rows, {summary['catalog_match_pct']}% matched", flush=True)
    spark.stop()


if __name__ == "__main__":
    main()
