"""Hand-checked cases for src/genes.py."""
import pytest
from pyspark.sql.types import StringType, StructField, StructType

import genes as G

CATALOG_COLUMNS = ["allele", "gene_family", "whitelisted_taxa", "type", "subtype", "class", "subclass"]
CATALOG = [
    # Allele with one row open to all taxa, in a family with other drugs.
    ("blaOXA-48", "blaOXA", None, "AMR", "AMR", "BETA-LACTAM", "CARBAPENEM"),
    ("blaOXA-1", "blaOXA", None, "AMR", "AMR", "BETA-LACTAM", "CEPHALOSPORIN"),
    # Family-level row.
    (None, "sul1", None, "AMR", "AMR", "SULFONAMIDE", "SULFONAMIDE"),
    # Family with alleles that all agree.
    ("blaTEM-1", "blaTEM", None, "AMR", "AMR", "BETA-LACTAM", "BETA-LACTAM"),
    # Same allele differs by taxon.
    ("gyrA_S83F", "gyrA", "Salmonella", "AMR", "POINT", "QUINOLONE", "SALMONELLA_DRUG"),
    ("gyrA_S83F", "gyrA", "Escherichia", "AMR", "POINT", "QUINOLONE", "ECOLI_DRUG"),
    # Family-level rows, one for the taxon and one open to all.
    (None, "mecA", "Salmonella", "AMR", "AMR", "BETA-LACTAM", "METHICILLIN"),
    (None, "mecA", None, "AMR", "AMR", "BETA-LACTAM", "OTHER"),
    # Family-level rows that disagree on class.
    (None, "cfr", None, "AMR", "AMR", "PHENICOL", "FLORFENICOL"),
    (None, "cfr", None, "AMR", "AMR", "LINCOSAMIDE", "CLINDAMYCIN"),
    # Disrupted gene, for this taxon and for another.
    (None, "ompK35", "Salmonella", "AMR", "POINT_DISRUPT", "BETA-LACTAM", "CARBAPENEM"),
    (None, "cirA", "Escherichia", "AMR", "POINT_DISRUPT", "BETA-LACTAM", "CEFIDEROCOL"),
    # Alleles that share one drug, and one inactive allele.
    ("blaNDM-1", "blaNDM", None, "AMR", "AMR", "BETA-LACTAM", "CARBAPENEM"),
    ("blaNDM-9", "blaNDM", None, "AMR", "AMR", "BETA-LACTAM", "CARBAPENEM/TANIBORBACTAM"),
    ("blaPDC-1", "blaPDC", None, "AMR", "AMR", "BETA-LACTAM", "CEPHALOSPORIN"),
    ("blaPDC-2", "blaPDC", None, "AMR", "AMR", "BETA-LACTAM", "CEFIDEROCOL/CEPHALOSPORIN"),
    ("blaPDC-3", "blaPDC", None, "AMR", "AMR", "NONE", "INACTIVE"),
    # Family-level rows that share one drug.
    (None, "mecC", None, "AMR", "AMR", "BETA-LACTAM", "METHICILLIN"),
    (None, "mecC", None, "AMR", "AMR", "BETA-LACTAM", "CEFTAROLINE/METHICILLIN"),
    # Not resistance, so never used.
    (None, "fimH", None, "VIRULENCE", "VIRULENCE", None, None),
]
MUTATIONS = [
    ("Salmonella", "parC_S80I", "QUINOLONE", "CIPROFLOXACIN"),
    ("Escherichia", "parC_S80R", "QUINOLONE", "OTHER"),
]


@pytest.fixture
def catalog(spark):
    return spark.createDataFrame(CATALOG, StructType([StructField(c, StringType()) for c in CATALOG_COLUMNS]))


@pytest.fixture
def mutations(spark):
    return spark.createDataFrame(MUTATIONS, ["taxgroup", "standard_mutation_symbol", "class", "subclass"])


def isolates(spark, *gene_lists):
    rows = [(f"S{i}", "India", 2020, gene_list) for i, gene_list in enumerate(gene_lists)]
    schema = StructType([StructField("biosample_acc", StringType()), StructField("country", StringType()),
                         StructField("year", StringType()), StructField("AMR_genotypes_core", StringType())])
    return spark.createDataFrame(rows, schema)


def lookup(spark, catalog, mutations, entry, taxon="Salmonella"):
    rows = G.annotate(isolates(spark, f'"{entry}"'), catalog, mutations, taxon)[0].collect()
    assert len(rows) == 1
    return rows[0]["match_source"], rows[0]["drug_class"], rows[0]["drug_subclass"]


def test_parse_splits_genes_and_suffixes(spark):
    frame = isolates(spark, '"blaTEM-1,gyrA_D87G=POINT,sinH=PARTIAL,ampC=HMM,x=PARTIAL_END_OF_CONTIG"', None)
    rows = {(r["gene"], r["gene_type"]) for r in G.parse_entries(frame).collect()}
    assert rows == {("blaTEM-1", "COMPLETE"), ("gyrA_D87G", "POINT"), ("sinH", "PARTIAL"), ("ampC", "HMM"),
                    ("x", "PARTIAL_END_OF_CONTIG")}


@pytest.mark.parametrize("entry, expected", [
    ("blaOXA-48", ("allele", "BETA-LACTAM", "CARBAPENEM")),
    ("sul1", ("family", "SULFONAMIDE", "SULFONAMIDE")),
    ("sul1=PARTIAL", ("family", "SULFONAMIDE", "SULFONAMIDE")),
    ("blaTEM", ("family_ambiguous", "BETA-LACTAM", "BETA-LACTAM")),
    ("parC_S80I=POINT", ("mutation", "QUINOLONE", "CIPROFLOXACIN")),
    ("gyrA_S83F=POINT", ("allele", "QUINOLONE", "SALMONELLA_DRUG")),
    ("ompK35_N29TfsTer34=POINT", ("disrupt", "BETA-LACTAM", "CARBAPENEM")),
    ("dfrA51", ("unmapped", None, None)),
    ("aph(3'')=HMM", ("unmapped", None, None)),
])
def test_lookup_steps(spark, catalog, mutations, entry, expected):
    assert lookup(spark, catalog, mutations, entry) == expected


def test_bare_family_with_mixed_drugs_is_never_carbapenem(spark, catalog, mutations):
    assert lookup(spark, catalog, mutations, "blaOXA") == ("family_ambiguous", "BETA-LACTAM", None)


@pytest.mark.parametrize("entry, expected", [
    ("blaNDM", ("family_ambiguous", "BETA-LACTAM", "CARBAPENEM")),
    ("mecC", ("family", "BETA-LACTAM", "METHICILLIN")),
    ("blaPDC", ("family_ambiguous", "BETA-LACTAM", "CEPHALOSPORIN")),
    ("blaPDC-3", ("allele", "NONE", "INACTIVE")),
    ("blaNDM-9", ("allele", "BETA-LACTAM", "CARBAPENEM/TANIBORBACTAM")),
])
def test_rows_keep_the_drugs_they_all_share(spark, catalog, mutations, entry, expected):
    assert lookup(spark, catalog, mutations, entry) == expected


def test_own_taxon_wins_over_open_rows(spark, catalog, mutations):
    assert lookup(spark, catalog, mutations, "mecA") == ("family", "BETA-LACTAM", "METHICILLIN")
    assert lookup(spark, catalog, mutations, "mecA", "Escherichia") == ("family", "BETA-LACTAM", "OTHER")


def test_rows_for_other_taxa_are_not_used(spark, catalog, mutations):
    assert lookup(spark, catalog, mutations, "gyrA_S83F=POINT", "Klebsiella_pneumoniae")[0] == "unmapped"
    assert lookup(spark, catalog, mutations, "parC_S80R=POINT")[0] == "unmapped"
    assert lookup(spark, catalog, mutations, "cirA_W243Ter=POINT")[0] == "unmapped"


def test_disagreeing_rows_leave_fields_empty(spark, catalog, mutations):
    assert lookup(spark, catalog, mutations, "cfr") == ("family", None, None)


def test_virulence_rows_are_not_used(spark, catalog, mutations):
    assert lookup(spark, catalog, mutations, "fimH")[0] == "unmapped"


def test_each_entry_gives_one_row_and_repeats_are_removed(spark, catalog, mutations):
    frame = isolates(spark, '"sul1,sul1,blaOXA-48,mecA,gyrA_S83F=POINT,dfrA51"', '"sul1"', None)
    genes, repeats = G.annotate(frame, catalog, mutations, "Salmonella")
    rows = [(r["biosample_acc"], r["gene"]) for r in genes.collect()]
    assert sorted(rows) == [("S0", "blaOXA-48"), ("S0", "dfrA51"), ("S0", "gyrA_S83F"), ("S0", "mecA"),
                            ("S0", "sul1"), ("S1", "sul1")]
    assert repeats == 1


def test_same_gene_can_appear_complete_and_partial(spark, catalog, mutations):
    genes, repeats = G.annotate(isolates(spark, '"sul1,sul1=PARTIAL"'), catalog, mutations, "Salmonella")
    assert genes.count() == 2 and repeats == 0


def test_summary_reports_match_rate_and_unmapped(spark, catalog, mutations):
    genes, repeats = G.annotate(isolates(spark, '"sul1,blaOXA,dfrA51,blaTEM-1"'), catalog, mutations, "Salmonella")
    result = G.gene_summary(genes, repeats)
    assert result["gene_rows"] == 4
    assert result["catalog_match_pct"] == 75.0
    assert result["by_match_source"] == {"family": 1, "family_ambiguous": 1, "unmapped": 1, "allele": 1}
    assert result["rows_without_drug_class"] == 1
    assert result["rows_without_drug_subclass"] == 2
    assert result["top_unmapped"] == {"dfrA51 (COMPLETE)": 1}
