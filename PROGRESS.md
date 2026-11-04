# Progress

Keep this file under about 60 lines. Replace old status instead of adding a log.

## Status
- **Last updated:** 2026-11-04
- **Done:** Sessions 1 to 3 and the Session 3 additions. 149 tests pass in the container, plus 5 for `src/aware.py` run on the host. All are committed. Work is on branch `session-3`; `master` does not have Session 3.
- **Results:** tables in `results/`, 20 MB. Reconciliation passes (`results/sanity_checks.json`).
- **Next:** Session 4 (its plan now includes the additions). The app reads `results/`, so Docker is only needed to re-run the pipeline.

## Sessions
- [x] 1. Setup and data audit
- [x] 2. Cleaning and gene pipeline
- [x] 3. Spatiotemporal analytics
- [ ] 4. Streamlit app
- [ ] 5. Report, slides, viva prep

## Environment
- Host: Python 3.11.9 with pandas, matplotlib, streamlit, plotly, pyarrow, pytest, psutil. No PySpark, so tests run in the container.
- Docker 29.9.2, about 7.6 GiB for the engine. Container: Spark 4.0.5, Python 3.10.12, capped at 5 GB.
- Data: `data/raw` 2.0 GB.

## Working commands
```bash
docker desktop start
docker compose up -d
python src/download.py   # add --organism NAME for one
MSYS_NO_PATHCONV=1 docker exec resistancemap-spark /opt/spark/bin/spark-submit --driver-memory 4g src/ingest.py
MSYS_NO_PATHCONV=1 docker exec resistancemap-spark /opt/spark/bin/spark-submit --driver-memory 4g src/profile_data.py
MSYS_NO_PATHCONV=1 docker exec resistancemap-spark /opt/spark/bin/spark-submit --driver-memory 4g src/clean.py
MSYS_NO_PATHCONV=1 docker exec resistancemap-spark /opt/spark/bin/spark-submit --driver-memory 4g src/genes.py
MSYS_NO_PATHCONV=1 docker exec resistancemap-spark /opt/spark/bin/spark-submit --driver-memory 4g src/analytics.py   # add --organism NAME for one, which writes to data/dev_results/
MSYS_NO_PATHCONV=1 docker exec resistancemap-spark /opt/spark/bin/spark-submit --driver-memory 4g src/sanity_checks.py
MSYS_NO_PATHCONV=1 docker exec resistancemap-spark python3 -m pip install -q --user --default-timeout=120 pytest pandas pyarrow   # again if the container is recreated
MSYS_NO_PATHCONV=1 docker exec resistancemap-spark python3 src/timing.py
MSYS_NO_PATHCONV=1 docker exec resistancemap-spark /opt/spark/bin/spark-submit --driver-memory 4g src/method_check.py
python src/aware.py   # host, needs data/raw/aware/B09489-eng.xlsx
python src/glass.py   # host, needs data/raw/glass/
MSYS_NO_PATHCONV=1 docker exec resistancemap-spark python3 -m pytest tests -q -p no:cacheprovider   # over 5 minutes, run in the background
```
Timing, all six: ingest 398 s, profile 247 s, clean 191 s, genes 264 s, analytics 1,918 s, sanity about 100 s, timing job 304 s.

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

**For Session 4**
- Lead with `established_year`, not `first_year`. Raw dates include errors such as `blaNDM` in 1943.
- Hide early warnings with `new_sequencing` by default. Show `earlier_records`, because some "new" genes have older lone records.
- Lead last-resort views with `acquired`. `intrinsic` is only `blaOXA` OXA-51 family in Acinetobacter.
- Empty `rate` means under the minimum sample. A missing `rising` row, or `enough_years` false, means too little data.
- `rising` has no cross-country ranking. Sort within a country or by name.
- Empty subclass: 121,959 rows have a class but no subclass, including bare `blaKPC` (749), so carbapenem is slightly undercounted.

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

## Changes to the plan
- Session 2: gene lookup rules are in `ARCHITECTURE.md`. Earliest valid year raised to 1910, because 1900 to 1909 dates are artefacts.
- Session 3 definitions and additions are in `ARCHITECTURE.md`. Added `config/settings.json`, `config/aware.csv`, `config/glass_map.csv`, and pandas and pyarrow in the container.
- Changed fixed decisions: GLASS and AWaRe as comparison and labelling sources; doctors as possible readers. The user asked for treatment suggestions; drugs are named with evidence, but recommending one stays out because the data cannot show a drug will work. Not-for-clinical-use stays.
- Pathogen search and import remain planned after the core. Nothing built.

## Known issues
- One profile run reported 36,007 s (about 10 hours). The re-run took 247 s. Cause unknown, so do not use that figure.
- GLASS has no bulk resistance file. The files came from its chart download, with the page setting filters. Regional medians: African Region 5 of 10; Eastern Mediterranean Region 4 of 10; European Region 8 of 10; Global 10 of 10; South-East Asia Region 6 of 10; Region of the Americas and Western Pacific Region missing. African Region has no colistin option. Country rows are complete for the 10 pairs.
- The pooled tables and AWaRe labels were rebuilt after fixes without a full re-run, using the same functions. A full run should give the same tables.
- The `mcr-1` 1980s paper (Shen et al. 2016) was read in summary only. Check it before citing.
