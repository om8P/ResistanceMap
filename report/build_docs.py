"""Build report/report.docx from report/report.md, and report/slides.pptx.

Run report/make_figures.py first. Slide numbers are read from report/numbers.json.

Usage: python report/build_docs.py
"""
import json
import re
from pathlib import Path

from docx import Document
from docx.shared import Inches, Pt, RGBColor
from pptx import Presentation
from pptx.dml.color import RGBColor as PRGB
from pptx.util import Inches as PIn, Pt as PPt

REPORT = Path(__file__).resolve().parent
FIG = REPORT / "figures"
INLINE = re.compile(r"(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)")


def add_inline(par, text):
    for part in INLINE.split(text):
        if not part:
            continue
        if part.startswith("**"):
            par.add_run(part[2:-2]).bold = True
        elif part.startswith("`"):
            run = par.add_run(part[1:-1])
            run.font.name = "Consolas"
            run.font.size = Pt(9.5)
        elif part.startswith("*"):
            par.add_run(part[1:-1]).italic = True
        else:
            par.add_run(part)


def build_docx():
    doc = Document()
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(11)
    lines = (REPORT / "report.md").read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(set(c) <= set("-: ") for c in cells):
                    rows.append(cells)
                i += 1
            table = doc.add_table(rows=len(rows), cols=len(rows[0]))
            table.style = "Light Grid Accent 1"
            for r, cells in enumerate(rows):
                for c, text in enumerate(cells):
                    par = table.cell(r, c).paragraphs[0]
                    add_inline(par, text)
                    for run in par.runs:
                        run.font.size = Pt(9.5)
                        run.bold = run.bold or r == 0
            doc.add_paragraph()
            continue
        m = re.match(r"!\[[^]]*\]\(([^)]+)\)", line)
        if m:
            doc.add_picture(str(REPORT / m.group(1)), width=Inches(6.2))
        elif line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            doc.add_heading(line.lstrip("# ").replace("`", ""), level=0 if level == 1 else level - 1)
        elif line.startswith("> "):
            par = doc.add_paragraph()
            add_inline(par, line[2:])
            for run in par.runs:
                run.font.color.rgb = RGBColor(0x9C, 0x2B, 0x2B)
        elif line.startswith("- "):
            add_inline(doc.add_paragraph(style="List Bullet"), line[2:])
        elif re.match(r"\d+\. ", line):
            add_inline(doc.add_paragraph(style="List Number"), line.split(". ", 1)[1])
        elif line.strip():
            add_inline(doc.add_paragraph(), line)
        i += 1
    doc.save(REPORT / "report.docx")


DARK, ACCENT, MUTED = PRGB(0x1F, 0x2A, 0x37), PRGB(0x2A, 0x6F, 0xB0), PRGB(0x6B, 0x72, 0x80)
FOOT = "Genotypic resistance among sequenced isolates. Not national prevalence. Not for clinical use."


def slide(prs, title, bullets=(), image=None, notes=""):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    box = s.shapes.add_textbox(PIn(0.5), PIn(0.3), PIn(12.3), PIn(0.9))
    p = box.text_frame.paragraphs[0]
    p.text, p.font.size, p.font.bold, p.font.color.rgb = title, PPt(30), True, DARK
    bar = s.shapes.add_shape(1, PIn(0.55), PIn(1.15), PIn(1.2), PIn(0.06))
    bar.fill.solid()
    bar.fill.fore_color.rgb = ACCENT
    bar.line.fill.background()
    text_w = 5.6 if image else 12.3
    if bullets:
        tf = s.shapes.add_textbox(PIn(0.5), PIn(1.35), PIn(text_w), PIn(5.4)).text_frame
        tf.word_wrap = True
        for k, b in enumerate(bullets):
            p = tf.paragraphs[0] if k == 0 else tf.add_paragraph()
            sub = b.startswith("  ")
            p.text = ("– " if sub else "• ") + b.strip()
            p.font.size = PPt(15 if sub else 18)
            p.font.color.rgb = MUTED if sub else DARK
            p.level = 1 if sub else 0
            p.space_after = PPt(8)
    if image:
        left = 6.4 if bullets else 1.2
        width = 6.6 if bullets else 10.9
        s.shapes.add_picture(str(FIG / image), PIn(left), PIn(1.4), width=PIn(width))
    foot = s.shapes.add_textbox(PIn(0.5), PIn(7.0), PIn(12.3), PIn(0.4)).text_frame.paragraphs[0]
    foot.text, foot.font.size, foot.font.color.rgb = FOOT, PPt(10), MUTED
    if notes:
        s.notes_slide.notes_text_frame.text = notes
    return s


def title_slide(prs, n):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    band = s.shapes.add_shape(1, 0, PIn(2.3), prs.slide_width, PIn(2.6))
    band.fill.solid()
    band.fill.fore_color.rgb = DARK
    band.line.fill.background()
    tf = s.shapes.add_textbox(PIn(0.8), PIn(2.5), PIn(11.7), PIn(2.3)).text_frame
    tf.word_wrap = True
    lines = [("ResistanceMap", 54, True), ("Where and when is antibiotic resistance spreading?", 26, False),
             (f"{n['rows_in_total']:,} sequenced isolates, six bacteria, PySpark and Streamlit", 18, False)]
    for k, (text, size, bold) in enumerate(lines):
        p = tf.paragraphs[0] if k == 0 else tf.add_paragraph()
        p.text, p.font.size, p.font.bold, p.font.color.rgb = text, PPt(size), bold, PRGB(0xFF, 0xFF, 0xFF)
    sub = s.shapes.add_textbox(PIn(0.8), PIn(5.3), PIn(11.7), PIn(0.6)).text_frame.paragraphs[0]
    sub.text, sub.font.size, sub.font.color.rgb = "BDSMA mini project · SpatioTemporal Data Analytics", PPt(16), MUTED
    foot = s.shapes.add_textbox(PIn(0.8), PIn(6.8), PIn(11.7), PIn(0.4)).text_frame.paragraphs[0]
    foot.text, foot.font.size, foot.font.color.rgb = FOOT, PPt(11), MUTED
    s.notes_slide.notes_text_frame.text = ("Open with the question. One sentence on what the tool is, "
                                           "one on who it is for.")


def build_pptx():
    n = json.loads((REPORT / "numbers.json").read_text())
    k, t, sp, cov = n["klebsiella_india"], n["timing"], n["spread"], n["coverage"]
    ag = n["agreement_klebsiella_meropenem_blaNDM"]
    prs = Presentation()
    prs.slide_width, prs.slide_height = PIn(13.333), PIn(7.5)

    title_slide(prs, n)
    slide(prs, "The problem", [
        "Resistance genes appear in one country, become established, then spread",
        "Carbapenems and colistin are last-resort drugs: genes against them matter most",
        f"NCBI holds {n['rows_in_total']:,} records for six bacteria, but the files are messy",
        "  Six date formats, free-text places, placeholders such as 'missing'",
        "  Outbreaks flood single years; recent years are incomplete",
    ], notes="Explain why raw counts mislead: outbreaks and upload delay.")
    slide(prs, "Users and guardrails", [
        "Public health students and researchers first; doctors may read it",
        "Every percentage has its count, Wilson interval and confidence label",
        "Says 'among sequenced isolates' and 'genotypic resistance' everywhere",
        "Never recommends a drug, never ranks countries",
        "Not for clinical use",
    ], notes="Doctors may read it, so the app shows evidence about genes, never advice about drugs.")
    slide(prs, "Data", [
        f"{n['rows_in_total']:,} rows, 1.92 GB TSV, six organisms",
        f"{n['gene_rows']:,} isolate and gene rows after splitting gene lists",
        "Gene catalog and cluster lists from NCBI",
        "WHO GLASS and AWaRe: comparison and labels only, never merged",
        f"USA {cov['usa_share_pct_of_all']}% of isolates, India {cov['india_share_pct_of_all']}%",
        f"Only {cov['groups_min_sample']:,} of {cov['groups']:,} country-year groups reach 30 isolates",
    ], "coverage_by_country.png", notes="The skew is the first limit to state. It shapes every page.")
    slide(prs, "Architecture", [], "architecture.png",
          notes="Spark in Docker because the host Java 22 is unsupported. Parquet throughout. "
                "The app reads only results/, so it runs with Docker stopped.")
    slide(prs, "Methods", [
        "Prevalence: isolates with a gene in the class / all isolates, zero-gene isolates kept",
        "Wilson 95% interval; hidden under 30 isolates",
        "Outbreak-adjusted: one count per SNP cluster per country and year",
        "Rising: slope > 0 and Cochran-Armitage z ≥ 1.96 over 2013–2022",
        "Established: 3+ isolates from 2+ clusters, not the first raw record",
        "Early warning: newly established in last 3 years, 'new sequencing' flagged",
        "Provisional from 2023 because uploads lag collection",
    ], notes="Each rule exists to stop one specific over-reading.")
    slide(prs, "Klebsiella in India: no clear rise", [
        f"2013–2022: {int(k['rising']['positives']):,} of {int(k['rising']['n']):,}, "
        f"slope {k['rising']['slope_points_per_year']} points/yr, z {k['rising']['z']}",
        f"Adjusted: slope {k['rising_adjusted']['slope_points_per_year']}, z {k['rising_adjusted']['z']}",
        f"Clinical only: slope {k['rising_clinical']['slope_points_per_year']}, z {k['rising_clinical']['z']}",
        "  Just under 1.96, so not a firm 'no rise'",
        "High level partly reflects what labs choose to sequence",
    ], "trend_klebsiella_india_carbapenem.png", notes="State the unfavourable result plainly.")
    slide(prs, "Spread of blaNDM and mcr-1", [
        f"blaNDM: established in {sp['blaNDM']['countries_established']} countries; "
        f"earliest {sp['blaNDM']['earliest_established']}, {', '.join(sp['blaNDM']['earliest_established_countries'])}",
        "  Fits its 2008 discovery linked to New Delhi",
        f"mcr-1: established in {sp['mcr-1']['countries_established']} countries; "
        f"earliest {sp['mcr-1']['earliest_established']}, {', '.join(sp['mcr-1']['earliest_established_countries'])}",
        "  Before its 2015 report, fits look-back studies",
        "Raw first records include errors such as a 1943 blaNDM",
    ], "spread_blandm_mcr1.png", notes="This is the validation against published history.")
    slide(prs, "Genes against lab results", [
        f"Klebsiella and meropenem, blaNDM family present: {ag['with_gene_resistant']} of {ag['with_gene']} resistant",
        f"Absent: {ag['without_gene_resistant']:,} of {ag['without_gene']:,} resistant",
        "A strong marker, but absence does not mean susceptible",
        f"Lab results exist for only {n['lab_results']['isolates_with_results']:,} isolates",
    ], "agreement_klebsiella_meropenem.png", notes="Evidence about the gene, not advice about the drug.")
    slide(prs, "Why Spark", [
        f"Same job on {t['gene_rows']:,} rows, 3 runs each, 5 GB container",
        f"Spark {t['spark_median_job_seconds']} s, pandas {t['pandas_median_job_seconds']} s (median job)",
        f"Peak memory {t['spark_max_peak_memory_gb']} GB against {t['pandas_max_peak_memory_gb']} GB",
        "  pandas ran right at the 5 GB cap",
        f"Identical answers on all {t['rows']:,} rows",
        "Honest: 1.92 GB is modest; Spark buys headroom and scaling",
    ], "timing_spark_pandas.png", notes="Do not oversell. The data fits on a laptop.")
    slide(prs, "Validation", [
        "Row counts match source files for every organism",
        f"Reconciliation: {n['reconciliation_isolates'][0]:,} isolates in both tables; all checks pass",
        "Known sample SAMN02147118 gives its six genes",
        "First-established years fit published gene history",
        "pytest on small hand-checked tables; pandas reproduces Spark exactly",
        "Staph aureus method mix shifted 34.1 points: trend caveat",
    ], notes="Validation is what lets a reader trust the numbers.")
    slide(prs, "Limits", [
        "Sampling bias: labs choose what to sequence; not prevalence",
        "Upload delay: 2023 on is provisional",
        "A gene is not a lab result; no gene does not mean a drug works",
        "Country and year only; most groups are under 30 isolates",
        "Many comparisons: some hotspots flag by chance",
        "Not for clinical use",
    ], notes="Say these before the examiner asks.")
    slide(prs, "Demo", [
        "Map and trends: Klebsiella, carbapenem, acquired, India",
        "Switch to outbreak-adjusted, then clinical only",
        "Gene profile: blaNDM spread timeline",
        "Early warnings: new-sequencing rows hidden by default",
        "Evidence panel: blaNDM against meropenem",
        "About the data: coverage and limits",
    ], notes="Follow report/viva_notes.md for the full script.")
    prs.save(REPORT / "slides.pptx")
    return len(prs.slides)


if __name__ == "__main__":
    build_docx()
    print(f"wrote report/report.docx and report/slides.pptx ({build_pptx()} slides)")
