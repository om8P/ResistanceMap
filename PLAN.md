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
1. Pathogen import, then pathogen search (see the Pathogen search section).
2. Optional visuals: early warning timeline, organism by drug class heatmap, data coverage chart.
3. Country report download (keep the page).
4. Outbreak-adjusted view.
5. Gene profile page.
6. Organisms: drop Salmonella and E. coli last, since they have the most data.

## Pathogen search (after the core)
Build the core first. This extends it, and is not part of any "done when" check. Sessions 2 and 3 should take any organism name rather than assume the six.

- **Session 4, if time allows:** search imported data by pathogen name, strain or serovar, NCBI ID, or disease.
- **Day 3 buffer, last:** "import a new pathogen" as a separate action that downloads the data and runs the pipeline in the background.

Requirements:
- **Disease search:** NCBI does not link diseases to pathogens here, so write and check `config/disease_pathogens.csv` by hand. It is not always one-to-one, as pneumonia has many possible causes, so the app offers a list of pathogens rather than picking one.
- **Coverage:** NCBI Pathogen Detection only covers the organisms it tracks. A search for something else, such as a virus, says "not covered" rather than showing nothing.
- **Strain tags:** first measure how well strain and serovar fields are filled, by organism, in `results/data_profile.json`. Offer strain search only where the audit supports it.
- **Drug class lookup:** point mutations are matched per species, and the mutation file only covers about 30 species groups, so other pathogens may leave more genes unmapped. The app shows the match rate for each pathogen.
- **Small datasets:** rare pathogens will often fall below the 30-isolate minimum, so many views are hidden. The app says why.
- **Offline browsing:** browsing stays offline with Docker stopped. Only import needs Docker and internet access.

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

The tables must supply what the Session 4 visuals need, including `coverage.parquet` with isolates by country and year.

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

**Core visuals**
- Animated world map with a year slider.
- Gene spread timeline: one row per country, in order of first detection.
- Country by year heatmap.
- Trend lines with confidence bands, with provisional years shaded.
- All-isolates and outbreak-adjusted lines on one chart.

**Optional visuals (can be cut)**
- Early warning timeline, with marker size showing the evidence.
- Organism by drug class heatmap.
- Data coverage chart of isolates by country and year.

**Rules for every chart**
- Hover text shows the sample count and says "among sequenced isolates" and "genotypic resistance".
- Groups under the minimum sample are greyed out or hidden.
- On the map, "no data" looks clearly different from 0%.
- No "worst country" rankings. Sort by first detection or name.
- One colourblind-safe palette across the app.

**Not building:** Sankey diagrams, 3D globes and gene spread networks. A network would suggest transmission routes the data cannot show.

**Done when:** every page loads with Docker stopped, checked in the browser, and these questions can be answered in the app: "Is carbapenem resistance rising in Klebsiella in India?" and "When did `blaNDM` reach each country?" If India has too little data, the app must say so.

## Session 5: Report, slides, viva prep
**Prompt:** `Do Session 5. Read PROGRESS.md and only the Session 5 section of PLAN.md.`

- Write a README and rerun the whole pipeline once from its steps.
- Write the report from saved results: problem, users, data, architecture, methods, findings, validation and limits.
- State the data size honestly (about 1.8 GB of source files) and use the measured Spark timing to justify the tool choice.
- Use static versions of the app's charts in the report and slides.
- Make slides and viva notes, including a demo script and likely questions on sampling bias, genes vs lab results, and Spark.

**Done when:** the README steps work and the report's numbers match `results/`.
