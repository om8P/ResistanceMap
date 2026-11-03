# Progress

Keep this file under about 60 lines. Replace old status instead of adding a log.

## Status
- **Last updated:** 2026-11-04
- **Done:** Session 1. Row counts match on all 14 files, profile saved, 31 tests pass. Not yet committed.
- **Next:** Session 2. Start Docker Desktop and the container first.

## Sessions
- [x] 1. Setup and data audit
- [ ] 2. Cleaning and gene pipeline
- [ ] 3. Spatiotemporal analytics
- [ ] 4. Streamlit app
- [ ] 5. Report, slides, viva prep

## Environment
- Host: Python 3.11.9 with pandas, matplotlib, streamlit, plotly, pyarrow, pytest, psutil. No PySpark, so tests run in the container.
- Docker 29.9.2, about 7.6 GiB for the engine. Container: Spark 4.0.5, Python 3.10.12, capped at 5 GB.
- Data: `data/raw` 2.0 GB, `data/parquet` 282 MB.

## Working commands
```bash
docker desktop start
docker compose up -d
python src/download.py   # add --organism NAME for one
MSYS_NO_PATHCONV=1 docker exec resistancemap-spark /opt/spark/bin/spark-submit --driver-memory 4g src/ingest.py
MSYS_NO_PATHCONV=1 docker exec resistancemap-spark /opt/spark/bin/spark-submit --driver-memory 4g src/profile_data.py
MSYS_NO_PATHCONV=1 docker exec resistancemap-spark python3 -m pip install -q --user pytest   # again if the container is recreated
MSYS_NO_PATHCONV=1 docker exec resistancemap-spark python3 -m pytest tests -q -p no:cacheprovider
```
Timing: ingest of all six 398 s, profile of all six 247 s.

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
- **Trends and early warnings:** only Salmonella reaches 90% uploaded within 5 years (at 4 years, provisional from 2023). The other five stay at 64 to 82%. Early warnings look at the last 3 data years, where data is least complete, so they can miss genes. Decide the provisional rule in Session 3.
- **India:** 11,943 of 1,991,552 rows (0.60%). Staph aureus (469) and Pseudomonas (814) will often fall under the minimum sample once split by year.
- **Sampling skew:** USA is 44.52% of rows, and 570,664 of Salmonella's rows.
- **Analysis method:** E. coli isolates with no core genes are 28.78% under `COMBINED` and 13.81% under `NUCLEOTIDE`. Method may affect detection; not yet explained.

**For Session 2 (`clean.py`)**
- 374 rows repeat a `biosample_acc`: needs a rule for which to keep.
- Placeholders can carry a reason (`missing: third party data`), so match the start of the value.
- Multi-year date ranges have no single year, for example 2,820 in Salmonella. Timestamps have a valid year.
- 14 rows have impossible years (before 1900 or after 2026), such as `2919`.
- 40 to 55% of real dates are year only, so stay at yearly resolution.

## Results so far
Audit only: `results/ingest_counts.json`, `results/data_profile.json`.

## Changes to the plan
- Added to Session 1: `AMRProt-mutation.tsv` download, Pseudomonas Metadata check, upload delay and analysis coverage in the profile, and `tests/` for the profile rules.

## Known issues
- One profile run reported 36,007 s (about 10 hours). The re-run took 247 s. Cause unknown, so do not use that figure.
