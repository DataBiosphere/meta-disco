"""Golden-fixture + structural guardrail for the classification output shape.

Stage 0 of the sentinel→status migration (epic #116, issue #117). Pins the
pipeline's output shape so the pure-refactor stages (#118/#119) can prove the
output is unchanged in structure and values, and the deliberate reshape stages
(#120/#121) produce a small, reviewable diff against the golden.

Three layers of protection:

1. ``test_output_matches_golden`` — the real pipeline output deep-equals a
   committed golden JSON. The comparison is on parsed records (semantic
   deep-equality, not byte-level), so it catches any change to structure or
   values while ignoring JSON key order / formatting.
2. ``test_output_structural_contract`` — an explicit keys+types contract per
   record and per field, for legible failures.
3. ``test_output_values_in_vocabulary`` — every classification *dimension* value
   is a member of the matching LinkML schema enum (or a sentinel / null). This is
   the slice of the schema that applies to today's output; full record-level
   JSON-Schema validation lands in Stage 4a (#122), once the output shape matches
   the schema.

The golden is produced by running the real FileTypeConfig classifiers (so it
guards the real ``to_output_dict`` record/dimension shape and the pipeline
envelope) with a per-type stub fetcher — deterministic, no network.

For bam/vcf/fastq/fasta the stub supplies a placeholder header with no real
content, so tier-3 rules that key on *specific* header content (contig lengths,
instrument IDs, assembly tokens) do not fire. Tier-3 rules that key on the
*absence* of such content (e.g. ``unaligned_no_sq``, ``fastq_modality_unknown``)
do fire and appear in the golden. The gfa stub is the exception: its payload is a
real rank-0 rGFA tag, and it is what drives that record's
``data_type: pangenome.reference`` (rule ``rgfa_stable_rank_reference``) — the
filename alone yields only ``pangenome``. Do not replace it with a content-free
value; the golden would silently record the unrefined result.

This guards output *shape*; it is not a substitute for the content-driven
classification tests in ``tests/test_evals.py``.

**Two committed fixtures, one regen command.** The golden covers the seven producers
``ClassifyPipeline`` writes; ``standalone_output.json`` covers the four standalone ones
(#465), which have no golden and so reached no schema validation at all. Both are read
across the component boundary by ``schema/tests/test_output_validation.py``, whose gate
is what makes them cover all eleven — ``test_the_schema_gate_covers_every_producer``
pins that union against ``producers.PRODUCERS``. Regenerate with::

    python -m tests.test_output_shape   # writes both fixtures under tests/fixtures/golden/

Note: the golden deep-equal is intentionally *value-sensitive* — it pins exact
values/reason strings so the migration's pure-refactor stages can prove
the output is unchanged. That couples it to rule content for the duration of epic
#116; once the shape stabilizes (after #122) this file should be de-tuned to
shape-only (drop the deep-equal layer, keep the structural + vocabulary layers).
"""

import dataclasses
import json
from pathlib import Path

import pytest

from meta_disco import schema_vocab
from meta_disco.evidence import BedSignals, SegmentTag
from meta_disco.file_types import FILE_TYPE_REGISTRY
from meta_disco.models import CLASSIFICATION_FIELDS, CLASSIFIED, ENTRY_KEYS
from meta_disco.pipeline import ClassifyPipeline
from meta_disco.producers import PRODUCERS
from meta_disco.validators.reference_builds import IDENTITY_FIELDS
from tests.metadata_fixtures import METADATA_KEYS, RECORD_KEYS, valid_record
from tests.producer_sweep import (
    STANDALONE_PRODUCERS,
    run_index_producer,
    run_producer,
    run_producer_envelope,
    write_snapshot,
)

FIXTURES = Path(__file__).parent / "fixtures" / "golden"
GOLDEN_PATH = FIXTURES / "expected_output.json"
# The four standalone producers' rows, for the same schema gate the golden feeds (#465).
STANDALONE_PATH = FIXTURES / "standalone_output.json"
# Named once, because every message that reports a stale or missing fixture has to say
# it — as `schema/tests/test_output_validation.py` does on its side of the boundary.
REGEN = "python -m tests.test_output_shape"

# Deterministic synthetic inputs per file type. Filenames target tier-1/2
# (extension/filename) rules so classification needs no real header and is stable
# across runs; a stub fetcher supplies a fixed header so no network is touched.
# Chosen to span the shape surface: a classified value (fasta assembly), sentinels
# (not_applicable / not_classified), and multi-evidence fields.
#
# Each record satisfies the input-metadata contract (issue #161) — the run path
# validates every routed record and diverts a classifier-relevant violation to
# validation_failed before classifying — so the md5s are lowercase-hex and the
# contract's other required fields are present (via _golden_record).
#
# Two of the seven carry published values, so the `published` block the pipeline writes
# reaches the schema gate as a record rather than as a dict typed by hand there (#465).
# The other five publish nothing, keeping real `published: null` rows in the gate too —
# the shape ~98% of the corpus takes.

# GRCh38 is a reference_assembly_enum term and GRCm39 is not, so one published list
# yields both halves of `in_vocabulary`: a populated entry and, on the other dimension,
# an empty one. `single-nucleus ATAC-seq` is AnVIL's spelling, which this vocabulary has
# no word for — the state of every published value in the corpus today (#424).
PUBLISHED_BOTH = {
    "data_modality": ["single-nucleus ATAC-seq"],
    "reference_assembly": ["GRCh38", "GRCm39"],
}
# The one-sided shape: 4,476 corpus records are assembly-only like this, and the
# dimension the repository says nothing for is absent from `in_vocabulary` entirely.
PUBLISHED_ASSEMBLY_ONLY = {"reference_assembly": ["GRCh38 + Gencode40"]}


def _golden_record(md5_seed: str, **fields):
    """A contract-valid fixture input: real classifier-facing fields plus the
    contract's other required fields, which do not appear in the output record.

    Serves both fixtures (#465). One dataset across all of them, which matters to the
    index producer alone: its parent lookup is dataset-scoped, so an index file in
    another dataset than its parent would match nothing, and the grounded edge would be
    missing from the fixture that exists to carry it.
    """
    return valid_record(
        file_md5sum=md5_seed * 32,  # lowercase-hex, per the contract
        # Per record, and deliberately not `drs://...v2_<file_id>`: one shared value
        # would not catch a producer that pairs a row with another row's identity, and
        # a derivable pair would not catch one that reconstructs the URI (#433).
        file_id=f"g-file-{md5_seed}",
        drs_uri=f"drs://golden/v2_g-object-{md5_seed}",
        dataset_id="g-dataset",
        dataset_title="GOLDEN_FIXTURE",
        **fields,
    )


GOLDEN_INPUTS = {
    "fasta": [
        _golden_record(
            "a", file_name="hapdup_contigs.hap1.fasta", file_size=2974881710, file_format=".fasta", entry_id="g-fasta-1"
        ),
    ],
    "bam": [
        _golden_record(
            "b",
            file_name="sample.rnaseq.bam",
            file_size=12345678,
            file_format=".bam",
            entry_id="g-bam-1",
            **PUBLISHED_BOTH,
        ),
    ],
    "vcf": [
        _golden_record(
            "c",
            file_name="sample.vcf.gz",
            file_size=5000,
            file_format=".vcf.gz",
            entry_id="g-vcf-1",
            **PUBLISHED_ASSEMBLY_ONLY,
        ),
    ],
    "fastq": [
        _golden_record("d", file_name="sample.fastq.gz", file_size=8000, file_format=".fastq.gz", entry_id="g-fastq-1"),
    ],
    "gfa": [
        _golden_record(
            "e",
            file_name="hprc-v1.0-minigraph-grch38.gfa.gz",
            file_size=848467761,
            file_format=".gfa.gz",
            entry_id="g-gfa-1",
        ),
    ],
    "tar": [
        _golden_record(
            "f", file_name="chr5.136400001_136500001.tar", file_size=45516800, file_format=".tar", entry_id="g-tar-1"
        ),
    ],
    "bed": [
        _golden_record(
            "7", file_name="sample.regions.bed.gz", file_size=45000, file_format=".bed.gz", entry_id="g-bed-1"
        ),
    ],
}

# The index producer's inputs. Its two record paths both have to reach the schema gate,
# because `DerivationEdge` models them as one class: a required verb with nullable
# grounding. `sample.rnaseq.bam` is the golden's own bam input, so the matched `.bai`
# inherits from a row a real producer wrote rather than a hand-built stand-in — the
# `inherited_evidence` shape is one of the two `make_claim` does not build (#413), which
# makes it the likeliest to drift from the schema unnoticed. `orphan.bai` names a parent
# the snapshot does not hold, so this producer declines it (#438) and writes the
# ungrounded edge, whose `parent_file` and `parent_md5sum` are null.
INDEX_INPUTS = [
    GOLDEN_INPUTS["bam"][0],
    _golden_record("1", file_name="sample.rnaseq.bam.bai", file_size=9000, file_format=".bai", entry_id="g-bai-1"),
    _golden_record("2", file_name="orphan.bai", file_size=9001, file_format=".bai", entry_id="g-bai-2"),
]

# The md5 seeds spoken for above, so the standalone producers' inputs below can be
# checked against them rather than against a comment listing which hex digits are free.
# Every fixture record needs its own identity for the reason `_golden_record` gives, and
# nothing else here would notice a reused one: #445's duplicate-`file_id` check scans a
# whole run directory (`output_utils.row_identities`), and these fixtures run each
# producer over its own single-record snapshot, so it never sees them.
SEEDS_TAKEN = {record["file_md5sum"] for records in GOLDEN_INPUTS.values() for record in records} | {
    record["file_md5sum"] for record in INDEX_INPUTS
}

STUB_HEADER = "stub-header-no-network"
# Real fetchers return str (bam/vcf header text), list[str] (fastq reads / fasta
# contig names), or list[SegmentTag] (gfa segment tags) — see fetchers.py. The stub
# honors each type's contract so the golden exercises realistic classifier input
# and stays robust if a classifier later type-guards its argument.
STUB_PAYLOADS = {
    "bam": STUB_HEADER,
    "vcf": STUB_HEADER,
    "fastq": [STUB_HEADER],
    "fasta": [STUB_HEADER],
    "gfa": [SegmentTag(sn="chr1", sr="0")],
    # tar returns member names (list[str]); a GenomicsDB-store marker set.
    "tar": ["chr5.1_2/callset.json", "chr5.1_2/vidmap.json", "chr5.1_2/vcfheader.vcf"],
    # bed returns BedSignals; bare (no-'chr'-prefix) standard chromosome names are the
    # GRCh37/b37 naming convention, so coordinate inference resolves reference_assembly to
    # GRCh37 — exercising the pipeline -> bed classifier -> value envelope path end-to-end.
    "bed": BedSignals(
        chromosomes=["1", "2"],
        has_chr_prefix=False,
        max_coordinates={"1": 1000, "2": 2000},
        line_count=2,
    ),
}
# Every evidence entry has a reason, and is either a synthetic resolution marker
# (carries `marker`) or something a producer made — the two are mutually exclusive
# (issue #228).
MARKER_EVIDENCE_KEYS = {"marker", "reason"}
# A non-marker entry names its producer. `rule_id` for one of ours; `source` for
# an external one, which carries no rule_id because no rule made it (#392). Either
# satisfies this, so the contract does not forbid the external shape `make_claim`
# and the schema both accept — no such producer exists yet (#369/#394), and this
# is the assertion that would otherwise fail on their first row.
PRODUCER_KEYS = {"rule_id", "source"}
# What makes an entry a *claim*: it declares something. A claim carries a
# source_type naming the kind of source behind it (#392) — pinned here because
# "every claim carries one" is the acceptance criterion, and a claim site added
# without one would otherwise publish null provenance silently. Claim-ness is
# defined by the declaration rather than by the producer handle, because the notes
# left by a failed fetch (`classify_without_content`) and a failed input contract
# (`validation_failed_classifications`) carry a rule_id and declare nothing — the
# schema calls those evidence, not claims, and gives them no source_type.
DECLARATION_KEYS = {"value", "status", "claim_state"}
FIELD_KEYS = set(ENTRY_KEYS)
# `build` (#340) is optional detail about a value, carried only by
# reference_assembly and only when something survives into the identity: a
# derived base/version, an observed key-contig checksum, or a declared reference
# name. `base` and `version` inside it are null when nothing resolved. A contig
# length is evidence for resolution but is not recorded, so a length-only header
# that resolves nothing carries no build (#349). The golden's stub headers carry
# none of these, so no build is emitted there and the golden is unaffected — but
# the contract below still has to permit and check it, or the field would slip
# through untested.
OPTIONAL_FIELD_KEYS = {"build"}
# Derived from the dataclass so the contract cannot drift from the fields it
# is meant to pin.
BUILD_KEYS = set(IDENTITY_FIELDS)


def _make_stub_fetcher(file_type: str):
    """A deterministic, network-free fetcher whose return type matches the real one."""
    if file_type not in STUB_PAYLOADS:
        raise ValueError(
            f"No stub payload for file type {file_type!r}. Add one to STUB_PAYLOADS "
            f"matching that fetcher's return type. Stubbed: {sorted(STUB_PAYLOADS)}"
        )
    payload = STUB_PAYLOADS[file_type]

    def _fetch(evidence_dir, md5, **kwargs):
        return payload

    return _fetch


def build_output(tmp_path: Path) -> dict:
    """Run the real classifiers for each file type with a stub fetcher (offline).

    Returns ``{file_type: pipeline_output_dict}``. Uses the production
    FileTypeConfig (real classifier + ``to_output_dict``) with the fetcher swapped
    out, so the shape is real but the run is deterministic and network-free.

    The input goes through ``write_snapshot``, the same envelope builder the standalone
    producers' tests use, so the golden's input names a repository and a catalog —
    without which ``published_source`` returns None and every ``published`` block in the
    golden would carry a null ``source`` (#465). Each type gets its own directory
    because that builder writes one fixed filename.
    """
    out = {}
    for ftype, records in GOLDEN_INPUTS.items():
        # Stub the fetcher (network-free), and drop the config's preflight with it:
        # the preflight guards the real fetcher's env deps (e.g. samtools), which the
        # stub does not use, so it must not run here.
        config = dataclasses.replace(FILE_TYPE_REGISTRY[ftype], fetcher=_make_stub_fetcher(ftype), preflight=None)
        input_dir = tmp_path / f"{ftype}_input"
        input_dir.mkdir()
        input_path = write_snapshot(input_dir, records)
        # workers=1 forces sequential processing so the record order in the output
        # is the input order (the parallel path writes in thread-completion order,
        # which is nondeterministic) — keeps the deep-equal golden stable even if
        # an input list ever grows beyond one record.
        pipeline = ClassifyPipeline(
            config,
            input_path,
            tmp_path / f"{ftype}_out.json",
            evidence_base=tmp_path / "evidence",
            workers=1,
        )
        results = pipeline.run()
        # run() returns [] (and writes no output file) if every record was filtered
        # out — surface that as a clear failure rather than a later FileNotFoundError.
        assert results, (
            f"No records classified for {ftype!r}: a GOLDEN_INPUTS record was filtered "
            "out (check its file_format/file_name against the config's extensions)."
        )
        out[ftype] = json.loads((tmp_path / f"{ftype}_out.json").read_text())
    return out


def build_standalone_output(tmp_path: Path, pipeline_output: dict) -> dict:
    """Run the four standalone producers; return ``{producer_name: output_envelope}``.

    The other half of the schema gate's input (#465). None of these four reads file
    content, so there is no fetcher to stub: they are offline and deterministic as they
    stand.

    ``pipeline_output`` is :func:`build_output`'s. Its bam rows are the parent
    classifications the matched index file inherits from — see :data:`INDEX_INPUTS` for
    why a real producer's rows and not a stand-in.
    """
    out = {}
    for i, param in enumerate(STANDALONE_PRODUCERS):
        producer, file_name, file_format = param.values
        # Positional rather than a hand-kept pool, so a producer added to
        # STANDALONE_PRODUCERS gets a seed without a second list to extend. A seed is one
        # hex digit because `_golden_record` repeats it 32 times, so both bounds are
        # checked: length here, and collision against `SEEDS_TAKEN` below. Neither is
        # decorative — two digits would build a 64-character `file_md5sum`, which is
        # excluded at load as unusable (#376) rather than refused, so the producer would
        # write no rows at all.
        seed = f"{i + 3:x}"
        assert len(seed) == 1, f"{len(STANDALONE_PRODUCERS)} standalone producers is more seeds than hex digits"
        # The param's id is the producer's registry name, which is the key this fixture
        # is read by — `test_the_schema_gate_covers_every_producer` checks those keys
        # against `PRODUCERS`, so an id-less param would key a record under "None".
        name = param.id
        assert isinstance(name, str), f"every STANDALONE_PRODUCERS param needs an id: {param}"
        # Each producer writes one fixed filename, so each gets its own directory.
        work = tmp_path / name
        work.mkdir()
        # Published values on all three, so the `published` block reaches the gate off
        # `OutputRecord.from_record` as well as off the pipeline's `from_work_item`;
        # the index rows below carry none, keeping `published: null` rows here too.
        record = _golden_record(
            seed,
            file_name=file_name,
            file_size=1000,
            file_format=file_format,
            entry_id=f"g-{name}-1",
            **PUBLISHED_BOTH,
        )
        assert record["file_md5sum"] not in SEEDS_TAKEN, (
            f"the {name!r} input's md5 seed {seed!r} is already used by another fixture input"
        )
        out[name] = run_producer_envelope(producer, work, [record])

    index_work = tmp_path / "index"
    index_work.mkdir()
    out["index"] = run_index_producer(
        index_work, INDEX_INPUTS, parent_classifications=pipeline_output["bam"]["classifications"]
    )
    # `build_output` asserts the same thing for the same reason. A producer that wrote no
    # rows would regenerate as an empty `classifications` list and reach no schema
    # validation at all — the hole #465 closes — while every test stayed green, since the
    # coverage test compares only the fixture's keys and a deep-equal against an
    # empty-regenerated fixture holds. Two index rows, one per record path (#438).
    expected_rows = dict.fromkeys(out, 1) | {"index": 2}
    for name, envelope in out.items():
        assert len(envelope["classifications"]) == expected_rows[name], (
            f"{name!r} wrote {len(envelope['classifications'])} rows, expected {expected_rows[name]}: "
            "check its input's file_name/file_format against what the producer routes on"
        )
    return out


def _all_records(output: dict):
    """Yield (file_type, record) for every classified record across types."""
    for ftype, type_output in output.items():
        for record in type_output["classifications"]:
            yield ftype, record


@pytest.fixture(scope="session")
def output(tmp_path_factory):
    """The deterministic pipeline output, built once and shared across the tests.

    All consumers are read-only assertions over the same deterministic dict, so a
    single session-scoped build is safe and avoids re-running every pipeline per test.
    """
    return build_output(tmp_path_factory.mktemp("golden"))


@pytest.fixture(scope="session")
def standalone_output(tmp_path_factory, output):
    """The four standalone producers' output, built once and shared (#465)."""
    return build_standalone_output(tmp_path_factory.mktemp("standalone"), output)


def test_golden_inputs_cover_all_file_types():
    """Every registered file type must be pinned, or its output shape goes unguarded."""
    assert set(GOLDEN_INPUTS) == set(FILE_TYPE_REGISTRY), (
        "GOLDEN_INPUTS must cover every FILE_TYPE_REGISTRY type so no output shape is "
        f"unguarded. Missing: {set(FILE_TYPE_REGISTRY) - set(GOLDEN_INPUTS)}"
    )


def test_stub_payloads_cover_all_file_types():
    """Every registered file type needs a stub payload, or build_output fails deep
    inside the session fixture instead of here with a clear message."""
    assert set(STUB_PAYLOADS) == set(FILE_TYPE_REGISTRY), (
        "STUB_PAYLOADS must cover every FILE_TYPE_REGISTRY type, with a payload whose "
        "type matches that fetcher's real return value. Missing: "
        f"{set(FILE_TYPE_REGISTRY) - set(STUB_PAYLOADS)}"
    )


def _assert_matches_fixture(actual: dict, path: Path, what: str):
    """Deep-equal ``actual`` against the committed fixture at ``path``.

    Shared by both fixtures' guards, so a change to the regen flow or to either message
    is made once. Deep-equal is what makes the schema gate bite: that gate reads
    committed files, so without this a change to `build_published` or `derivation_edge`
    would leave a fixture stale and the gate green.
    """
    assert path.exists(), f"{what} fixture missing at {path}. Regenerate with `{REGEN}`."
    assert actual == json.loads(path.read_text()), (
        f"{what} output changed. If intentional, regenerate the fixture with `{REGEN}` and review the diff."
    )


def test_output_matches_golden(output):
    """The real pipeline output must deep-equal the committed golden fixture."""
    _assert_matches_fixture(output, GOLDEN_PATH, "Classification")


def test_standalone_output_matches_fixture(standalone_output):
    """The four standalone producers' output must deep-equal its committed fixture."""
    _assert_matches_fixture(standalone_output, STANDALONE_PATH, "Standalone producer")


def test_the_schema_gate_covers_every_producer():
    """The gate's input is these two fixtures; together they must be all eleven.

    Read off the committed files rather than off the builders above, because the files
    are what `schema/tests/test_output_validation.py` actually validates — a fixture
    regenerated without a producer would otherwise drop out of the gate in silence,
    which is the hole #465 closes.
    """
    covered = set(json.loads(GOLDEN_PATH.read_text())) | set(json.loads(STANDALONE_PATH.read_text()))
    assert covered == set(PRODUCERS), f"producers the schema gate never sees: {covered ^ set(PRODUCERS)}"


def test_output_structural_contract(output):
    """Explicit keys+types contract per record and per field (legible failures)."""
    for ftype, type_output in output.items():
        assert set(type_output) >= {"metadata", "classifications"}, ftype
        assert isinstance(type_output["classifications"], list)

    for ftype, record in _all_records(output):
        assert set(record) == RECORD_KEYS, f"{ftype}: {set(record) ^ RECORD_KEYS}"
        classifications = record["classifications"]
        # The 5 dimensions must be present; some classifiers (fastq) also emit
        # extra type-specific scalar keys (instrument_model, is_paired_end, ...)
        # which the deep-equal golden pins but are outside the dimension contract.
        assert set(CLASSIFICATION_FIELDS) <= set(classifications), ftype
        for field in CLASSIFICATION_FIELDS:
            entry = classifications[field]
            assert set(entry) >= FIELD_KEYS, f"{ftype}.{field}: missing {FIELD_KEYS - set(entry)}"
            extra = set(entry) - FIELD_KEYS
            assert extra <= OPTIONAL_FIELD_KEYS, f"{ftype}.{field}: unexpected keys {extra}"
            if "build" in entry:
                assert field == "reference_assembly", f"{ftype}.{field}: only reference_assembly carries a build"
                assert set(entry["build"]) == BUILD_KEYS, f"{ftype}.{field}.build: {set(entry['build'])}"
                # Every member null would say nothing while looking like an
                # answer; such an identity is omitted upstream, not emitted.
                assert any(v is not None for v in entry["build"].values()), (
                    f"{ftype}.{field}: an all-null build should be omitted, not emitted"
                )
            assert entry["value"] is None or isinstance(entry["value"], str)
            # Stage 3 (#116) coherence: status is a schema-defined value (incl.
            # conflict, #88); sentinels live only in `status`; `value` is non-null
            # iff the field is CLASSIFIED.
            assert entry["status"] in schema_vocab.status_values(), f"{ftype}.{field}: status={entry['status']!r}"
            assert (entry["status"] == CLASSIFIED) == (entry["value"] is not None), (
                f"{ftype}.{field}: incoherent value={entry['value']!r} status={entry['status']!r}"
            )
            assert isinstance(entry["evidence"], list)
            for ev in entry["evidence"]:
                if "marker" in ev:
                    assert set(ev) >= MARKER_EVIDENCE_KEYS, f"{ftype}.{field} marker: {set(ev)}"
                else:
                    assert "reason" in ev, f"{ftype}.{field} evidence has no reason: {set(ev)}"
                    assert PRODUCER_KEYS & set(ev), f"{ftype}.{field} evidence names no producer: {set(ev)}"
                assert not (PRODUCER_KEYS & set(ev) and "marker" in ev), (
                    f"{ftype}.{field} evidence is both a producer's and a marker: {ev}"
                )
                if DECLARATION_KEYS & set(ev) and "marker" not in ev:
                    assert ev.get("source_type") in schema_vocab.source_type_values(), (
                        f"{ftype}.{field} claim has missing or unknown source_type: {ev}"
                    )


def test_output_values_in_vocabulary(output):
    """Every classification *dimension* value must be in the schema vocabulary.

    Scoped to the five CLASSIFICATION_FIELDS (or null/sentinel). Type-specific
    scalar keys some classifiers add (fastq's instrument_model, is_paired_end, ...)
    are not enum-backed, so they have no vocabulary to check against.
    """
    violations = []
    for ftype, record in _all_records(output):
        for field in CLASSIFICATION_FIELDS:
            value = record["classifications"][field]["value"]
            if value is None:
                continue
            if not schema_vocab.value_in_vocabulary(field, value):
                violations.append(f"{ftype}: {field}={value!r}")
    assert not violations, (
        "Pipeline output emits dimension values not in the LinkML schema vocabulary:\n  " + "\n  ".join(violations)
    )


@pytest.mark.parametrize("producer,name,fmt", STANDALONE_PRODUCERS)
def test_a_standalone_producer_emits_the_record_keys(tmp_path, producer, name, fmt):
    """All eleven output files carry one record shape (#450).

    The golden fixture covers the seven the pipeline writes; this covers the four that
    used to assemble dicts by hand and so could each carry a different set. That is what
    `published` (#424) and the catalog identity (#433) each needed a sweep for, and what
    building `OutputRecord` makes structural instead.
    """
    [row] = run_producer(producer, tmp_path, [valid_record(file_name=name, file_format=fmt)])
    assert set(row) == RECORD_KEYS, f"{name}: {set(row) ^ RECORD_KEYS}"


@pytest.mark.parametrize("with_parent", [True, False], ids=["matched", "declined"])
def test_the_index_producer_emits_the_record_keys(tmp_path, with_parent):
    """Both of its record paths: a matched parent, and one it declined (#438)."""
    parent = [valid_record(file_name="sample.bam", file_format=".bam", file_md5sum="b" * 32)]
    records = (parent if with_parent else []) + [valid_record(file_name="sample.bam.bai", file_format=".bai")]
    for row in run_index_producer(tmp_path, records)["classifications"]:
        assert set(row) == RECORD_KEYS, f"{set(row) ^ RECORD_KEYS}"


@pytest.mark.parametrize("producer,name,fmt", STANDALONE_PRODUCERS)
def test_a_standalone_producer_emits_the_metadata_keys(tmp_path, producer, name, fmt):
    """The `metadata` block is one shape across producers too (#450).

    `RECORD_KEYS` pins the rows; this pins the envelope's tally block, which was five
    ad-hoc shapes sharing only `complete`. `test_records` checks `RunMetadata.to_dict`
    in isolation — it cannot see whether a producer actually emits it.
    """
    envelope = run_producer_envelope(producer, tmp_path, [valid_record(file_name=name, file_format=fmt)])
    assert list(envelope["metadata"]) == METADATA_KEYS


def test_the_index_producer_emits_the_metadata_keys(tmp_path):
    envelope = run_index_producer(tmp_path, [valid_record(file_name="sample.bam.bai", file_format=".bai")])
    assert list(envelope["metadata"]) == METADATA_KEYS


def test_the_pipeline_emits_the_metadata_keys(output):
    """The seven header types, off the golden run, so all eleven are covered."""
    for ftype, payload in output.items():
        assert list(payload["metadata"]) == METADATA_KEYS, ftype


def test_the_shape_test_covers_every_producer():
    """Otherwise a twelfth producer is added and nothing notices — which is exactly how
    the two sweeps this replaced could go stale."""
    covered = set(FILE_TYPE_REGISTRY) | {param.id for param in STANDALONE_PRODUCERS} | {"index"}
    assert covered == set(PRODUCERS), f"producers with no record-shape coverage: {set(PRODUCERS) ^ covered}"


def _regenerate_fixtures():
    """Write both committed fixtures from a fresh run (manual regen entry point).

    One command for both, because the standalone fixture's index records inherit from
    the golden's bam rows: regenerating either alone would leave that inheritance
    pinned against the other fixture's previous contents.
    """
    import tempfile

    FIXTURES.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        output = build_output(Path(tmp))
        standalone_dir = Path(tmp) / "standalone"
        standalone_dir.mkdir()
        standalone = build_standalone_output(standalone_dir, output)
    for path, payload in ((GOLDEN_PATH, output), (STANDALONE_PATH, standalone)):
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        print(f"Wrote fixture to {path}")


if __name__ == "__main__":
    _regenerate_fixtures()
