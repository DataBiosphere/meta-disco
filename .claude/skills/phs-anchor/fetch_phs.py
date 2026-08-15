#!/usr/bin/env python3
"""Deterministic fetches for the phs-anchor skill (.claude/skills/phs-anchor/).

Each subcommand prints JSON to stdout. Interpretation — which paper is the
marker paper, which FHIR fields matter — is the agent's job, per SKILL.md.

Subcommands:
    datasets              AnVIL open-access datasets from Azul (title,
                          registered_identifier — a phs accession or
                          none — consent group, data modality)
    fhir PHSID            dbGaP FHIR ResearchStudy bundle for the study
    gap-exchange PHSID    Selected-publication PMIDs from the latest
                          GapExchange XML on the dbGaP FTP site
    pubmed-si PHSID       PubMed records registering the accession as a
                          secondary source ID ([SI] field)
    pmc PHSID             PMC full-text search for the accession string
    reporter SERIALS      Publications NIH RePORTER links to the given
                          comma-separated grant serials (e.g. HG012047,
                          as listed on dbGaP attribution pages)
    esummary PMIDS        PubMed esummary records (title/year/ids) for
                          comma-separated PMIDs — resolves reporter's bare
                          PMIDs so roles can be judged
"""

from __future__ import annotations

import json
import re
import sys
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

AZUL_DATASETS_URL = "https://service.explore.anvilproject.org/index/datasets"
FHIR_BASE = "https://dbgap-api.ncbi.nlm.nih.gov/fhir/x1"
EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
DBGAP_FTP_BASE = "https://ftp.ncbi.nlm.nih.gov/dbgap/studies"
REPORTER_PUBS_URL = "https://api.reporter.nih.gov/v2/publications/search"
REPORTER_LIMIT = 500  # the API's maximum page size
TIMEOUT = 30
# NCBI asks for at most 3 requests/second without an API key.
EUTILS_DELAY_S = 0.4
MAX_SUMMARIES = 20

# Retry transient failures (NCBI intermittently returns 429/5xx) so one
# blip does not abort a whole subcommand run.
_session = requests.Session()
_session.mount(
    "https://",
    HTTPAdapter(
        max_retries=Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            # Default allowed_methods excludes POST, which would leave the
            # RePORTER search (an idempotent POST) unprotected.
            allowed_methods=frozenset({"GET", "POST"}),
        )
    ),
)


def _get(url: str, params: dict | None = None) -> requests.Response:
    resp = _session.get(url, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp


def _get_json(url: str, params: dict | None = None) -> dict:
    return _get(url, params).json()


def datasets() -> dict:
    """AnVIL datasets with accessible=true, with their registered_identifier (a phs accession, or "none"/null)."""
    raw = _get_json(
        AZUL_DATASETS_URL,
        params={"filters": json.dumps({"accessible": {"is": [True]}}), "size": "200"},
    )
    found = [
        {
            "title": ds.get("title"),
            "registered_identifier": ds.get("registered_identifier"),
            "consent_group": ds.get("consent_group"),
            "data_modality": ds.get("data_modality"),
        }
        for hit in raw.get("hits", [])
        for ds in hit.get("datasets", [])
    ]
    return {"count": len(found), "datasets": found}


def fhir(phsid: str) -> dict:
    """dbGaP FHIR ResearchStudy bundle for the accession, verbatim."""
    return _get_json(f"{FHIR_BASE}/ResearchStudy", params={"_id": phsid, "_format": "json"})


def gap_exchange(phsid: str) -> dict:
    """Selected-publication PMIDs from the latest GapExchange XML on the dbGaP FTP.

    This is the machine-readable source behind the study page's JS-loaded
    "Selected Publications" section (same route ncpi-dataset-catalog uses).
    """
    try:
        listing = _get(f"{DBGAP_FTP_BASE}/{phsid}/")
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            # SKILL.md's contract: a young study with no FTP directory is a
            # recordable miss, not a failed run.
            return {"phsid": phsid, "versions": [], "pmids": [], "note": "no dbGaP FTP directory (HTTP 404)"}
        raise
    versions = sorted(
        set(re.findall(rf"{phsid}\.v(\d+)\.p(\d+)", listing.text)), key=lambda vp: (int(vp[0]), int(vp[1]))
    )
    if not versions:
        return {"phsid": phsid, "versions": [], "pmids": []}
    v, p = versions[-1]
    xml_url = f"{DBGAP_FTP_BASE}/{phsid}/{phsid}.v{v}.p{p}/GapExchange_{phsid}.v{v}.p{p}.xml"
    xml_resp = _get(xml_url)
    return {
        "phsid": phsid,
        "versions": [f"v{v}.p{p}" for v, p in versions],
        "xml_url": xml_url,
        "pmids": re.findall(r'<Pubmed\s+pmid="(\d+)"', xml_resp.text),
    }


def _search_with_summaries(db: str, term: str) -> dict:
    search = _get_json(
        f"{EUTILS_BASE}/esearch.fcgi",
        params={"db": db, "term": term, "retmax": "100", "retmode": "json"},
    )
    result = search.get("esearchresult", {})
    ids = result.get("idlist", [])
    summaries = {}
    if ids:
        time.sleep(EUTILS_DELAY_S)
        summaries = _get_json(
            f"{EUTILS_BASE}/esummary.fcgi",
            params={"db": db, "id": ",".join(ids[:MAX_SUMMARIES]), "retmode": "json"},
        ).get("result", {})
        summaries.pop("uids", None)
    return {
        "db": db,
        "term": term,
        "count": int(result.get("count", 0)),
        "ids": ids,
        "summaries": summaries,
    }


def reporter(grant_serials: str) -> dict:
    """Publications NIH RePORTER links to the given grant serials (comma-separated).

    Serials are the bare numbers dbGaP attribution pages list (e.g. HG012047);
    each is queried as a leading-wildcard core project number so any activity
    code (U01/UM1/R01/…) matches. PMIDs are ranked by how many of the given
    grants link them — papers shared across a study's grants rank first.
    """
    serials = [s.strip() for s in grant_serials.split(",") if s.strip()]
    criteria = {"core_project_nums": [f"*{s}" for s in serials]}
    core_projects_by_pmid: dict[str, set[str]] = {}
    offset, total = 0, None
    while total is None or offset < total:
        payload = {"criteria": criteria, "limit": REPORTER_LIMIT, "offset": offset}
        resp = _session.post(REPORTER_PUBS_URL, json=payload, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        total = data.get("meta", {}).get("total", 0)
        rows = data.get("results", [])
        if not rows:
            break
        for row in rows:
            pmid, core = row.get("pmid"), row.get("coreproject")
            if pmid is None or core is None:
                continue  # an incomplete link row would pollute the ranking (or crash sorted())
            core_projects_by_pmid.setdefault(str(pmid), set()).add(core)
        offset += len(rows)
        if offset < total:
            time.sleep(1)  # RePORTER asks for at most 1 request/second
    ranked = sorted(core_projects_by_pmid.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    return {
        "grant_serials": serials,
        "total_publication_links": total,
        "publications": [{"pmid": pmid, "core_projects": sorted(cores)} for pmid, cores in ranked],
    }


def esummary(pmids: str) -> dict:
    """PubMed esummary records for the given comma-separated PMIDs.

    Companion to `reporter`, whose output is bare PMIDs: this resolves them
    to titles/years/article ids. Pass a modest batch (a URL-length-bounded
    GET carries the ids).
    """
    ids = [p.strip() for p in pmids.split(",") if p.strip()]
    summaries = {}
    if ids:
        summaries = _get_json(
            f"{EUTILS_BASE}/esummary.fcgi",
            params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"},
        ).get("result", {})
        summaries.pop("uids", None)
    return {"pmids": ids, "summaries": summaries}


def pubmed_si(phsid: str) -> dict:
    """PubMed records that registered this accession as a secondary source ID."""
    return _search_with_summaries("pubmed", f"{phsid}[SI]")


def pmc(phsid: str) -> dict:
    """PMC records whose indexed full text contains the accession string."""
    return _search_with_summaries("pmc", f'"{phsid}"')


def main(argv: list[str]) -> int:
    commands = {
        "fhir": fhir,
        "gap-exchange": gap_exchange,
        "pubmed-si": pubmed_si,
        "pmc": pmc,
        "reporter": reporter,
        "esummary": esummary,
    }
    try:
        if argv == ["datasets"]:
            out = datasets()
        elif len(argv) == 2 and argv[0] in commands:
            out = commands[argv[0]](argv[1])
        else:
            print(__doc__, file=sys.stderr)
            return 2
    except requests.RequestException as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    json.dump(out, sys.stdout, indent=1)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
