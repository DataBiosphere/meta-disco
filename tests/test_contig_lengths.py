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

CHM13 is checked against NCBI instead, because Ensembl's REST API does not serve
it. The row is T2T-CHM13v2.0 (#473) and matches it exactly on all 24 contigs; the
earlier releases fall inside ``detect_reference_from_contigs``' ±1000 bp, and the
exact-match table in ``rule_loader.reference_builds`` is what tells them apart.
Before #473 the row mixed releases — v1.0's chr1-chr3, v1.1/v2.0's chrX, v2.0's
chrY — which is why three of its lengths disagreed with NCBI (#466).

GRCh38 and GRCh37 match their cited NCBI accessions exactly too, on all 24
contigs.

Network-marked, so neither ``make test`` nor CI runs it. Run it with::

    make test-network
"""

import pytest
import requests

from meta_disco.validators.contig_lengths import REFERENCE_CONTIG_LENGTHS

pytestmark = pytest.mark.network

# 1-22, X, Y. The table's own comment calls this "all 22 autosomes + X and Y for
# each assembly"; naming it here is what makes that checkable rather than stated.
PRIMARY_CHROMOSOMES = frozenset([*(str(n) for n in range(1, 23)), "X", "Y"])

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

    Two ways the comparison can quietly stop comparing, and each needs its own
    assertion — neither implies the other:

    - **Our table loses a contig.** Every remaining one still matches, so a
      relationship check passes while the dropped contig goes unverified. Pinning
      the expected set is what catches that.
    - **Ensembl stops publishing one.** Our set is intact, but a contig is no
      longer checked against anything.

    A count catches neither cleanly: add ``MT`` and lose ``chr5``, and the total
    is still 24. This is where an upstream omission is meant to bite, which is
    why the test above tolerates one — that test is about conflicting values,
    this one about the comparison still covering what it claims to.
    """
    upstream = _ensembl_top_level(ENSEMBL_HOSTS[build])
    comparable = {c for c in REFERENCE_CONTIG_LENGTHS[build] if not c.startswith("chr")}

    assert comparable == PRIMARY_CHROMOSOMES, (
        f"{build}: table holds {sorted(comparable - PRIMARY_CHROMOSOMES)} beyond the primary "
        f"chromosomes and is missing {sorted(PRIMARY_CHROMOSOMES - comparable)}"
    )
    missing = sorted(comparable - set(upstream))
    assert not missing, f"{build}: Ensembl no longer publishes {missing}, so those contigs are unchecked"


# T2T-CHM13v2.0's GenBank accession; its RefSeq pair is the GCF_009914755.1 that
# validators/contig_lengths.py cites.
NCBI_CHM13_V2 = "GCA_009914755.4"


def test_chm13_matches_ncbi_t2t_chm13v2():
    """The CHM13 row is NCBI's T2T-CHM13v2.0, on exactly the primary chromosomes (#473).

    Skips on a transport error, a 5xx or a 429, and fails on a 4xx, for the reasons
    ``_ensembl_top_level`` gives.
    """
    url = f"https://api.ncbi.nlm.nih.gov/datasets/v2/genome/accession/{NCBI_CHM13_V2}/sequence_reports"
    try:
        resp = requests.get(url, params={"page_size": 100}, timeout=30)
    except requests.RequestException as exc:
        pytest.skip(f"NCBI unreachable at {url}: {exc}")
    if resp.status_code >= 500 or resp.status_code == 429:
        pytest.skip(f"NCBI returned {resp.status_code} for {url}")
    assert resp.status_code == 200, f"NCBI returned {resp.status_code} for {url} — this test's URL is wrong"
    upstream = {
        r["chr_name"]: r["length"]
        for r in resp.json().get("reports", [])
        if r.get("role") == "assembled-molecule" and r.get("chr_name") in PRIMARY_CHROMOSOMES
    }
    ours = {c: n for c, n in REFERENCE_CONTIG_LENGTHS["CHM13"].items() if not c.startswith("chr")}
    assert set(upstream) == PRIMARY_CHROMOSOMES, (
        f"NCBI no longer publishes {sorted(PRIMARY_CHROMOSOMES - set(upstream))}"
    )
    assert ours == upstream
