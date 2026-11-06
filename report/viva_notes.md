# Viva notes

Numbers come from `report/numbers.json` and `results/`. Always say "among sequenced isolates" and "genotypic resistance".

## One-minute pitch
ResistanceMap shows where and when antibiotic resistance genes are spreading, using 1,991,552 public NCBI genome records for six bacteria. PySpark in Docker cleans the data, maps each gene to a drug class and builds yearly rates by country, with confidence intervals, an outbreak-adjusted view and early warnings. A Streamlit app reads only the prepared results, so it runs offline on a laptop. It is for public health students and researchers. It never recommends a drug and is not for clinical use.

## Demo script (about 6 minutes)
Start the app before the viva with `python -m streamlit run app/app.py`. Docker can stay stopped. The map needs internet for country outlines; if there is none, use the trend chart and the heatmap figure in the slides.

1. **Map and trends.** Choose Klebsiella, carbapenem, acquired. Point out the sample count and interval on hover, and that small countries are blank (under 30 isolates). Select India: the trend is flat, 918 of 1,610 over 2013 to 2022, slope 0.06 points a year, z 0.08, not rising. Point to the grey provisional band from 2023.
2. **Outbreak-adjusted.** Switch it on. India becomes 414 of 916 over 7 usable years, slope -0.87, z -0.92. Explain that one cluster now counts once.
3. **Clinical filter.** Clinical isolates only: slope 1.44, z 1.91, just under 1.96. Say plainly that this is close, so "no rise" is not firm.
4. **Gene profile.** Choose `blaNDM`. The spread timeline shows 105 countries where it is established, earliest India in 2009. Mention that the raw earliest record is 1943 and is treated as a date error.
5. **Early warnings.** Show that `new_sequencing` rows are hidden by default: 561 of 1,393 rows, where a country had fewer than 30 earlier isolates.
6. **Evidence panel.** Klebsiella and meropenem with the `blaNDM` family: 217 of 222 lab-resistant with the gene, 510 of 1,141 without. Say this is evidence about the gene, not advice about the drug.
7. **About the data.** Coverage: USA 44.53% of isolates, India 0.60%. End on the not-for-clinical-use notice.

## Likely questions

### Sampling bias
**Q: Is this the real resistance rate in India?**
No. It is the share among isolates that labs chose to sequence. Labs often sequence outbreaks and resistant isolates, so rates can run high. The app says "among sequenced isolates" on every page and never calls a rate prevalence.

**Q: The USA dominates. Does that distort the results?**
Yes, for anything pooled across countries, which is why every rate is per country and year. The USA is 44.53% of isolates. For hotspots we compare a country with *all other countries*, so the USA is not compared mostly with itself. And the app never ranks countries.

**Q: What about small countries?**
Only 2,848 of 9,470 organism, country and year groups reach 30 isolates. Below that the rate is hidden, and the count is kept so the reader sees why. Three-year pooled periods raise the share to 37% (1,727 of 4,640), which helps a little.

**Q: Why are recent years marked provisional?**
Uploads lag collection. Only Salmonella has 90% of isolates uploaded within 5 years; Pseudomonas is at 63.81%. So 2023 onward is provisional, and that is a floor for five of the six organisms. The rising test uses 2013 to 2022 only.

**Q: How do outbreaks affect it?**
One hospital outbreak can add hundreds of near-identical genomes in a year. The outbreak-adjusted view counts each NCBI SNP cluster once per country and year. For Klebsiella in India in 2023 that cuts 960 isolates to 373 counted units.

### Genes against lab results
**Q: Does a resistance gene mean the drug will fail?**
Not always. The gene can be present but not expressed, and resistance can come from other mechanisms. Among Klebsiella tested against meropenem, 217 of 222 with a `blaNDM` family gene were resistant, but so were 510 of 1,141 without it.

**Q: So can a doctor use this to pick a drug?**
No. No gene does not prove a drug will work, and lab results exist for only 24,803 isolates, most of them environmental (14,771) rather than clinical (9,973). The app names drugs only beside resistance evidence, never in a "best" order, and says it is not for clinical use.

**Q: How do you map a gene to a drug?**
The AMRFinderPlus catalog, preferring the organism's own taxon: exact allele, then gene family. Point mutations use the species' mutation table. Where catalog rows disagree, only drugs all of them list are kept. 99.878% of entries matched. `blaKPC` is not counted for carbapenem because some catalog rows list only cephalosporins, which slightly undercounts carbapenem.

**Q: Why compare with WHO GLASS but not merge?**
They measure different things: GLASS is lab results from bloodstream infections in 32 countries; ours is genes in sequenced isolates. India 2023: GLASS 5,405 of 8,610 *K. pneumoniae* resistant to meropenem; ours 576 of 960 Klebsiella with an acquired carbapenem gene. Side by side only.

### Spark
**Q: Is 1.92 GB really big data?**
Not by size. It fits on a laptop, and the report says so. It becomes 11,274,636 gene rows. We measured instead of assuming: the same job took 11.2 s in Spark and 18.7 s in pandas (median of 3 runs), with 3.93 GB against 4.97 GB peak memory in a 5 GB container. An earlier run on a busier machine gave 28.7 s and 52.1 s: the times move, the order and the memory do not. pandas ran right at the cap, so more organisms or releases would break it. The answers were identical on all 85,404 rows.

**Q: Was the comparison fair?**
Same container, same job, 3 fresh runs each, medians reported. The pandas code was written plainly, not tuned, so a tuned version could do better. That is stated in the report.

**Q: Did anything go wrong in the final run?**
Yes. Analytics ran out of Java heap with 16 parallel tasks in a 4 GB driver. With 8 tasks (`--master local[8]`) it passed, and every result file was identical to the earlier run. It shows the memory limit is real on one laptop.

**Q: Why local mode and not a cluster?**
The data fits one machine, and local mode uses all 16 cores. The same code would run on a cluster without changes. A cluster would add cost and setup for no gain here.

**Q: Why Docker?**
Spark 4 does not support the host's Java 22. The `apache/spark:4.0.5-python3` image pins Spark, Java and Python, so the run is repeatable.

**Q: Why Parquet?**
Columnar and compressed, so later steps read only the columns they need, partitioned by organism. The app reads small Parquet files directly with pandas.

**Q: What in the pipeline is actually distributed?**
Parsing and cleaning two million rows, exploding gene lists into 11.3 million rows, joining them to the gene catalog and cluster lists, and the grouped counts behind every table. These are wide shuffles that Spark spreads over cores and spills to disk when memory is short.

### Methods and validation
**Q: Why the Wilson interval?**
It behaves well for small samples and rates near 0 or 100%, where the normal approximation gives impossible limits.

**Q: Why "established" rather than first seen?**
Single early records are often date errors, such as a 1943 `blaNDM`. Established means at least 3 isolates from at least 2 clusters, which needs more than one lab mistake.

**Q: How do you know the numbers are right?**
Row counts match the source files. The isolate and coverage tables both hold 1,991,177 isolates and every reconciliation check passes. A known sample gives its six listed genes. First-established years for `blaNDM` (India 2009) and `mcr-1` (China 2004) fit published history. pandas reproduced the Spark answers exactly. Tests cover the rules on small hand-checked tables.

**Q: Hotspots: 7,408 flags is a lot. Are they real?**
Each is a prompt to look further, not a finding. With thousands of comparisons, some will flag by chance. 4,432 persist into a neighbouring year, and the adjusted view has 4,517.

**Q: Anything that could distort trends?**
NCBI ran AMRFinderPlus in two modes. For Staph aureus the `COMBINED` share fell from 72.1% to 38.0% between 2013 and 2022, a 34.1 point shift, so its trends carry a caveat.

**Q: What would you do next?**
Pathogen search and import beyond the six organisms, which is planned but not built. Testing the map with internet off. A tuned pandas or DuckDB baseline for a fairer timing comparison.
