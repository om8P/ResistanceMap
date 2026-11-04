"""Hand-checked cases for the Session 3 additions in src/analytics.py and src/method_check.py."""
import pytest
from pyspark.sql import functions as F

import analytics as A
import method_check as M
from test_analytics import (BOUNDS, LOW_SAMPLE, SETTINGS, TREND_SCHEMA, gene_row, genes_frame, isolate, isolates_frame,
                            one, prevalence_frame)

INTRINSIC_SCHEMA = "organism string, gene string, _intrinsic boolean"
COLISTIN = {"cls": "COLISTIN", "sub": "COLISTIN"}


def hotspots_for_a(spark, rows):
    # Country B is large, with a rate of 10% every year. Country A's count is given for each year.
    expanded = []
    for year, positives in rows:
        expanded += [("A", year, 100, positives), ("B", year, 1000, 100)]
    table = A.hotspots(prevalence_frame(spark, expanded), spark.createDataFrame([], TREND_SCHEMA), SETTINGS, BOUNDS)
    return table.filter(F.col("country") == "A").collect()


def test_two_years_running_are_persistent(spark):
    rows = hotspots_for_a(spark, [(2019, 60), (2020, 60)])
    assert len(rows) == 2 and all(r["persistent"] for r in rows)


def test_a_missing_year_breaks_persistence(spark):
    rows = hotspots_for_a(spark, [(2018, 60), (2020, 60)])
    assert len(rows) == 2 and not any(r["persistent"] for r in rows)


def test_a_low_year_between_breaks_persistence(spark):
    rows = hotspots_for_a(spark, [(2018, 60), (2019, 10), (2020, 60)])
    assert sorted(r["year"] for r in rows) == [2018, 2020] and not any(r["persistent"] for r in rows)


def test_source_view_uses_only_that_type_as_denominator(spark):
    other = list(isolate("e0"))
    other[7] = "environmental/other"
    missing = list(isolate("m0"))
    missing[7] = None
    isolates = isolates_frame(spark, [isolate(f"c{i}") for i in range(30)] + [tuple(other), tuple(missing)])
    genes = genes_frame(spark, [gene_row("c0"), gene_row("e0"), gene_row("m0")])
    chosen, chosen_genes = A.source_view(isolates, genes, "clinical")
    row = one(A.prevalence(chosen, chosen_genes, SETTINGS, BOUNDS))
    assert (row["n"], row["positives"]) == (30, 1)


def dual_table(spark, adjusted=False):
    names = [("both", "P1"), ("c1", "P1"), ("c2", "P1"), ("alone", "P2"), ("other", "P2")]
    isolates = isolates_frame(spark, [isolate(i, cluster=c) for i, c in names])
    genes = genes_frame(spark, [
        gene_row("both", "blaNDM-1", cluster="P1"), gene_row("both", "mcr-1.1", cluster="P1", **COLISTIN),
        gene_row("alone", "blaNDM-1", cluster="P2"), gene_row("other", "mcr-1.1", cluster="P2", **COLISTIN),
        gene_row("c1", "blaKPC-2", cluster="P1"),
        gene_row("c2", "oprD_Q1", gene_type="POINT", source="disrupt", cluster="P1"),
    ])
    intrinsic = spark.createDataFrame([("Acinetobacter", "blaOXA-66", True)], INTRINSIC_SCHEMA)
    return A.last_resort(isolates, genes, intrinsic, LOW_SAMPLE, BOUNDS, adjusted)


def test_dual_needs_both_genes_in_one_isolate(spark):
    row = one(dual_table(spark), drug=A.BOTH_DRUGS, mechanism="acquired")
    assert (row["positives"], row["n"]) == (1, 5)


def test_dual_adjusted_does_not_combine_isolates_in_a_cluster(spark):
    # P2 has carbapenem in one isolate and colistin in another, so only P1 counts.
    row = one(dual_table(spark, True), drug=A.BOTH_DRUGS, mechanism="acquired")
    assert (row["positives"], row["n"]) == (1, 2)


def test_dual_acquired_needs_both_to_be_acquired(spark):
    isolates = isolates_frame(spark, [isolate("x")])
    genes = genes_frame(spark, [gene_row("x", "oprD_Q1", gene_type="POINT", source="disrupt"), gene_row("x", "mcr-1.1", **COLISTIN)])
    intrinsic = spark.createDataFrame([("Acinetobacter", "blaOXA-66", True)], INTRINSIC_SCHEMA)
    table = A.last_resort(isolates, genes, intrinsic, LOW_SAMPLE, BOUNDS)
    assert one(table, drug=A.BOTH_DRUGS, mechanism="acquired")["positives"] == 0
    assert one(table, drug=A.BOTH_DRUGS, mechanism=A.ANY_MECHANISM)["positives"] == 1


def test_pooling_periods_including_a_short_final_one(spark):
    years = [2019, 2020, 2022, 2023, 2025, 2026]
    rows = isolates_frame(spark, [isolate(f"s{y}", year=y) for y in years])
    genes = genes_frame(spark, [gene_row(f"s{y}", year=y) for y in years])
    pooled = A.prevalence(A.pool_years(rows, BOUNDS), A.pool_years(genes, BOUNDS), LOW_SAMPLE, BOUNDS)
    table = A.period_columns(pooled, BOUNDS).collect()
    assert sorted((r["period_start"], r["period_end"], r["n"]) for r in table) == [
        (2017, 2019, 1), (2020, 2022, 2), (2023, 2025, 2), (2026, 2026, 1)]
    assert {r["period_end"]: r["provisional"] for r in table} == {2019: False, 2022: False, 2025: True, 2026: True}


def test_pooling_keeps_an_unknown_year_out_of_every_period(spark):
    rows = isolates_frame(spark, [isolate("known", year=2026), isolate("unknown", year=None)])
    genes = genes_frame(spark, [gene_row("known", year=2026), gene_row("unknown", year=None)])
    row = one(A.prevalence(A.pool_years(rows, BOUNDS), A.pool_years(genes, BOUNDS), LOW_SAMPLE, BOUNDS))
    assert (row["year"], row["n"], row["positives"]) == (2026, 1, 1)


def test_pooling_three_small_years_reach_the_minimum(spark):
    rows = [isolate(f"{y}_{i}", year=y) for y in (2020, 2021, 2022) for i in range(10)]
    genes = [gene_row("2020_0", year=2020)]
    pooled = A.prevalence(A.pool_years(isolates_frame(spark, rows), BOUNDS), A.pool_years(genes_frame(spark, genes), BOUNDS), SETTINGS, BOUNDS)
    row = one(pooled)
    assert row["n"] == 30 and row["rate"] == pytest.approx(1 / 30)


def test_pooling_counts_a_cluster_once_across_its_years(spark):
    rows = [isolate("a", year=2020, cluster="P1"), isolate("b", year=2021, cluster="P1"), isolate("c", year=2022)]
    genes = [gene_row("a", year=2020, cluster="P1"), gene_row("b", year=2021, cluster="P1")]
    row = one(A.prevalence(A.pool_years(isolates_frame(spark, rows), BOUNDS), A.pool_years(genes_frame(spark, genes), BOUNDS),
                           LOW_SAMPLE, BOUNDS, adjusted=True))
    assert (row["n"], row["positives"]) == (2, 1)


def test_cluster_watch(spark):
    intrinsic = spark.createDataFrame([("Acinetobacter", "blaOXA-66", True)], INTRINSIC_SCHEMA)
    rows = [isolate("a", country="India", year=2024, cluster="KEEP"), isolate("b", country="Peru", year=2020, cluster="KEEP"),
            isolate("c", country="India", year=2025, cluster="ONE"), isolate("d", country="India", year=2025, cluster="ONE"),
            isolate("e", country="India", year=2015, cluster="OLD"), isolate("f", country="Peru", year=2016, cluster="OLD"),
            isolate("g", country="India", year=2025, cluster="NEW"), isolate("h", country="Peru", year=2024, cluster="NEW")]
    genes = genes_frame(spark, [gene_row("a", "blaNDM-1", country="India", year=2024, cluster="KEEP"),
                                gene_row("g", "tetA", cls="TETRACYCLINE", sub="TETRACYCLINE", country="India", year=2025, cluster="NEW")])
    table = A.cluster_watch(isolates_frame(spark, rows), genes, intrinsic, BOUNDS)
    assert {r["cluster_id"] for r in table.collect()} == {"KEEP", "NEW"}
    keep = one(table, cluster_id="KEEP")
    assert keep["acquired_last_resort"] is True and keep["last_resort_genes"] == "blaNDM-1"
    assert keep["new_since_window"] is False
    assert (keep["countries"], keep["country_count"], keep["recent_country_count"], keep["recent_isolates"]) == ("India | Peru", 2, 1, 1)
    fresh = one(table, cluster_id="NEW")
    assert fresh["acquired_last_resort"] is False and fresh["new_since_window"] is True


def lab_frame(spark, rows):
    return spark.createDataFrame([(b, "Org", a) for b, a in rows], "biosample_acc string, organism string, AST_phenotypes string")


def test_lab_calls_ignore_undetermined_and_leave_out_conflicts(spark):
    text = '"meropenem=R,meropenem=ND,colistin=S,amikacin=I,gentamicin=R,gentamicin=S,tobramycin=I,tobramycin=S,imipenem=NS,cefepime=DD"'
    table = A.lab_calls(lab_frame(spark, [("a", text), ("b", None)]))
    assert {r["antibiotic"]: r["resistant"] for r in table.collect()} == {
        "meropenem": True, "colistin": False, "tobramycin": False, "imipenem": True}


def test_gene_lab_agreement_by_hand(spark):
    # 30 carriers with results, 24 resistant. 40 without the gene, 4 resistant. One carrier has no result.
    lab = [(f"g{i}", f'"meropenem={"R" if i < 24 else "S"}"') for i in range(30)]
    lab += [(f"n{i}", f'"meropenem={"R" if i < 4 else "S"}"') for i in range(40)]
    genes = genes_frame(spark, [gene_row(f"g{i}", "blaNDM-1", family="blaNDM") for i in range(31)])
    table = A.gene_lab_agreement(A.lab_calls(lab_frame(spark, lab)), genes, SETTINGS)
    row = one(table, level="gene")
    assert (row["with_gene"], row["with_gene_resistant"], row["without_gene"], row["without_gene_resistant"]) == (30, 24, 40, 4)
    assert row["with_gene_rate"] == pytest.approx(0.8) and row["without_gene_rate"] == pytest.approx(0.1)
    assert one(table, level="family")["gene"] == "blaNDM"


def test_agreement_under_minimum_keeps_counts_only(spark):
    lab = [(f"g{i}", '"meropenem=R"') for i in range(29)] + [(f"n{i}", '"meropenem=S"') for i in range(40)]
    genes = genes_frame(spark, [gene_row(f"g{i}", "blaNDM-1") for i in range(29)])
    row = one(A.gene_lab_agreement(A.lab_calls(lab_frame(spark, lab)), genes, SETTINGS), level="gene")
    assert row["with_gene"] == 29 and row["with_gene_rate"] is None and row["without_gene_rate"] == 0.0


def test_aware_matches_combination_names_in_either_order(spark):
    table = spark.createDataFrame([("trimethoprim-sulfamethoxazole",), ("ceftiofur",)], "antibiotic string")
    aware = spark.createDataFrame([("sulfamethoxazole+trimethoprim", "Sulfamethoxazole/trimethoprim", "Access")],
                                  "key string, name string, category string")
    found = {r["antibiotic"]: r["aware_category"] for r in A.add_aware(table, aware).collect()}
    assert found == {"trimethoprim-sulfamethoxazole": "Access", "ceftiofur": None}


def test_output_dir_protects_full_results():
    assert A.output_dir("Klebsiella") == A.DEV_RESULTS
    assert A.output_dir(None) == A.RESULTS
    assert A.DEV_RESULTS != A.RESULTS


def method_isolates(spark, rows):
    return spark.createDataFrame(rows, f"biosample_acc string, organism string, year int, {M.METHOD} string")


def test_method_check_by_hand(spark):
    rows = [(f"c{i}", "Org", 2020, "COMBINED") for i in range(30)] + [(f"n{i}", "Org", 2020, "NUCLEOTIDE") for i in range(30)]
    genes = spark.createDataFrame([(f"c{i}", "Org", "X") for i in range(15)] + [(f"n{i}", "Org", "X") for i in range(3)],
                                  "biosample_acc string, organism string, drug_class string")
    isolates = method_isolates(spark, rows)
    assert all(r["share"] == pytest.approx(0.5) for r in M.method_shares(isolates).collect())
    gap = one(M.within_year_gaps(M.method_rates(isolates, genes, 30)))
    assert gap["gap_points"] == pytest.approx(40.0) and gap["methods"] == 2


def test_method_check_skips_small_method_groups(spark):
    rows = [(f"c{i}", "Org", 2020, "COMBINED") for i in range(30)] + [(f"n{i}", "Org", 2020, "NUCLEOTIDE") for i in range(29)]
    genes = spark.createDataFrame([("c0", "Org", "X")], "biosample_acc string, organism string, drug_class string")
    assert M.within_year_gaps(M.method_rates(method_isolates(spark, rows), genes, 30)).count() == 0
