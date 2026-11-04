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

## Measured results
All in `results/findings.md`: data quality, sampling limits, table sizes, sanity checks, timing and the additions. Read it only when a task needs those numbers.

Limits that shape every page:
- USA is 44.52% of rows and India 0.60%, and only 2,848 of 9,470 country and year groups reach the minimum sample.
- Provisional from 2023, and this is a floor: only Salmonella reaches 90% uploaded.
- Zero-gene isolates stay in the denominator.

## For Session 4
- Lead with `established_year`, not `first_year`. Raw dates include errors such as `blaNDM` in 1943.
- Hide early warnings with `new_sequencing` by default. Show `earlier_records`, because some "new" genes have older lone records.
- Lead last-resort views with `acquired`. `intrinsic` is only `blaOXA` OXA-51 family in Acinetobacter.
- Empty `rate` means under the minimum sample. A missing `rising` row, or `enough_years` false, means too little data.
- `rising` has no cross-country ranking. Sort within a country or by name.
- Empty subclass: 121,959 rows have a class but no subclass, including bare `blaKPC` (749), so carbapenem is slightly undercounted.
- Show the method caveat on Staph aureus trends. Lead hotspots with `persistent`.
- Use pooled rows only when one year is too small, and label them.

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
