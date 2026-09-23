"""The value translation table (#414): loading, lookup, claims, seeding and the review queue.

One test per acceptance criterion of the issue, numbered ``ac<N>`` in its name, plus the
bound contract 3.5 puts on the normalizer, the id namespace, and the bundled table's own
invariants. Evidence fixtures are written through ``write_evidence_file`` into the
generation layout, so the seeder and queue read them the way they read a real generation.
"""

import ast
import re
from pathlib import Path

import pytest
import yaml
from classify_index_files import AMBIGUOUS_PARENT, NO_MATCHING_PARENT

from meta_disco.models import CLASSIFICATION_FIELDS, JOIN_KEY_DRS_URI, NOT_APPLICABLE, SOURCE_REPOSITORY_METADATA
from meta_disco.rule_loader import get_unified_rules
from meta_disco.schema_vocab import dimension_values
from meta_disco.source_evidence import (
    EvidenceEntry,
    EvidenceFileSource,
    EvidenceTarget,
    claim_source_for,
    discover,
    evidence_file_path,
    generation_dir,
    list_cell,
    write_evidence_file,
)
from meta_disco.value_map import (
    Scope,
    ValueMap,
    claims_from,
    load_value_map,
    match_key,
    normalize,
    render_queue,
    review_queue,
    row_id,
    seed,
)
from tests.test_source_evidence import evidence_file_envelope

REAL_EVIDENCE_ROOT = Path("data/source_evidence")
HPRC_VALUES = Path("tests/fixtures/hprc_evidence_values.yaml")
HPRC_DATASETS = ["AnVIL_HPRC_R2", "ANVIL_HPRC"]
STAMP = "20260920T175642Z"
HPRC_GENERATIONS = [generation_dir(REAL_EVIDENCE_ROOT, "anvil", "anvil15", d, STAMP) for d in HPRC_DATASETS]


def hprc_generation_is_current() -> bool:
    """The pinned generation is on disk *and* is what `discover` reads — a newer import would change the counts."""
    if not all(p.is_dir() for p in HPRC_GENERATIONS):
        return False
    current = {p.parent for p in discover(REAL_EVIDENCE_ROOT) if p.parent.parent.name in HPRC_DATASETS}
    return current == set(HPRC_GENERATIONS)


# --- helpers -------------------------------------------------------------------------


def load(tmp_path: Path, text: str) -> ValueMap:
    path = tmp_path / "map.yaml"
    path.write_text(text)
    return load_value_map(path)


def refuses(tmp_path: Path, text: str, *fragments: str) -> None:
    with pytest.raises(ValueError) as exc:
        load(tmp_path, text)
    for fragment in fragments:
        assert fragment in str(exc.value), str(exc.value)


def file_source(dataset="AnVIL_HPRC_R2", table="hifi") -> EvidenceFileSource:
    return EvidenceFileSource(repository="anvil", dataset=dataset, table=table, url="https://example.org")


def entry(field, raw_value, file="drs://f1", dataset="AnVIL_HPRC_R2", table="hifi", column="instrument_model"):
    """One evidence line; its ``ClaimSource`` is derived from the file source the way the reader derives it."""
    source = claim_source_for(file_source(dataset, table), column)
    return EvidenceEntry(field=field, target_key_value=file, raw_value=raw_value, source=source)


def write_generation(
    root: Path, dataset: str, table: str, entries: list[EvidenceEntry], envelope=None, source: str = "anvil"
) -> Path:
    """One evidence file in the generation layout the reader discovers, keyed by DRS URI.

    ``envelope`` replaces the default submitter-table one, and ``source`` names the
    evidence directory it lands under (``anvil_published`` for the published importer's);
    the version directory is the envelope's ``source_version``.
    """
    if envelope is None:
        envelope = evidence_file_envelope(
            source=file_source(dataset, table),
            source_version="anvil15",
            source_key=JOIN_KEY_DRS_URI,
            target=EvidenceTarget(system="anvil", dataset=dataset, version="anvil15"),
            target_key=JOIN_KEY_DRS_URI,
        )
    directory = generation_dir(root, source, envelope.source_version, dataset, STAMP)
    directory.mkdir(parents=True, exist_ok=True)
    write_evidence_file(evidence_file_path(directory, table), envelope, entries)
    return directory


@pytest.fixture
def evidence_root(tmp_path: Path) -> Path:
    return tmp_path / "evidence"


@pytest.fixture
def hprc_fixture_root(tmp_path: Path) -> Path:
    """The HPRC evidence rebuilt from the committed value list: one file per table, lines in the listed order."""
    root = tmp_path / "hprc_evidence"
    by_table: dict[tuple[str, str], list[EvidenceEntry]] = {}
    for n, v in enumerate(yaml.safe_load(HPRC_VALUES.read_text())):
        cell = entry(v["slot"], v["raw_value"], f"drs://fixture/{n}", v["dataset"], v["table"], v["column"])
        by_table.setdefault((v["dataset"], v["table"]), []).append(cell)
    for (dataset, table), cells in by_table.items():
        write_generation(root, dataset, table, cells)
    return root


@pytest.fixture
def empty_table(tmp_path: Path) -> Path:
    path = tmp_path / "map.yaml"
    path.write_text("rows:\n")
    return path


AUTHORED_REVIO = """
rows:
  - id: platform.revio
    match: {slot: platform, value: Revio, alternates: [REVIO]}
    declares: {platform: PACBIO}
    reason: a PacBio instrument
"""


# --- loading (AC 1-8) ------------------------------------------------------------------


def test_ac1_two_rows_sharing_an_id_fail_naming_it(tmp_path):
    refuses(
        tmp_path,
        """
rows:
  - id: platform.revio
    match: {slot: platform, value: Revio}
  - id: platform.revio
    match: {slot: platform, value: Sequel II}
""",
        "platform.revio",
        "repeats id",
    )


def test_ac2_an_authored_row_declaring_a_term_outside_the_slot_vocabulary_fails_naming_row_and_term(tmp_path):
    refuses(
        tmp_path,
        """
rows:
  - id: platform.revio
    match: {slot: platform, value: Revio}
    declares: {platform: pacbio}
    reason: typo
""",
        "'platform.revio'",
        "'pacbio'",
        "platform's vocabulary",
    )


def test_ac3_a_seeded_row_for_a_value_with_no_term_loads_clean(tmp_path, recwarn):
    table = load(
        tmp_path,
        """
rows:
  - id: assay_type.hi_c
    match: {slot: assay_type, value: Hi-C}
""",
    )
    (row,) = table.rows
    assert not row.authored
    assert row.declares == {}
    assert "Hi-C" not in dimension_values("assay_type")
    assert len(recwarn) == 0


def test_ac4_a_row_declaring_two_pairs_for_one_slot_fails_naming_the_row(tmp_path):
    refuses(
        tmp_path,
        """
rows:
  - id: platform.revio
    match: {slot: platform, value: Revio}
    declares: {platform: PACBIO, platform: ONT}
    reason: two answers
""",
        "'platform.revio'",
        "'platform' given twice",
    )


def test_ac5_two_rows_whose_keys_normalize_alike_at_one_scope_fail_naming_both(tmp_path):
    refuses(
        tmp_path,
        """
rows:
  - id: platform.revio
    match: {slot: platform, value: Revio}
  - id: platform.revio_caps
    match: {slot: platform, value: Sequel II, alternates: [REVIO]}
""",
        "'platform.revio'",
        "'platform.revio_caps'",
        "alternates included",
    )
    refuses(
        tmp_path,
        """
rows:
  - id: assay_type.a+b
    match: {slot: assay_type, value: [A, B]}
  - id: assay_type.b+a
    match: {slot: assay_type, value: [B, A]}
""",
        "'assay_type.a+b'",
        "'assay_type.b+a'",
    )


def test_ac6_two_rows_with_different_keys_declaring_one_slot_load(tmp_path):
    table = load(
        tmp_path,
        """
rows:
  - id: assay_type.hi_c
    match: {slot: assay_type, value: Hi-C}
    declares: {data_modality: genomic}
    reason: chromatin conformation of genomic DNA
  - id: data_modality.genomic
    match: {slot: data_modality, value: GENOMIC}
    declares: {data_modality: genomic}
    reason: identity by ruling
""",
    )
    assert [r.declares for r in table.rows] == [{"data_modality": "genomic"}] * 2


def test_a_scope_member_is_a_non_empty_single_line_identifier(tmp_path):
    for bad in ('""', '"  "', '"an\\nvil"', '"an\\rvil"'):
        refuses(
            tmp_path,
            f"""
rows:
  - id: platform.revio
    match: {{slot: platform, value: Revio}}
    scope: {{source: {bad}}}
""",
            "'platform.revio'",
            "not an identifier",
        )


def test_ac7_a_scope_of_a_dataset_alone_fails_and_the_two_nesting_forms_load(tmp_path):
    refuses(
        tmp_path,
        """
rows:
  - id: platform.revio
    match: {slot: platform, value: Revio}
    scope: {dataset: AnVIL_HPRC_R2}
""",
        "'platform.revio'",
        "dataset with no source",
    )
    table = load(
        tmp_path,
        """
rows:
  - id: platform.revio@anvil
    match: {slot: platform, value: Revio}
    scope: {source: anvil}
  - id: platform.revio@anvil.AnVIL_HPRC_R2
    match: {slot: platform, value: Revio}
    scope: {source: anvil, dataset: AnVIL_HPRC_R2}
""",
    )
    assert [r.scope for r in table.rows] == [Scope("anvil"), Scope("anvil", "AnVIL_HPRC_R2")]


def test_ac8_no_row_carries_a_table_or_column_name(tmp_path):
    for key in ("table", "column"):
        refuses(
            tmp_path,
            f"""
rows:
  - id: platform.revio
    match: {{slot: platform, value: Revio}}
    {key}: hifi
""",
            "'platform.revio'",
            key,
            "slot map",
        )
    load_value_map()  # the bundled table would be refused if a row carried either


# --- lookup (AC 9-13) ------------------------------------------------------------------


def test_ac9_three_spellings_select_one_authored_row(tmp_path):
    table = load(tmp_path, AUTHORED_REVIO)
    rows = {table.select("platform", spelling, "anvil", "AnVIL_HPRC_R2") for spelling in ("Revio", "REVIO", " revio ")}
    assert rows == {table.by_id("platform.revio")}


def test_ac10_nothing_matches_by_similarity(tmp_path):
    table = load(
        tmp_path,
        """
rows:
  - id: assay_type.wgs
    match: {slot: assay_type, value: WGS}
""",
    )
    assert table.select("assay_type", "WES", "anvil", None) is None
    assert table.select("assay_type", "WGS ", "anvil", None) is not None


def test_ac11_the_narrowest_scope_is_selected_and_taken_whole(tmp_path):
    table = load(
        tmp_path,
        """
rows:
  - id: platform.revio
    match: {slot: platform, value: Revio}
    declares: {platform: PACBIO, assay_type: WGS}
    reason: the default
  - id: platform.revio@anvil.AnVIL_HPRC_R2
    match: {slot: platform, value: Revio}
    scope: {source: anvil, dataset: AnVIL_HPRC_R2}
    declares: {platform: PACBIO}
    reason: this dataset says nothing about the assay
""",
    )
    scoped = table.select("platform", "Revio", "anvil", "AnVIL_HPRC_R2")
    assert scoped is not None and scoped.id == "platform.revio@anvil.AnVIL_HPRC_R2"
    assert scoped.declares == {"platform": "PACBIO"}, "nothing merged in from the default"
    other = table.select("platform", "Revio", "anvil", "ANVIL_T2T")
    assert other is not None and other.id == "platform.revio"


def test_ac12_a_list_cell_matches_as_a_whole_set_and_never_per_element(tmp_path):
    table = load(
        tmp_path,
        """
rows:
  - id: assay_type.atac+rna
    match: {slot: assay_type, value: ["single-nucleus ATAC-seq", "single-nucleus RNA sequencing assay"]}
""",
    )
    both = [
        '["single-nucleus ATAC-seq", "single-nucleus RNA sequencing assay"]',
        '["single-nucleus RNA sequencing assay", "single-nucleus ATAC-seq"]',
    ]
    assert {table.select("assay_type", raw, "anvil", None) for raw in both} == {table.by_id("assay_type.atac+rna")}
    elements_only = load(
        tmp_path,
        """
rows:
  - id: assay_type.a
    match: {slot: assay_type, value: A}
  - id: assay_type.b
    match: {slot: assay_type, value: B}
""",
    )
    assert elements_only.select("assay_type", '["A", "B"]', "anvil", None) is None


def test_ac13_a_one_element_list_selects_the_row_for_the_bare_string(tmp_path):
    table = load(
        tmp_path,
        """
rows:
  - id: assay_type.a
    match: {slot: assay_type, value: A}
""",
    )
    assert table.select("assay_type", '["A"]', "anvil", None) is table.select("assay_type", "A", "anvil", None)
    assert match_key('["A"]') == match_key("a") == frozenset({"a"})


# --- claims (AC 14-20) -----------------------------------------------------------------


def test_ac14_one_claim_carrying_row_id_raw_value_table_and_column(tmp_path):
    table = load(tmp_path, AUTHORED_REVIO)
    claims = claims_from(
        entry("platform", "Revio", table="hifi", column="instrument_model"), SOURCE_REPOSITORY_METADATA, table
    )
    assert len(claims) == 1
    slot, claim = claims[0]
    assert slot == "platform"
    assert claim["value"] == "PACBIO"
    assert claim["rule_id"] == "platform.revio"
    assert claim["raw_value"] == "Revio"
    assert claim["source"]["table"] == "hifi"
    assert claim["source"]["column"] == "instrument_model"
    assert claim["source_type"] == SOURCE_REPOSITORY_METADATA
    assert "tier" not in claim


def test_ac15_an_identity_row_is_cited_like_any_other(tmp_path):
    table = load(
        tmp_path,
        """
rows:
  - id: platform.pacbio
    match: {slot: platform, value: PACBIO}
    declares: {platform: PACBIO}
    reason: identity by ruling
""",
    )
    ((_, claim),) = claims_from(entry("platform", "PACBIO"), SOURCE_REPOSITORY_METADATA, table)
    assert claim["rule_id"] == "platform.pacbio"
    assert claim["value"] == claim["raw_value"] == "PACBIO"


def test_ac16_a_seeded_row_or_no_row_produces_no_claim(tmp_path):
    table = load(
        tmp_path,
        """
rows:
  - id: platform.revio
    match: {slot: platform, value: Revio}
""",
    )
    assert claims_from(entry("platform", "Revio"), SOURCE_REPOSITORY_METADATA, table) == []
    assert claims_from(entry("platform", "Sequel II"), SOURCE_REPOSITORY_METADATA, table) == []


def test_ac17_a_row_declaring_another_slot_claims_that_slot_only(tmp_path):
    table = load(
        tmp_path,
        """
rows:
  - id: assay_type.hi_c
    match: {slot: assay_type, value: Hi-C}
    declares: {data_modality: genomic}
    reason: chromatin conformation of genomic DNA
""",
    )
    claims = claims_from(entry("assay_type", "Hi-C"), SOURCE_REPOSITORY_METADATA, table)
    assert [(slot, claim["value"]) for slot, claim in claims] == [("data_modality", "genomic")]


def test_ac18_an_authored_no_op_makes_no_claim_and_leaves_the_queue(tmp_path, evidence_root):
    table = load(
        tmp_path,
        """
rows:
  - id: data_type.bam
    match: {slot: data_type, value: bam}
    declares: {}
    reason: a file format in a data_type column
""",
    )
    assert claims_from(entry("data_type", "bam"), SOURCE_REPOSITORY_METADATA, table) == []
    write_generation(
        evidence_root, "AnVIL_HPRC_R2", "kinnex", [entry("data_type", "bam", table="kinnex", column="data_type")]
    )
    assert review_queue(evidence_root, table) == []


def test_ac19_two_cells_disagreeing_on_one_slot_give_two_claims_neither_dropped(tmp_path):
    table = load(
        tmp_path,
        """
rows:
  - id: assay_type.bisulfite
    match: {slot: assay_type, value: Bisulfite-Seq}
    declares: {data_modality: epigenomic.methylation}
    reason: the strategy carries the modality
  - id: data_modality.genomic
    match: {slot: data_modality, value: GENOMIC}
    declares: {data_modality: genomic}
    reason: identity by ruling
""",
    )
    cells = [
        entry("assay_type", "Bisulfite-Seq", column="library_strategy"),
        entry("data_modality", "GENOMIC", column="library_source"),
    ]
    claims = [
        c
        for cell in cells
        for slot, c in claims_from(cell, SOURCE_REPOSITORY_METADATA, table)
        if slot == "data_modality"
    ]
    assert [(c["rule_id"], c["source"]["column"], c["raw_value"], c["value"]) for c in claims] == [
        ("assay_type.bisulfite", "library_strategy", "Bisulfite-Seq", "epigenomic.methylation"),
        ("data_modality.genomic", "library_source", "GENOMIC", "genomic"),
    ]


def test_ac20_two_cells_agreeing_give_two_claims_with_one_value(tmp_path):
    table = load(
        tmp_path,
        """
rows:
  - id: platform.pacbio_smrt
    match: {slot: platform, value: PACBIO_SMRT}
    declares: {platform: PACBIO}
    reason: SRA's platform value
  - id: platform.revio
    match: {slot: platform, value: Revio}
    declares: {platform: PACBIO}
    reason: a PacBio instrument
""",
    )
    cells = [entry("platform", "PACBIO_SMRT", column="platform"), entry("platform", "Revio", column="instrument_model")]
    claims = [claim for cell in cells for _, claim in claims_from(cell, SOURCE_REPOSITORY_METADATA, table)]
    assert len(claims) == 2
    assert {c["value"] for c in claims} == {"PACBIO"}
    assert {c["rule_id"] for c in claims} == {"platform.pacbio_smrt", "platform.revio"}


def test_a_status_declaration_becomes_a_status_claim(tmp_path):
    table = load(
        tmp_path,
        """
rows:
  - id: reference_assembly.unaligned
    match: {slot: reference_assembly, value: unaligned}
    declares: {reference_assembly: not_applicable}
    reason: the source's word for no reference
""",
    )
    ((slot, claim),) = claims_from(entry("reference_assembly", "unaligned"), SOURCE_REPOSITORY_METADATA, table)
    assert slot == "reference_assembly"
    assert claim["status"] == NOT_APPLICABLE
    assert "value" not in claim


# --- seeding and the queue (AC 21-25) ----------------------------------------------------


def assert_hprc_seed(empty_table: Path, evidence_root: Path) -> None:
    """43 distinct raw strings on that run; 41 keys, because ``Revio``/``REVIO`` and ``ILLUMINA``/``illumina``
    normalize alike and are one row each with the other spelling as an alternate — two rows would fail AC 5
    (amended on the issue). The seeded rows are a function of the distinct values, not of how often each
    occurs, so the committed value list — one entry per distinct value per table, in file order, written
    back out as evidence files by the ``hprc_fixture_root`` fixture — mints the same rows as the real generation."""
    result = seed(empty_table, evidence_root, datasets=HPRC_DATASETS)
    assert len(result.rows_added) == 41
    table = load_value_map(empty_table)
    assert len(table.rows) == 41
    assert all(row.id and not row.authored for row in table.rows)
    assert {a for row in table.rows for a in row.alternates} == {"REVIO", "illumina"}
    assert all("anvil/anvil15/" in s and f"/{STAMP}" in s for row in table.rows for s in row.seeded_from)
    assert {row.id for row in table.rows} >= {"platform.revio", "platform.illumina", "reference_assembly.unaligned"}


def test_ac21_seeding_an_empty_table_from_the_hprc_evidence_fixture(empty_table, hprc_fixture_root):
    assert_hprc_seed(empty_table, hprc_fixture_root)


@pytest.mark.skipif(
    not hprc_generation_is_current(), reason="the pinned HPRC evidence generation is not the current one on disk"
)
def test_ac21_seeding_an_empty_table_from_the_real_hprc_evidence(empty_table):
    """The same over the real generation where it is on disk, plus the line count the issue measured."""
    assert_hprc_seed(empty_table, REAL_EVIDENCE_ROOT)
    assert seed(empty_table, REAL_EVIDENCE_ROOT, datasets=HPRC_DATASETS).lines_scanned == 50_344


def test_ac21_seeding_mints_one_row_per_key_with_id_no_reason_and_the_run_scanned(empty_table, evidence_root):
    write_generation(
        evidence_root,
        "AnVIL_HPRC_R2",
        "hifi",
        [
            entry("platform", "Revio", "drs://a"),
            entry("platform", "REVIO", "drs://b"),
            entry("assay_type", '["A", "B"]', "drs://a", column="assay_titles"),
            entry("assay_type", '["B", "A"]', "drs://b", column="assay_titles"),
        ],
    )
    result = seed(empty_table, evidence_root)
    assert result.rows_added == ("assay_type.a+b", "platform.revio")
    table = load_value_map(empty_table)
    by_id = {row.id: row for row in table.rows}
    assert by_id["platform.revio"].value == "Revio" and by_id["platform.revio"].alternates == ("REVIO",)
    assert by_id["assay_type.a+b"].value == ("A", "B") and by_id["assay_type.a+b"].alternates == (("B", "A"),)
    assert all(not row.authored for row in table.rows)
    assert by_id["platform.revio"].seeded_from == (f"anvil/anvil15/AnVIL_HPRC_R2/{STAMP}",)


def test_ac22_reseeding_leaves_an_authored_row_untouched_and_mints_no_second_row(tmp_path, evidence_root):
    write_generation(
        evidence_root, "AnVIL_HPRC_R2", "hifi", [entry("platform", "REVIO"), entry("platform", "Sequel II")]
    )
    table_path = tmp_path / "map.yaml"
    table_path.write_text(AUTHORED_REVIO.lstrip())
    before = table_path.read_bytes()
    result = seed(table_path, evidence_root)
    assert result.rows_added == ("platform.sequel_ii",)
    after = table_path.read_bytes()
    assert after.startswith(before), "the seeder appends; every earlier byte is where it was"
    assert seed(table_path, evidence_root).rows_added == ()
    assert table_path.read_bytes() == after


def test_a_row_scoped_to_one_dataset_does_not_cover_the_same_key_from_another(tmp_path, evidence_root):
    """The seeder asks selection with the line's provenance (3.7); a key with a row only under another scope has none here."""
    table_path = tmp_path / "map.yaml"
    table_path.write_text(
        "rows:\n  - id: platform.revio@anvil.AnVIL_HPRC_R2\n    match: {slot: platform, value: Revio}\n"
        "    scope: {source: anvil, dataset: AnVIL_HPRC_R2}\n"
    )
    write_generation(evidence_root, "AnVIL_HPRC_R2", "hifi", [entry("platform", "Revio")])
    write_generation(evidence_root, "ANVIL_T2T", "hifi", [entry("platform", "Revio", dataset="ANVIL_T2T")])
    assert seed(table_path, evidence_root).rows_added == ("platform.revio",)
    table = load_value_map(table_path)
    assert table.select("platform", "Revio", "anvil", "AnVIL_HPRC_R2") is table.by_id(
        "platform.revio@anvil.AnVIL_HPRC_R2"
    )
    assert table.select("platform", "Revio", "anvil", "ANVIL_T2T") is table.by_id("platform.revio")


def test_a_seed_that_would_not_reload_leaves_the_file_as_it_was(empty_table, evidence_root, monkeypatch):
    import meta_disco.value_map as vm

    write_generation(evidence_root, "AnVIL_HPRC_R2", "hifi", [entry("platform", "Revio")])
    before = empty_table.read_bytes()
    monkeypatch.setattr(vm, "_row_text", lambda *a, **k: "  - id: [not a\n")
    with pytest.raises(ValueError, match="does not load; left unchanged"):
        seed(empty_table, evidence_root)
    assert empty_table.read_bytes() == before
    assert list(empty_table.parent.glob("*.tmp")) == [], "no sibling is left behind"


def test_two_keys_that_slug_alike_get_stable_distinct_ids(empty_table, evidence_root):
    """The second id is a digest of its key, not an ordinal, so the same scan mints the same ids on a fresh table."""
    write_generation(
        evidence_root,
        "AnVIL_HPRC_R2",
        "hifi",
        [entry("platform", "a-b", "drs://a"), entry("platform", "a_b", "drs://b")],
    )
    first = seed(empty_table, evidence_root).rows_added
    empty_table.write_text("rows:\n")
    assert seed(empty_table, evidence_root).rows_added == first
    assert first[0] == "platform.a_b"
    assert first[1].startswith("platform.a_b_") and len(first[1]) == len("platform.a_b_") + 6


def test_a_digest_id_already_in_the_table_is_extended_until_unused():
    from meta_disco.value_map import _fresh_id

    key = frozenset({"a-b"})
    short = _fresh_id("platform.a_b", key, {"platform.a_b"})
    assert len(short) == len("platform.a_b_") + 6
    longer = _fresh_id("platform.a_b", key, {"platform.a_b", short})
    assert longer.startswith(short) and len(longer) == len(short) + 1


def test_ac23_the_queue_lists_a_seeded_value_with_its_provenance_and_file_count(tmp_path, evidence_root):
    table = load(
        tmp_path,
        """
rows:
  - id: assay_type.hi_c
    match: {slot: assay_type, value: Hi-C}
""",
    )
    cells = [entry("assay_type", "Hi-C", f"drs://{n}", table="hic", column="library_strategy") for n in range(3)]
    cells.append(entry("assay_type", "Hi-C", "drs://0", table="hic", column="library_strategy"))
    write_generation(evidence_root, "AnVIL_HPRC_R2", "hic", cells)
    (listed,) = review_queue(evidence_root, table)
    assert (listed.source, listed.dataset, listed.table, listed.column) == (
        "anvil",
        "AnVIL_HPRC_R2",
        "hic",
        "library_strategy",
    )
    assert (listed.slot, listed.raw_value, listed.files, listed.row_id) == ("assay_type", "Hi-C", 3, "assay_type.hi_c")


def test_a_raw_value_is_shown_as_its_repr_whatever_it_holds(tmp_path, evidence_root):
    """Evidence keeps a raw value verbatim — line endings, pipes, backticks, controls, an empty string — and the
    queue shows each as Python spells it, one row each, with no raw line ending or control left in the file."""
    table = load(tmp_path, "rows:\n")
    values = ["Sequel\r\nII", "a|b", "a`b", "x\x00y", " A ", "", "a\u0085b\ud800c \u00e9"]
    write_generation(
        evidence_root, "AnVIL_HPRC_R2", "hifi", [entry("platform", v, f"drs://{n}") for n, v in enumerate(values)]
    )
    rendered = render_queue(review_queue(evidence_root, table), evidence_root)
    rows = [line for line in rendered.splitlines() if line.startswith("| 1 ")]
    assert len(rows) == len(values)
    for v in values:
        assert repr(v).replace("|", "\\|") in rendered, repr(v)
    assert "\r" not in rendered and "\x00" not in rendered and "\u0085" not in rendered
    (tmp_path / "queue.md").write_text(rendered, encoding="utf-8")


def test_a_lone_surrogate_can_be_seeded_even_where_its_slug_collides(empty_table, evidence_root):
    """The digest hashes a repr and PyYAML escapes the surrogate, so the row is minted, written as UTF-8,
    and read back to the same key."""
    cells = [entry("platform", "a b", "drs://a"), entry("platform", "a\ud800b", "drs://b")]
    write_generation(evidence_root, "AnVIL_HPRC_R2", "hifi", cells)
    added = seed(empty_table, evidence_root).rows_added
    assert added[0] == "platform.a_b" and added[1].startswith("platform.a_b_")
    table = load_value_map(empty_table)
    assert table.select("platform", "a\ud800b", "anvil", "AnVIL_HPRC_R2") is table.by_id(added[1])
    assert seed(empty_table, evidence_root).rows_added == ()


def test_an_astral_non_printable_round_trips_through_a_seeded_row(empty_table, evidence_root):
    """PyYAML writes U+E0001 as an eight-digit escape and reads it back; the row keeps matching its evidence."""
    write_generation(evidence_root, "AnVIL_HPRC_R2", "hifi", [entry("platform", "tag\U000e0001x")])
    (added,) = seed(empty_table, evidence_root).rows_added
    assert empty_table.read_text(encoding="utf-8").isascii(), "PyYAML spells every non-ASCII character as an escape"
    table = load_value_map(empty_table)
    assert table.select("platform", "tag\U000e0001x", "anvil", "AnVIL_HPRC_R2") is table.by_id(added)
    assert seed(empty_table, evidence_root).rows_added == ()


def test_ac24_a_seeded_scoped_row_over_an_authored_default_keeps_the_value_queued(tmp_path, evidence_root):
    table = load(
        tmp_path,
        """
rows:
  - id: platform.revio
    match: {slot: platform, value: Revio}
    declares: {platform: PACBIO}
    reason: the default
  - id: platform.revio@anvil.AnVIL_HPRC_R2
    match: {slot: platform, value: Revio}
    scope: {source: anvil, dataset: AnVIL_HPRC_R2}
""",
    )
    write_generation(evidence_root, "AnVIL_HPRC_R2", "hifi", [entry("platform", "Revio")])
    write_generation(evidence_root, "ANVIL_T2T", "hifi", [entry("platform", "Revio", dataset="ANVIL_T2T")])
    listed = review_queue(evidence_root, table)
    assert [(e.dataset, e.row_id) for e in listed] == [("AnVIL_HPRC_R2", "platform.revio@anvil.AnVIL_HPRC_R2")]


def test_ac25_a_value_with_no_row_is_listed_like_a_seeded_one(tmp_path, evidence_root):
    table = load(
        tmp_path,
        """
rows:
  - id: platform.revio
    match: {slot: platform, value: Revio}
""",
    )
    write_generation(
        evidence_root, "AnVIL_HPRC_R2", "hifi", [entry("platform", "Revio"), entry("platform", "Sequel II")]
    )
    listed = {e.raw_value: e for e in review_queue(evidence_root, table)}
    assert set(listed) == {"Revio", "Sequel II"}
    assert listed["Revio"].row_id == "platform.revio" and listed["Sequel II"].row_id is None
    seeded, unseen = listed["Revio"], listed["Sequel II"]
    assert (seeded.source, seeded.dataset, seeded.table, seeded.files) == (
        unseen.source,
        unseen.dataset,
        unseen.table,
        unseen.files,
    )


# --- what must not change (AC 26-27) -------------------------------------------------------


def imported_segments(path: Path) -> set[str]:
    """Every dotted segment any import form in ``path`` touches — the collector ``test_source_evidence`` uses,
    because ``ImportFrom.module`` alone misses ``from meta_disco import value_map``."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    return {segment for name in names for segment in name.split(".")}


def test_two_rows_keyed_alike_are_refused_by_the_table_itself(tmp_path):
    """The invariant is `ValueMap`'s, not only the loader's, so a table built directly cannot shadow a row."""
    (a,) = load(tmp_path, "rows:\n  - id: platform.revio\n    match: {slot: platform, value: Revio}\n").rows
    (b,) = load(tmp_path, "rows:\n  - id: platform.again\n    match: {slot: platform, value: REVIO}\n").rows
    with pytest.raises(ValueError, match="both match"):
        ValueMap(rows=(a, b))


def test_ac26_nothing_but_reconcile_imports_the_table():
    """Inference output is unchanged because no classification code reaches the module: the argument the
    issue allows in place of a corpus diff, made checkable over every module and script but the table's own.
    The reconcile stage is the table's one reader (#432), and it writes its own artifact, never inference's."""
    sources = [*Path("src/meta_disco").rglob("*.py"), *Path("scripts").glob("*.py")]
    importers = sorted(str(p) for p in sources if p.name != "value_map.py" and "value_map" in imported_segments(p))
    assert importers == ["src/meta_disco/reconcile.py"], importers


def test_ac27_the_seeder_and_the_queue_read_every_line_through_iter_evidence(empty_table, evidence_root, monkeypatch):
    import meta_disco.value_map as vm

    write_generation(
        evidence_root, "AnVIL_HPRC_R2", "hifi", [entry("platform", "Revio", f"drs://{n}") for n in range(5)]
    )
    real = vm.iter_evidence
    yielded: list[EvidenceEntry] = []

    def counting(path):
        for e in real(path):
            yielded.append(e)
            yield e

    monkeypatch.setattr(vm, "iter_evidence", counting)
    assert seed(empty_table, evidence_root).lines_scanned == len(yielded) == 5
    yielded.clear()
    (listed,) = review_queue(evidence_root, load_value_map(empty_table))
    assert listed.files == len(yielded) == 5


# --- the normalizer's bound, the id namespace, and the bundled table --------------------------


def test_the_normalizer_cannot_merge_two_terms_of_any_slot():
    """Contract 3.5's binding half: casefold-and-strip keeps every slot's terms distinct."""
    for slot in CLASSIFICATION_FIELDS:
        terms = dimension_values(slot)
        assert len({normalize(t) for t in terms}) == len(terms), slot
    assert normalize(" WGS ") == "wgs" and normalize("WES") == "wes"


def test_row_ids_are_slot_dot_slug_with_set_elements_joined():
    assert row_id("platform", frozenset({"illumina novaseq 6000"})) == "platform.illumina_novaseq_6000"
    assert row_id("assay_type", frozenset({"b", "a"})) == "assay_type.a+b"


def test_row_ids_and_rule_ids_are_disjoint_by_shape(tmp_path):
    """A row id starts with its slot and a dot; no rule id contains a dot; so a claim's ``rule_id`` names one or
    the other and neither loader has to read the other's file. Rule ids live in two places: the rule set, and the
    literals the content classifiers and standalone producers write — as a keyword, a dictionary entry, or a
    ``*_RULE_ID`` constant."""
    rules = get_unified_rules()
    ids = {rule.id for rule in rules.rules}
    for path in [*Path("src/meta_disco").rglob("*.py"), *Path("scripts").glob("*.py")]:
        if path.name != "value_map.py":
            # Both spellings a producer writes one in: `rule_id="x"` to `make_claim`, `"rule_id": "x"` in a dict.
            ids.update(re.findall(r"rule_id=\"([^\"]+)\"", path.read_text()))
            ids.update(re.findall(r"\"rule_id\":\s*\"([^\"\s]+)\"", path.read_text()))
            # And the third: a module constant handed to `make_claim` (`FETCH_FAILED_RULE_ID`, `VALIDATION_RULE_ID`).
            ids.update(re.findall(r"RULE_ID\s*=\s*\"([^\"\s]+)\"", path.read_text()))
    # The index producer writes its *reason* for taking no parent as the `rule_id` (#438); those two
    # values flow through constants no regex names, so they are imported rather than scanned for.
    ids.update({NO_MATCHING_PARENT, AMBIGUOUS_PARENT})
    assert {"inherited_from_parent", "index_by_extension", "fetch_failed", "input_validation"} <= ids, (
        "each spelling a rule id is written in is collected"
    )
    assert ids, "no rule ids found — the search is broken, not the namespace"
    assert sorted(i for i in ids if "." in i) == []
    refuses(
        tmp_path,
        """
rows:
  - id: revio
    match: {slot: platform, value: Revio}
""",
        "'revio'",
        "must be 'platform.<slug>'",
    )
    for bad in ('"platform."', '"platform. "', '"platform.re\\nvio"'):
        refuses(
            tmp_path,
            f"""
rows:
  - id: {bad}
    match: {{slot: platform, value: Revio}}
""",
            "non-blank slug",
        )


def test_an_authored_row_must_say_what_it_declares(tmp_path):
    """A reason with no `declares` is a slip, not a no-op: the deliberate no-op is spelled `declares: {}`."""
    refuses(
        tmp_path,
        """
rows:
  - id: platform.revio
    match: {slot: platform, value: Revio}
    reason: forgot the declaration
""",
        "'platform.revio'",
        "no `declares`",
    )


def test_every_empty_spelling_of_rows_can_be_seeded(tmp_path, evidence_root):
    write_generation(evidence_root, "AnVIL_HPRC_R2", "hifi", [entry("platform", "Revio")])
    spellings = (
        "rows:\n",
        "rows: []\n",
        "rows: null\n",
        "rows: ~\n",
        "rows: []  # awaiting evidence\n",
        "rows: [\n]\n",
    )
    for spelling in spellings:
        table_path = tmp_path / "map.yaml"
        table_path.write_text(spelling)
        assert seed(table_path, evidence_root).rows_added == ("platform.revio",), spelling
        assert len(load_value_map(table_path).rows) == 1
        if "#" in spelling:
            assert table_path.read_text().startswith("rows:  # awaiting evidence\n"), "the comment survives the rewrite"
        else:
            assert table_path.read_text().startswith("rows:\n"), spelling


def test_the_text_of_an_empty_array_is_a_scalar_not_a_list_cell():
    """The importer writes no line for an empty list, so `[]` arriving is a string the source wrote."""
    assert list_cell("[]") is None
    assert match_key("[]") == frozenset({"[]"})
    assert list_cell('["A"]') == ["A"]


def test_a_seeded_row_may_not_declare(tmp_path):
    refuses(
        tmp_path,
        """
rows:
  - id: platform.revio
    match: {slot: platform, value: Revio}
    declares: {platform: PACBIO}
""",
        "'platform.revio'",
        "no reason",
    )


def test_an_empty_list_is_not_a_match_value(tmp_path):
    for where in ("value: []", "value: A, alternates: [[]]"):
        refuses(
            tmp_path,
            f"""
rows:
  - id: assay_type.x
    match: {{slot: assay_type, {where}}}
""",
            "'assay_type.x'",
            "empty list matches nothing",
        )


def test_a_row_value_must_be_a_string(tmp_path):
    refuses(
        tmp_path,
        """
rows:
  - id: reference_assembly.38
    match: {slot: reference_assembly, value: 38}
""",
        "expected a string",
    )


SEEDED_IN_BUNDLED_TABLE = [
    "assay_type.isoseq",
    "data_modality.transcriptomic",
    "data_type.alignments",
    "data_type.chains",
    "data_type.gaps",
    "data_type.sequences",
    "reference_assembly.chm13",
]


def test_the_bundled_table_covers_every_hprc_fixture_value(hprc_fixture_root):
    """Every fixture value selects a row of the bundled table, and the ones it leaves queued are exactly the
    seven seeded values — so a deleted or misspelled authored row would surface here as a new queue entry."""
    queued = review_queue(hprc_fixture_root, load_value_map(), datasets=HPRC_DATASETS)
    assert all(e.row_id is not None for e in queued), [e.raw_value for e in queued if e.row_id is None]
    assert sorted({e.row_id for e in queued if e.row_id is not None}) == SEEDED_IN_BUNDLED_TABLE
    assert len(queued) == 16


def test_the_bundled_table_covers_hprc_and_leaves_the_named_values_seeded():
    table = load_value_map()
    assert sorted(row.id for row in table.rows if not row.authored) == SEEDED_IN_BUNDLED_TABLE
    assert table.by_id("reference_assembly.unaligned").declares == {"reference_assembly": NOT_APPLICABLE}
    assert table.by_id("data_type.bam").authored and table.by_id("data_type.bam").declares == {}
    assert table.by_id("assay_type.wgs").declares == {"assay_type": "WGS", "data_modality": "genomic"}
    assert all(row.scope is None for row in table.rows)
