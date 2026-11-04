"""Hand-checked cases for src/analytics.py. Expected values are worked out by hand."""
import pytest
from pyspark.sql import functions as F

import analytics as A

ISOLATE_COLUMNS = ["biosample_acc", "organism", "organism_label", "country", "iso3", "year", "cluster_id",
                   "epi_type", "host", "isolation_source"]
GENE_COLUMNS = ["biosample_acc", "gene", "gene_type", "drug_class", "drug_subclass", "match_source", "organism",
                "organism_label", "country", "iso3", "year", "cluster_id", "family"]
SETTINGS = {"min_sample": 30, "provisional_years": 4, "early_warning_years": 3, "support_isolates": 3,
            "support_clusters": 2, "baseline_isolates": 30, "hotspot_margin_points": 10, "rising_years": 10,
            "rising_min_years": 5, "rising_min_gene_positives": 10, "rising_z": 1.96,
            "intrinsic": [{"organism": "Acinetobacter", "product_prefix": "OXA-51 family"}]}
BOUNDS = A.windows(SETTINGS, 2026)
LOW_SAMPLE = dict(SETTINGS, min_sample=1)


def schema(columns):
    return ", ".join(f"{c} {'int' if c == 'year' else 'string'}" for c in columns)


def iso3(country):
    return country[:3].upper() if country else None


def isolate(accession, organism="Org", country="India", year=2020, cluster=None):
    return (accession, organism, organism, country, iso3(country), year, cluster, "clinical", "human", "blood")


def gene_row(accession, gene="g1", cls="BETA-LACTAM", sub="CARBAPENEM", gene_type="COMPLETE", source="allele",
             organism="Org", country="India", year=2020, cluster=None, family=None):
    return (accession, gene, gene_type, cls, sub, source, organism, organism, country, iso3(country), year, cluster,
            family or gene)


def isolates_frame(spark, rows):
    return spark.createDataFrame(rows, schema(ISOLATE_COLUMNS))


def genes_frame(spark, rows):
    return spark.createDataFrame(rows, schema(GENE_COLUMNS))


def one(frame, **filters):
    for column, value in filters.items():
        frame = frame.filter(F.col(column) == value)
    rows = frame.collect()
    assert len(rows) == 1, rows
    return rows[0]


def test_windows_match_the_agreed_years():
    assert BOUNDS["provisional_from"] == 2023
    assert BOUNDS["early_warning_from"] == 2024
    assert (BOUNDS["rising_from"], BOUNDS["rising_to"]) == (2013, 2022)


@pytest.mark.parametrize("k,n,low,high", [(5, 10, 0.2366, 0.7634), (0, 10, 0.0, 0.2775), (10, 10, 0.7225, 1.0)])
def test_wilson_limits(spark, k, n, low, high):
    frame = spark.createDataFrame([(k, n)], "positives int, n int")
    lower, upper = A.wilson_limits("positives", "n")
    row = frame.select(lower.alias("l"), upper.alias("u")).first()
    assert row["l"] == pytest.approx(low, abs=1e-4)
    assert row["u"] == pytest.approx(high, abs=1e-4)


def test_split_drugs_splits_merges_and_skips(spark):
    frame = spark.createDataFrame([("A/B",), ("FUSIDIC ACID",), ("FUSIDIC_ACID",), ("NONE",), (None,)], "drug_class string")
    assert sorted(r[0] for r in A.split_drugs(frame).collect()) == ["A", "B", "FUSIDIC_ACID", "FUSIDIC_ACID"]


def test_denominator_counts_isolates_with_no_genes_and_repeats_count_once(spark):
    isolates = isolates_frame(spark, [isolate(f"s{i}") for i in range(40)])
    genes = genes_frame(spark, [gene_row("s0", "g1"), gene_row("s0", "g2"), gene_row("s1", "g3", cls="A/BETA-LACTAM")])
    table = A.prevalence(isolates, genes, SETTINGS, BOUNDS)
    row = one(table, drug_class="BETA-LACTAM")
    assert (row["positives"], row["n"]) == (2, 40)
    assert row["rate"] == pytest.approx(0.05)
    assert one(table, drug_class="A")["positives"] == 1


def test_zero_rate_gets_a_row(spark):
    rows = [isolate(f"a{i}") for i in range(30)] + [isolate(f"b{i}", country="Peru") for i in range(30)]
    row = one(A.prevalence(isolates_frame(spark, rows), genes_frame(spark, [gene_row("a0")]), SETTINGS, BOUNDS), country="Peru")
    assert (row["positives"], row["n"], row["rate"]) == (0, 30, 0.0)
    assert row["ci_high"] > 0


@pytest.mark.parametrize("size,shown", [(29, False), (30, True)])
def test_minimum_sample_hides_rate_but_keeps_counts(spark, size, shown):
    isolates = isolates_frame(spark, [isolate(f"s{i}") for i in range(size)])
    row = one(A.prevalence(isolates, genes_frame(spark, [gene_row("s0")]), SETTINGS, BOUNDS))
    assert row["n"] == size and row["positives"] == 1
    assert (row["rate"] is not None) == shown and (row["ci_low"] is not None) == shown
    assert row["meets_min_sample"] == shown


def test_rows_without_country_or_year_are_left_out_of_prevalence_only(spark):
    isolates = isolates_frame(spark, [isolate("a"), isolate("b", country=None), isolate("c", year=None)])
    genes = genes_frame(spark, [gene_row("a")])
    assert one(A.prevalence(isolates, genes, LOW_SAMPLE, BOUNDS))["n"] == 1
    assert A.coverage(isolates, BOUNDS).agg(F.sum("isolates")).first()[0] == 3


def test_provisional_starts_in_2023(spark):
    isolates = isolates_frame(spark, [isolate("a", year=2022), isolate("b", year=2023)])
    genes = genes_frame(spark, [gene_row("a", year=2022), gene_row("b", year=2023)])
    table = A.prevalence(isolates, genes, LOW_SAMPLE, BOUNDS)
    assert one(table, year=2022)["provisional"] is False
    assert one(table, year=2023)["provisional"] is True


def test_outbreak_adjustment_counts_a_cluster_once(spark):
    outbreak = [isolate(f"o{i}", cluster="PDS1") for i in range(5)]
    singles = [isolate(f"s{i}") for i in range(5)]
    genes = genes_frame(spark, [gene_row(f"o{i}", cluster="PDS1") for i in range(5)])
    isolates = isolates_frame(spark, outbreak + singles)
    raw = one(A.prevalence(isolates, genes, LOW_SAMPLE, BOUNDS))
    adjusted = one(A.prevalence(isolates, genes, LOW_SAMPLE, BOUNDS, adjusted=True))
    assert (raw["positives"], raw["n"]) == (5, 10)
    assert (adjusted["positives"], adjusted["n"]) == (1, 6)


def test_family_uses_finer_oxa_name_and_keeps_bare_names(spark):
    catalog = spark.createDataFrame(
        [("blaOXA-48", "blaOXA", "OXA-48 family carbapenem-hydrolyzing class D beta-lactamase OXA-48", "AMR"),
         ("blaNDM-5", "blaNDM", "subclass B1 metallo-beta-lactamase NDM-5", "AMR")],
        "allele string, gene_family string, product_name string, type string")
    genes = genes_frame(spark, [gene_row("a", "blaOXA-48"), gene_row("a", "blaNDM-5"), gene_row("a", "blaNDM"),
                                gene_row("a", "gyrA_S83L", gene_type="POINT")]).drop("family")
    found = {r["gene"]: r["family"] for r in A.add_family(genes, A.family_map(catalog)).collect()}
    assert found == {"blaOXA-48": "blaOXA-48 family", "blaNDM-5": "blaNDM", "blaNDM": "blaNDM", "gyrA_S83L": "gyrA"}


def seen_for(spark, rows):
    counts = A.yearly_gene_counts(genes_frame(spark, rows))
    return counts, A.first_seen(counts, SETTINGS)


def test_lone_old_record_does_not_set_established_year(spark):
    rows = [gene_row("old", year=1943)] + [gene_row(f"n{i}", year=2010) for i in range(2)]
    row = one(seen_for(spark, rows)[1], level="gene", organism="Org")
    assert (row["first_year"], row["established_year"], row["first_year_isolates"]) == (1943, 2010, 1)


def test_three_isolates_in_one_cluster_are_not_enough(spark):
    seen = seen_for(spark, [gene_row(f"c{i}", cluster="PDS1") for i in range(3)])[1]
    assert one(seen, level="gene", organism="Org")["established_year"] is None


def test_support_builds_across_years(spark):
    rows = [gene_row("a", year=2015, cluster="P1"), gene_row("b", year=2016, cluster="P1"), gene_row("c", year=2018, cluster="P2")]
    row = one(seen_for(spark, rows)[1], level="gene", organism="Org")
    assert (row["established_year"], row["isolates"], row["clusters"]) == (2018, 3, 2)


def test_all_organisms_scope_combines_support(spark):
    rows = [gene_row("a", organism="X", year=2015), gene_row("b", organism="Y", year=2016), gene_row("c", organism="Y", year=2017)]
    seen = seen_for(spark, rows)[1]
    row = one(seen, level="gene", organism=A.ALL_ORGANISMS)
    assert (row["first_year"], row["established_year"]) == (2015, 2017)
    assert one(seen, level="gene", organism="X")["established_year"] is None


def warnings_for(spark, gene_rows, isolate_rows):
    counts, seen = seen_for(spark, gene_rows)
    cover = A.coverage(isolates_frame(spark, isolate_rows), BOUNDS)
    return A.early_warnings(counts, seen, cover, SETTINGS, BOUNDS)


def arrival(gene="g1", country="India", organism="Org", **kwargs):
    return [gene_row(f"{gene}{country}{i}", gene, year=2025, country=country, organism=organism, **kwargs) for i in range(3)]


def test_true_arrival_is_not_flagged_as_new_sequencing(spark):
    baseline = [isolate(f"b{i}", year=2020) for i in range(30)]
    row = one(warnings_for(spark, arrival(), baseline), level="gene")
    assert row["new_sequencing"] is False and row["baseline_isolates"] == 30
    assert (row["recent_isolates"], row["recent_clusters"], row["earlier_records"]) == (3, 3, 0)
    assert row["first_in_country_any_organism"] is True and row["provisional"] is True


def test_country_that_just_started_sequencing_is_flagged(spark):
    row = one(warnings_for(spark, arrival(), [isolate(f"b{i}", year=2020) for i in range(29)]), level="gene")
    assert row["new_sequencing"] is True and row["baseline_isolates"] == 29


def test_lone_earlier_record_is_reported_without_voiding_the_baseline(spark):
    rows = arrival() + [gene_row("old", year=1984)]
    baseline = [isolate(f"b{i}", year=2020) for i in range(30)]
    row = one(warnings_for(spark, rows, baseline), level="gene")
    assert row["earlier_records"] == 1 and row["first_year"] == 1984
    assert row["new_sequencing"] is False and row["first_recent_year"] == 2025


def test_gene_already_established_is_not_a_warning(spark):
    rows = arrival() + [gene_row(f"e{i}", year=2015) for i in range(3)]
    assert warnings_for(spark, rows, [isolate("b", year=2010)]).count() == 0


def test_one_cluster_and_point_mutations_are_not_warnings(spark):
    clustered = [gene_row(f"c{i}", year=2025, cluster="P1") for i in range(3)]
    point = arrival("gyrA_S83L", gene_type="POINT")
    assert warnings_for(spark, clustered + point, [isolate("b", year=2010)]).count() == 0


def test_seen_earlier_in_another_organism_is_marked(spark):
    rows = arrival(organism="Org") + [gene_row("x", organism="Other", year=2010)]
    row = one(warnings_for(spark, rows, [isolate("b", year=2010)]), level="gene", organism="Org")
    assert row["first_in_country_any_organism"] is False


def test_last_resort_mechanisms_and_any_is_not_a_sum(spark):
    intrinsic = spark.createDataFrame([("Acinetobacter", "blaOXA-66", True)], "organism string, gene string, _intrinsic boolean")
    isolates = isolates_frame(spark, [isolate(f"s{i}", organism=o) for i, o in enumerate(["Acinetobacter"] * 3 + ["Org"])])
    acin = dict(organism="Acinetobacter")
    genes = genes_frame(spark, [
        gene_row("s0", "blaOXA-66", **acin),
        gene_row("s1", "blaOXA-23", sub="CARBAPENEM/SULBACTAM-DURLOBACTAM", **acin),
        gene_row("s1", "oprD_Q1", gene_type="POINT", source="disrupt", **acin),
        gene_row("s1", "ompA_X1", gene_type="POINT", source="mutation", **acin),
        gene_row("s2", "blaTEM-1", sub="BETA-LACTAM", **acin),
        gene_row("s3", "blaOXA-66", organism="Org"),
        gene_row("s3", "mcr-1.1", cls="COLISTIN", sub="COLISTIN", organism="Org"),
    ])
    table = A.last_resort(isolates, genes, intrinsic, LOW_SAMPLE, BOUNDS)

    def positives(organism, mechanism, drug="CARBAPENEM"):
        return one(table, organism=organism, mechanism=mechanism, drug=drug)["positives"]

    assert positives("Acinetobacter", "intrinsic") == 1
    assert positives("Acinetobacter", "acquired") == 1
    assert positives("Acinetobacter", "disrupted") == 1
    assert positives("Acinetobacter", "mutation") == 1
    assert positives("Acinetobacter", A.ANY_MECHANISM) == 1
    assert positives("Acinetobacter", "acquired", "COLISTIN") == 0
    assert positives("Org", "acquired") == 1
    assert positives("Org", "intrinsic") == 0
    assert positives("Org", "acquired", "COLISTIN") == 1


def test_intrinsic_comes_from_product_name(spark):
    catalog = spark.createDataFrame(
        [("blaOXA-66", "OXA-51 family carbapenem-hydrolyzing class D beta-lactamase OXA-66", "AMR"),
         ("blaOXA-23", "OXA-23 family carbapenem-hydrolyzing class D beta-lactamase OXA-23", "AMR")],
        "allele string, product_name string, type string")
    rows = A.intrinsic_alleles(catalog, SETTINGS).collect()
    assert [(r["organism"], r["gene"]) for r in rows] == [("Acinetobacter", "blaOXA-66")]


def trend_frame(spark, points):
    rows = [("Org", "Org", "India", "IND", year, n, r, "drug_class", "X") for year, n, r in points]
    return spark.createDataFrame(rows, "organism string, organism_label string, country string, iso3 string, year int, "
                                       "n long, positives long, kind string, value string")


def test_trend_slope_and_z_by_hand(spark):
    # x = 0, 1, 2 with n = 100 each: mean 1, Sxx = 200, T = 10*-1 + 20*0 + 30*1 = 20.
    # p = 0.2, so slope = 20 / 200 = 0.1 (10 points a year) and z = 20 / sqrt(0.16 * 200) = 3.5355.
    row = one(A.trend(trend_frame(spark, [(2013, 100, 10), (2014, 100, 20), (2015, 100, 30)]), SETTINGS, 2013, 2022))
    assert row["slope_points_per_year"] == pytest.approx(10.0)
    assert row["z"] == pytest.approx(3.5355, abs=1e-3)
    assert row["years_used"] == 3
    assert row["rising"] is False  # Fewer than the 5 years needed.


def test_trend_ignores_small_years_and_years_outside_the_window(spark):
    points = [(2012, 500, 0), (2013, 100, 10), (2014, 29, 29), (2015, 100, 20), (2016, 100, 30),
              (2017, 100, 40), (2018, 100, 50), (2023, 500, 500)]
    row = one(A.trend(trend_frame(spark, points), SETTINGS, 2013, 2022))
    assert row["years_used"] == 5 and row["n"] == 500 and row["positives"] == 150
    assert row["rising"] is True


def test_trend_flat_and_all_zero_are_not_rising(spark):
    flat = one(A.trend(trend_frame(spark, [(y, 100, 20) for y in range(2013, 2019)]), SETTINGS, 2013, 2022))
    zero = one(A.trend(trend_frame(spark, [(y, 100, 0) for y in range(2013, 2019)]), SETTINGS, 2013, 2022))
    assert flat["rising"] is False and flat["slope_points_per_year"] == pytest.approx(0, abs=1e-9)
    assert zero["rising"] is False and zero["z"] is None


TREND_SCHEMA = "organism string, country string, kind string, value string, slope_points_per_year double, z double, rising boolean"


def prevalence_frame(spark, rows):
    frame = spark.createDataFrame(
        [("Org", "Org", c, c[:3], y, "X", n, p) for c, y, n, p in rows],
        "organism string, organism_label string, country string, iso3 string, year int, drug_class string, n long, positives long")
    return A.add_rates(frame, SETTINGS, BOUNDS)


def test_hotspot_compares_a_dominant_country_with_the_others(spark):
    # USA 500/1000 and Peru 10/100. The overall rate is 46%, so USA could not flag at 10 points above it.
    table = prevalence_frame(spark, [("USA", 2020, 1000, 500), ("Peru", 2020, 100, 10)])
    row = one(A.hotspots(table, spark.createDataFrame([], TREND_SCHEMA), SETTINGS, BOUNDS))
    assert row["country"] == "USA" and row["reason"] == "high"
    assert row["rest_rate"] == pytest.approx(0.10)


def test_hotspot_needs_the_margin_and_a_big_enough_comparison(spark):
    empty = spark.createDataFrame([], TREND_SCHEMA)
    close = prevalence_frame(spark, [("A", 2020, 1000, 150), ("B", 2020, 1000, 100)])
    assert A.hotspots(close, empty, SETTINGS, BOUNDS).count() == 0
    small_rest = prevalence_frame(spark, [("A", 2020, 1000, 900), ("B", 2020, 29, 0)])
    assert A.hotspots(small_rest, empty, SETTINGS, BOUNDS).count() == 0


def test_hotspot_rising_uses_latest_complete_year(spark):
    table = prevalence_frame(spark, [("A", 2021, 100, 20), ("A", 2022, 100, 25), ("A", 2024, 100, 30),
                                     ("B", 2021, 100, 20), ("B", 2022, 100, 25), ("B", 2024, 100, 30)])
    trends = spark.createDataFrame([("Org", "A", "drug_class", "X", 2.5, 2.0, True)], TREND_SCHEMA)
    row = one(A.hotspots(table, trends, SETTINGS, BOUNDS))
    assert (row["country"], row["year"], row["reason"]) == ("A", 2022, "rising")


def test_gene_rates_keep_zero_years_for_common_genes_only(spark):
    isolates = isolates_frame(spark, [isolate(f"a{i}", year=2015) for i in range(30)] + [isolate(f"b{i}", year=2016) for i in range(30)])
    genes = genes_frame(spark, [gene_row(f"a{i}", "common", year=2015) for i in range(10)] + [gene_row("a0", "rare", year=2015)])
    table = A.gene_rates(isolates, genes, SETTINGS, BOUNDS, False)
    assert {r["gene"] for r in table.collect()} == {"common"}
    assert one(table, year=2016)["positives"] == 0


def test_gene_summary_totals_and_sources(spark):
    isolates = isolates_frame(spark, [isolate("a"), isolate("b", country="Peru"), isolate("c", country="Peru")])
    genes = genes_frame(spark, [gene_row("a"), gene_row("b", country="Peru"), gene_row("c", country="Peru")])
    seen = A.first_seen(A.yearly_gene_counts(genes), SETTINGS)
    row = A.gene_summary(genes, isolates, seen).first()
    assert (row["isolates"], row["countries"], row["first_year"]) == (3, 2, 2020)
    assert '"value":"blood"' in row["top_isolation_source"] and '"isolates":3' in row["top_isolation_source"]
