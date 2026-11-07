"""Starting a pathogen import from the app. The import itself is src/import_pathogen.py, run detached,
so the app only starts it and reads its status file. Browsing never needs Docker."""
import shutil
import sys

from lib.rules import ROOT

sys.path.insert(0, str(ROOT / "src"))
import import_pathogen  # noqa: E402

COMMAND = "python src/import_pathogen.py {organism}"


def can_import():
    """True where a Docker client is installed, so an import could run on this machine."""
    return shutil.which("docker") is not None


def start(organism):
    import_pathogen.start_detached(organism)


def command(organism):
    return COMMAND.format(organism=organism)
