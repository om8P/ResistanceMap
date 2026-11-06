# ResistanceMap

Where and when is antibiotic resistance spreading? ResistanceMap answers this for six bacteria, using public genome data from NCBI Pathogen Detection, PySpark for the analysis and a Streamlit app for browsing.

It is a BDSMA mini project, built under the course's "SpatioTemporal Data Analytics" option, for public health students and researchers.

> **Not for clinical use.** All figures show *genotypic* resistance *among sequenced isolates*. They reflect what labs chose to sequence, not all infections, and are not national prevalence. The app names antibiotics only beside resistance evidence and never recommends one.

## What it shows
- **Map and trends:** resistance by country and year, with Wilson 95% intervals, sample counts and a "rising" test.
- **Early warnings:** genes newly established in a country, with the evidence behind each.
- **Last-resort drugs:** carbapenem and colistin resistance by mechanism.
- **Gene profile, cluster watch, country report, compare countries, guided questions and an evidence panel** that shows how often a gene matches lab results.
- Every view has an **outbreak-adjusted** option, which counts each genetic cluster once, and a confidence label.

## Organisms and data
Salmonella, E. coli/Shigella, Klebsiella, Staphylococcus aureus, Pseudomonas aeruginosa and Acinetobacter: 1,991,552 isolates in six `.amr.metadata.tsv` files, 1.92 GB (1.78 GiB). The results in `results/` come from the NCBI release downloaded on 2026-11-03 (file versions are recorded in `data/raw/manifest.json`). WHO GLASS and the WHO AWaRe list are used only for comparison and labels, never merged into our rates.

## Requirements
- Python 3.11 on the host, for the app and two small host scripts.
- Docker Desktop, for the pipeline only. Spark runs in the `apache/spark:4.0.5-python3` image, so Spark and Java are not installed on the host.
- About 8 GB of memory for Docker and 3 GB of disk for the data.

```bash
python -m pip install -r requirements.txt
python -m pip install matplotlib openpyxl pytest python-pptx python-docx
```
The first line is enough for the app. The second adds the host scripts, tests and the report build.

## Run the app
The prepared results are committed in `results/`, so the app runs with Docker stopped.
```bash
python -m streamlit run app/app.py
```
The map's country outlines load from the Plotly CDN, so the map needs internet. Everything else works offline.

## Rebuild the results
Run from the project folder. In Git Bash on Windows, keep `MSYS_NO_PATHCONV=1`, or Docker paths are rewritten. Timings are for all six organisms on a 16-core laptop with the container capped at 5 GB.

1. Start Spark.
   ```bash
   docker desktop start
   docker compose up -d
   MSYS_NO_PATHCONV=1 docker exec resistancemap-spark python3 -m pip install -q --user --default-timeout=120 pytest pandas pyarrow
   ```
2. Download the data (host, about 2 GB). This fetches the *current* NCBI release, so numbers can differ slightly from those in `results/` and the report. Skip it to reuse files already in `data/raw/`.
   ```bash
   python src/download.py
   ```
   WHO files are downloaded by hand: the AWaRe list (`B09489-eng.xlsx`) into `data/raw/aware/`, and the GLASS chart downloads into `data/raw/glass/`.
3. Run the Spark steps in order (20 to 50 minutes in all, depending on the machine).
   ```bash
   MSYS_NO_PATHCONV=1 docker exec resistancemap-spark /opt/spark/bin/spark-submit --driver-memory 4g src/ingest.py
   MSYS_NO_PATHCONV=1 docker exec resistancemap-spark /opt/spark/bin/spark-submit --driver-memory 4g src/profile_data.py
   MSYS_NO_PATHCONV=1 docker exec resistancemap-spark /opt/spark/bin/spark-submit --driver-memory 4g src/clean.py
   MSYS_NO_PATHCONV=1 docker exec resistancemap-spark /opt/spark/bin/spark-submit --driver-memory 4g src/genes.py
   MSYS_NO_PATHCONV=1 docker exec resistancemap-spark /opt/spark/bin/spark-submit --master "local[8]" --driver-memory 4g src/analytics.py
   MSYS_NO_PATHCONV=1 docker exec resistancemap-spark /opt/spark/bin/spark-submit --driver-memory 4g src/sanity_checks.py
   ```
4. Run the checks (about 10 minutes).
   ```bash
   MSYS_NO_PATHCONV=1 docker exec resistancemap-spark python3 src/timing.py
   MSYS_NO_PATHCONV=1 docker exec resistancemap-spark /opt/spark/bin/spark-submit --driver-memory 4g src/method_check.py
   ```
5. Build the WHO comparison and label files (host).
   ```bash
   python src/aware.py
   python src/glass.py
   ```
6. Rebuild the report figures and numbers (host).
   ```bash
   python report/make_figures.py
   ```

To try the pipeline on one small organism first, add `--organism Pseudomonas_aeruginosa` to each step from `download.py` to `analytics.py`. With that flag, `analytics.py` writes to `data/dev_results/` and leaves `results/` alone.

## Tests
```bash
python -m pytest tests/test_app_rules.py tests/test_app_pages.py tests/test_aware.py -q -p no:cacheprovider
MSYS_NO_PATHCONV=1 docker exec resistancemap-spark python3 -m pytest tests -q -p no:cacheprovider
```
The first runs on the host in about a minute. The second runs every test in the container and takes about 3 to 5 minutes.

## Layout
```
docker-compose.yml   Spark container
config/              Countries, organisms, thresholds, AWaRe and GLASS mappings
src/                 Pipeline: download, ingest, profile, clean, genes, analytics, checks
app/                 Streamlit app (reads results/ only)
tests/               pytest tests on small hand-checked inputs
results/             Prepared tables and JSON for the app
report/              Report, slides, viva notes and the figure script
data/, logs/         Downloads, Parquet and logs (not committed)
```
Design details, definitions and thresholds are in `ARCHITECTURE.md`. Measured findings are in `results/findings.md` and the report.

## Limits
- Sequencing is uneven: the USA is 44.53% of isolates and India 0.60%. Only 2,848 of 9,470 organism, country and year groups reach the 30-isolate minimum.
- Uploads lag collection, so 2023 onward is marked provisional.
- A resistance gene does not prove a drug will fail, and its absence does not prove a drug will work.
