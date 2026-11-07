"""Pathogen and disease search. Pure functions on prepared frames, so tests need no Streamlit.

A query is matched against the six organisms, the organism groups NCBI tracks, the
hand-checked disease list and the search index (scientific name, serovar, strain,
NCBI taxonomy ID and the free-text host_disease field).
"""
import difflib
import re

import pandas as pd

INDEX_FIELDS = {"scientific_name": "Scientific name", "serovar": "Serovar", "strain": "Strain",
                "taxid": "NCBI taxonomy ID", "species_taxid": "NCBI species taxonomy ID"}
WORD_MATCH_MIN = 4
SUGGESTIONS = 3
SUGGEST_CUTOFF = 0.75


def normalise(text):
    """Lower case, underscores and punctuation as spaces, single spaces."""
    text = re.sub(r"[_\s]+", " ", str(text).lower())
    return re.sub(r"[^\w\s.+-]", " ", text).strip()


def _words(text):
    return normalise(text).split()


def name_match(query, name, prefix=True):
    """Query equals the name, holds it as whole words, or (with prefix) starts a word of it, from 4 letters."""
    q, n = normalise(query), normalise(name)
    if not q or not n:
        return False
    if q == n or re.search(rf"(?<!\w){re.escape(n)}(?!\w)", q):
        return True
    end = "" if prefix else r"(?![\w-])"
    return len(q) >= WORD_MATCH_MIN and re.search(rf"(?<![\w-]){re.escape(q)}{end}", n) is not None


def disease_terms(row):
    synonyms = row["synonyms"] if isinstance(row["synonyms"], str) else ""
    return [row["disease"], *[s for s in synonyms.split(";") if s.strip()]]


def disease_hits(query, diseases):
    """Disease rows whose name or a synonym matches in whole words, with every listed pathogen for each.
    Whole words, so "typhoid" does not find "non-typhoidal"."""
    matched = [name for name, rows in diseases.groupby("disease", sort=False)
               if any(name_match(query, term, prefix=False) for term in disease_terms(rows.iloc[0]))]
    return diseases[diseases["disease"].isin(matched)]


def organism_hits(query, labels, ncbi):
    """(core, tracked): core organism ids, and NCBI groups that are tracked but not among the six."""
    core = [o for o, label in labels.items() if name_match(query, o) or name_match(query, label)]
    tracked = [o for o in ncbi["organism"] if o not in labels and name_match(query, o)]
    return core, tracked


def index_hits(query, index, limit=20):
    """Index rows for the query: exact key or ID, or whole-word matches in scientific names and serovars."""
    q = normalise(query)
    if not q:
        return index.iloc[0:0]
    searchable = index[index["field"].isin(INDEX_FIELDS)]
    exact = searchable[searchable["key"].map(normalise) == q]
    if q.isdigit() or len(q) < WORD_MATCH_MIN:
        hits = exact
    else:
        pattern = rf"(?<!\w){re.escape(q)}(?!\w)"
        partial = searchable[searchable["field"].isin(["scientific_name", "serovar"])
                             & searchable["key"].str.contains(pattern, regex=True)]
        hits = pd.concat([exact, partial]).drop_duplicates(["organism", "field", "key"])
    order = hits.assign(_exact=hits["key"].map(normalise) == q).sort_values(["_exact", "isolates"], ascending=False)
    return order.drop(columns="_exact").head(limit)


def recorded_disease(terms, index):
    """What isolates record in host_disease for these terms, per organism. Each isolate has one value, so sums do not double count."""
    rows = index[index["field"] == "host_disease"]
    patterns = [rf"(?<!\w){re.escape(normalise(t))}(?!\w)" for t in terms if normalise(t)]
    if not patterns:
        return rows.iloc[0:0]
    keys = rows["key"].map(normalise)
    mask = pd.Series(False, index=rows.index)
    for pattern in patterns:
        mask |= keys.str.contains(pattern, regex=True)
    return rows[mask]


def suggestions(query, labels, ncbi, diseases):
    """Close spellings among organism and disease names, for a query with no match."""
    vocabulary = {}
    for organism, label in labels.items():
        vocabulary[normalise(label)] = label
    for organism in ncbi["organism"]:
        vocabulary.setdefault(normalise(organism), organism.replace("_", " "))
    for _, row in diseases.drop_duplicates("disease").iterrows():
        for term in disease_terms(row):
            vocabulary.setdefault(normalise(term), row["disease"])
    close = difflib.get_close_matches(normalise(query), list(vocabulary), n=SUGGESTIONS * 2, cutoff=SUGGEST_CUTOFF)
    return list(dict.fromkeys(vocabulary[c] for c in close))[:SUGGESTIONS]


def search(query, labels, ncbi, diseases, index):
    """Everything the page shows for one query."""
    core, tracked = organism_hits(query, labels, ncbi)
    found_diseases = disease_hits(query, diseases)
    found_index = index_hits(query, index)
    empty = not (core or tracked or len(found_diseases) or len(found_index))
    return {
        "organisms": core,
        "tracked": tracked,
        "diseases": found_diseases,
        "index": found_index,
        "suggestions": suggestions(query, labels, ncbi, diseases) if empty else [],
        "not_covered": empty,
    }


def organism_card(organism, coverage, summary, min_sample):
    """Data coverage for one organism: isolates, countries, years, groups at the minimum and gene match rate."""
    part = coverage[coverage["organism"] == organism]
    placed = part[part["country"].notna() & part["year"].notna()]
    genes = summary["organisms"][organism]["genes"]
    return {
        "isolates": int(part["isolates"].sum()),
        "countries": int(part["country"].nunique()),
        "first_year": int(placed["year"].min()) if len(placed) else None,
        "last_year": int(placed["year"].max()) if len(placed) else None,
        "groups": len(placed),
        "groups_at_minimum": int((placed["isolates"] >= min_sample).sum()),
        "catalog_match_pct": genes["catalog_match_pct"],
        "gene_rows": genes["gene_rows"],
    }
