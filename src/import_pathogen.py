"""Import one more pathogen that NCBI Pathogen Detection tracks, on the host.

Adds it to config/imported.csv, downloads its files and runs the pipeline for it
alone in the Spark container. Its results go to results/imported/<organism>/,
so the core results in results/ never change. Progress is in status.json there,
and the full output in logs/import_<organism>.log. Stops at the first failure.

Needs Docker running and internet access. Browsing the results afterwards does not.

Usage: python src/import_pathogen.py ORGANISM [--dry-run]
"""
import argparse
import csv
import json
import subprocess
import sys
import time
from pathlib import Path

from datasets import COLUMNS, IMPORTED, IMPORTED_RESULTS, ROOT, is_core
from datasets import read_rows

CONTAINER = "resistancemap-spark"
SUBMIT = ["/opt/spark/bin/spark-submit", "--driver-memory", "4g"]
LOGS = ROOT / "logs"
MUTATIONS = ROOT / "data" / "parquet" / "reference" / "point_mutations"
SPARK_STEPS = [
    ("ingest", [*SUBMIT, "src/ingest.py"]),
    ("profile", [*SUBMIT, "src/profile_data.py"]),
    ("clean", [*SUBMIT, "src/clean.py"]),
    ("genes", [*SUBMIT, "src/genes.py"]),
    ("analytics", [*SUBMIT[:1], "--master", "local[8]", *SUBMIT[1:], "src/analytics.py"]),
    ("search index", [*SUBMIT, "src/search_index.py"]),
]


def results_folder(organism):
    return IMPORTED_RESULTS / organism


def relative_results(organism):
    return results_folder(organism).relative_to(ROOT).as_posix()


def commands(organism, python=sys.executable):
    """(step name, argv) in run order. Spark steps run in the container with RESULTS_DIR set."""
    steps = [("download", [python, "src/download.py", "--organism", organism])]
    for name, argv in SPARK_STEPS:
        steps.append((name, ["docker", "exec", "-e", f"RESULTS_DIR={relative_results(organism)}", CONTAINER,
                             *argv, "--organism", organism]))
    return steps


def taxgroups():
    """Species groups with a point-mutation table in the gene catalog."""
    import pyarrow.parquet as pq

    if not MUTATIONS.exists():
        return set()
    return set(pq.read_table(MUTATIONS, columns=["taxgroup"]).column(0).unique().to_pylist())


def choose_taxon(organism, groups):
    """The organism's own mutation group, or blank. Blank leaves point mutations unmapped, which the match rate shows."""
    return organism if organism in groups else ""


def add_imported(organism, taxon, path=IMPORTED):
    """Add or replace the organism's row in config/imported.csv."""
    rows = [r for r in read_rows(path) if r["organism"] != organism]
    rows.append({"organism": organism, "label": organism.replace("_", " "), "taxon": taxon})
    with open(path, "w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda r: r["organism"]))


def write_status(organism, **values):
    path = results_folder(organism) / "status.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    status = json.loads(path.read_text()) if path.exists() else {}
    status.update(values, updated=time.strftime("%Y-%m-%d %H:%M:%S"))
    path.write_text(json.dumps(status, indent=2))
    return status


def read_status(organism):
    path = results_folder(organism) / "status.json"
    return json.loads(path.read_text()) if path.exists() else None


def container_running():
    try:
        out = subprocess.run(["docker", "ps", "--filter", f"name={CONTAINER}", "--format", "{{.Names}}"],
                             capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return out.returncode == 0 and CONTAINER in out.stdout.split()


def tracked(organism):
    from download import tracked_organisms

    return organism in tracked_organisms()


def run(organism):
    if is_core(organism):
        raise SystemExit(f"{organism} is a core organism; rebuild it with the README steps.")
    if not tracked(organism):
        raise SystemExit(f"{organism} is not in config/ncbi_organisms.csv. Run python src/download.py --list first.")
    steps = commands(organism)
    log = LOGS / f"import_{organism}.log"
    LOGS.mkdir(exist_ok=True)
    write_status(organism, name=organism, state="running", step="checks", steps=[s for s, _ in steps],
                 started=time.strftime("%Y-%m-%d %H:%M:%S"), error=None, log=log.relative_to(ROOT).as_posix())
    if not container_running():
        write_status(organism, state="failed", error=f"The {CONTAINER} container is not running. Start Docker and run docker compose up -d.")
        return 1
    taxon = choose_taxon(organism, taxgroups())
    add_imported(organism, taxon)
    write_status(organism, taxon=taxon or None)

    with open(log, "a", encoding="utf-8") as out:
        for name, argv in steps:
            write_status(organism, step=name)
            out.write(f"\n=== {name}: {' '.join(argv)}\n")
            out.flush()
            started = time.time()
            code = subprocess.run(argv, cwd=ROOT, stdout=out, stderr=subprocess.STDOUT).returncode
            out.write(f"=== {name} finished with code {code} in {time.time() - started:.0f}s\n")
            out.flush()
            if code != 0:
                write_status(organism, state="failed", error=f"Step '{name}' failed (code {code}). See {log.name}.")
                return 1
    write_status(organism, state="done", step=None, finished=time.strftime("%Y-%m-%d %H:%M:%S"))
    return 0


def start_detached(organism):
    """Start an import in the background, for the app. Returns at once."""
    flags = {}
    if sys.platform == "win32":
        flags["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        flags["start_new_session"] = True
    write_status(organism, name=organism, state="starting", step=None, error=None)
    return subprocess.Popen([sys.executable, str(ROOT / "src" / "import_pathogen.py"), organism], cwd=ROOT,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **flags)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("organism", help="An NCBI organism group, as in config/ncbi_organisms.csv")
    parser.add_argument("--dry-run", action="store_true", help="Print the steps without running them")
    args = parser.parse_args()
    if args.dry_run:
        for name, argv in commands(args.organism):
            print(f"{name}: {' '.join(argv)}")
        return 0
    return run(args.organism)


if __name__ == "__main__":
    sys.exit(main())
