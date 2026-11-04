"""Convert the WHO AWaRe spreadsheet to config/aware.csv, so the app can label antibiotics.

Source: WHO AWaRe classification of antibiotics for evaluation and monitoring of use, 2025.
https://iris.who.int/items/4fa2de82-388c-46d9-a6cb-41ffbd10677d
WHO states it is a tool for monitoring and stewardship, so it is not treatment guidance.

WHO lists some antibiotics by route (Colistin_IV, Colistin_oral). NCBI lab results don't give a
route, so these combine when every route has the same group. Where routes differ, as with
minocycline, the antibiotic gets no group rather than a guess.

Usage: python src/aware.py
"""
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "data" / "raw" / "aware" / "B09489-eng.xlsx"
OUTPUT = ROOT / "config" / "aware.csv"
SHEET = "AWaRe classification 2025"
HEADER_ROW = 3
CATEGORIES = {"Access", "Watch", "Reserve"}
# NCBI name to WHO name, only where they are clearly the same antibiotic.
ALIASES = {
    "imipenem": "Imipenem/cilastatin",
    "imipenem-relebactam": "Imipenem/cilastatin/relebactam",
    "rifampin": "Rifampicin",
    "sulfisoxazole": "Sulfafurazole",
    "cephalexin": "Cefalexin",
    "cephalothin": "Cefalotin",
    "cefpodoxime": "Cefpodoxime-proxetil",
    "ceftaroline": "Ceftaroline-fosamil",
    "polymyxin": "Polymyxin-B",
}


def drug_key(name):
    """Match src/analytics.py: lower case, with the parts of a combination sorted."""
    parts = re.split(r"[\s/+-]+", name.strip().lower())
    return "+".join(sorted(parts))


def combine_routes(rows):
    """One row per antibiotic. Routes that disagree on the group are dropped and returned."""
    rows = rows.assign(name=rows["Antibiotic"].str.strip().str.split("_").str[0])
    groups = rows.groupby("name")["Category"].nunique()
    conflicts = sorted(groups[groups > 1].index)
    kept = rows[~rows["name"].isin(conflicts)].drop_duplicates("name")
    return kept, conflicts


def add_aliases(table):
    """Add NCBI names for the same antibiotic. Returns the aliases WHO's list doesn't support."""
    extra, unmatched = [], []
    for ncbi_name, who_name in ALIASES.items():
        found = table[table["name"] == who_name]
        if found.empty:
            unmatched.append(ncbi_name)
            continue
        extra.append(found.assign(key=drug_key(ncbi_name)))
    return pd.concat([table] + extra, ignore_index=True), unmatched


def build(table):
    rows = table[table["Category"].isin(CATEGORIES)]
    kept, conflicts = combine_routes(rows)
    output = pd.DataFrame({
        "key": kept["name"].map(drug_key), "name": kept["name"], "drug_class": kept["Class"].str.strip(),
        "atc_code": kept["ATC code"], "category": kept["Category"],
    })
    output, unmatched = add_aliases(output)
    return output.drop_duplicates("key").sort_values("key"), conflicts, unmatched


def main():
    output, conflicts, unmatched = build(pd.read_excel(SOURCE, sheet_name=SHEET, header=HEADER_ROW))
    output.to_csv(OUTPUT, index=False)
    print(len(output), "names", output["category"].value_counts().to_dict())
    print("routes disagree, no group:", conflicts)
    print("aliases not on the list:", unmatched)


if __name__ == "__main__":
    main()
