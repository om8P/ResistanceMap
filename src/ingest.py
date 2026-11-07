"""Convert the raw TSV files in data/raw/manifest.json to Parquet.

Every file's Parquet row count is compared with its raw line count minus the
header. Results go to results/ingest_counts.json, and any mismatch fails the run.

Usage: spark-submit src/ingest.py [--organism NAME]
"""
import argparse
import json
import re
import sys
from pathlib import Path

from pyspark.sql import SparkSession

from datasets import core_organisms, is_core, results_dir

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "data" / "raw" / "manifest.json"
PARQUET = ROOT / "data" / "parquet"
COUNTS = results_dir() / "ingest_counts.json"


def read_tsv(spark, path):
    """Read a TSV as all strings, with NULL as missing and quoting off."""
    return (spark.read
            .option("sep", "\t")
            .option("header", True)
            .option("nullValue", "NULL")
            .option("quote", "")
            .option("inferSchema", False)
            .csv(str(path)))


def clean_name(name):
    return re.sub(r"\W+", "_", name.lstrip("#").strip()).strip("_")


def raw_counts(path):
    """Count data rows and any lines that Spark could read differently."""
    data_rows = blank = wrong_fields = stray_cr = 0
    with open(path, "rb") as source:
        expected = source.readline().count(b"\t")
        for line in source:
            data_rows += 1
            line = line.rstrip(b"\n")
            if line.endswith(b"\r"):
                line = line[:-1]
            if not line:
                blank += 1
            elif line.count(b"\t") != expected:
                wrong_fields += 1
            if b"\r" in line:
                stray_cr += 1
    return {"raw_rows": data_rows, "blank_lines": blank, "wrong_field_count": wrong_fields, "stray_cr": stray_cr}


def convert(spark, record, output):
    source = ROOT / record["path"]
    frame = read_tsv(spark, source)
    frame = frame.toDF(*[clean_name(c) for c in frame.columns])
    frame.write.mode("overwrite").parquet(str(output))

    result = raw_counts(source)
    result.update(file=record["file"], columns=len(frame.columns),
                  parquet_rows=spark.read.parquet(str(output)).count())
    result["match"] = result["raw_rows"] == result["parquet_rows"]
    print(f"{record['file']}: raw {result['raw_rows']}, parquet {result['parquet_rows']}, match {result['match']}",
          flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organism", help="Convert one organism only")
    args = parser.parse_args()

    manifest = json.loads(MANIFEST.read_text())
    counts = json.loads(COUNTS.read_text()) if COUNTS.exists() else {}
    spark = SparkSession.builder.appName("ingest").getOrCreate()
    spark.sparkContext.setLogLevel("WARN")

    core = core_organisms()
    for organism, record in manifest["organisms"].items():
        if (args.organism and organism != args.organism) or (not args.organism and organism not in core):
            continue
        for kind in ("amr", "clusters"):
            counts[f"{organism}/{kind}"] = convert(spark, record[kind], PARQUET / kind / organism)
    # An imported pathogen reuses the core gene catalog, so the reference tables stay as they are.
    if not args.organism or is_core(args.organism):
        for key, record in manifest["reference"].items():
            counts[f"reference/{key}"] = convert(spark, record, PARQUET / "reference" / key)

    COUNTS.parent.mkdir(exist_ok=True)
    COUNTS.write_text(json.dumps(counts, indent=2))
    spark.stop()
    return 0 if all(c["match"] for c in counts.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
