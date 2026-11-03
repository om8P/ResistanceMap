# Progress

Keep this file under about 60 lines. Replace old status instead of adding a log.

## Status
- **Last updated:** 2026-11-04
- **Done:** Sessions 1 and 2. 91 tests pass. Session 2 and the md updates are not yet committed.
- **Session 2 results:** 1,991,177 isolates and 11,274,636 gene rows. Catalog match 99.465 to 99.998% by organism. `SAMN02147118` gives its six genes with drug classes. Details in `results/pipeline_summary.json`.
- **Next:** Session 3. Start Docker Desktop and the container first.

## Sessions
- [x] 1. Setup and data audit
- [x] 2. Cleaning and gene pipeline
- [ ] 3. Spatiotemporal analytics
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
MSYS_NO_PATHCONV=1 docker exec resistancemap-spark python3 -m pip install -q --user pytest   # again if the container is recreated
MSYS_NO_PATHCONV=1 docker exec resistancemap-spark python3 -m pytest tests -q -p no:cacheprovider   # over 5 minutes, run in the background
```
Timing, all six: ingest 398 s, profile 247 s, clean 191 s, genes 264 s.

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

**Pipeline (`results/pipeline_summary.json`)**
- 1,991,177 isolates kept. 2 rows dropped (no ID), 373 duplicates removed; in 155 groups the duplicates' genes differed. 717,879 isolates have no core genes and stay in the denominator.
- Usable country 89.64% (missing 9.25, placeholder 1.10, unrecognised 230 rows). Usable year 85.91% (missing 13.50, multi-year range 0.57, impossible 281 rows). 77.09% of isolates are in a cluster.
- 11,274,636 gene rows, equal to the distinct input entries, so no join multiplied rows. Catalog match 99.878% (13,755 unmapped, mostly `dfrA51` and generic `=HMM` names). Lowest: Salmonella 99.465%.

**For Session 3 (`analytics.py`)**
- **Last-resort tracker overcounts if it only matches `CARBAPENEM`.** Of 506,008 carbapenem rows, 130,806 are point mutations and 99,624 disrupted genes, and `blaOXA-66` (38,855) is intrinsic to Acinetobacter. Use `match_source` to separate acquired genes from these.
- **First-seen needs support.** Single old records remain: `blaNDM` in 1943, 1968 and 1984, `mcr-1` in 1975 and 1984. A minimum count is needed, not the earliest year.
- **Empty subclass:** 121,959 rows have a class but no subclass, because the family mixes drugs (`blaOXA`, `blaTEM`). Bare `blaKPC` (749) is among them, so carbapenem is slightly undercounted there.
- Skip `drug_class = NONE` (inactive allele, 1 row). Split combined drugs on `/`.
- 40 to 55% of real dates are year only, so stay at yearly resolution.
- `China: Hong Kong` counts as China and plain `Hong Kong` separately, following the text before the colon. Not measured.

## Results so far
Audit and pipeline only: `results/ingest_counts.json`, `results/data_profile.json`, `results/pipeline_summary.json`.

## Changes to the plan
- Added to Session 1: `AMRProt-mutation.tsv` download, Pseudomonas Metadata check, upload delay and analysis coverage in the profile, and `tests/` for the profile rules.
- Session 2: gene lookup uses each organism's taxon, plus disrupted-gene and whole-family steps, recorded in `match_source`. Where catalog rows differ, only drugs they all share are kept. Earliest valid year raised to 1910, because 1900 to 1909 dates are artefacts such as `1900-01-01` and years read as Excel day counts.
- Added after the core: pathogen search and import (`PLAN.md`). This changes two fixed decisions: the six-organism limit, and the app needing only prepared files, which now applies to browsing but not import. Nothing built yet.
- Added to Sessions 3 to 5: richer visuals with chart rules, and `coverage.parquet` (`PLAN.md`). Nothing built yet.

## Known issues
- One profile run reported 36,007 s (about 10 hours). The re-run took 247 s. Cause unknown, so do not use that figure.
