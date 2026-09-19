"""Check ``REFERENCE_CONTIG_LENGTHS`` against Ensembl, the authority it came from.

Every other test in this suite compares the repo against itself. This one is the
only check that our contig table matches an external source, so a silent edit to
it — or an upstream correction we never picked up — is caught here and nowhere
else. It came from ``scripts/validate_reference_assemblies.py``, deleted in #466
as one of the nine scripts nothing ran; the script's other two checks did not
survive with it. Its file-sampling half duplicated what the corpus reports
already cover, and its CHM13 half compared the table against a hand-copy of
itself, so it could not fail (see #466 for the numbers that check never
compared).

CHM13 is therefore not covered: Ensembl's main REST API does not serve it, and
there is no equivalent endpoint to point at.

Network-marked, so it is opt-in and neither ``make test`` nor CI runs it:

    uv run pytest tests/test_contig_lengths.py -m network
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
    """``{contig name: length}`` for one assembly, or skip if Ensembl is unreachable.

    A skip rather than a failure: this test asserts about our table, so an
    outage upstream is not evidence of a defect here.
    """
    url = f"{host}/info/assembly/homo_sapiens"
    try:
        resp = requests.get(url, headers={"Content-Type": "application/json"}, timeout=30)
    except requests.RequestException as exc:
        pytest.skip(f"Ensembl unreachable at {url}: {exc}")
    if resp.status_code != 200:
        pytest.skip(f"Ensembl returned {resp.status_code} for {url}")
    regions = resp.json().get("top_level_region", [])
    return {r["name"]: r["length"] for r in regions if "name" in r and "length" in r}


@pytest.mark.parametrize("build", sorted(ENSEMBL_HOSTS))
def test_our_contig_lengths_match_ensembl(build):
    """Every contig Ensembl also knows must have the length we recorded.

    Only the bare names (``1``, ``X``) are compared. The table carries each
    contig twice, bare and ``chr``-prefixed, because a file may name it either
    way; Ensembl publishes the bare form, so the prefixed keys are skipped
    rather than reported as absent upstream.

    Contigs Ensembl does not list are not failures either — the table holds
    entries the assembly report omits, and this test is about disagreement, not
    coverage.
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
    success while comparing nothing. The 24 primary chromosomes are the floor.
    """
    upstream = _ensembl_top_level(ENSEMBL_HOSTS[build])
    compared = [c for c in REFERENCE_CONTIG_LENGTHS[build] if not c.startswith("chr") and c in upstream]
    assert len(compared) >= 24, f"only {len(compared)} {build} contigs matched Ensembl by name: {sorted(compared)}"
