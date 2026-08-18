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
                          studies, invalid_records}. A study record is
                          identity only — {phsid|null, title, description}
                          with title resolved from dbGaP FHIR for
                          phs-anchored studies; datasets, consent labels
                          (with flag-only validation buckets), and
                          derivation flags live under each record's
                          annotations object
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
FHIR_STUDY_URL = f"{FHIR_BASE}/ResearchStudy"
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
FHIR_ID_CHUNK = 50  # phsids per batched ResearchStudy _id query (~11 chars each — well under URL limits)
# AnVIL-side open-access labels (GA4GH DUO:0000004 territory) — no
# unrestricted code appears in the observed dbGaP registries; see
# findings.md "Consent vocabulary".
OPEN_CHANNEL_LABELS = {"NRES", "Unrestricted access"}
PLACEHOLDER_LABELS = {"TBD"}


def _chunks(ids: list[str], size: int):
    """Successive size-bounded slices of ids (bounds each GET URL's length)."""
    for start in range(0, len(ids), size):
        yield ids[start : start + size]


def _fhir_study_index(phsids: list[str]) -> dict[str, dict]:
    """{phsid: {title, consents}} from batched dbGaP FHIR ResearchStudy queries.

    consents is the set of StudyConsents display codes (e.g. "GRU",
    "DS-CRM-PUB-MDS"). Studies the FHIR API does not know are absent from
    the index. Follows bundle next-links if the server paginates; the
    _elements projection trims each resource to what the index reads
    (checked 2026-08-18 against the live server: the projected resource
    keeps the full extension array, StudyConsents included).
    """
    index: dict[str, dict] = {}
    first = True
    for chunk in _chunks(phsids, FHIR_ID_CHUNK):
        url: str | None = FHIR_STUDY_URL
        params: dict | None = {"_id": ",".join(chunk), "_format": "json", "_elements": "id,title,extension"}
        while url:
            if not first:
                time.sleep(EUTILS_DELAY_S)  # same NCBI-host etiquette as the E-utilities calls
            first = False
            bundle = _get_json(url, params=params)
            for entry in bundle.get("entry", []):
                res = entry.get("resource", {})
                sid = res.get("id")
                if not (isinstance(sid, str) and sid):
                    continue  # an entry without a usable id cannot be joined back to a phsid
                consents = set()
                for ext in res.get("extension", []):
                    if not ext.get("url", "").endswith("ResearchStudy-StudyConsents"):
                        continue
                    for c in ext.get("extension", []):
                        display = c.get("valueCoding", {}).get("display")
                        if isinstance(display, str):
                            consents.add(display)
                # Normalize the title at the boundary: the output contract is
                # str-or-null, so a non-string or whitespace-only value
                # becomes None here rather than leaking through.
                title = res.get("title")
                title = title.strip() if isinstance(title, str) else None
                index[sid] = {"title": title or None, "consents": consents}
            url = next((ln.get("url") for ln in bundle.get("link", []) if ln.get("relation") == "next"), None)
            params = None
    return index


def _consent_bucket(label: str, registered: set[str]) -> str:
    """Flag-only validation bucket for one consent label.

    Buckets (see findings.md "Consent vocabulary"): dbgap-registered (label
    is one of the study's FHIR StudyConsents codes), open-channel (an
    AnVIL-side open-access label), placeholder, malformed (underscore
    variant — the only malformation signal checked; other anomalies land
    in unmatched), unmatched (none of the above). A study with no anchor
    passes an empty `registered`, so its labels land in the four
    non-registered buckets — underscore-bearing ones still as malformed.
    """
    if label in registered:
        return "dbgap-registered"
    if label in OPEN_CHANNEL_LABELS:
        return "open-channel"
    if label in PLACEHOLDER_LABELS:
        return "placeholder"
    if "_" in label:
        return "malformed"
    return "unmatched"


def _study_record(
    phsid: str | None,
    title: str | None,
    title_source: str,
    dataset_titles: list[str],
    descriptions: list[str],
    consents,
    registered: set[str],
) -> dict:
    """One slim study record — the single schema for phs-anchored and
    anchor-less studies alike: the identity trio plus the annotations
    object (description hoisting per findings.md "Description hoisting
    measurement": longest distinct non-placeholder wins; the sort makes the
    equal-length tie-break deterministic)."""
    distinct = sorted({s for d in descriptions if (s := d.strip()) and s != PLACEHOLDER_DESC})
    return {
        "phsid": phsid,
        "title": title,
        "description": max(distinct, key=len) if distinct else None,
        "annotations": {
            "datasets": sorted(dataset_titles),
            "descriptions_differ": len(distinct) > 1,
            "title_source": title_source,
            "consent_group": [{"label": c, "bucket": _consent_bucket(c, registered)} for c in sorted(set(consents))],
        },
    }


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

    Terminology is adapter-agnostic: a *study* (the general concept,
    anchored by phsid when one exists) has one or more *datasets* — the
    platform's deposit unit, which in AnVIL is a Terra workspace (Azul's
    `datasets[].title`). A study record is identity only:
    {phsid|null, title, description}. `title` is the STUDY's title: for a
    phs-anchored study it comes from the dbGaP FHIR ResearchStudy, falling
    back to the dataset title when FHIR yields none and the study has a
    single distinct dataset title, else null (title_source records which);
    a dataset with no anchor becomes its own study record with the dataset
    title. `description` is hoisted from the datasets (see
    findings.md "Description hoisting measurement": longest non-placeholder
    wins). Everything else is metadata about the study and lives under the
    record's `annotations` object: the dataset titles, descriptions_differ,
    title_source (dbgap-fhir | dataset-title | none), and consent_group as
    inline {label, bucket} pairs — flag-only label validation, checked
    against the study's FHIR StudyConsents registry for phs-anchored
    studies; anchor-less studies have no registry, so their labels bucket
    among the non-registered buckets (see _consent_bucket; no consent
    label is ever rejected). Dataset records failing shape validation are
    excluded and reported under `invalid_records`.
    """
    grouped: dict[str, dict] = {}
    no_anchor = []
    invalid = []
    for r in datasets()["datasets"]:
        problems = _validate_dataset_record(r)
        if problems:
            invalid.append({"record": r, "problems": problems})
            continue
        if r["phsid"] is None:
            no_anchor.append(r)
            continue
        entry = grouped.setdefault(r["phsid"], {"datasets": [], "consents": set(), "descriptions": []})
        entry["datasets"].append(r["title"])
        entry["consents"].update(r["consent_group"])
        entry["descriptions"].append(r["description"] or "")
    phsids = sorted(grouped)
    fhir_index = _fhir_study_index(phsids)
    out = []
    for phsid in phsids:
        entry = grouped[phsid]
        fhir_rec = fhir_index.get(phsid, {})
        title = fhir_rec.get("title")
        distinct_titles = set(entry["datasets"])
        if title:
            title_source = "dbgap-fhir"
        elif len(distinct_titles) == 1:
            title, title_source = next(iter(distinct_titles)), "dataset-title"
        else:
            title, title_source = None, "none"
        out.append(
            _study_record(
                phsid,
                title,
                title_source,
                entry["datasets"],
                entry["descriptions"],
                entry["consents"],
                fhir_rec.get("consents", set()),
            )
        )
    for r in sorted(no_anchor, key=lambda r: r["title"]):
        out.append(
            _study_record(
                None, r["title"], "dataset-title", [r["title"]], [r["description"] or ""], r["consent_group"], set()
            )
        )
    return {"count": len(out), "studies": out, "invalid_records": invalid}


def fhir(phsid: str) -> dict:
    """dbGaP FHIR ResearchStudy bundle for the accession, verbatim."""
    return _get_json(FHIR_STUDY_URL, params={"_id": phsid, "_format": "json"})


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
    for i, chunk_ids in enumerate(_chunks(ids, ESUMMARY_CHUNK)):
        if i:
            time.sleep(EUTILS_DELAY_S)
        chunk = _get_json(
            f"{EUTILS_BASE}/esummary.fcgi",
            params={"db": db, "id": ",".join(chunk_ids), "retmode": "json"},
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
