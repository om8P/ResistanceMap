"""Hand-checked cases for pathogen import: organism lists, results folders and the import steps.
Runs on the host, with no Spark, Docker or network."""
import csv
import json

import pytest

import datasets
import import_pathogen as I


@pytest.fixture
def config(tmp_path, monkeypatch):
    """Core and imported organism lists in a temporary folder."""
    core = tmp_path / "organisms.csv"
    core.write_text("organism,label,taxon\nKlebsiella,Klebsiella,Klebsiella_pneumoniae\n", encoding="utf-8")
    imported = tmp_path / "imported.csv"
    monkeypatch.setattr(datasets, "ORGANISMS", core)
    monkeypatch.setattr(datasets, "IMPORTED", imported)
    monkeypatch.setattr(I, "IMPORTED", imported)
    monkeypatch.setattr(I, "IMPORTED_RESULTS", tmp_path / "results" / "imported")
    return imported


def test_full_run_never_includes_imported(config):
    I.add_imported("Vibrio_cholerae", "Vibrio_cholerae", config)
    assert [r["organism"] for r in datasets.read_organisms()] == ["Klebsiella"]
    assert datasets.read_organisms("Vibrio_cholerae") == [{"organism": "Vibrio_cholerae", "label": "Vibrio cholerae", "taxon": "Vibrio_cholerae"}]
    assert datasets.core_organisms() == ["Klebsiella"] and not datasets.is_core("Vibrio_cholerae")


def test_add_imported_replaces_and_sorts(config):
    I.add_imported("Vibrio_cholerae", "", config)
    I.add_imported("Serratia", "", config)
    I.add_imported("Vibrio_cholerae", "Vibrio_cholerae", config)
    with open(config, encoding="utf-8", newline="") as source:
        rows = list(csv.DictReader(source))
    assert [r["organism"] for r in rows] == ["Serratia", "Vibrio_cholerae"]
    assert rows[1]["taxon"] == "Vibrio_cholerae"


def test_results_dir_follows_the_environment(monkeypatch, tmp_path):
    monkeypatch.delenv("RESULTS_DIR", raising=False)
    assert datasets.results_dir() == datasets.CORE_RESULTS and not datasets.redirected()
    monkeypatch.setenv("RESULTS_DIR", str(tmp_path / "imported" / "X"))
    assert datasets.results_dir() == tmp_path / "imported" / "X" and datasets.redirected()
    assert (tmp_path / "imported" / "X").is_dir()


def test_steps_run_in_order_into_the_pathogen_folder():
    steps = I.commands("Vibrio_cholerae", python="python")
    assert [name for name, _ in steps] == ["download", "ingest", "profile", "clean", "genes", "analytics", "search index"]
    assert steps[0][1] == ["python", "src/download.py", "--organism", "Vibrio_cholerae"]
    for name, argv in steps[1:]:
        assert argv[:5] == ["docker", "exec", "-e", "RESULTS_DIR=results/imported/Vibrio_cholerae", I.CONTAINER]
        assert argv[-2:] == ["--organism", "Vibrio_cholerae"]
    assert "local[8]" in dict(steps)["analytics"]


def test_taxon_is_the_organism_own_group_or_blank():
    groups = {"Vibrio_cholerae", "Serratia_marcescens"}
    assert I.choose_taxon("Vibrio_cholerae", groups) == "Vibrio_cholerae"
    assert I.choose_taxon("Serratia", groups) == ""


def test_status_file_keeps_earlier_values(config):
    I.write_status("Vibrio_cholerae", state="running", step="ingest")
    status = I.write_status("Vibrio_cholerae", step="clean")
    assert status["state"] == "running" and status["step"] == "clean" and "updated" in status
    assert json.loads((I.results_folder("Vibrio_cholerae") / "status.json").read_text())["step"] == "clean"


def test_core_organism_cannot_be_imported(config):
    with pytest.raises(SystemExit):
        I.run("Klebsiella")
