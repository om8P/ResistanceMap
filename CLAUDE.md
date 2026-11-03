# ResistanceMap

BDSMA mini project: a spatiotemporal big data application that shows where and when antibiotic resistance is spreading, using PySpark on public NCBI data.

**Build for the user first.** The tool must be useful to a public health student or researcher. Do not add a technique only because it is on the syllabus. The course brief needs one real-life application; this is its "SpatioTemporal Data Analytics" option.

## Start of every session
1. Read `PROGRESS.md`.
2. Read only the current session's section of `PLAN.md`, not the whole file.
3. Read `ARCHITECTURE.md` only if the task needs design details, such as columns, tables or thresholds.
4. Do that session only. Do not start the next one or add features outside the plan.

## End of every session
Update `PROGRESS.md` (keep it short: replace old status, do not append a log), then ask before committing.

## Saving tokens
- Never print or read files in `data/`. Inspect with Spark summaries, `head -c` or small samples.
- Keep command output short: pipe to `tail`, `grep` or a summary. Save long logs to `logs/` and read only the end or the matching lines.
- Run jobs over about 2 minutes in the background.
- Develop on the smallest organism (Pseudomonas, 59 MB) first, then run all six.
- Read only the files the task needs, with line ranges for long files. Do not re-read a file you just edited.
- Do not spawn subagents or explore the repo broadly. The layout is below.
- Keep replies brief. Put results in `results/` and `PROGRESS.md`, not in chat.

## Fixed decisions
Do not revisit these unless something blocks the work. Record any change in `PROGRESS.md`.
- Data: NCBI Pathogen Detection `.amr.metadata.tsv` files for six organisms, the gene catalog and the cluster lists.
- Organisms: Salmonella, E. coli/Shigella, Klebsiella, Staph aureus, Pseudomonas aeruginosa, Acinetobacter.
- Analysis: PySpark in local mode inside Docker, using image `apache/spark:4.0.5-python3`. Do not install Spark on the host, because the installed Java 22 is unsupported.
- Storage: Parquet files.
- App: Streamlit on the host, reading only prepared files in `results/`, so it works with Docker stopped.
- Features: map and trends, hotspots, early warning feed, last-resort drug tracker, country report, gene profile, confidence indicators, outbreak-adjusted view.
- Out of scope: treatment suggestions, outbreak prediction, "worst country" rankings, AI chatbots, Kafka, Hadoop, Redis.

## Rules for results
- Report only measured numbers from `results/`, including unfavourable ones.
- Every percentage shown must have its sample count. Say "among sequenced isolates" and "genotypic resistance".
- The data reflects what labs chose to sequence, not all infections. Never present it as true national prevalence.
- Not for clinical use. Say so in the app and report.

## Layout
```
docker-compose.yml   Spark container
config/              countries.csv, drug and threshold settings
data/raw/            Downloaded files (not committed)
data/parquet/        Converted and cleaned tables (not committed)
logs/                Long command output (not committed)
src/download.py      Finds current file names and downloads them
src/ingest.py        TSV to Parquet
src/profile_data.py  Data quality audit
src/clean.py         Standard country and year, one row per isolate
src/genes.py         One row per isolate and gene, with drug class
src/analytics.py     Trends, spread, hotspots, early warnings
app/                 Streamlit app
tests/               pytest tests on small known inputs
results/             Prepared tables and JSON for the app
report/              Report and slides
```

## Environment
Windows 11, Python 3.11, Docker Desktop. Use forward slashes and POSIX syntax in the Bash tool. In Git Bash, set `MSYS_NO_PATHCONV=1` on `docker exec`, or container paths get rewritten. Start Docker with `docker desktop start`, and check with `docker desktop status`. Commands are recorded in `PROGRESS.md` once they work.
