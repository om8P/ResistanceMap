"""Convert WHO GLASS chart downloads into tables the app can show beside our rates.

GLASS is lab-confirmed resistance in bloodstream infections. Our rates are resistance genes in
sequenced isolates. The two measure different things, so they are shown side by side and are
never merged. GLASS shows a country only if it reports at least 10 infections with test results
in at least 70% of the years, and shows regional medians only with at least 5 countries.

Source: WHO GLASS dashboard, https://worldhealthorg.shinyapps.io/glass-dashboard/ (chart "Time
series of resistance to antibiotics", 2016 to 2023 data, updated 25 September 2025).

Writes results/glass.parquet and results/glass_regions.parquet.

Usage: python src/glass.py
"""
import csv
import io
import json
import re
from math import sqrt
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "glass"
MAP = ROOT / "config" / "glass_map.csv"
SETTINGS = ROOT / "config" / "settings.json"
RESULTS = ROOT / "results"
SUMMARY_TITLE = "Data for time series"
COUNTRY_TITLE = "Data for line plots for individual CTAs"
ALL_REGIONS = "All"
GLOBAL = "Global"
Z_95 = 1.96


def filter_value(text, label):
    found = re.search(rf"{label}: (.+)", text)
    return found.group(1).strip() if found else None


def section(text, title):
    """Return one titled section of a chart download as a table."""
    lines = text.splitlines()
    if title not in lines:
        return pd.DataFrame()
    start = lines.index(title) + 1
    rows = []
    for line in lines[start:]:
        if not line.strip():
            break
        rows.append(line)
    if len(rows) < 2:
        return pd.DataFrame()
    return pd.read_csv(io.StringIO("\n".join(rows)), quoting=csv.QUOTE_MINIMAL)


def parse_file(text):
    """Return the filter values, the summary rows and the country rows of one download."""
    filters = {"region": filter_value(text, "Region filter"), "pathogen": filter_value(text, "pathogen filter"),
               "antibiotic": filter_value(text, "Antibiotic filter")}
    return filters, section(text, SUMMARY_TITLE), section(text, COUNTRY_TITLE)


def wilson(resistant, tested):
    """Wilson 95% limits as fractions."""
    p = resistant / tested
    z2 = Z_95 * Z_95
    denominator = 1 + z2 / tested
    centre = (p + z2 / (2 * tested)) / denominator
    half = Z_95 * sqrt(p * (1 - p) / tested + z2 / (4 * tested * tested)) / denominator
    return max(0.0, centre - half), min(1.0, centre + half)


def add_map(rows, mapping):
    """Keep only pairs with a clear match in our tables. Anything else is left out."""
    return rows.merge(mapping, left_on=["pathogen", "antibiotic"], right_on=["glass_pathogen", "glass_antibiotic"]).drop(
        columns=["glass_pathogen", "glass_antibiotic"])


def country_table(rows, min_sample):
    """Standard columns, with rates left empty under the minimum sample, as in our tables."""
    table = pd.DataFrame({
        "iso3": rows["Iso3"], "country": rows["CountryTerritoryArea"], "who_region": rows["WHORegionName"],
        "year": rows["Year"].astype(int), "pathogen": rows["PathogenName"], "antibiotic": rows["AbTargets"],
        "tested": rows["InterpretableAST"], "resistant": rows["Resistant"], "infections": rows["TotalSpecimenIsolates"],
    }).dropna(subset=["tested", "resistant"])
    table = table[table["tested"] > 0].copy()
    limits = [wilson(r, n) for r, n in zip(table["resistant"], table["tested"])]
    enough = table["tested"] >= min_sample
    table["rate"] = (table["resistant"] / table["tested"]).where(enough)
    table["ci_low"] = pd.Series([low for low, _ in limits], index=table.index, dtype=float).where(enough)
    table["ci_high"] = pd.Series([high for _, high in limits], index=table.index, dtype=float).where(enough)
    table["meets_min_sample"] = enough
    return table


def region_table(rows, region):
    """GLASS's own regional or global summary, as percentages among reporting countries."""
    return pd.DataFrame({
        "who_region": GLOBAL if region == ALL_REGIONS else region, "year": rows["Year"].astype(int),
        "pathogen": rows["PathogenName"], "antibiotic": rows["AbTargets"], "min_percent": rows["Min"],
        "q1_percent": rows["Q1"], "median_percent": rows["Median"], "q3_percent": rows["Q3"], "max_percent": rows["Max"],
    })


def build(texts, mapping, min_sample):
    """Countries come from the all-regions files, and summaries from every file."""
    countries, regions = [], []
    for text in texts:
        filters, summary, country = parse_file(text)
        if not summary.empty:
            regions.append(region_table(summary, filters["region"]))
        if filters["region"] == ALL_REGIONS and not country.empty:
            countries.append(country_table(country, min_sample))
    country_rows = add_map(pd.concat(countries, ignore_index=True), mapping)
    region_rows = add_map(pd.concat(regions, ignore_index=True), mapping) if regions else pd.DataFrame()
    return country_rows, region_rows


def main():
    settings = json.loads(SETTINGS.read_text())
    mapping = pd.read_csv(MAP)
    files = sorted(RAW.glob("glass_*.csv"))
    countries, regions = build([path.read_text(encoding="utf-8") for path in files], mapping, settings["min_sample"])
    countries.to_parquet(RESULTS / "glass.parquet", index=False)
    regions.to_parquet(RESULTS / "glass_regions.parquet", index=False)
    pairs = len(mapping)
    found = countries[["pathogen", "antibiotic"]].drop_duplicates().shape[0]
    print(f"{len(files)} files, {found} of {pairs} pairs, {countries['iso3'].nunique()} countries, "
          f"{len(countries)} country rows, {int(countries['meets_min_sample'].sum())} meet the minimum, "
          f"{len(regions)} region rows, years {countries['year'].min()} to {countries['year'].max()}")


if __name__ == "__main__":
    main()
