"""Prepare the tables the app reads: prevalence, trends, hotspots and early warnings.

Every function takes and returns DataFrames, so tests can call them on small tables.
Counts have two views: "all" counts isolates, and "adjusted" counts each cluster once
per organism, country and year, with unclustered isolates counted individually.

Usage: spark-submit src/analytics.py [--organism NAME]
"""
import argparse
import json
from pathlib import Path

from pyspark.sql import SparkSession, Window
from pyspark.sql import functions as F

from clean import PARQUET, ROOT, SUMMARY
from datasets import core_organisms, read_organisms, redirected, results_dir
from profile_data import is_real

SETTINGS = ROOT / "config" / "settings.json"
RESULTS = results_dir()
DEV_RESULTS = ROOT / "data" / "dev_results"
AWARE = ROOT / "config" / "aware.csv"
Z_95 = 1.96
ALL_ORGANISMS = "ALL"
GROUP = ["organism", "organism_label", "country", "iso3", "year"]
PLACE = ["organism", "organism_label", "country", "iso3"]
LAST_RESORT_DRUGS = ["CARBAPENEM", "COLISTIN"]
MECHANISMS = ["acquired", "mutation", "disrupted", "intrinsic"]
ANY_MECHANISM = "any_excl_intrinsic"
BOTH_DRUGS = "CARBAPENEM+COLISTIN"
SOURCES = ["clinical", "environmental/other"]
RESISTANT_CALLS = ["R", "NS"]
SUSCEPTIBLE_CALLS = ["S"]
TOP_SOURCES = 5


def load_settings():
    return json.loads(SETTINGS.read_text())


def windows(settings, latest_year):
    """Work out the year boundaries from the latest data year."""
    provisional_from = latest_year - settings["provisional_years"] + 1
    return {
        "latest_year": latest_year,
        "provisional_from": provisional_from,
        "early_warning_from": latest_year - settings["early_warning_years"] + 1,
        "rising_from": provisional_from - settings["rising_years"],
        "rising_to": provisional_from - 1,
    }


def add_units(frame):
    """A cluster counts as one unit, and an unclustered isolate as its own."""
    return frame.withColumn("unit", F.coalesce(F.col("cluster_id"), F.col("biosample_acc")))


def item_column(adjusted):
    return "unit" if adjusted else "biosample_acc"


def usable(frame):
    return frame.filter(F.col("country").isNotNull() & F.col("year").isNotNull())


def split_drugs(genes, column="drug_class", output="drug_class"):
    """One row per drug listed, with spelling variants merged and inactive alleles skipped."""
    parts = F.explode(F.split(F.col(column), "/"))
    split = genes.filter(F.col(column).isNotNull()).withColumn(output, parts)
    named = split.withColumn(output, F.regexp_replace(F.trim(F.col(output)), "FUSIDIC ACID", "FUSIDIC_ACID"))
    return named.filter(~F.col(output).isin("", "NONE"))


def wilson_limits(positives, n):
    """Return the Wilson 95% lower and upper limits as fractions."""
    p = F.col(positives) / F.col(n)
    z2 = Z_95 * Z_95
    denominator = 1 + z2 / F.col(n)
    centre = (p + z2 / (2 * F.col(n))) / denominator
    half = Z_95 * F.sqrt(p * (1 - p) / F.col(n) + z2 / (4 * F.col(n) * F.col(n))) / denominator
    return F.greatest(F.lit(0.0), centre - half), F.least(F.lit(1.0), centre + half)


def add_rates(frame, settings, bounds):
    """Add the rate and limits, left empty under the minimum sample so they cannot be shown."""
    low, high = wilson_limits("positives", "n")
    enough = F.col("n") >= settings["min_sample"]
    return (frame.withColumn("meets_min_sample", enough)
            .withColumn("rate", F.when(enough, F.col("positives") / F.col("n")))
            .withColumn("ci_low", F.when(enough, low))
            .withColumn("ci_high", F.when(enough, high))
            .withColumn("provisional", F.col("year") >= bounds["provisional_from"]))


def denominators(isolates, adjusted):
    return (usable(add_units(isolates)).groupBy(GROUP)
            .agg(F.countDistinct(item_column(adjusted)).alias("n")))


def rate_table(totals, positives, targets, target_columns, adjusted, on=("organism",)):
    """Count positives for every group and target, keeping groups with none as zeros."""
    counted = (positives.groupBy(GROUP + target_columns)
               .agg(F.countDistinct(item_column(adjusted)).alias("positives")))
    grid = totals.join(F.broadcast(targets), list(on))
    return (grid.join(counted, GROUP + target_columns, "left")
            .withColumn("positives", F.coalesce(F.col("positives"), F.lit(0)).cast("long")))


def prevalence(isolates, genes, settings, bounds, adjusted=False):
    """Share of isolates or units with a gene in each drug class, per place and year."""
    positives = split_drugs(usable(add_units(genes)))
    targets = positives.select("organism", "drug_class").distinct()
    table = rate_table(denominators(isolates, adjusted), positives, targets, ["drug_class"], adjusted)
    return add_rates(table, settings, bounds)


def coverage(isolates, bounds):
    """Isolates by place and year. Rows with no country or year stay, so totals reconcile."""
    return (add_units(isolates).groupBy(GROUP)
            .agg(F.count("*").alias("isolates"), F.countDistinct("unit").alias("units"))
            .withColumn("provisional", F.col("year") >= bounds["provisional_from"]))


def family_map(catalog):
    """Map each allele to its family. OXA genes use the finer family in the product name."""
    oxa = F.regexp_extract("product_name", r"^(OXA-\d+) family", 1)
    family = F.when((F.col("gene_family") == "blaOXA") & (oxa != ""), F.concat(F.lit("bla"), oxa, F.lit(" family")))
    rows = catalog.filter((F.col("type") == "AMR") & F.col("allele").isNotNull())
    return (rows.withColumn("_family", F.coalesce(family, F.col("gene_family")))
            .groupBy("allele").agg(F.min("_family").alias("family")))


def add_family(genes, families):
    """Attach the family. Mutations use the gene name, and bare family names stay as they are."""
    point_gene = F.regexp_extract("gene", r"^([^_]+)", 1)
    joined = genes.join(F.broadcast(families), genes["gene"] == families["allele"], "left").drop("allele")
    return joined.withColumn("family", F.when(F.col("gene_type") == "POINT", point_gene)
                             .otherwise(F.coalesce(F.col("family"), F.col("gene"))))


def yearly_gene_counts(genes):
    """Isolates per gene, place and year, and clusters seen for the first time that year."""
    base = usable(add_units(genes))
    levels = []
    for level, column in [("gene", "gene"), ("family", "family")]:
        named = base.withColumn("level", F.lit(level)).withColumn("name", F.col(column))
        keys = PLACE + ["level", "name"]
        isolates = (named.groupBy(keys + ["year"])
                    .agg(F.countDistinct("biosample_acc").alias("isolates"),
                         F.min(F.col("gene_type") == "POINT").alias("point_mutation")))
        first = named.groupBy(keys + ["unit"]).agg(F.min("year").alias("year"))
        new_units = first.groupBy(keys + ["year"]).agg(F.count("*").alias("new_units"))
        levels.append(isolates.join(new_units, keys + ["year"], "left")
                      .withColumn("new_units", F.coalesce(F.col("new_units"), F.lit(0))))
    return levels[0].unionByName(levels[1])


def across_organisms(counts):
    """Combine organisms. Clusters belong to one organism, so new clusters can be summed."""
    keys = ["country", "iso3", "level", "name", "year"]
    return (counts.groupBy(keys)
            .agg(F.sum("isolates").alias("isolates"), F.sum("new_units").alias("new_units"),
                 F.min("point_mutation").alias("point_mutation"))
            .withColumn("organism", F.lit(ALL_ORGANISMS)).withColumn("organism_label", F.lit("All organisms")))


def first_seen(counts, settings):
    """First year on record, and the first year with enough support to trust it."""
    combined = counts.unionByName(across_organisms(counts))
    keys = PLACE + ["level", "name"]
    order = Window.partitionBy(keys).orderBy("year").rowsBetween(Window.unboundedPreceding, 0)
    running = (combined.withColumn("_isolates", F.sum("isolates").over(order))
               .withColumn("_units", F.sum("new_units").over(order)))
    supported = (F.col("_isolates") >= settings["support_isolates"]) & (F.col("_units") >= settings["support_clusters"])
    earliest = Window.partitionBy(keys).orderBy("year")
    return (running.withColumn("_first", F.row_number().over(earliest))
            .groupBy(keys)
            .agg(F.min("year").alias("first_year"),
                 F.min(F.when(supported, F.col("year"))).alias("established_year"),
                 F.max(F.when(F.col("_first") == 1, F.col("isolates"))).alias("first_year_isolates"),
                 F.sum("isolates").alias("isolates"), F.sum("new_units").alias("clusters"),
                 F.min("point_mutation").alias("point_mutation"))
            .withColumnRenamed("name", "gene"))


def early_warnings(counts, seen, cover, settings, bounds):
    """Genes that became established in a country recently, with their evidence.

    The baseline counts isolates before the gene's first recent record, not before a lone
    old record, which would make any country with such a record look newly sequenced.
    """
    start = bounds["early_warning_from"]
    keys = PLACE + ["level", "gene"]
    by_year = counts.withColumnRenamed("name", "gene")
    recent = (by_year.groupBy(keys)
              .agg(F.sum(F.when(F.col("year") >= start, F.col("isolates")).otherwise(0)).alias("recent_isolates"),
                   F.sum(F.when(F.col("year") >= start, F.col("new_units")).otherwise(0)).alias("recent_clusters"),
                   F.sum(F.when(F.col("year") < start, F.col("isolates")).otherwise(0)).alias("earlier_records"),
                   F.min(F.when(F.col("year") >= start, F.col("year"))).alias("first_recent_year")))
    candidates = (seen.filter((F.col("organism") != ALL_ORGANISMS) & ~F.col("point_mutation")
                              & (F.col("established_year") >= start))
                  .join(recent, keys)
                  .filter((F.col("recent_isolates") >= settings["support_isolates"])
                          & (F.col("recent_clusters") >= settings["support_clusters"])))
    prior = usable(cover).select("organism", "country", F.col("year").alias("_year"), F.col("isolates").alias("_prior"))
    baseline = (candidates.select(keys + ["first_recent_year"]).join(prior, ["organism", "country"])
                .filter(F.col("_year") < F.col("first_recent_year"))
                .groupBy(keys).agg(F.sum("_prior").alias("baseline_isolates")))
    anywhere = (seen.filter(F.col("organism") == ALL_ORGANISMS)
                .select("country", "level", "gene", F.col("first_year").alias("_any_first")))
    return (candidates.join(baseline, keys, "left").join(anywhere, ["country", "level", "gene"], "left")
            .withColumn("baseline_isolates", F.coalesce(F.col("baseline_isolates"), F.lit(0)))
            .withColumn("new_sequencing", F.col("baseline_isolates") < settings["baseline_isolates"])
            .withColumn("first_in_country_any_organism", F.col("_any_first") >= F.col("first_recent_year"))
            .withColumn("provisional", F.lit(True))
            .drop("_any_first", "point_mutation"))


def intrinsic_alleles(catalog, settings):
    """Alleles that belong to the organism rather than having been acquired."""
    frames = []
    for rule in settings["intrinsic"]:
        rows = catalog.filter((F.col("type") == "AMR") & F.col("allele").isNotNull()
                              & F.col("product_name").startswith(rule["product_prefix"]))
        frames.append(rows.select(F.lit(rule["organism"]).alias("organism"), F.col("allele").alias("gene")).distinct())
    result = frames[0]
    for frame in frames[1:]:
        result = result.unionByName(frame)
    return result.withColumn("_intrinsic", F.lit(True))


def typed_last_resort(genes, intrinsic):
    """One row per gene with a last-resort drug, labelled with its mechanism."""
    drugs = split_drugs(usable(add_units(genes)), "drug_subclass", "_token")
    carbapenem = F.col("_token").contains("CARBAPENEM")
    colistin = F.col("_token").contains("COLISTIN")
    named = (drugs.filter(carbapenem | colistin)
             .withColumn("drug", F.when(carbapenem, "CARBAPENEM").otherwise("COLISTIN"))
             .join(F.broadcast(intrinsic), ["organism", "gene"], "left"))
    return named.withColumn(
        "mechanism",
        F.when(F.col("_intrinsic").isNotNull(), "intrinsic")
        .when(F.col("match_source") == "disrupt", "disrupted")
        .when(F.col("gene_type") == "POINT", "mutation")
        .otherwise("acquired")).drop("_intrinsic", "_token")


def both_drugs(rows, mechanism):
    """Isolates with carbapenem and colistin genes in the same isolate, for one mechanism."""
    counted = rows.groupBy(GROUP + ["biosample_acc", "unit"]).agg(F.countDistinct("drug").alias("_drugs"))
    return (counted.filter(F.col("_drugs") == len(LAST_RESORT_DRUGS)).drop("_drugs")
            .withColumn("drug", F.lit(BOTH_DRUGS)).withColumn("mechanism", F.lit(mechanism)))


def last_resort_rows(genes, intrinsic):
    """One row per isolate, drug and mechanism, plus any-mechanism and both-drug rows."""
    columns = GROUP + ["biosample_acc", "unit", "drug", "mechanism"]
    typed = typed_last_resort(genes, intrinsic).select(columns)
    acquired = typed.filter(F.col("mechanism") == "acquired")
    others = typed.filter(F.col("mechanism") != "intrinsic").withColumn("mechanism", F.lit(ANY_MECHANISM))
    return (typed.unionByName(others).unionByName(both_drugs(acquired, "acquired").select(columns))
            .unionByName(both_drugs(others, ANY_MECHANISM).select(columns)))


def last_resort(isolates, genes, intrinsic, settings, bounds, adjusted=False):
    """Carbapenem and colistin rates by mechanism, with zeros for every combination."""
    spark = isolates.sparkSession
    combos = [(d, m) for d in LAST_RESORT_DRUGS for m in MECHANISMS + [ANY_MECHANISM]]
    combos += [(BOTH_DRUGS, m) for m in ["acquired", ANY_MECHANISM]]
    targets = spark.createDataFrame(combos, ["drug", "mechanism"]).crossJoin(isolates.select("organism").distinct())
    table = rate_table(denominators(isolates, adjusted), last_resort_rows(genes, intrinsic), targets,
                       ["drug", "mechanism"], adjusted)
    return add_rates(table, settings, bounds)


def trend(rates, settings, first_year, last_year):
    """Weighted slope in points per year and the Cochran-Armitage z, for one year window.

    Takes rows with kind, value, year, n and positives. Only years that meet the minimum
    sample count. With x centred on the weighted mean year, T = sum(r * x) and
    Sxx = sum(n * x * x). Then slope = T / Sxx and z = T / sqrt(p * (1 - p) * Sxx).
    """
    keys = PLACE + ["kind", "value"]
    used = rates.filter((F.col("year").between(first_year, last_year)) & (F.col("n") >= settings["min_sample"]))
    x = (F.col("year") - first_year).cast("double")
    totals = (used.withColumn("_x", x).groupBy(keys)
              .agg(F.count("*").alias("years_used"), F.sum("n").alias("n"), F.sum("positives").alias("positives"),
                   F.sum(F.col("n") * F.col("_x")).alias("_sx"),
                   F.sum(F.col("n") * F.col("_x") * F.col("_x")).alias("_sxx"),
                   F.sum(F.col("positives") * F.col("_x")).alias("_srx")))
    mean = F.col("_sx") / F.col("n")
    p = F.col("positives") / F.col("n")
    sxx = F.col("_sxx") - F.col("n") * mean * mean
    t = F.col("_srx") - F.col("positives") * mean
    variance = p * (1 - p) * sxx
    return (totals.withColumn("slope_points_per_year", F.when(sxx > 0, 100 * t / sxx))
            .withColumn("z", F.when(variance > 0, t / F.sqrt(variance)))
            .withColumn("rising", F.coalesce((F.col("years_used") >= settings["rising_min_years"])
                                             & (F.col("slope_points_per_year") > 0) & (F.col("z") >= settings["rising_z"]),
                                             F.lit(False)))
            .drop("_sx", "_sxx", "_srx"))


def gene_rates(isolates, genes, settings, bounds, adjusted):
    """Rates for genes with enough positives in the trend window, including zero years."""
    base = usable(add_units(genes)).filter(F.col("year") >= bounds["rising_from"])
    item = item_column(adjusted)
    common = (base.groupBy("organism", "country", "gene").agg(F.countDistinct(item).alias("_total"))
              .filter(F.col("_total") >= settings["rising_min_gene_positives"]).drop("_total"))
    totals = denominators(isolates, adjusted).filter((F.col("year") >= bounds["rising_from"])
                                                     & (F.col("n") >= settings["min_sample"]))
    return rate_table(totals, base.join(common, ["organism", "country", "gene"]), common, ["gene"], adjusted,
                      on=("organism", "country"))


def rising(prevalence_rows, last_resort_table, gene_rows, settings, bounds):
    """Trends for drug classes, last-resort drugs and genes, on two year windows.

    gene_rows can be None, for views that leave out gene-level trends.
    """
    columns = GROUP + ["n", "positives", "kind", "value"]
    classes = (prevalence_rows.withColumn("kind", F.lit("drug_class")).withColumn("value", F.col("drug_class"))
               .select(columns))
    last = (last_resort_table.filter(F.col("mechanism").isin("acquired", ANY_MECHANISM))
            .withColumn("kind", F.lit("last_resort"))
            .withColumn("value", F.concat_ws(":", "drug", "mechanism")).select(columns))
    rows = classes.unionByName(last)
    if gene_rows is not None:
        gene = gene_rows.withColumn("kind", F.lit("gene")).withColumn("value", F.col("gene")).select(columns)
        rows = rows.unionByName(gene)
    keys = PLACE + ["kind", "value"]
    complete = trend(rows, settings, bounds["rising_from"], bounds["rising_to"])
    extended = trend(rows, settings, bounds["rising_from"], bounds["latest_year"])
    renamed = extended.select(keys + [F.col(c).alias(f"{c}_with_provisional") for c in
                                      ["years_used", "n", "positives", "slope_points_per_year", "z", "rising"]])
    result = complete.join(renamed, keys, "full")
    for column in ["rising", "rising_with_provisional"]:
        result = result.withColumn(column, F.coalesce(F.col(column), F.lit(False)))
    years = F.coalesce(F.col("years_used"), F.lit(0))
    keep = (F.col("kind") != "gene") | (years >= settings["rising_min_years"])
    return (result.filter(keep)
            .withColumn("enough_years", years >= settings["rising_min_years"])
            .withColumn("window_from", F.lit(bounds["rising_from"]))
            .withColumn("window_to", F.lit(bounds["rising_to"])))


def hotspots(prevalence_rows, trends, settings, bounds):
    """Groups well above the same organism, class and year elsewhere, or rising."""
    world = Window.partitionBy("organism", "drug_class", "year")
    margin = settings["hotspot_margin_points"] / 100
    minimum = settings["min_sample"]
    rest = (prevalence_rows.withColumn("rest_n", F.sum("n").over(world) - F.col("n"))
            .withColumn("rest_positives", F.sum("positives").over(world) - F.col("positives"))
            .withColumn("rest_rate", F.when(F.col("rest_n") >= minimum, F.col("rest_positives") / F.col("rest_n")))
            .withColumn("margin_points", F.lit(settings["hotspot_margin_points"]))
            .filter(F.col("n") >= minimum))
    going_up = (trends.filter((F.col("kind") == "drug_class") & F.col("rising"))
                .select("organism", "country", F.col("value").alias("drug_class"),
                        "slope_points_per_year", "z", F.lit(True).alias("_rising")))
    latest = Window.partitionBy("organism", "country", "drug_class")
    in_window = F.when(F.col("year") <= bounds["rising_to"], F.col("year"))
    flagged = (rest.join(F.broadcast(going_up), ["organism", "country", "drug_class"], "left")
               .withColumn("_rising", F.coalesce(F.col("_rising"), F.lit(False)))
               .withColumn("_high", F.coalesce(F.col("ci_low") > F.col("rest_rate") + margin, F.lit(False)))
               .withColumn("_last", F.max(in_window).over(latest)))
    # Rows under the minimum sample are already gone, so a missing year breaks the run.
    ordered = latest.orderBy("year")
    before = F.coalesce(F.lag("_high").over(ordered) & (F.lag("year").over(ordered) == F.col("year") - 1), F.lit(False))
    after = F.coalesce(F.lead("_high").over(ordered) & (F.lead("year").over(ordered) == F.col("year") + 1), F.lit(False))
    flagged = flagged.withColumn("persistent", F.col("_high") & (before | after))
    return (flagged.filter(F.col("_high") | (F.col("_rising") & (F.col("year") == F.col("_last"))))
            .withColumn("reason", F.when(F.col("_high") & F.col("_rising"), "both")
                        .when(F.col("_high"), "high").otherwise("rising"))
            .drop("_rising", "_high", "_last", "rest_positives"))


def top_values(rows, column):
    """The most common real values of a text column per gene, as JSON."""
    real = rows.filter(is_real(column)).withColumn("value", F.lower(F.trim(F.col(column))))
    counted = real.groupBy("gene", "value").agg(F.count("*").alias("isolates"))
    rank = F.row_number().over(Window.partitionBy("gene").orderBy(F.desc("isolates"), "value"))
    top = counted.withColumn("_rank", rank).filter(F.col("_rank") <= TOP_SOURCES)
    return top.groupBy("gene").agg(
        F.to_json(F.sort_array(F.collect_list(F.struct("_rank", "value", "isolates")))).alias(f"top_{column}"))


def gene_summary(genes, isolates, seen):
    """Per-gene totals, drug class, where it was found and what it was isolated from."""
    def names(column):
        return F.array_join(F.array_sort(F.collect_set(column)), " | ")

    totals = genes.groupBy("gene").agg(
        F.first("family", ignorenulls=True).alias("family"), F.countDistinct("biosample_acc").alias("isolates"),
        F.countDistinct("country").alias("countries"), names("organism_label").alias("organisms"),
        names("drug_class").alias("drug_class"), names("drug_subclass").alias("drug_subclass"),
        names("gene_type").alias("gene_types"), names("match_source").alias("match_sources"))
    first = (seen.filter((F.col("organism") == ALL_ORGANISMS) & (F.col("level") == "gene")).groupBy("gene")
             .agg(F.min("first_year").alias("first_year"), F.min("established_year").alias("established_year")))
    details = isolates.select("biosample_acc", "organism", "epi_type", "host", "isolation_source")
    rows = genes.select("biosample_acc", "organism", "gene").distinct().join(details, ["biosample_acc", "organism"])
    result = totals.join(first, "gene", "left")
    for column in ["epi_type", "host", "isolation_source"]:
        result = result.join(top_values(rows, column), "gene", "left")
    return result


def source_view(isolates, genes, source):
    """Keep one isolate type. Genes follow their isolates, and the denominator is that type only."""
    chosen = isolates.filter(F.col("epi_type") == source)
    return chosen, genes.join(chosen.select("biosample_acc", "organism"), ["biosample_acc", "organism"], "left_semi")


def pool_years(frame, bounds):
    """Replace year with the last year of its three-year period, anchored on the provisional start."""
    anchor = bounds["provisional_from"]
    start = F.lit(anchor) + 3 * F.floor((F.col("year") - anchor) / 3)
    # F.least skips empty values, so an unknown year must stay empty rather than become the latest year.
    period_end = F.least(start + 2, F.lit(bounds["latest_year"])).cast("int")
    return frame.withColumn("year", F.when(F.col("year").isNotNull(), period_end))


def period_columns(table, bounds):
    """Rename the pooled year to period_end and add period_start."""
    anchor = bounds["provisional_from"]
    start = F.lit(anchor) + 3 * F.floor((F.col("year") - anchor) / 3)
    return table.withColumn("period_start", start.cast("int")).withColumnRenamed("year", "period_end")


def cluster_watch(isolates, genes, intrinsic, bounds):
    """Clusters with recent records, seen in at least two countries. Says nothing about routes."""
    start = bounds["early_warning_from"]
    recent = F.col("year") >= start
    keys = ["organism", "organism_label", "cluster_id"]
    clusters = (usable(isolates).filter(F.col("cluster_id").isNotNull()).groupBy(keys)
                .agg(F.min("year").alias("first_year"), F.max("year").alias("last_year"), F.count("*").alias("isolates"),
                     F.sum(F.when(recent, 1).otherwise(0)).alias("recent_isolates"),
                     F.array_join(F.array_sort(F.collect_set("country")), " | ").alias("countries"),
                     F.countDistinct("country").alias("country_count"),
                     F.countDistinct(F.when(recent, F.col("country"))).alias("recent_country_count")))
    watched = clusters.filter((F.col("last_year") >= start) & (F.col("country_count") >= 2))
    acquired = (typed_last_resort(genes.filter(F.col("cluster_id").isNotNull()), intrinsic)
                .filter(F.col("mechanism") == "acquired").groupBy("organism", "cluster_id")
                .agg(F.array_join(F.array_sort(F.collect_set("gene")), " | ").alias("last_resort_genes")))
    return (watched.join(acquired, ["organism", "cluster_id"], "left")
            .withColumn("acquired_last_resort", F.col("last_resort_genes").isNotNull())
            .withColumn("new_since_window", F.col("first_year") >= start)
            .withColumn("provisional", F.lit(True)))


def drug_key(column):
    """A name that matches across sources: lower case, with combination parts sorted."""
    parts = F.split(F.regexp_replace(F.lower(F.trim(column)), r"[\s/+-]+", "+"), r"\+")
    return F.array_join(F.array_sort(parts), "+")


def lab_calls(ast):
    """One result per isolate and antibiotic. Mixed R and S results are left out, not guessed.

    Takes biosample_acc, organism and AST_phenotypes. Only R, NS and S are used. ND means not
    determined, and I and DD are neither resistant nor susceptible.
    """
    entries = (ast.filter(F.col("AST_phenotypes").isNotNull())
               .withColumn("_entry", F.explode(F.split(F.regexp_replace("AST_phenotypes", '"', ""), ",")))
               .withColumn("antibiotic", F.lower(F.trim(F.regexp_extract("_entry", r"^(.*)=[^=]*$", 1))))
               .withColumn("_call", F.trim(F.regexp_extract("_entry", r"=([^=]*)$", 1)))
               .filter(F.col("antibiotic") != ""))
    grouped = (entries.groupBy("biosample_acc", "organism", "antibiotic")
               .agg(F.max(F.col("_call").isin(RESISTANT_CALLS)).alias("_r"),
                    F.max(F.col("_call").isin(SUSCEPTIBLE_CALLS)).alias("_s")))
    return grouped.filter(F.col("_r") != F.col("_s")).withColumn("resistant", F.col("_r")).drop("_r", "_s")


def gene_lab_agreement(calls, genes, settings):
    """How often isolates with and without a gene were lab-resistant to each antibiotic.

    Evidence on how far a gene can be trusted, not a statement that any drug will work.
    """
    tested = calls.groupBy("organism", "antibiotic").agg(
        F.count("*").alias("tested"), F.sum(F.col("resistant").cast("int")).alias("tested_resistant"))
    results = []
    for level in ["gene", "family"]:
        carriers = genes.select("biosample_acc", "organism", F.col(level).alias("name")).distinct()
        counted = (carriers.join(calls, ["biosample_acc", "organism"]).groupBy("organism", "name", "antibiotic")
                   .agg(F.count("*").alias("with_gene"), F.sum(F.col("resistant").cast("int")).alias("with_gene_resistant")))
        results.append(counted.withColumn("level", F.lit(level)))
    rows = results[0].unionByName(results[1]).join(tested, ["organism", "antibiotic"])
    rows = (rows.withColumn("without_gene", F.col("tested") - F.col("with_gene"))
            .withColumn("without_gene_resistant", F.col("tested_resistant") - F.col("with_gene_resistant"))
            .withColumnRenamed("name", "gene"))
    for prefix in ["with_gene", "without_gene"]:
        low, high = wilson_limits(f"{prefix}_resistant", prefix)
        enough = F.col(prefix) >= settings["min_sample"]
        rows = (rows.withColumn(f"{prefix}_rate", F.when(enough, F.col(f"{prefix}_resistant") / F.col(prefix)))
                .withColumn(f"{prefix}_ci_low", F.when(enough, low)).withColumn(f"{prefix}_ci_high", F.when(enough, high)))
    return rows


def add_aware(table, aware):
    """Attach the WHO AWaRe group. Antibiotics not on the list, such as veterinary ones, stay empty."""
    keyed = aware.select(F.col("key").alias("_key"), F.col("category").alias("aware_category"), F.col("name").alias("who_name"))
    return table.withColumn("_key", drug_key(F.col("antibiotic"))).join(F.broadcast(keyed), "_key", "left").drop("_key")


def lab_coverage(calls, isolates):
    """Which isolates have lab results, because they are not a random sample."""
    tested = calls.select("biosample_acc", "organism").distinct().join(isolates, ["biosample_acc", "organism"])
    result = {"isolates_with_results": tested.count(), "antibiotic_results": calls.count()}
    for name, column in [("by_organism", "organism"), ("by_source", "epi_type")]:
        result[name] = {str(r[column]): r["count"] for r in tested.groupBy(column).count().collect()}
    top = tested.groupBy("country").count().orderBy(F.desc("count")).limit(5).collect()
    result["top_countries"] = {str(r["country"]): r["count"] for r in top}
    return result


def read_lab_results(spark, organism):
    """Read lab results from each organism's source table, keeping only the needed columns."""
    frames = []
    for row in read_organisms(organism):
        if organism and row["organism"] != organism:
            continue
        table = spark.read.parquet(str(PARQUET / "amr" / row["organism"]))
        frames.append(table.select("biosample_acc", "AST_phenotypes").withColumn("organism", F.lit(row["organism"])))
    result = frames[0]
    for frame in frames[1:]:
        result = result.unionByName(frame)
    return result.filter(~F.upper(F.trim(F.col("AST_phenotypes"))).isin("NULL", "", "MISSING"))


def output_dir(organism):
    """A single-organism run must not replace the full results, unless an import named its own folder."""
    return DEV_RESULTS if organism and not redirected() else RESULTS


def write_table(frame, name, folder=RESULTS):
    """Write one Parquet part in a folder pandas can open, and return its row count."""
    path = folder / f"{name}.parquet"
    frame.coalesce(1).write.mode("overwrite").parquet(str(path))
    for extra in Path(path).glob(".*.crc"):
        extra.unlink()
    written = frame.sparkSession.read.parquet(str(path)).count()
    print(f"{name}: {written} rows", flush=True)
    return written


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organism", help="Process one organism only")
    args = parser.parse_args()

    spark = (SparkSession.builder.appName("analytics").config("spark.sql.shuffle.partitions", "16")
             .config("spark.hadoop.mapreduce.fileoutputcommitter.marksuccessfuljobs", "false").getOrCreate())
    spark.sparkContext.setLogLevel("WARN")
    settings = load_settings()
    isolates = spark.read.parquet(str(PARQUET / "isolates"))
    raw_genes = spark.read.parquet(str(PARQUET / "isolate_genes"))
    keep = [args.organism] if args.organism else core_organisms()
    isolates = isolates.filter(F.col("organism").isin(keep))
    raw_genes = raw_genes.filter(F.col("organism").isin(keep))
    catalog = spark.read.parquet(str(PARQUET / "reference" / "gene_catalog")).cache()
    isolates = isolates.cache()
    genes = add_family(raw_genes, family_map(catalog)).cache()
    bounds = windows(settings, usable(isolates).agg(F.max("year")).first()[0])
    intrinsic = intrinsic_alleles(catalog, settings)
    counts = {}

    out = output_dir(args.organism)

    def save(frame, name):
        counts[name] = write_table(frame, name, out)
        return spark.read.parquet(str(out / f"{name}.parquet"))

    cover = save(coverage(isolates, bounds), "coverage")
    pooled_isolates, pooled_genes = pool_years(isolates, bounds), pool_years(genes, bounds)
    for adjusted, suffix in [(False, ""), (True, "_adjusted")]:
        rates = save(prevalence(isolates, genes, settings, bounds, adjusted), f"prevalence{suffix}")
        last = save(last_resort(isolates, genes, intrinsic, settings, bounds, adjusted), f"last_resort{suffix}")
        gene = gene_rates(isolates, genes, settings, bounds, adjusted)
        trends = save(rising(rates, last, gene, settings, bounds), f"rising{suffix}")
        save(hotspots(rates, trends, settings, bounds), f"hotspots{suffix}")

        pooled_rates = prevalence(pooled_isolates, pooled_genes, settings, bounds, adjusted)
        pooled_last = last_resort(pooled_isolates, pooled_genes, intrinsic, settings, bounds, adjusted)
        save(period_columns(pooled_rates, bounds), f"prevalence_pooled{suffix}")
        save(period_columns(pooled_last, bounds), f"last_resort_pooled{suffix}")

        by_source = {"prevalence": [], "last_resort": [], "rising": []}
        for source in SOURCES:
            chosen, chosen_genes = source_view(isolates, genes, source)
            source_rates = prevalence(chosen, chosen_genes, settings, bounds, adjusted)
            source_last = last_resort(chosen, chosen_genes, intrinsic, settings, bounds, adjusted)
            source_trends = rising(source_rates, source_last, None, settings, bounds)
            for name, frame in [("prevalence", source_rates), ("last_resort", source_last), ("rising", source_trends)]:
                by_source[name].append(frame.withColumn("epi_type", F.lit(source)))
        for name, frames in by_source.items():
            save(frames[0].unionByName(frames[1]), f"{name}_by_source{suffix}")

    yearly = yearly_gene_counts(genes).cache()
    seen = save(first_seen(yearly, settings), "first_seen")
    save(early_warnings(yearly, seen, cover, settings, bounds), "early_warnings")
    save(gene_summary(genes, isolates, seen), "gene_summary")
    save(cluster_watch(isolates, genes, intrinsic, bounds), "cluster_watch")

    kept = isolates.select("biosample_acc", "organism")
    lab = read_lab_results(spark, args.organism).join(kept, ["biosample_acc", "organism"], "left_semi")
    calls = lab_calls(lab).cache()
    agreement = gene_lab_agreement(calls, genes, settings)
    if AWARE.exists():
        agreement = add_aware(agreement, spark.read.csv(str(AWARE), header=True))
    save(agreement, "gene_lab_agreement")

    if not args.organism:
        summary = json.loads(SUMMARY.read_text())
        summary["analytics"] = {
            "rows": counts,
            "years": bounds,
            "isolates_without_epi_type": isolates.filter(F.col("epi_type").isNull()).count(),
            "lab_results": lab_coverage(calls, isolates),
        }
        SUMMARY.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    spark.stop()


if __name__ == "__main__":
    main()
