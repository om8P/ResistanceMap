"""Hand-checked cases for src/aware.py."""
import pandas as pd

import aware as W


def table(rows):
    return pd.DataFrame(rows, columns=["Antibiotic", "Class", "ATC code", "Category"])


def test_routes_with_one_group_combine():
    output, conflicts, _ = W.build(table([("Colistin_IV", "Polymyxins", "J01XB01", "Reserve"), ("Colistin_oral", "Polymyxins", "A07AA10", "Reserve")]))
    assert output["name"].tolist() == ["Colistin"] and output["category"].tolist() == ["Reserve"]
    assert conflicts == []


def test_routes_that_disagree_get_no_group():
    output, conflicts, _ = W.build(table([("Minocycline_IV", "Tetracyclines", "J01AA08", "Reserve"), ("Minocycline_oral", "Tetracyclines", "J01AA08", "Watch")]))
    assert output.empty and conflicts == ["Minocycline"]


def test_alias_points_at_the_who_entry():
    output, _, _ = W.build(table([("Imipenem/cilastatin", "Carbapenems", "J01DH51", "Watch")]))
    assert output.set_index("key").loc["imipenem", "category"] == "Watch"


def test_key_matches_combination_names_in_either_order():
    assert W.drug_key("Amoxicillin/clavulanic-acid") == W.drug_key("amoxicillin-clavulanic acid")
    assert W.drug_key("Polymyxin-B") == W.drug_key("polymyxin b")


def test_categories_outside_aware_are_excluded():
    output, _, _ = W.build(table([("Something", "Other", "X", "Not recommended")]))
    assert output.empty
