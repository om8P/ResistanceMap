"""Static figures and cited numbers for the report and slides, read from results/.

Writes report/figures/*.png and report/numbers.json. Every number in the report
should come from numbers.json, so a rebuild of results/ can be checked.

Usage: python report/make_figures.py [--results DIR]
"""
import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "report" / "figures"
NOTE = "Genotypic resistance among sequenced isolates. Not national prevalence. Not for clinical use."
BLUE, ORANGE, GREY, GREEN, PURPLE = "#2a6fb0", "#d9822b", "#8a8f98", "#3a9a5b", "#7a5ab5"
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.titleweight": "bold", "axes.titlesize": 11, "figure.dpi": 150})


def save(fig, name, note=True):
    if note:
        fig.text(0.01, 0.005, NOTE, fontsize=7, color=GREY)
    fig.tight_layout(rect=(0, 0.03 if note else 0, 1, 1))
    fig.savefig(OUT / f"{name}.png", bbox_inches="tight")
    plt.close(fig)


def shade_provisional(ax, start, end):
    ax.axvspan(start - 0.5, end + 0.5, color=GREY, alpha=0.12, lw=0)
    ax.text(start - 0.4, ax.get_ylim()[1] * 0.97, "provisional", fontsize=7, color=GREY, va="top")


def coverage_figures(res, years):
    cov = pd.read_parquet(res / "coverage.parquet")
    all_isolates = int(cov.isolates.sum())
    share = cov.groupby("country").isolates.sum() / all_isolates * 100
    india = cov[cov.country == "India"].groupby("organism").isolates.sum()
    cov = cov[cov.country.notna() & cov.year.notna()]
    total = cov.isolates.sum()
    by_country = cov.groupby("country").isolates.sum().sort_values(ascending=False)
    top = by_country.head(12)[::-1]
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.barh(top.index, top.values, color=BLUE)
    for i, v in enumerate(top.values):
        ax.text(v, i, f" {v:,} ({v / total:.1%})", va="center", fontsize=8)
    ax.set_xlabel("Sequenced isolates with a usable country and year")
    ax.set_title("Sequencing is uneven: isolates by country, top 12")
    ax.set_xlim(0, top.max() * 1.3)
    save(fig, "coverage_by_country")

    by_year = cov[(cov.year >= 2000)].pivot_table(index="year", columns="organism_label", values="isolates",
                                                  aggfunc="sum").fillna(0)
    fig, ax = plt.subplots(figsize=(7, 3.6))
    by_year.plot.area(ax=ax, lw=0, alpha=0.85, colormap="tab10")
    ax.set_ylabel("Sequenced isolates")
    ax.set_xlabel("Collection year")
    ax.set_title("Isolates by collection year, 2000 on")
    ax.legend(fontsize=7, ncol=2, frameon=False, loc="upper left")
    shade_provisional(ax, years["provisional_from"], years["latest_year"])
    save(fig, "coverage_by_year")
    return {"isolates": all_isolates, "isolates_with_country_and_year": int(total),
            "usa_share_pct_of_all": round(float(share["USA"]), 2), "india_share_pct_of_all": round(float(share["India"]), 2),
            "india_by_organism": {o: int(v) for o, v in india.items()}, "india_total": int(india.sum()),
            "top_countries": {c: int(v) for c, v in by_country.head(5).items()},
            "groups": int(len(cov)), "groups_min_sample": int((cov.isolates >= 30).sum())}


def trend_figure(res, years):
    out = {}
    fig, ax = plt.subplots(figsize=(7, 3.8))
    for name, color, label in [("last_resort", BLUE, "All isolates"),
                               ("last_resort_adjusted", ORANGE, "Outbreak-adjusted (one per cluster)")]:
        lr = pd.read_parquet(res / f"{name}.parquet")
        s = lr[(lr.organism == "Klebsiella") & (lr.country == "India") & (lr.drug == "CARBAPENEM")
               & (lr.mechanism == "acquired") & lr.meets_min_sample].sort_values("year")
        ax.plot(s.year, s.rate * 100, "o-", color=color, label=label, ms=4)
        ax.fill_between(s.year, s.ci_low * 100, s.ci_high * 100, color=color, alpha=0.15, lw=0)
        y23 = lr[(lr.organism == "Klebsiella") & (lr.country == "India") & (lr.drug == "CARBAPENEM")
                 & (lr.mechanism == "acquired") & (lr.year == 2023)]
        out[name] = {"years_shown": [int(y) for y in s.year],
                     "2023": {"n": int(y23.n.iloc[0]), "positives": int(y23.positives.iloc[0])} if len(y23) else None}
    ax.set_ylim(0, 100)
    ax.set_ylabel("% with an acquired carbapenem gene")
    ax.set_xlabel("Collection year")
    ax.set_title("Klebsiella in India: acquired carbapenem genes, 95% Wilson interval")
    ax.legend(fontsize=8, frameon=False, loc="lower right")
    shade_provisional(ax, years["provisional_from"], years["latest_year"])
    save(fig, "trend_klebsiella_india_carbapenem")
    for name in ["rising", "rising_adjusted"]:
        r = pd.read_parquet(res / f"{name}.parquet")
        row = r[(r.organism == "Klebsiella") & (r.country == "India") & (r.kind == "last_resort")
                & (r.value == "CARBAPENEM:acquired")].iloc[0]
        out[name] = {k: (None if pd.isna(row[k]) else round(float(row[k]), 2)) for k in
                     ["years_used", "n", "positives", "slope_points_per_year", "z",
                      "slope_points_per_year_with_provisional", "z_with_provisional"]}
        out[name]["rising"] = bool(row.rising)
    src = pd.read_parquet(res / "rising_by_source.parquet")
    row = src[(src.organism == "Klebsiella") & (src.country == "India") & (src.kind == "last_resort")
              & (src.value == "CARBAPENEM:acquired") & (src.epi_type == "clinical")]
    if len(row):
        row = row.iloc[0]
        out["rising_clinical"] = {"slope_points_per_year": round(float(row.slope_points_per_year), 2),
                                  "z": round(float(row.z), 2), "rising": bool(row.rising),
                                  "years_used": int(row.years_used), "n": int(row.n), "positives": int(row.positives)}
    return out


def heatmap_figure(res, years):
    lr = pd.read_parquet(res / "last_resort.parquet")
    s = lr[(lr.organism == "Klebsiella") & (lr.drug == "CARBAPENEM") & (lr.mechanism == "acquired")
           & (lr.year.between(2013, years["latest_year"]))]
    shown = s[s.meets_min_sample]
    top = shown.groupby("country").year.nunique().sort_values(ascending=False).head(15).index
    grid = shown[shown.country.isin(top)].pivot_table(index="country", columns="year", values="rate") * 100
    grid = grid.sort_index()  # alphabetical, so the chart is not read as a ranking
    fig, ax = plt.subplots(figsize=(8, 4.8))
    im = ax.imshow(grid.values, aspect="auto", cmap="viridis", vmin=0, vmax=100)
    ax.set_yticks(range(len(grid.index)), grid.index, fontsize=8)
    ax.set_xticks(range(len(grid.columns)), [str(c) for c in grid.columns], fontsize=7, rotation=45)
    ax.set_title("Klebsiella: % with an acquired carbapenem gene (blank: under 30 isolates)\n"
                 "15 countries with the most usable years, alphabetical")
    fig.colorbar(im, ax=ax, label="% of sequenced isolates", shrink=0.8)
    save(fig, "heatmap_klebsiella_carbapenem")


def spread_figure(res):
    fs = pd.read_parquet(res / "first_seen.parquet")
    out = {}
    fig, ax = plt.subplots(figsize=(7, 3.6))
    for gene, color in [("blaNDM", BLUE), ("mcr-1", ORANGE)]:
        g = fs[(fs.organism == "ALL") & (fs.level == "family") & (fs.gene == gene)]
        est = g.established_year.dropna().astype(int)
        cum = est.value_counts().sort_index().cumsum()
        cum = cum[cum.index >= 2000]
        ax.step(cum.index, cum.values, where="post", color=color, label=f"{gene} family")
        first = g[g.established_year == est.min()]
        out[gene] = {"countries_on_record": int(g.first_year.notna().sum()), "countries_established": int(len(est)),
                     "earliest_established": int(est.min()), "earliest_established_countries": sorted(first.country)}
    ax.set_ylabel("Countries where established")
    ax.set_xlabel("Established year (3+ isolates from 2+ clusters)")
    ax.set_title("How two last-resort resistance genes spread between countries")
    ax.legend(frameon=False, fontsize=8)
    save(fig, "spread_blandm_mcr1")
    return out


def timing_figure(res):
    t = json.loads((res / "timing.json").read_text())
    eng = t["engines"]
    fig, axes = plt.subplots(1, 2, figsize=(7, 2.8))
    names = ["spark", "pandas"]
    axes[0].bar(names, [eng[n]["median_job_seconds"] for n in names], color=[BLUE, GREY])
    axes[0].set_title("Median job time (s)")
    axes[1].bar(names, [eng[n]["max_peak_memory_gb"] for n in names], color=[BLUE, GREY])
    axes[1].axhline(t["setup"]["container_memory_limit_gb"], color=ORANGE, ls="--", lw=1)
    axes[1].text(1.45, t["setup"]["container_memory_limit_gb"], "5 GB cap", color=ORANGE, fontsize=8, va="bottom", ha="right")
    axes[1].set_title("Peak memory (GB)")
    for ax, fmt in zip(axes, ["{:.1f}", "{:.2f}"]):
        for p in ax.patches:
            ax.text(p.get_x() + p.get_width() / 2, p.get_height(), fmt.format(p.get_height()), ha="center",
                    va="bottom", fontsize=8)
    fig.suptitle(f"Same job on {t['gene_rows']:,} gene rows, 3 runs each", fontsize=10)
    save(fig, "timing_spark_pandas", note=False)
    return {"gene_rows": t["gene_rows"], "identical": t["answers"]["identical"], "rows": t["answers"]["spark_rows"],
            **{f"{n}_{k}": eng[n][k] for n in names
               for k in ["median_job_seconds", "median_total_seconds", "max_peak_memory_gb"]}}


def agreement_figure(res):
    g = pd.read_parquet(res / "gene_lab_agreement.parquet")
    row = g[(g.organism == "Klebsiella") & (g.level == "family") & (g.gene == "blaNDM")
            & (g.antibiotic == "meropenem")].iloc[0]
    fig, ax = plt.subplots(figsize=(6, 2.6))
    labels = [f"blaNDM family present\n({row.with_gene_resistant} of {row.with_gene})",
              f"blaNDM family absent\n({row.without_gene_resistant} of {row.without_gene})"]
    rates = [row.with_gene_rate * 100, row.without_gene_rate * 100]
    lows = [row.with_gene_ci_low * 100, row.without_gene_ci_low * 100]
    highs = [row.with_gene_ci_high * 100, row.without_gene_ci_high * 100]
    ax.barh(labels, rates, color=[BLUE, GREY],
            xerr=[[r - lo for r, lo in zip(rates, lows)], [h - r for r, h in zip(rates, highs)]], capsize=3)
    ax.set_xlim(0, 100)
    ax.set_xlabel("% lab-resistant to meropenem among tested isolates")
    ax.set_title("Klebsiella: does the gene match the lab result?")
    save(fig, "agreement_klebsiella_meropenem")
    return {"with_gene": int(row.with_gene), "with_gene_resistant": int(row.with_gene_resistant),
            "without_gene": int(row.without_gene), "without_gene_resistant": int(row.without_gene_resistant)}


def architecture_figure():
    fig, ax = plt.subplots(figsize=(9.5, 2.8))
    ax.axis("off")
    steps = [("NCBI Pathogen\nDetection\n6 TSV, 1.92 GB", GREY), ("download.py\n(host)", GREY),
             ("ingest.py\nTSV to Parquet", BLUE), ("clean.py\none row\nper isolate", BLUE),
             ("genes.py\ngene to\ndrug class", BLUE), ("analytics.py\ntrends, hotspots,\nwarnings", BLUE),
             ("results/\nParquet + JSON", GREEN), ("Streamlit app\n(host, offline)", ORANGE)]
    w, gap = 0.112, 0.013
    for i, (text, color) in enumerate(steps):
        x = i * (w + gap)
        ax.add_patch(plt.Rectangle((x, 0.35), w, 0.45, color=color, alpha=0.18, ec=color, lw=1.2))
        ax.text(x + w / 2, 0.575, text, ha="center", va="center", fontsize=7.5)
        if i:
            ax.annotate("", (x, 0.575), (x - gap, 0.575), arrowprops={"arrowstyle": "->", "lw": 1})
    ax.add_patch(plt.Rectangle((2 * (w + gap) - 0.005, 0.25), 4 * (w + gap) - gap + 0.01, 0.62, fill=False,
                               ec=BLUE, ls="--", lw=1))
    ax.text(2 * (w + gap), 0.17, "PySpark 4.0.5, local mode, in Docker (5 GB)", fontsize=8, color=BLUE)
    ax.text(5 * (w + gap), 0.95, "gene catalog + point mutations + cluster lists", fontsize=7.5, color=GREY, ha="center")
    ax.annotate("", (4 * (w + gap) + w / 2, 0.8), (5 * (w + gap), 0.92), arrowprops={"arrowstyle": "->", "color": GREY})
    ax.set_xlim(0, 1)
    ax.set_ylim(0.1, 1)
    save(fig, "architecture", note=False)


def summary_numbers(res):
    p = json.loads((res / "pipeline_summary.json").read_text())
    prof = json.loads((res / "data_profile.json").read_text())
    sanity = json.loads((res / "sanity_checks.json").read_text())
    method = json.loads((res / "method_check.json").read_text())
    ew = pd.read_parquet(res / "early_warnings.parquet")
    hs = pd.read_parquet(res / "hotspots.parquet")
    hsa = pd.read_parquet(res / "hotspots_adjusted.parquet")
    cw = pd.read_parquet(res / "cluster_watch.parquet")
    glass = pd.read_parquet(res / "glass.parquet")
    lr = pd.read_parquet(res / "last_resort.parquet")
    pooled = pd.read_parquet(res / "prevalence_pooled.parquet").groupby(
        ["organism", "country", "period_start"]).n.max()
    pooled = pooled[pooled.index.get_level_values("country").notna()]
    g_in = glass[(glass.iso3 == "IND") & (glass.year == 2023) & (glass.antibiotic.str.lower() == "meropenem")
                 & glass.pathogen.str.contains("pneumoniae")]
    ok = {k: v for k, v in sanity["reconciliation"].items() if isinstance(v, int) and not isinstance(v, bool)}
    rows_in = {o: v["clean"]["rows_in"] for o, v in p["organisms"].items()}
    both = lr[(lr.drug == "CARBAPENEM+COLISTIN") & (lr.mechanism == "acquired")].groupby("organism_label").positives.sum()
    return {
        "rows_in": rows_in, "rows_in_total": sum(rows_in.values()),
        "isolates_kept": sum(v["clean"]["isolates_kept"] for v in p["organisms"].values()),
        "gene_rows": sum(v["genes"]["gene_rows"] for v in p["organisms"].values()),
        "catalog_match_pct": round(100 - 100 * sum(v["genes"]["by_match_source"].get("unmapped", 0)
                                                   for v in p["organisms"].values())
                                   / sum(v["genes"]["gene_rows"] for v in p["organisms"].values()), 3),
        "result_files": len([f for f in res.iterdir() if f.suffix in (".parquet", ".json")]),
        "table_rows": p["analytics"]["rows"], "years": p["analytics"]["years"],
        "lab_results": {k: p["analytics"]["lab_results"][k] for k in ["isolates_with_results", "antibiotic_results", "by_source"]},
        "profile": {o: {"rows": v["rows"], "date_pct": v["fill"]["collection_date"]["pct_filled"],
                        "geo_pct": v["fill"]["geo_loc_name"]["pct_filled"],
                        "uploaded_5y_pct": v["upload_delay"]["cumulative_pct_by_lag_years"]["5"]}
                    for o, v in prof["organisms"].items()},
        "reconciliation_isolates": [sanity["reconciliation"]["isolates_in_table"], sanity["reconciliation"]["isolates_in_coverage"]],
        "reconciliation_nonzero": {k: v for k, v in ok.items() if v and not k.startswith("isolates_in")},
        "reconciliation_passed": sanity["reconciliation"].get("passed"),
        "sanity_genes": {g: v["in_data"] for g, v in sanity["genes"].items()},
        "method_staph": method["share_shift"]["Staphylococcus_aureus"],
        "early_warnings": int(len(ew)), "early_warnings_new_sequencing": int(ew.new_sequencing.sum()),
        "early_warnings_shown_by_default": int((~ew.new_sequencing).sum()),
        "hotspots": int(len(hs)), "hotspots_adjusted": int(len(hsa)),
        "hotspots_persistent": int(hs.persistent.sum()) if "persistent" in hs else None,
        "hotspots_adjusted_persistent": int(hsa.persistent.sum()) if "persistent" in hsa else None,
        "clusters": int(len(cw)), "clusters_recent_multi_country": int((cw.recent_country_count >= 2).sum()),
        "clusters_new": int(cw.new_since_window.sum()), "clusters_acquired_last_resort": int(cw.acquired_last_resort.sum()),
        "both_last_resort_acquired_by_organism": {k: int(v) for k, v in both.items()},
        "both_last_resort_acquired_total": int(both.sum()),
        "pooled_periods": int(len(pooled)), "pooled_periods_min_sample": int((pooled >= 30).sum()),
        "glass_india_kpn_meropenem_2023": {"tested": int(g_in.tested.iloc[0]), "resistant": int(g_in.resistant.iloc[0])}
        if len(g_in) else None,
        "glass_meets_min": int(glass.meets_min_sample.sum()),
        "glass_countries": int(glass.iso3.nunique()), "glass_rows": int(len(glass)),
        "glass_years": [int(glass.year.min()), int(glass.year.max())],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", default=str(ROOT / "results"))
    res = Path(parser.parse_args().results)
    OUT.mkdir(parents=True, exist_ok=True)
    years = json.loads((res / "pipeline_summary.json").read_text())["analytics"]["years"]
    numbers = summary_numbers(res)
    numbers["coverage"] = coverage_figures(res, years)
    numbers["klebsiella_india"] = trend_figure(res, years)
    heatmap_figure(res, years)
    numbers["spread"] = spread_figure(res)
    numbers["timing"] = timing_figure(res)
    numbers["agreement_klebsiella_meropenem_blaNDM"] = agreement_figure(res)
    architecture_figure()
    (ROOT / "report" / "numbers.json").write_text(json.dumps(numbers, indent=2, default=str))
    print(f"wrote {len(list(OUT.glob('*.png')))} figures and report/numbers.json")


if __name__ == "__main__":
    main()
