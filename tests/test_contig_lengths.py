"""Cross-check ``REFERENCE_CONTIG_LENGTHS`` against Ensembl.

The table is copied from NCBI assembly reports (the accessions are in
``validators/contig_lengths.py``) and lives in ``unified_rules.yaml``. Ensembl is
an independent publisher of the same assemblies, so this is a second opinion on
our numbers rather than a read-back of their source. No other test compares a
table in this repo against an upstream copy of it: a silent edit here, or an
upstream correction we never picked up, is caught here or not at all.

It came from ``scripts/validate_reference_assemblies.py``, deleted in #466. That
script had three checks and only this one worked:

- **Files.** ``validate_classified_files`` ignored its ``sample_size`` argument and
  read ``record["reference_assembly"]``, while records nest the five dimensions
  under ``classifications``. It reported 0 files with a reference assembly, for
  every file, in every run. ``generate_coverage_report.py`` covers that ground
  correctly.
- **CHM13.** Compared our live table against ``chm13_v2``, a frozen hand-copy of
  the same five values — so an edit to our table would have failed it, but it
  could never disagree with the consortium, because the consortium's numbers sat
  in ``_chm13_official`` and nothing read them.
- **GRCh37/GRCh38 against Ensembl.** This one. Ported.

CHM13 is not covered here. Ensembl's REST API does not serve it, and while NCBI
does publish the accession our table cites, pointing at it is not free: its
lengths disagree with ours on three of the twenty-four contigs. Whether that is a
release difference or an error in our table is open, and recorded on #466 with the
numbers.

Network-marked, so neither ``make test`` nor CI runs it. Run it with::

    make test-network
"""

import pytest
import requests

from meta_disco.validators.contig_lengths import REFERENCE_CONTIG_LENGTHS

pytestmark = pytest.mark.network

# The GRCh37 archive is a separate host; the current assembly lives on the main one.
ENSEMBL_HOSTS = {
    "GRCh38": "https://rest.ensembl.org",
    "GRCh37": "https://grch37.rest.ensembl.org",
}


def _ensembl_top_level(host: str) -> dict[str, int]:
    """``{contig name: length}`` for one assembly.

    Skips on a transport error, a 5xx or a 429 — this test asserts about our
    table, and an outage upstream is not evidence of a defect here. A 4xx fails
    instead: that means *this* URL is wrong, and since nothing in `make test` or
    CI runs this file, skipping would retire the check without anyone noticing.
    """
    url = f"{host}/info/assembly/homo_sapiens"
    try:
        resp = requests.get(url, headers={"Content-Type": "application/json"}, timeout=30)
    except requests.RequestException as exc:
        pytest.skip(f"Ensembl unreachable at {url}: {exc}")
    if resp.status_code >= 500 or resp.status_code == 429:
        pytest.skip(f"Ensembl returned {resp.status_code} for {url}")
    assert resp.status_code == 200, (
        f"Ensembl returned {resp.status_code} for {url} — a 4xx means this test's URL is wrong, "
        "not that upstream is down, and skipping it would retire the check silently"
    )
    regions = resp.json().get("top_level_region", [])
    return {r["name"]: r["length"] for r in regions if "name" in r and "length" in r}


@pytest.mark.parametrize("build", sorted(ENSEMBL_HOSTS))
def test_our_contig_lengths_match_ensembl(build):
    """Every contig Ensembl also knows must have the length we recorded.

    Only the bare names (``1``, ``X``) are compared. The table carries each
    contig twice, bare and ``chr``-prefixed, because a file may name it either
    way; Ensembl publishes the bare form, so the prefixed keys are skipped
    rather than reported as absent upstream.

    A contig Ensembl does not list is skipped rather than failed: absence upstream
    is not disagreement. That case does not arise today — the guard below pins
    that all 24 are compared — but the check is about conflicting values, so a
    future omission should not read as one.
    """
    upstream = _ensembl_top_level(ENSEMBL_HOSTS[build])
    assert upstream, f"Ensembl returned no top-level regions for {build}"

    mismatches = {
        contig: (ours, upstream[contig])
        for contig, ours in REFERENCE_CONTIG_LENGTHS[build].items()
        if not contig.startswith("chr") and contig in upstream and upstream[contig] != ours
    }
    assert not mismatches, f"{build} disagrees with Ensembl (contig: ours vs Ensembl): {mismatches}"


@pytest.mark.parametrize("build", sorted(ENSEMBL_HOSTS))
def test_ensembl_covers_enough_of_our_table_to_be_a_real_check(build):
    """Guard the assertion above against passing vacuously.

    If Ensembl changed its payload shape, or the names stopped matching, the
    mismatch set would be empty for the wrong reason and the check would report
    success while comparing nothing.

    Every bare-named contig we hold must be one Ensembl also publishes — not a
    floor, the whole set. A count would drift quietly: add ``MT`` to the table
    and a `>= 24` guard still passes while one contig silently stops being
    checked. This is where an upstream omission is meant to bite, which is why
    the test above tolerates one: that test is about conflicting values, this one
    about coverage not eroding.
    """
    upstream = _ensembl_top_level(ENSEMBL_HOSTS[build])
    comparable = [c for c in REFERENCE_CONTIG_LENGTHS[build] if not c.startswith("chr")]
    missing = sorted(set(comparable) - set(upstream))
    assert not missing, f"{build}: Ensembl no longer publishes {missing}, so those contigs are unchecked"
