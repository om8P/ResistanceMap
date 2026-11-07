"""Time the same job in Spark and pandas on the full gene table, and compare the answers.

The job counts distinct isolates per organism, country, year and drug class, as the
prevalence numerator does. Each run is a fresh process, in the same container, so both
engines get the same memory limit and neither gains from an earlier run's cache.

Usage (in the container, needs pandas and pyarrow): python3 src/timing.py
"""
import argparse
import csv
import glob
import json
import os
import platform
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

from datasets import core_organisms

ROOT = Path(__file__).resolve().parent.parent
GENES = ROOT / "data" / "parquet" / "isolate_genes"
OUTPUT = ROOT / "results" / "timing.json"
WORK = Path("/tmp/timing")
RUNS = 3
SPARK_MEMORY = "4g"
KEYS = ["organism", "country", "year", "drug_class"]
COLUMNS = ["biosample_acc", "drug_class", "country", "year"]


def run_spark(answer):
    from pyspark.sql import SparkSession
    from pyspark.sql import functions as F

    spark = SparkSession.builder.appName("timing").config("spark.sql.shuffle.partitions", "16").getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")
    started = time.perf_counter()
    genes = spark.read.parquet(str(GENES)).filter(F.col("organism").isin(core_organisms()) & F.col("country").isNotNull() & F.col("year").isNotNull()
                                                  & F.col("drug_class").isNotNull())
    split = (genes.withColumn("drug_class", F.explode(F.split("drug_class", "/")))
             .withColumn("drug_class", F.regexp_replace(F.trim("drug_class"), "FUSIDIC ACID", "FUSIDIC_ACID")))
    rows = (split.filter(~F.col("drug_class").isin("", "NONE")).groupBy(KEYS)
            .agg(F.countDistinct("biosample_acc").alias("positives")).collect())
    seconds = time.perf_counter() - started
    write_answer(answer, ((r["organism"], r["country"], r["year"], r["drug_class"], r["positives"]) for r in rows))
    spark.stop()
    return seconds


def run_pandas(answer):
    import pandas as pd

    started = time.perf_counter()
    frame = pd.read_parquet(GENES, columns=COLUMNS + ["organism"], filters=[("organism", "in", core_organisms())])
    frame = frame.dropna(subset=["country", "year", "drug_class"])
    frame["year"] = frame["year"].astype(int)
    frame["drug_class"] = frame["drug_class"].str.split("/")
    frame = frame.explode("drug_class")
    frame["drug_class"] = frame["drug_class"].str.strip().str.replace("FUSIDIC ACID", "FUSIDIC_ACID", regex=False)
    frame = frame[~frame["drug_class"].isin(["", "NONE"])]
    frame["organism"] = frame["organism"].astype(str)
    counted = frame.groupby(KEYS, observed=True)["biosample_acc"].nunique().reset_index()
    seconds = time.perf_counter() - started
    write_answer(answer, counted.itertuples(index=False, name=None))
    return seconds


def write_answer(path, rows):
    with open(path, "w", newline="") as handle:
        csv.writer(handle).writerows(sorted((a, b, int(c), d, int(e)) for a, b, c, d, e in rows))


def memory_in_use():
    """Resident memory of every process in the container except this one, in bytes."""
    total = 0
    for status in glob.glob("/proc/[0-9]*/statm"):
        try:
            if int(status.split("/")[2]) != os.getpid():
                with open(status) as handle:
                    total += int(handle.read().split()[1]) * os.sysconf("SC_PAGE_SIZE")
        except (OSError, ValueError, IndexError):
            continue
    return total


def measured_run(engine, number):
    answer = WORK / f"{engine}_{number}.csv"
    seconds_file = WORK / f"{engine}_{number}.seconds"
    if engine == "spark":
        command = ["/opt/spark/bin/spark-submit", "--driver-memory", SPARK_MEMORY, __file__]
    else:
        command = [sys.executable, __file__]
    command += ["--engine", engine, "--answer", str(answer), "--seconds", str(seconds_file)]

    baseline = memory_in_use()
    peak = [0]
    finished = threading.Event()

    def watch():
        while not finished.wait(0.2):
            peak[0] = max(peak[0], memory_in_use() - baseline)

    watcher = threading.Thread(target=watch)
    watcher.start()
    started = time.perf_counter()
    process = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    total = time.perf_counter() - started
    finished.set()
    watcher.join()

    result = {"run": number, "exit_code": process.returncode, "total_seconds": round(total, 1),
              "peak_memory_gb": round(peak[0] / 1024 ** 3, 2)}
    if process.returncode == 0:
        result["job_seconds"] = round(float(seconds_file.read_text()), 1)
    else:
        result["failure"] = "killed, likely out of memory" if process.returncode in (-9, 137) else process.stderr[-300:]
    print(engine, result, flush=True)
    return result


def summary(runs):
    good = [r for r in runs if r["exit_code"] == 0]
    if not good:
        return {"runs": runs, "completed": 0}
    return {
        "runs": runs,
        "completed": len(good),
        "median_job_seconds": statistics.median(r["job_seconds"] for r in good),
        "median_total_seconds": statistics.median(r["total_seconds"] for r in good),
        "max_peak_memory_gb": max(r["peak_memory_gb"] for r in good),
    }


def compare_answers():
    paths = {engine: WORK / f"{engine}_1.csv" for engine in ("spark", "pandas")}
    if not all(path.exists() for path in paths.values()):
        return {"compared": False}
    rows = {engine: path.read_text().splitlines() for engine, path in paths.items()}
    spark_rows, pandas_rows = set(rows["spark"]), set(rows["pandas"])
    return {"compared": True, "spark_rows": len(spark_rows), "pandas_rows": len(pandas_rows),
            "rows_only_in_spark": len(spark_rows - pandas_rows), "rows_only_in_pandas": len(pandas_rows - spark_rows),
            "identical": spark_rows == pandas_rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=["spark", "pandas"])
    parser.add_argument("--answer")
    parser.add_argument("--seconds")
    args = parser.parse_args()

    if args.engine:
        seconds = (run_spark if args.engine == "spark" else run_pandas)(args.answer)
        Path(args.seconds).write_text(str(seconds))
        return

    WORK.mkdir(exist_ok=True)
    engines = {engine: summary([measured_run(engine, n) for n in range(1, RUNS + 1)]) for engine in ("spark", "pandas")}
    import pandas
    result = {
        "job": "Distinct isolates per organism, country, year and drug class, over the full isolate_genes table",
        "gene_rows": 11274636,
        "setup": {"container_memory_limit_gb": 5, "spark_driver_memory": SPARK_MEMORY, "spark_mode": "local[*]",
                  "cpus": os.cpu_count(), "python": platform.python_version(), "pandas": pandas.__version__},
        "measure": "job_seconds excludes process start-up and writing the answer. total_seconds covers the whole "
                   "process. Peak memory is resident memory, sampled every 0.2 s. Each engine ran in a fresh process.",
        "engines": engines,
        "answers": compare_answers(),
    }
    OUTPUT.write_text(json.dumps(result, indent=2))
    print(json.dumps(result["answers"]), flush=True)


if __name__ == "__main__":
    main()
