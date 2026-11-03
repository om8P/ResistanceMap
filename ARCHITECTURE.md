# ResistanceMap architecture

Planned design. Built so far: download, ingest, profile, clean and genes. Update this file if the design changes during a session.

## Overview
```
NCBI Pathogen Detection             Gene catalog     Cluster lists
(6 organisms, about 1.8 GB TSV)          |                |
          |                              |                |
     download.py                         |                |
          |                              |                |
     ingest.py  ----> Parquet            |                |
          |                              |                |
     clean.py   ----> isolates           |                |
          |              |               |                |
          +-------- genes.py <-----------+----------------+
                         |
                    isolate_genes
                         |
                   analytics.py (PySpark)
                         |
                     results/
                         |
                  Streamlit app  ---> Users
```
Spark runs in Docker. The app runs on the host and reads only `results/`, so it works with Docker stopped.

## Source data
Base: `https://ftp.ncbi.nlm.nih.gov/pathogen/`

| Data | Path | Size |
|---|---|---|
| Isolates and genes | `Results/<Organism>/latest_snps/AMR/PDG*.amr.metadata.tsv` | See below |
| Cluster lists | `Results/<Organism>/latest_snps/Clusters/PDG*.reference_target.cluster_list.tsv` | Klebsiella 7 MB |
| Gene catalog | `Antimicrobial_resistance/AMRFinderPlus/database/latest/ReferenceGeneCatalog.txt` | 11,554 rows |
| Point mutations | `Antimicrobial_resistance/AMRFinderPlus/database/latest/AMRProt-mutation.tsv` | Small |

Sizes on 2026-11-03: Salmonella 836 MB, E. coli/Shigella 528 MB, Klebsiella 185 MB, Staph aureus 159 MB, Acinetobacter 60 MB, Pseudomonas 59 MB. The `PDG` version in each file name changes between releases, so never hard-code it.

Organism folders: `Salmonella`, `Escherichia_coli_Shigella`, `Klebsiella`, `Staphylococcus_aureus`, `Pseudomonas_aeruginosa`, `Acinetobacter`.

## Tables
| Table | One row per | Main columns |
|---|---|---|
| `isolates` | Isolate | `biosample_acc`, `target_acc`, `organism`, `organism_label`, `country`, `iso3`, `raw_location`, `location_flag`, `year`, `year_flag`, `collection_date`, `host`, `isolation_source`, `epi_type`, `cluster_id`, `amrfinder_analysis_type`, `AMR_genotypes_core` |
| `isolate_genes` | Isolate and gene | `biosample_acc`, `gene`, `gene_type`, `drug_class`, `drug_subclass`, `match_source`, plus `organism`, `organism_label`, `country`, `iso3`, `year` and `cluster_id` |

Both are in `data/parquet/`, in `organism=<name>` folders. `gene_type` is the suffix, or `COMPLETE` if there is none.

**Parsing rules seen in the real file**
- Missing values are the text `NULL`.
- Lists are quoted and comma-separated: `"blaTEM-1,sul1"`.
- Suffixes mark gene type: `gyrA_D87G=POINT`, `sinH=PARTIAL`.
- `geo_loc_name` looks like `USA: Western Region`.
- `collection_date` can be a year only, such as `2013`.
- Use `AMR_genotypes_core`. It leaves out some non-core genes such as `mdsA` and `mdsB`.
- An empty `AMR_genotypes_core` means analysed with no core genes (`number_core_amr_genes = 0`), not missing data. Keep these rows in the denominator.
- Placeholders can carry a reason, such as `missing: third party data`. They are not countries or dates.
- `collection_date` can also be a range (`2015/2018`) or a timestamp (`2019-09-26T10:00:04Z`).

**Join columns**
- Gene catalog: `allele` and `gene_family`, giving `class` and `subclass`. Use rows for the organism's taxon (`config/organisms.csv`) if any exist, otherwise rows open to all taxa.
- Point mutations: `taxgroup` and `standard_mutation_symbol`, giving `class` and `subclass`. Ingest removes the `#` from the first column's name.
- Cluster lists (`PDS_acc`, `target_acc`, `biosample_acc`, `gencoll_acc`): join on `biosample_acc` and use `PDS_acc` as `cluster_id`. If there are several, prefer the same `target_acc`, then the lowest `PDS_acc`.

**Gene lookup order**, recorded in `match_source`:
- `=POINT` entries: `mutation`, then `allele`, then `disrupt` (gene name before `_`, `POINT_DISRUPT` catalog rows).
- Other entries: `allele`, then `family` (family-level row), then `family_ambiguous` (all active rows of the family).
- No match: `unmapped`, with empty drug fields.
- Where rows differ, keep only the drugs all of them list: `blaNDM` stays `CARBAPENEM`, and `blaOXA` gets no subclass.

**Flags:** rows are kept with an empty value and a reason. `location_flag`: `missing`, `placeholder`, `unrecognised`. `year_flag`: `missing`, `multi_year_range`, `unparsed`, `out_of_range` (before 1910 or after the latest upload year), `after_upload`.

**Gene lookup as built:** each entry takes one lookup, recorded in `match_source`, preferring the isolate's own taxon. `=POINT` entries try `mutation`, `allele`, then `disrupt`. Others try `allele`, `family`, then `family_ambiguous`, which keeps drug fields only where the catalog rows agree. No match gives `unmapped`.

**Combined drug values:** `class` can be `MULTIDRUG` or slash-separated, and `subclass` can be `CARBAPENEM/VABORBACTAM`. Split on `/` and count the gene towards each drug listed.

## Definitions
These values live in `config/` and can be tuned.

| Measure | Definition |
|---|---|
| **Prevalence** | Isolates with at least one gene in a drug class, divided by all isolates in that organism, country and year. Count each isolate once per class |
| **Denominator** | Include isolates with no resistance genes. Dropping them would inflate every rate |
| **Confidence** | Wilson 95% interval |
| **Minimum sample** | Hide percentages when fewer than 30 isolates are in the group |
| **Outbreak-adjusted** | Count each `PDS_acc` once per organism, country and year. Isolates with no cluster count individually |
| **Rising** | Positive trend across recent years, using only years that meet the minimum sample |
| **Hotspot** | Lower confidence limit above the organism's overall rate for that drug class and year |
| **Early warning** | Gene first seen in a country in the last 3 data years, with at least 3 isolates from at least 2 clusters |
| **Last-resort drugs** | `subclass` contains `CARBAPENEM` or `COLISTIN`. Match on contains, not equals |

Recent years are incomplete, because samples are uploaded long after collection. Mark the latest years as provisional.

## Features
| Feature | Question it answers | Table used |
|---|---|---|
| World map | Where is this resistance over time? | `prevalence` |
| Trends | What is rising here? | `prevalence`, `rising` |
| Hotspots | Where is it unusually high? | `hotspots` |
| Early warnings | What has newly arrived, and how strong is the evidence? | `early_warnings` |
| Last-resort tracker | How are the most critical resistances changing? | `last_resort` |
| Gene profile | What do we know about this gene? | `first_seen`, `gene_summary` |
| Country report | What should someone in this country know? | Several |
| Confidence indicators | How far can I trust this number? | Columns on all tables |
| Outbreak-adjusted view | Is this a trend or one outbreak? | `*_adjusted` versions |
| Gene spread timeline | When did this gene reach each country? | `first_seen` |
| Country by year heatmap | Where and when did rates rise? | `prevalence` |
| Early warning timeline (optional) | What arrived recently, on how much evidence? | `early_warnings` |
| Organism by drug class heatmap (optional) | Which resistance matters for which pathogen? | `prevalence` |
| Data coverage chart (optional) | Can I trust this view? | `coverage` |
| Pathogen search (optional, after the core) | Is this pathogen, strain or disease covered, and how good is the data? | `data_profile.json`, `pipeline_summary.json`, `config/disease_pathogens.csv` |
| Pathogen import (optional, last) | Can I analyse a pathogen not yet imported? | Runs the pipeline; needs Docker and internet |

## Result files
All in `results/`.

| File | Contents |
|---|---|
| `data_profile.json` | Fill rates, date formats, country and year coverage |
| `pipeline_summary.json` | Rows kept, flagged and dropped; catalog match rate |
| `prevalence.parquet`, `prevalence_adjusted.parquet` | Rate, counts and confidence limits |
| `coverage.parquet` | Isolates by organism, country and year |
| `first_seen.parquet` | Gene, country and first year |
| `rising.parquet` | Trend per gene or drug class and country |
| `hotspots.parquet` | Flagged groups |
| `early_warnings.parquet` | New appearances and evidence counts |
| `last_resort.parquet` | Carbapenem and colistin trends |
| `gene_summary.parquet` | Per-gene totals and sources |
| `sanity_checks.json` | Checks against published gene history |
| `timing.json` | Spark vs pandas on the same job |

## Validation
- Known sample: `SAMN02147118` must give its six listed genes.
- Published history: first-seen dates for `blaNDM` and `mcr-1` should be broadly consistent with what is published.
- Tests: small hand-checked tables for prevalence, Wilson intervals and outbreak adjustment.
- Reasonable totals: row counts match source files, and catalog match rate is reported.

## Limits
- Data reflects what labs chose to sequence, and it is heavily weighted towards some countries.
- Upload delays make the latest years incomplete.
- Having a gene does not prove a drug will fail.
- Location is mostly country-level.
- About 1.8 GB of source data is modest, so one laptop may be enough for it. Report the measured Spark timing honestly.
- Not for clinical use.
