# ResistanceMap plan

Five sessions over 3 days, leaving Day 3 afternoon as a buffer. Start each session in a new chat and paste its prompt. Read only the section for the current session.

| Day | Session | Work |
|---|---|---|
| 1 | 1 | Setup and data audit |
| 1 | 2 | Cleaning and gene pipeline |
| 2 | 3 | Spatiotemporal analytics |
| 2 | 4 | Streamlit app |
| 3 | 5 | Report, slides, viva prep |

If time runs short, cut in this order. Always keep the map, trends, confidence indicators and early warning feed.
1. Country report download (keep the page).
2. Outbreak-adjusted view.
3. Gene profile page.
4. Organisms: drop Salmonella and E. coli last, since they have the most data.

## Session 1: Setup and data audit
**Prompt:** `Do Session 1. Read PROGRESS.md and only the Session 1 section of PLAN.md.`

- Run `git init`. Add `.gitignore` (covering `data/` and `logs/`), and `.gitattributes` forcing LF line endings. Create the folders.
- Write `docker-compose.yml` for the Spark container, with the project folder mounted and about 5 GB of memory. Confirm PySpark runs in it.
- Write `src/download.py`. File names change with each release, so read the directory listing for each organism to find the current names. Download the six `.amr.metadata.tsv` files (about 1.8 GB), the matching `cluster_list.tsv` files and `ReferenceGeneCatalog.txt`. Skip the `.xml` files.
- Write `src/ingest.py` to convert TSVs to Parquet, using tab separator, `NULL` as missing and quoting off.
- Write `src/profile_data.py`. Save to `results/data_profile.json`, by organism: row count, percent filled for `collection_date`, `geo_loc_name`, `host`, `isolation_source`, `epi_type`, `lat_lon`, `AST_phenotypes` and `AMR_genotypes_core`, plus date formats, isolates per year, top countries and India's count.

**Done when:** Spark row counts match line counts minus the header for each file, and the profile is saved. Record any finding that weakens a feature in `PROGRESS.md`.

## Session 2: Cleaning and gene pipeline
**Prompt:** `Do Session 2. Read PROGRESS.md and only the Session 2 section of PLAN.md.`

- Write `src/clean.py`: standard country from the text before the colon using `config/countries.csv`, year from `collection_date`, and an organism label. Keep rows with missing location or year but flag them, and report how many.
- Check for duplicate `biosample_acc` values and keep one row per isolate.
- Write `src/genes.py`: split `AMR_genotypes_core` into one row per gene, keep the suffix type such as `=POINT` or `=PARTIAL` as a separate column, and join drug class from the catalog on `allele`, then `gene_family`. Map `=POINT` entries to `class` and `subclass` through `standard_mutation_symbol` in `AMRProt-mutation.tsv`, and report any left unmapped.
- Join cluster IDs from the cluster lists on `biosample_acc`, using `PDS_acc` as the cluster ID.
- Add pytest tests on small known inputs.

**Done when:** tests pass, sample `SAMN02147118` gives `ant(2'')-Ia`, `aph(3')-Ia`, `blaTEM-1`, `catA1`, `dfrA10` and `sul1` with drug classes, and `results/pipeline_summary.json` records the catalog match rate and rows dropped or flagged.

## Session 3: Spatiotemporal analytics
**Prompt:** `Do Session 3. Read PROGRESS.md and only the Session 3 section of PLAN.md.`

Write `src/analytics.py` to prepare these tables for the app (see `ARCHITECTURE.md` for definitions):
- Prevalence by organism, country, year and drug class, with Wilson intervals and sample counts.
- First year each gene was seen in each country.
- Fastest-rising genes and drug classes.
- Hotspots: places where the lower confidence limit is well above the organism's overall rate, or rising.
- Early warning feed of genes newly seen in a country.
- Last-resort tracker for carbapenem and colistin resistance.
- Every prevalence table twice: all isolates and outbreak-adjusted.

Also save one timing of Spark against pandas on the full gene table, and report the real result.

**Done when:** tests pass on a small hand-checked table, tables are in `results/`, and `results/sanity_checks.json` compares `blaNDM` and `mcr-1` first-seen dates with the published history of those genes, with any oddities explained.

## Session 4: Streamlit app
**Prompt:** `Do Session 4. Read PROGRESS.md and only the Session 4 section of PLAN.md.`

Build `app/` with these pages, using Streamlit and Plotly.
- **World map:** pick organism, drug class and year, or play over time. Hide or grey out groups under the minimum sample size.
- **Early warnings:** latest new gene and country appearances, with evidence counts.
- **Last-resort drugs:** carbapenem and colistin trends and spread.
- **Gene profile:** search a gene to see its drug class, timeline, countries and sources.
- **Country report:** top threats, trends and data quality, with a downloadable file.
- **About the data:** sources, data quality, limits and a not-for-clinical-use notice.
- A switch on the relevant pages for the outbreak-adjusted view.
- A confidence indicator beside every percentage.

Use data in `data_profile.json` to label or hide views where a field is too sparse.

**Done when:** every page loads with Docker stopped, checked in the browser, and these questions can be answered in the app: "Is carbapenem resistance rising in Klebsiella in India?" and "When did `blaNDM` reach each country?" If India has too little data, the app must say so.

## Session 5: Report, slides, viva prep
**Prompt:** `Do Session 5. Read PROGRESS.md and only the Session 5 section of PLAN.md.`

- Write a README and rerun the whole pipeline once from its steps.
- Write the report from saved results: problem, users, data, architecture, methods, findings, validation and limits.
- State the data size honestly (about 1.8 GB of source files) and use the measured Spark timing to justify the tool choice.
- Make slides and viva notes, including a demo script and likely questions on sampling bias, genes vs lab results, and Spark.

**Done when:** the README steps work and the report's numbers match `results/`.
