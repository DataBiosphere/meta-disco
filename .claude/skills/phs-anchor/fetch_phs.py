#!/usr/bin/env python3
"""Deterministic fetches for the phs-anchor skill (.claude/skills/phs-anchor/).

Each subcommand prints JSON to stdout. On a fetch or JSON-decode error,
main() prints a JSON {"error": ...} object to stderr and exits 1; invalid
usage or arguments print to stderr and exit 2. Interpretation — which paper
is the marker paper, which FHIR fields matter — is the agent's job, per
SKILL.md.

Subcommands:
    datasets              All AnVIL datasets from Azul (a dataset = a Terra
                          workspace; Azul's datasets[].title), as an
                          envelope {count, azul_total, datasets: [{phsid|
                          null, title, description, consent_group}, ...]}
    studies               The per-study input list, as an envelope {count,
                          studies, no_phsid_datasets, invalid_records}:
                          dataset records validated, then aggregated on
                          phsid — dataset titles listed, consent groups
                          unioned, description hoisted to the study
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
ESUMMARY_CHUNK = 200  # keep each esummary GET's id list well under URL-length limits

# Retry transient failures (NCBI intermittently returns 429/5xx) so one
# blip does not abort a whole subcommand run.
_session = requests.Session()
# NCBI asks clients to identify themselves; an identifiable UA also reduces
# the chance of throttling on the other public APIs we hit.
_session.headers["User-Agent"] = "meta-disco-phs-anchor/1.0 (https://github.com/DataBiosphere/meta-disco)"
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
    """All AnVIL datasets from Azul as per-dataset records (one per Terra workspace).

    The dataset record is {phsid|null, title, description, consent_group},
    where title is Azul's `datasets[].title` (the workspace name). The
    *study* record is the `studies` subcommand's aggregate of these —
    reserve that term for it. Another platform can substitute an adapter
    emitting this per-dataset shape.
    """
    records = []
    azul_total = None
    url: str | None = AZUL_DATASETS_URL
    params: dict | None = {"size": "300"}
    while url:
        raw = _get_json(url, params=params)
        # Keep the last int total seen — a later page returning total: null
        # must not clobber the count captured from an earlier page.
        page_total = raw.get("pagination", {}).get("total")
        if isinstance(page_total, int):
            azul_total = page_total
        for hit in raw.get("hits", []):
            for ds in hit.get("datasets", []):
                rids = ds.get("registered_identifier") or []
                if not isinstance(rids, list):
                    rids = [rids]
                phsid = None
                for rid in rids:
                    # search, not match: tolerate an accession embedded in a
                    # longer identifier string.
                    match = re.search(r"(phs\d{6})", str(rid or ""))
                    if match:
                        phsid = match.group(1)
                        break
                consent = ds.get("consent_group") or []
                if not isinstance(consent, list):
                    consent = [consent]
                records.append(
                    {
                        "phsid": phsid,
                        "title": ds.get("title"),
                        "description": ds.get("description"),
                        # Azul emits null entries (e.g. [null]); drop them —
                        # normalization is the adapter's job.
                        "consent_group": [c for c in consent if isinstance(c, str)],
                    }
                )
        # Azul's `next` is a fully-formed URL carrying the cursor.
        url = raw.get("pagination", {}).get("next")
        params = None
    return {"count": len(records), "azul_total": azul_total, "datasets": records}


PLACEHOLDER_DESC = "[Description currently not available]"


def _validate_dataset_record(r: dict) -> list[str]:
    """Shape problems in one adapter-emitted dataset record ([] when valid)."""
    problems = []
    if not (isinstance(r.get("title"), str) and r["title"].strip()):
        problems.append("title missing/empty")
    if r.get("phsid") is not None and not re.fullmatch(r"phs\d{6}", str(r["phsid"])):
        problems.append(f"phsid malformed: {r.get('phsid')!r}")
    if r.get("description") is not None and not isinstance(r["description"], str):
        problems.append("description not a string")
    if not (isinstance(r.get("consent_group"), list) and all(isinstance(c, str) for c in r["consent_group"])):
        problems.append("consent_group not a list of strings")
    return problems


def studies() -> dict:
    """Aggregate datasets() records into the per-study input list.

    Terminology is adapter-agnostic: a *study* (anchored by phsid) has one
    or more *datasets* — the platform's deposit unit, which in AnVIL is a
    Terra workspace (Azul's `datasets[].title`). The distinct phsids form
    the study list; each study lists its dataset titles, unions consent
    groups, and hoists description to study level (see findings.md
    "Description hoisting measurement" for the validation behind the
    policy: longest non-placeholder wins, descriptions_differ flags
    disagreement). Dataset records failing shape validation are excluded
    and reported under `invalid_records`; datasets with no phsid are
    returned separately (no study anchor to aggregate on).
    """
    grouped: dict[str, dict] = {}
    descs: dict[str, list[str]] = {}
    no_phsid = []
    invalid = []
    for r in datasets()["datasets"]:
        problems = _validate_dataset_record(r)
        if problems:
            invalid.append({"record": r, "problems": problems})
            continue
        if r["phsid"] is None:
            no_phsid.append(r)
            continue
        entry = grouped.setdefault(
            r["phsid"], {"phsid": r["phsid"], "description": None, "datasets": [], "consent_group": set()}
        )
        entry["datasets"].append(r["title"])
        entry["consent_group"].update(r["consent_group"])
        descs.setdefault(r["phsid"], []).append((r["description"] or "").strip())
    out = []
    for phsid, entry in sorted(grouped.items()):
        distinct = sorted({x for x in descs[phsid] if x and x != PLACEHOLDER_DESC})
        entry["description"] = max(distinct, key=len) if distinct else None
        entry["descriptions_differ"] = len(distinct) > 1
        entry["consent_group"] = sorted(entry["consent_group"])
        entry["datasets"].sort()
        out.append(entry)
    return {"count": len(out), "studies": out, "no_phsid_datasets": no_phsid, "invalid_records": invalid}


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
        set(re.findall(rf"{re.escape(phsid)}\.v(\d+)\.p(\d+)", listing.text)), key=lambda vp: (int(vp[0]), int(vp[1]))
    )
    if not versions:
        return {"phsid": phsid, "versions": [], "pmids": []}
    v, p = versions[-1]
    xml_url = f"{DBGAP_FTP_BASE}/{phsid}/{phsid}.v{v}.p{p}/GapExchange_{phsid}.v{v}.p{p}.xml"
    try:
        xml_resp = _get(xml_url)
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            # A version dir without its GapExchange XML is a recordable
            # partial result, same contract as the missing-directory case.
            return {
                "phsid": phsid,
                "versions": [f"v{v}.p{p}" for v, p in versions],
                "pmids": [],
                "note": f"GapExchange XML not found for latest version v{v}.p{p} (HTTP 404)",
            }
        raise
    return {
        "phsid": phsid,
        "versions": [f"v{v}.p{p}" for v, p in versions],
        "xml_url": xml_url,
        "pmids": re.findall(r'<Pubmed\s+pmid="(\d+)"', xml_resp.text),
    }


def _esummary_result(db: str, ids: list[str]) -> dict:
    """Cleaned esummary result dict for ids, chunked to bound the GET URL length."""
    summaries: dict = {}
    for start in range(0, len(ids), ESUMMARY_CHUNK):
        if start:
            time.sleep(EUTILS_DELAY_S)
        chunk = _get_json(
            f"{EUTILS_BASE}/esummary.fcgi",
            params={"db": db, "id": ",".join(ids[start : start + ESUMMARY_CHUNK]), "retmode": "json"},
        ).get("result", {})
        chunk.pop("uids", None)
        summaries.update(chunk)
    return summaries


def _search_with_summaries(db: str, term: str) -> dict:
    """esearch + esummary, with both caps made explicit in the output.

    `ids` is capped at retmax (100) — `ids_truncated` is true when `count`
    exceeds it; `summaries` covers only the first MAX_SUMMARIES ids, listed
    in `summarized_ids` so absence from `summaries` is not mistaken for
    "no summary data".
    """
    search = _get_json(
        f"{EUTILS_BASE}/esearch.fcgi",
        params={"db": db, "term": term, "retmax": "100", "retmode": "json"},
    )
    result = search.get("esearchresult", {})
    ids = result.get("idlist", [])
    count = int(result.get("count", 0))
    summarized = ids[:MAX_SUMMARIES]
    summaries = {}
    if summarized:
        time.sleep(EUTILS_DELAY_S)
        summaries = _esummary_result(db, summarized)
    return {
        "db": db,
        "term": term,
        "count": count,
        "ids": ids,
        "ids_truncated": count > len(ids),
        "summarized_ids": summarized,
        "summaries": summaries,
    }


def reporter(grant_serials: str) -> dict:
    """Publications NIH RePORTER links to the given grant serials (comma-separated).

    Serials are the bare numbers dbGaP attribution pages list (e.g. HG012047);
    each is queried as a leading-wildcard core project number so any activity
    code (U01/UM1/R01/…) matches. PMIDs are ranked by how many distinct
    *input serials* link them: each returned core project number is mapped
    back to its serial (suffix match), so a grant renewed under a new
    activity code (U01→UM1 keeps the serial) cannot count twice and the
    count is capped at the number of serials given. Papers shared across a
    study's grants rank first.
    """
    serials = [s.strip() for s in grant_serials.split(",") if s.strip()]
    if not serials:
        return {"grant_serials": [], "total_publication_links": 0, "publications": [], "note": "no grant serials given"}
    criteria = {"core_project_nums": [f"*{s}" for s in serials]}
    serials_by_pmid: dict[str, set[str]] = {}
    offset, total = 0, None
    while total is None or offset < total:
        payload = {"criteria": criteria, "limit": REPORTER_LIMIT, "offset": offset}
        resp = _session.post(REPORTER_PUBS_URL, json=payload, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        # Defensive: only an int meta.total is kept (and a later page cannot
        # clobber a known total back to None — same policy as datasets()).
        # With no int total ever seen, the loop runs until an empty page.
        raw_total = data.get("meta", {}).get("total")
        if isinstance(raw_total, int):
            total = raw_total
        rows = data.get("results", [])
        if not rows:
            break
        for row in rows:
            pmid, core = row.get("pmid"), row.get("coreproject")
            if core is None or not str(pmid).isdigit():
                continue  # an incomplete link row would pollute the ranking (or crash the sort)
            serial = next((s for s in serials if str(core).endswith(s)), None)
            if serial is None:
                continue  # core project the wildcard matched but no input serial explains
            serials_by_pmid.setdefault(str(pmid), set()).add(serial)
        offset += len(rows)
        if total is None or offset < total:
            time.sleep(1)  # RePORTER asks for at most 1 request/second
    ranked = sorted(serials_by_pmid.items(), key=lambda kv: (-len(kv[1]), int(kv[0])))
    return {
        "grant_serials": serials,
        "total_publication_links": total,
        "publications": [{"pmid": pmid, "serials": sorted(matched)} for pmid, matched in ranked],
    }


def esummary(pmids: str) -> dict:
    """PubMed esummary records for the given comma-separated PMIDs.

    Companion to `reporter`, whose output is bare PMIDs: this resolves them
    to titles/years/article ids. Large batches are fetched in chunks of
    ESUMMARY_CHUNK ids so a reporter-sized list cannot overflow the GET URL.
    """
    ids = [p.strip() for p in pmids.split(",") if p.strip()]
    return {"pmids": ids, "summaries": _esummary_result("pubmed", ids)}


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
    zero_arg = {"datasets": datasets, "studies": studies}
    phsid_commands = {"fhir", "gap-exchange", "pubmed-si", "pmc"}
    try:
        if len(argv) == 1 and argv[0] in zero_arg:
            out = zero_arg[argv[0]]()
        elif len(argv) == 2 and argv[0] in commands:
            # Validate up front so a bad argument is a usage error, not a
            # downstream HTTP error against a mangled URL/query.
            if argv[0] in phsid_commands and not re.fullmatch(r"phs\d{6}", argv[1]):
                print(f"invalid phsid {argv[1]!r}: expected phs + 6 digits (e.g. phs000424)", file=sys.stderr)
                return 2
            if argv[0] == "esummary" and not all(p.strip().isdigit() for p in argv[1].split(",") if p.strip()):
                print(f"invalid pmid list {argv[1]!r}: expected comma-separated numeric PMIDs", file=sys.stderr)
                return 2
            out = commands[argv[0]](argv[1])
        else:
            print(__doc__, file=sys.stderr)
            return 2
    except (requests.RequestException, json.JSONDecodeError) as exc:
        # JSONDecodeError covers a 200-OK non-JSON body (requests' variant
        # subclasses it); kept narrow so an internal logic bug still
        # tracebacks instead of masquerading as a transport error.
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    json.dump(out, sys.stdout, indent=1)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
