# Findings

Measured results for the report and viva, moved from `PROGRESS.md`. The source of truth is the tables and JSON files in `results/`.

## Data findings
From `results/data_profile.json`. Percent with real values, placeholders such as `missing` excluded. "Upload" is the percent uploaded within 5 years of collection.

| Organism | Rows | Date | Geo | Host | Source | Epi | Lat/lon | AST | Core genes | India | Upload |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Salmonella | 908,677 | 91.56 | 93.41 | 40.09 | 57.60 | 94.03 | 3.39 | 1.10 | 37.51 | 1,659 | 94.09 |
| E. coli/Shigella | 592,815 | 82.84 | 86.96 | 55.55 | 60.48 | 74.65 | 12.48 | 1.87 | 75.46 | 4,098 | 82.12 |
| Klebsiella | 178,938 | 83.05 | 89.64 | 79.97 | 65.31 | 82.26 | 33.54 | 1.47 | 100 | 3,409 | 70.77 |
| Staph aureus | 179,096 | 77.43 | 79.91 | 71.16 | 54.87 | 69.34 | 23.72 | 0.85 | 97.44 | 469 | 68.93 |
| Pseudomonas | 67,170 | 80.42 | 86.46 | 79.16 | 73.60 | 82.30 | 37.82 | 1.46 | 100 | 814 | 63.81 |
| Acinetobacter | 64,856 | 89.94 | 91.89 | 84.97 | 74.52 | 87.99 | 28.70 | 1.91 | 100 | 1,494 | 78.01 |

**Denominator is sound.** Zero-gene isolates are in the file with an empty `AMR_genotypes_core`. All six: 0 rows not analysed, and every empty value has `number_core_amr_genes = 0`. Do not drop these rows. Pseudomonas AMR and Metadata files hold the same isolates.

**Findings that weaken features**
- **Trends and early warnings:** only Salmonella reaches 90% uploaded within 5 years (at 4 years, provisional from 2023). The other five stay at 64 to 82%. Early warnings look at the last 3 data years, where data is least complete, so they can miss genes. Provisional rule: 2023 on, a floor for the other five.
- **India:** 11,943 of 1,991,552 rows (0.60%). Staph aureus (469) and Pseudomonas (814) will often fall under the minimum sample once split by year.
- **Sampling skew:** USA is 44.52% of rows, and 570,664 of Salmonella's rows.
- **Analysis method:** E. coli isolates with no core genes are 28.78% under `COMBINED` and 13.81% under `NUCLEOTIDE`. Method may affect detection; not yet explained.

**Pipeline:** usable country 89.64%, usable year 85.91%, cluster 77.09%, catalog match 99.878%. 717,879 isolates have no core genes and stay in the denominator. Details in `results/pipeline_summary.json`.

## Results so far
Measured, among sequenced isolates, genotypic resistance.
- **Tables:** prevalence 205,076 rows each view, of which 62,929 (all) and 46,429 (adjusted) meet the minimum sample. last_resort 94,700 each. rising 27,552 and 19,934 adjusted. first_seen 267,489. gene_summary 20,528.
- **Hotspots:** 7,408 rows, and 4,517 adjusted. This is many. Each flag is not a finding on its own, and some are chance.
- **Early warnings:** 1,393 rows, of which 561 are `new_sequencing`. At family level, 33 have enough baseline and no older record in any organism.
- **`blaNDM` (`sanity_checks.json`):** on record in 123 countries, established in 105. Earliest established 2009, India, which fits the 2008 discovery. 8 records predate 2008: 1943, 1968 and 1984 look like date errors, 4 from 2005 are lab strains, 2007 Germany is unverified.
- **`mcr-1`:** on record in 84 countries, established in 68. Earliest established 2004, China. 1,451 records predate 2015, as expected from later look-back studies. The 1975 record is earlier than the 1980s usually cited and stays unresolved. Check the original 1980s paper before citing it.
- **Klebsiella, India, acquired carbapenem genes:** 3,409 isolates. Not rising on 2013 to 2022: slope 0.06 points a year, z 0.08, 8 usable years. With provisional years: slope 0.64, not significant. Adjusted: slope -0.87, z -0.92.
- **Spark against pandas (`timing.json`):** same job on 11,274,636 rows, 3 runs each in the 5 GB container. Median job 28.7 s for Spark and 52.1 s for pandas; whole process 42.1 s and 57.4 s. Peak memory about 3.9 GB and 4.97 GB, so pandas ran right at the limit. Answers identical on all 85,404 rows, an independent check of the Spark numbers. Pandas was written plainly, not tuned, so a tuned version could do better.

## Additions, measured
Among sequenced isolates, genotypic resistance, unless labelled GLASS.
- **Persistent hotspots:** 4,432 of 7,408 rows, and 2,662 of 4,517 adjusted. Still many, so the app needs filters.
- **Pooling:** 1,727 of 4,640 periods reach the minimum (37%), against 2,848 of 9,470 single years (30%). Modest, not a cure.
- **Both last-resort drugs, acquired:** 1,165 isolates: E. coli/Shigella 950, Klebsiella 209, Acinetobacter 3, Salmonella 3, none in Pseudomonas or Staph aureus. Any mechanism: 17,105, mostly chromosomal changes, so lead with acquired.
- **Clinical view, Klebsiella in India, acquired carbapenem genes:** slope 1.44 points a year, z 1.91, not significant at 1.96. Close, so do not state it as a firm "no rise".
- **Cluster watch:** 7,135 clusters. 3,154 in 2 or more countries within the last 3 years. 650 new, 1,388 with an acquired last-resort gene, 96 both.
- **Gene and lab agreement:** 24,803 isolates with usable results (clinical 9,973, environmental 14,771), 85,304 rows, 14,865 with a rate. Example, Klebsiella and meropenem: with `blaNDM` family 217 of 222 resistant, without 510 of 1,141. AWaRe labels miss veterinary drugs, antifungals, and fosfomycin and minocycline, where WHO's routes differ.
- **GLASS:** 32 countries, 2018 to 2023, bloodstream, no USA, 1,182 rows (1,114 meet the minimum). India, K. pneumoniae and meropenem, 2023: 5,405 of 8,610 resistant. Our acquired carbapenem genes for Klebsiella in India, 2023: 576 of 960. These are different measures. Regional medians are partial (see Known issues).
- **Analysis method (`method_check.json`):** Staph aureus `COMBINED` share fell from 72.1% (2013) to 38.0% (2022), with gaps of about 11 points in aminoglycosides and macrolides, so its trends are most at risk. Very roughly 3.8 points over the decade. Salmonella and E. coli gaps reach about 20 points, but their mix moved under 2 points. No trends were changed; the proposal is a caveat on Staph aureus trends.
- **`blaKPC`:** stays uncounted. 96 of its 301 catalog rows list cephalosporin, not carbapenem, so it fails the rule that every allele must list carbapenem.
