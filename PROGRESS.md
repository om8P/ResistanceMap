# Progress

Keep this file under about 60 lines. Replace old status instead of adding a log.

## Status
- **Last updated:** 2026-11-04
- **Done:** Sessions 1 to 3. 124 tests pass. All are committed.
- **Session 3 results:** 12 prepared tables in `results/`, 9.2 MB. Table totals reconcile with the 1,991,177 isolates (`results/sanity_checks.json`).
- **Next:** Session 4. Start Docker only if the pipeline must re-run; the app reads `results/`.

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
MSYS_NO_PATHCONV=1 docker exec resistancemap-spark /opt/spark/bin/spark-submit --driver-memory 4g src/analytics.py   # add --organism NAME for one, but that overwrites results/
MSYS_NO_PATHCONV=1 docker exec resistancemap-spark /opt/spark/bin/spark-submit --driver-memory 4g src/sanity_checks.py
MSYS_NO_PATHCONV=1 docker exec resistancemap-spark python3 -m pip install -q --user --default-timeout=120 pytest pandas pyarrow   # again if the container is recreated
MSYS_NO_PATHCONV=1 docker exec resistancemap-spark python3 src/timing.py
MSYS_NO_PATHCONV=1 docker exec resistancemap-spark python3 -m pytest tests -q -p no:cacheprovider   # over 5 minutes, run in the background
```
Timing, all six: ingest 398 s, profile 247 s, clean 191 s, genes 264 s, analytics 597 s, sanity 98 s, timing job 304 s.

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

## Changes to the plan
- Session 2: gene lookup rules are in `ARCHITECTURE.md`. Earliest valid year raised to 1910, because 1900 to 1909 dates are artefacts.
- Added after the core: pathogen search and import (`PLAN.md`). This changes two fixed decisions: the six-organism limit, and the app needing only prepared files, which now applies to browsing but not import. Nothing built yet.
- Added to Sessions 3 to 5: richer visuals with chart rules, and `coverage.parquet` (`PLAN.md`). Coverage is built; visuals are not.
- Session 3 definitions, now in `ARCHITECTURE.md`: provisional from 2023; two trend windows; `established_year`; `new_sequencing` baseline; hotspots compared with other countries, 10-point margin; last-resort mechanisms; adjusted versions of last_resort, rising and hotspots.
- Added files: `config/settings.json`, `src/sanity_checks.py`, `src/timing.py`. pandas and pyarrow in the container, for the timing only.

## Known issues
- One profile run reported 36,007 s (about 10 hours). The re-run took 247 s. Cause unknown, so do not use that figure.
