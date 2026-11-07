"""Which organisms a run covers, and where its results go.

The six core organisms are in config/organisms.csv. Pathogens imported later are
in config/imported.csv and are processed only when named with --organism, so a
full run never mixes them into the core results.

An import sets RESULTS_DIR (relative to the project, or absolute) so every step
writes into results/imported/<organism>/ instead of results/.
"""
import csv
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ORGANISMS = ROOT / "config" / "organisms.csv"
IMPORTED = ROOT / "config" / "imported.csv"
NCBI_LIST = ROOT / "config" / "ncbi_organisms.csv"
CORE_RESULTS = ROOT / "results"
IMPORTED_RESULTS = CORE_RESULTS / "imported"
COLUMNS = ["organism", "label", "taxon"]


def read_rows(path):
    if not path.exists():
        return []
    with open(path, encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def core_organisms():
    return [row["organism"] for row in read_rows(ORGANISMS)]


def imported_rows():
    return read_rows(IMPORTED)


def read_organisms(organism=None):
    """Core organism rows, or the one row for a named organism, which may be imported."""
    if organism is None:
        return read_rows(ORGANISMS)
    return [row for row in read_rows(ORGANISMS) + read_rows(IMPORTED) if row["organism"] == organism]


def is_core(organism):
    return organism in core_organisms()


def results_dir():
    """results/, or the folder named by RESULTS_DIR for an imported pathogen."""
    folder = os.environ.get("RESULTS_DIR")
    if not folder:
        return CORE_RESULTS
    path = Path(folder)
    path = path if path.is_absolute() else ROOT / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def redirected():
    return bool(os.environ.get("RESULTS_DIR"))
