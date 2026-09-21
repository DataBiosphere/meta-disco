"""The value translation table (#414): loading, lookup, claims, seeding and the review queue.

One test per acceptance criterion of the issue, numbered ``ac<N>`` in its name, plus the
bound contract 3.5 puts on the normalizer and the bundled table's own invariants. The
evidence fixtures are written through ``write_evidence_file`` so the seeder and queue
read them the way they read a real generation.
"""

from datetime import datetime
from pathlib import Path

import pytest

from meta_disco.models import (
    CLASSIFICATION_FIELDS,
    JOIN_KEY_DRS_URI,
    NOT_APPLICABLE,
    SOURCE_REPOSITORY_METADATA,
    ClaimSource,
)
from meta_disco.rule_loader import get_unified_rules
from meta_disco.schema_vocab import dimension_values
from meta_disco.source_evidence import (
    EvidenceEntry,
    EvidenceFileEnvelope,
    EvidenceFileSource,
    EvidenceTarget,
    write_evidence_file,
)
from meta_disco.value_map import (
    Scope,
    ValueMap,
    claims_from,
    default_value_map_resource,
    load_value_map,
    match_key,
    normalize,
    review_queue,
    row_id,
    seed,
)

HPRC_GENERATIONS = [
    Path("data/source_evidence/anvil/anvil15/AnVIL_HPRC_R2/20260920T175642Z"),
    Path("data/source_evidence/anvil/anvil15/ANVIL_HPRC/20260920T175642Z"),
]

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


def source(dataset="AnVIL_HPRC_R2", table="hifi", column="instrument_model") -> ClaimSource:
    return ClaimSource(name="anvil", url="https://example.org", dataset=dataset, table=table, column=column)


def entry(field, raw_value, file="drs://f1", **where) -> EvidenceEntry:
    return EvidenceEntry(field=field, target_key_value=file, raw_value=raw_value, source=source(**where))


def write_generation(root: Path, dataset: str, table: str, entries: list[EvidenceEntry], stamp="20260920T175642Z"):
    """One evidence file in the generation layout the reader discovers."""
    directory = root / "anvil" / "anvil15" / dataset / stamp
    directory.mkdir(parents=True, exist_ok=True)
    envelope = EvidenceFileEnvelope(
        source=EvidenceFileSource(repository="anvil", dataset=dataset, table=table, url="https://example.org"),
        source_type=SOURCE_REPOSITORY_METADATA,
        source_version="anvil15",
        source_key="drs_uri",
        target=EvidenceTarget(system="anvil", dataset=dataset, version="anvil15"),
        target_key=JOIN_KEY_DRS_URI,
        fetched_at=datetime(2026, 9, 3, 21, 45, 47),
    )
    write_evidence_file(directory / f"{table}.ndjson", envelope, entries)
    return directory


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
    # And the bundled table holds to it: the loader would have refused the keys.
    bundled = default_value_map_resource().read_text()
    assert "\n    table:" not in bundled and "\n    column:" not in bundled
    load_value_map()


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
    both = ['["single-nucleus ATAC-seq", "single-nucleus RNA sequencing assay"]']
    both.append('["single-nucleus RNA sequencing assay", "single-nucleus ATAC-seq"]')
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


def test_ac18_an_authored_no_op_makes_no_claim_and_leaves_the_queue(tmp_path):
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
    root = tmp_path / "evidence"
    write_generation(root, "AnVIL_HPRC_R2", "kinnex", [entry("data_type", "bam", table="kinnex", column="data_type")])
    assert review_queue(root, table) == []


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
        entry("assay_type", "Bisulfite-Seq", table="hifi", column="library_strategy"),
        entry("data_modality", "GENOMIC", table="hifi", column="library_source"),
    ]
    claims = [
        claim
        for cell in cells
        for slot, claim in claims_from(cell, SOURCE_REPOSITORY_METADATA, table)
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


@pytest.mark.skipif(not all(p.is_dir() for p in HPRC_GENERATIONS), reason="the HPRC evidence generation is not on disk")
def test_ac21_seeding_an_empty_table_from_the_hprc_evidence(tmp_path):
    """43 distinct raw strings on that run; 41 keys, because ``Revio``/``REVIO`` and ``ILLUMINA``/``illumina``
    normalize alike and are one row each with the other spelling as an alternate — two rows would fail AC 5."""
    table_path = tmp_path / "map.yaml"
    table_path.write_text("rows:\n")
    result = seed(table_path, Path("data/source_evidence"), datasets=["AnVIL_HPRC_R2", "ANVIL_HPRC"])
    assert result.lines_scanned == 50_344
    assert len(result.rows_added) == 41
    table = load_value_map(table_path)
    assert len(table.rows) == 41
    assert all(row.id and not row.authored for row in table.rows)
    assert {a for row in table.rows for a in row.alternates} == {"REVIO", "illumina"}
    assert all("anvil/anvil15/" in s and "/20260920T175642Z" in s for row in table.rows for s in row.seeded_from)


def test_ac21_seeding_mints_one_row_per_key_with_id_no_reason_and_the_run_scanned(tmp_path):
    root = tmp_path / "evidence"
    write_generation(
        root,
        "AnVIL_HPRC_R2",
        "hifi",
        [
            entry("platform", "Revio", "drs://a", column="instrument_model"),
            entry("platform", "REVIO", "drs://b", column="instrument_model"),
            entry("assay_type", '["A", "B"]', "drs://a", column="assay_titles"),
            entry("assay_type", '["B", "A"]', "drs://b", column="assay_titles"),
        ],
    )
    table_path = tmp_path / "map.yaml"
    table_path.write_text("rows:\n")
    result = seed(table_path, root)
    assert result.rows_added == ("assay_type.a+b", "platform.revio")
    table = load_value_map(table_path)
    by_id = {row.id: row for row in table.rows}
    assert by_id["platform.revio"].value == "Revio" and by_id["platform.revio"].alternates == ("REVIO",)
    assert by_id["assay_type.a+b"].value == ("A", "B") and by_id["assay_type.a+b"].alternates == (("B", "A"),)
    assert all(not row.authored for row in table.rows)
    assert by_id["platform.revio"].seeded_from == ("anvil/anvil15/AnVIL_HPRC_R2/20260920T175642Z",)


def test_ac22_reseeding_leaves_an_authored_row_untouched_and_mints_no_second_row(tmp_path):
    root = tmp_path / "evidence"
    write_generation(root, "AnVIL_HPRC_R2", "hifi", [entry("platform", "REVIO"), entry("platform", "Sequel II")])
    table_path = tmp_path / "map.yaml"
    table_path.write_text(AUTHORED_REVIO.lstrip())
    before = table_path.read_bytes()
    result = seed(table_path, root)
    assert result.rows_added == ("platform.sequel_ii",)
    after = table_path.read_bytes()
    assert after.startswith(before), "the seeder appends; every earlier byte is where it was"
    assert seed(table_path, root).rows_added == ()
    assert table_path.read_bytes() == after


def test_a_seed_that_would_not_reload_restores_the_file(tmp_path, monkeypatch):
    import meta_disco.value_map as vm

    root = tmp_path / "evidence"
    write_generation(root, "AnVIL_HPRC_R2", "hifi", [entry("platform", "Revio")])
    table_path = tmp_path / "map.yaml"
    table_path.write_text("rows:\n")
    before = table_path.read_bytes()
    monkeypatch.setattr(vm, "_row_text", lambda *a, **k: "  - id: [not a\n")
    with pytest.raises(ValueError, match="does not load; restored"):
        seed(table_path, root)
    assert table_path.read_bytes() == before


def test_ac23_the_queue_lists_a_seeded_value_with_its_provenance_and_file_count(tmp_path):
    table = load(
        tmp_path,
        """
rows:
  - id: assay_type.hi_c
    match: {slot: assay_type, value: Hi-C}
""",
    )
    root = tmp_path / "evidence"
    cells = [entry("assay_type", "Hi-C", f"drs://{n}", table="hic", column="library_strategy") for n in range(3)]
    cells.append(entry("assay_type", "Hi-C", "drs://0", table="hic", column="library_strategy"))
    write_generation(root, "AnVIL_HPRC_R2", "hic", cells)
    (listed,) = review_queue(root, table)
    assert (listed.source, listed.dataset, listed.table, listed.column) == (
        "anvil",
        "AnVIL_HPRC_R2",
        "hic",
        "library_strategy",
    )
    assert (listed.slot, listed.raw_value, listed.files, listed.row_id) == ("assay_type", "Hi-C", 3, "assay_type.hi_c")


def test_ac24_a_seeded_scoped_row_over_an_authored_default_keeps_the_value_queued(tmp_path):
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
    root = tmp_path / "evidence"
    write_generation(root, "AnVIL_HPRC_R2", "hifi", [entry("platform", "Revio")])
    write_generation(root, "ANVIL_T2T", "hifi", [entry("platform", "Revio", dataset="ANVIL_T2T")])
    listed = review_queue(root, table)
    assert [(e.dataset, e.row_id) for e in listed] == [("AnVIL_HPRC_R2", "platform.revio@anvil.AnVIL_HPRC_R2")]


def test_ac25_a_value_with_no_row_is_listed_like_a_seeded_one(tmp_path):
    table = load(
        tmp_path,
        """
rows:
  - id: platform.revio
    match: {slot: platform, value: Revio}
""",
    )
    root = tmp_path / "evidence"
    write_generation(root, "AnVIL_HPRC_R2", "hifi", [entry("platform", "Revio"), entry("platform", "Sequel II")])
    listed = {e.raw_value: e for e in review_queue(root, table)}
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


def test_ac26_nothing_in_a_run_imports_the_table():
    """Classification output is unchanged because no run code reaches the module: the argument the
    issue allows in place of a corpus diff, made checkable."""
    import ast

    importers = []
    for path in sorted([*Path("src/meta_disco").rglob("*.py"), *Path("scripts").glob("*.py")]):
        if path.name == "value_map.py":
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if (isinstance(node, ast.ImportFrom) and node.module and "value_map" in node.module) or (
                isinstance(node, ast.Import) and any("value_map" in a.name for a in node.names)
            ):
                importers.append(str(path))
    assert importers == [], importers


def test_ac27_the_seeder_and_the_queue_read_evidence_through_iter_evidence_only():
    text = Path("src/meta_disco/value_map.py").read_text()
    assert "iter_evidence" in text
    assert "json.load(" not in text
    assert "read_text" not in text.split("def _current_files")[1].split("class QueueEntry")[0]


# --- the normalizer's bound and the bundled table -----------------------------------------------


def test_the_normalizer_cannot_merge_two_terms_of_any_slot(tmp_path):
    """Contract 3.5's binding half: casefold-and-strip keeps every slot's terms distinct."""
    for slot in CLASSIFICATION_FIELDS:
        terms = dimension_values(slot)
        assert len({normalize(t) for t in terms}) == len(terms), slot
    assert normalize(" WGS ") == "wgs" and normalize("WES") == "wes"


def test_row_ids_are_slot_dot_slug_with_sets_joined_and_scope_appended():
    assert row_id("platform", frozenset({"illumina novaseq 6000"})) == "platform.illumina_novaseq_6000"
    assert row_id("assay_type", frozenset({"b", "a"})) == "assay_type.a+b"
    assert (
        row_id("platform", frozenset({"revio"}), Scope("anvil", "AnVIL_HPRC_R2"))
        == "platform.revio@anvil.AnVIL_HPRC_R2"
    )


def test_a_row_id_the_rule_set_uses_is_refused(tmp_path):
    rule_id = get_unified_rules().rules[0].id
    refuses(
        tmp_path,
        f"""
rows:
  - id: {rule_id}
    match: {{slot: platform, value: Revio}}
""",
        rule_id,
        "one namespace",
    )


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


def test_the_bundled_table_covers_hprc_and_leaves_the_named_values_seeded():
    table = load_value_map()
    seeded = sorted(row.id for row in table.rows if not row.authored)
    assert seeded == [
        "assay_type.isoseq",
        "data_modality.transcriptomic",
        "data_type.alignments",
        "data_type.chains",
        "data_type.sequences",
        "reference_assembly.chm13",
    ]
    assert table.by_id("reference_assembly.unaligned").declares == {"reference_assembly": NOT_APPLICABLE}
    assert table.by_id("data_type.bam").authored and table.by_id("data_type.bam").declares == {}
    assert table.by_id("assay_type.wgs").declares == {"assay_type": "WGS", "data_modality": "genomic"}
    assert all(row.scope is None for row in table.rows)
