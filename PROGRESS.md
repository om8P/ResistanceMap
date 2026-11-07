# Progress

Keep this file under about 60 lines. Replace old status instead of adding a log.

## Status
- **Last updated:** 2026-11-07
- **Done:** Sessions 1 to 5, all on `master`. Full pipeline rerun on 2026-11-06 from the README steps, download skipped to keep the 2026-11-03 release: every file in `results/` came out identical except `timing.json`. With search and import: 98 host tests pass; 164 pass and 3 are skipped in the container (2026-11-07).
- **Session 5 outputs:** `README.md`; `report/report.md` and `report.docx`, `slides.pptx` (13 slides with speaker notes), `viva_notes.md` (demo script and questions). `report/make_figures.py` writes the figures and `report/numbers.json`, and every report number traces to it. `report/build_docs.py` builds the .docx and .pptx. Demo checked in the app: trend, evidence panel and gene profile match the report.
- **Results:** tables in `results/`, 20 MB. Reconciliation passes (`results/sanity_checks.json`).
- **Optional, phase A done (2026-11-07):** pathogen and disease search over the six organisms, offline. New: `src/search_index.py` (`results/search_index.parquet`), `search_fill` in `data_profile.json` (old keys unchanged), `config/disease_pathogens.csv` (28 conditions, hand-written, **user to check every row**), `config/ncbi_organisms.csv` (`download.py --list`, 107 groups), `app/lib/search.py`, Search page. Core results unchanged; `report/numbers.json` differs only in result_files (33). Plan: `C:/Users/ommga/.claude/plans/polymorphic-snuggling-cocoa.md`.
- **Optional, phase B done (2026-11-07):** pathogen import. `src/import_pathogen.py ORGANISM` (or the Search page button) adds it to `config/imported.csv`, downloads, and runs ingest to search index for it alone in Docker with `RESULTS_DIR=results/imported/<organism>`; status in `status.json` there, log in `logs/import_<organism>.log`. `src/datasets.py` holds the core list and results folder; full runs (ingest, profile, analytics, sanity, method check, timing) are core only. App: sidebar Dataset switch, imported data shows map and trends, early warnings, gene profile and About. Tested with Vibrio cholerae (see `results/findings.md`).
- **Next:** all planned work is done.

## Sessions
- [x] 1. Setup and data audit
- [x] 2. Cleaning and gene pipeline
- [x] 3. Spatiotemporal analytics
- [x] 4. Streamlit app
- [x] 5. Report, slides, viva prep

## Environment
- Host: Python 3.11.9 with pandas, matplotlib, streamlit, plotly, pyarrow, pytest, psutil, python-docx, python-pptx. No PySpark, so tests run in the container.
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
MSYS_NO_PATHCONV=1 docker exec resistancemap-spark /opt/spark/bin/spark-submit --driver-memory 4g src/analytics.py   # use --master "local[8]" (see Changes to the plan); add --organism NAME for one, which writes to data/dev_results/
MSYS_NO_PATHCONV=1 docker exec resistancemap-spark /opt/spark/bin/spark-submit --driver-memory 4g src/sanity_checks.py
MSYS_NO_PATHCONV=1 docker exec resistancemap-spark /opt/spark/bin/spark-submit --driver-memory 4g src/search_index.py   # about 1 minute
python src/download.py --list   # host, refreshes config/ncbi_organisms.csv
python src/import_pathogen.py Vibrio_cholerae   # host, Docker running; about 4 minutes for a 16 MB pathogen
MSYS_NO_PATHCONV=1 docker exec resistancemap-spark python3 -m pip install -q --user --default-timeout=120 pytest pandas pyarrow   # again if the container is recreated
MSYS_NO_PATHCONV=1 docker exec resistancemap-spark python3 src/timing.py
MSYS_NO_PATHCONV=1 docker exec resistancemap-spark /opt/spark/bin/spark-submit --driver-memory 4g src/method_check.py
python src/aware.py   # host, needs data/raw/aware/B09489-eng.xlsx
python src/glass.py   # host, needs data/raw/glass/
python -m streamlit run app/app.py   # host, with Docker stopped
python -m pytest tests/test_app_rules.py tests/test_app_pages.py tests/test_aware.py tests/test_search.py tests/test_import.py -q -p no:cacheprovider   # host, about 1 minute
MSYS_NO_PATHCONV=1 docker exec resistancemap-spark python3 -m pytest tests -q -p no:cacheprovider   # over 5 minutes, run in the background
```
Timing, all six, rerun 2026-11-06: ingest 119 s, profile 84 s, clean 72 s, genes 113 s, analytics 751 s (local[8]), sanity 41 s, timing job 112 s, method check 28 s. The earlier run took about 3 times longer on a busier machine.
```bash
python report/make_figures.py   # host, figures and report/numbers.json from results/
python report/build_docs.py     # host, report.docx and slides.pptx
```

## Measured results
All in `results/findings.md`: data quality, sampling limits, table sizes, sanity checks, timing and the additions. Read it only when a task needs those numbers.

Limits that shape every page:
- USA is 44.52% of rows and India 0.60%, and only 2,848 of 9,470 country and year groups reach the minimum sample.
- Provisional from 2023, and this is a floor: only Salmonella reaches 90% uploaded.
- Zero-gene isolates stay in the denominator.

## Changes to the plan
- Session 4: confidence levels from Wilson width (stronger up to 10 points, moderate up to 25, weak above), a 95% near-universal label and sparse-field thresholds, all in `config/settings.json`. Map scale is viridis, because cividis has a grey middle that looked like "too few isolates". All optional visuals were built. Pathogen search and import were not.
- Session 2: gene lookup rules are in `ARCHITECTURE.md`. Earliest valid year raised to 1910, because 1900 to 1909 dates are artefacts.
- Session 3 definitions and additions are in `ARCHITECTURE.md`. Added `config/settings.json`, `config/aware.csv`, `config/glass_map.csv`, and pandas and pyarrow in the container.
- Changed fixed decisions: GLASS and AWaRe as comparison and labelling sources; doctors as possible readers. The user asked for treatment suggestions; drugs are named with evidence, but recommending one stays out because the data cannot show a drug will work. Not-for-clinical-use stays.
- Optional import: results folder set by the RESULTS_DIR environment variable rather than a --out flag per step (one setting, read by every step through `src/datasets.py`). An import reuses the core gene catalog (no reference download), so the core is unaffected. Taxon is the organism's own point-mutation group or blank.
- Optional search: matching is whole-word for diseases (so "typhoid" does not find "non-typhoidal"), word-prefix from 4 letters for organism names. Strain is indexed only where seen 5+ times. The host_disease block is one per search, so diseases sharing a word are not double counted. Search shows coverage, not rates by serovar or strain.
- Session 5: analytics now runs with `--master "local[8]"`. With the default 16 tasks in a 4 GB driver it ran out of Java heap once (`logs/rerun_analytics_oom.log`), though it had passed before. The timing rerun gave Spark 11.2 s and pandas 18.7 s (median job), peak memory 3.93 and 4.97 GB. The report cites these and mentions the earlier 28.7 s and 52.1 s.

## Known issues
- The map's country outlines load from `cdn.plot.ly/un/world_110m.json`, so the map needs internet. All data and other charts work offline. Not tested with internet off.
- In `coverage`, 10.4% of isolates have no usable country and 14.1% no usable year. `data.coverage()` leaves them out of yearly views, and totals say so.
- GLASS has no bulk file; files came from its chart download. Regional medians are partial (Americas and Western Pacific missing, African Region has no colistin). Country rows are complete for the 10 pairs.
- The `mcr-1` 1980s paper (Shen et al. 2016) was read in summary only. Check it before citing.
