# Progress

Keep this file under about 60 lines. Replace old status instead of adding a log.

## Status
- **Last updated:** 2026-11-04
- **Done:** Sessions 1 to 4. 149 tests pass in the container (not re-run, as `src/` is unchanged), plus the host tests for the app and `src/aware.py`. Session 4 is on branch `session-4`, cut from `session-3`; `master` has neither.
- **Results:** tables in `results/`, 20 MB. Reconciliation passes (`results/sanity_checks.json`).
- **Next:** Session 5. The app reads `results/`, so Docker is only needed to re-run the pipeline.
- **Answers in the app:** Klebsiella in India, carbapenem, acquired: not flagged as rising (2013 to 2022, 8 usable years, 918 of 1,610, slope +0.06, z 0.08). `blaNDM`: on record in 123 countries, established in 105, earliest established 2009 in India.

## Sessions
- [x] 1. Setup and data audit
- [x] 2. Cleaning and gene pipeline
- [x] 3. Spatiotemporal analytics
- [x] 4. Streamlit app
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
python -m streamlit run app/app.py   # host, with Docker stopped
python -m pytest tests/test_app_rules.py tests/test_app_pages.py tests/test_aware.py -q -p no:cacheprovider   # host, about 1 minute
MSYS_NO_PATHCONV=1 docker exec resistancemap-spark python3 -m pytest tests -q -p no:cacheprovider   # over 5 minutes, run in the background
```
Timing, all six: ingest 398 s, profile 247 s, clean 191 s, genes 264 s, analytics 1,918 s, sanity about 100 s, timing job 304 s.

## Measured results
All in `results/findings.md`: data quality, sampling limits, table sizes, sanity checks, timing and the additions. Read it only when a task needs those numbers.

Limits that shape every page:
- USA is 44.52% of rows and India 0.60%, and only 2,848 of 9,470 country and year groups reach the minimum sample.
- Provisional from 2023, and this is a floor: only Salmonella reaches 90% uploaded.
- Zero-gene isolates stay in the denominator.

## Changes to the plan
- Session 4: new confidence levels from Wilson width (stronger up to 10 points, moderate up to 25, weak above), a 95% near-universal label and sparse-field thresholds, all in `config/settings.json`. Map scale is viridis, because cividis has a grey middle that looked like "too few isolates". All optional visuals were built. Pathogen search and import were not.
- Session 2: gene lookup rules are in `ARCHITECTURE.md`. Earliest valid year raised to 1910, because 1900 to 1909 dates are artefacts.
- Session 3 definitions and additions are in `ARCHITECTURE.md`. Added `config/settings.json`, `config/aware.csv`, `config/glass_map.csv`, and pandas and pyarrow in the container.
- Changed fixed decisions: GLASS and AWaRe as comparison and labelling sources; doctors as possible readers. The user asked for treatment suggestions; drugs are named with evidence, but recommending one stays out because the data cannot show a drug will work. Not-for-clinical-use stays.
- Pathogen search and import remain planned after the core. Nothing built.

## Known issues
- The map's country outlines load from `cdn.plot.ly/un/world_110m.json`, so the map needs internet. All data and other charts work offline. Not tested with internet off.
- In `coverage`, 10.4% of isolates have no usable country and 14.1% no usable year. `data.coverage()` leaves them out of yearly views, and totals say so.
- One profile run reported 36,007 s (about 10 hours). The re-run took 247 s. Cause unknown, so do not use that figure.
- GLASS has no bulk resistance file. The files came from its chart download, with the page setting filters. Regional medians: African Region 5 of 10; Eastern Mediterranean Region 4 of 10; European Region 8 of 10; Global 10 of 10; South-East Asia Region 6 of 10; Region of the Americas and Western Pacific Region missing. African Region has no colistin option. Country rows are complete for the 10 pairs.
- The pooled tables and AWaRe labels were rebuilt after fixes without a full re-run, using the same functions. A full run should give the same tables.
- The `mcr-1` 1980s paper (Shen et al. 2016) was read in summary only. Check it before citing.
