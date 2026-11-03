"""Download the current NCBI Pathogen Detection files into data/raw/.

File names change with each release, so they are read from the directory
listings and recorded in data/raw/manifest.json for the later scripts.

Usage: python src/download.py [--organism NAME] [--with-metadata NAME]
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://ftp.ncbi.nlm.nih.gov/pathogen"
ORGANISMS = [
    "Salmonella",
    "Escherichia_coli_Shigella",
    "Klebsiella",
    "Staphylococcus_aureus",
    "Pseudomonas_aeruginosa",
    "Acinetobacter",
]
REFERENCE_URL = f"{BASE}/Antimicrobial_resistance/AMRFinderPlus/database/latest"
REFERENCE_FILES = {"gene_catalog": "ReferenceGeneCatalog.txt", "point_mutations": "AMRProt-mutation.tsv"}

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
MANIFEST = RAW / "manifest.json"
CHUNK = 1024 * 1024
RETRIES = 5


def open_url(url, start=0):
    headers = {"User-Agent": "ResistanceMap-student-project"}
    if start:
        headers["Range"] = f"bytes={start}-"
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=120)


def find_file(url, pattern):
    """Return the one file name in a directory listing that matches pattern."""
    with open_url(url + "/") as response:
        listing = response.read().decode("utf-8", "replace")
    names = sorted(set(re.findall(rf'href="({pattern})"', listing)))
    if len(names) != 1:
        raise RuntimeError(f"Expected one match for {pattern} in {url}, found {names}")
    return names[0]


def remote_size(url):
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "ResistanceMap-student-project"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return int(response.headers["Content-Length"])


def fetch(url, dest):
    """Download url to dest through a .part file, resuming after a failure."""
    size = remote_size(url)
    if dest.exists() and dest.stat().st_size == size:
        print(f"have {dest.name} ({size / CHUNK:.0f} MB)", flush=True)
        return size

    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    for attempt in range(1, RETRIES + 1):
        try:
            start = part.stat().st_size if part.exists() else 0
            if start > size:
                part.unlink()
                start = 0
            if start < size:
                with open_url(url, start) as response:
                    # A plain 200 means the server ignored the range request.
                    mode = "ab" if start and response.status == 206 else "wb"
                    with open(part, mode) as out:
                        while chunk := response.read(CHUNK):
                            out.write(chunk)
            got = part.stat().st_size
            if got != size:
                raise OSError(f"size {got} does not match expected {size}")
            part.replace(dest)
            print(f"got  {dest.name} ({size / CHUNK:.0f} MB)", flush=True)
            return size
        except (urllib.error.URLError, OSError) as error:
            print(f"retry {attempt}/{RETRIES} for {dest.name}: {error}", flush=True)
            time.sleep(5 * attempt)
    raise RuntimeError(f"Could not download {url}")


def entry(url, folder, name):
    size = fetch(f"{url}/{name}", RAW / folder / name)
    return {"path": f"data/raw/{folder}/{name}", "file": name, "bytes": size}


def download_organism(organism, with_metadata):
    url = f"{BASE}/Results/{organism}/latest_snps"
    amr = find_file(f"{url}/AMR", r"PDG[\w.\-]+\.amr\.metadata\.tsv")
    clusters = find_file(f"{url}/Clusters", r"PDG[\w.\-]+\.reference_target\.cluster_list\.tsv")
    record = {
        "pdg_version": re.match(r"PDG\d+\.\d+", amr).group(0),
        "amr": entry(f"{url}/AMR", organism, amr),
        "clusters": entry(f"{url}/Clusters", organism, clusters),
    }
    if with_metadata:
        metadata = find_file(f"{url}/Metadata", r"PDG[\w.\-]+\.metadata\.tsv")
        record["metadata"] = entry(f"{url}/Metadata", organism, metadata)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--organism", choices=ORGANISMS, help="Download one organism only")
    parser.add_argument("--with-metadata", choices=ORGANISMS, action="append", default=[],
                        help="Also download this organism's Metadata file for the denominator check")
    args = parser.parse_args()

    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {"organisms": {}, "reference": {}}
    for organism in [args.organism] if args.organism else ORGANISMS:
        keep_metadata = organism in args.with_metadata or "metadata" in manifest["organisms"].get(organism, {})
        manifest["organisms"][organism] = download_organism(organism, keep_metadata)
        manifest["updated"] = time.strftime("%Y-%m-%d")
        MANIFEST.write_text(json.dumps(manifest, indent=2))
    for key, name in REFERENCE_FILES.items():
        manifest["reference"][key] = entry(REFERENCE_URL, "reference", name)
    MANIFEST.write_text(json.dumps(manifest, indent=2))
    print("manifest written", flush=True)


if __name__ == "__main__":
    sys.exit(main())
