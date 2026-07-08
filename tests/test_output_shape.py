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
envelope) with a per-type stub fetcher — deterministic, no network. The stub
supplies a placeholder header with no real content, so tier-3 rules that key on
*specific* header content (contig lengths, instrument IDs, assembly tokens) do
not fire — content-driven classification is not exercised. Tier-3 rules that key
on the *absence* of such content (e.g. ``unaligned_no_sq``,
``fastq_modality_unknown``) do fire and appear in the golden. That is acceptable:
this guards output *shape*, not content-driven classification accuracy.
Regenerate with::

    python -m tests.test_output_shape   # writes tests/fixtures/golden/expected_output.json

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

from src.meta_disco import schema_vocab
from src.meta_disco.file_types import FILE_TYPE_REGISTRY
from src.meta_disco.models import CLASSIFICATION_FIELDS, CLASSIFIED
from src.meta_disco.pipeline import ClassifyPipeline

FIXTURES = Path(__file__).parent / "fixtures" / "golden"
GOLDEN_PATH = FIXTURES / "expected_output.json"

# Deterministic synthetic inputs per file type. Filenames target tier-1/2
# (extension/filename) rules so classification needs no real header and is stable
# across runs; a stub fetcher supplies a fixed header so no network is touched.
# Chosen to span the shape surface: a classified value (fasta assembly), sentinels
# (not_applicable / not_classified), and multi-evidence fields.
GOLDEN_INPUTS = {
    "fasta": [
        {"file_md5sum": "golden_fasta_assembly", "file_name": "hapdup_contigs.hap1.fasta",
         "file_size": 2974881710, "file_format": ".fasta", "entry_id": "g-fasta-1",
         "dataset_title": "GOLDEN_FIXTURE"},
    ],
    "bam": [
        {"file_md5sum": "golden_bam_rnaseq", "file_name": "sample.rnaseq.bam",
         "file_size": 12345678, "file_format": ".bam", "entry_id": "g-bam-1",
         "dataset_title": "GOLDEN_FIXTURE"},
    ],
    "vcf": [
        {"file_md5sum": "golden_vcf", "file_name": "sample.vcf.gz",
         "file_size": 5000, "file_format": ".vcf.gz", "entry_id": "g-vcf-1",
         "dataset_title": "GOLDEN_FIXTURE"},
    ],
    "fastq": [
        {"file_md5sum": "golden_fastq", "file_name": "sample.fastq.gz",
         "file_size": 8000, "file_format": ".fastq.gz", "entry_id": "g-fastq-1",
         "dataset_title": "GOLDEN_FIXTURE"},
    ],
}

STUB_HEADER = "stub-header-no-network"
# Real fetchers return str (bam/vcf header text) or list[str] (fastq reads /
# fasta contig names) — see fetchers.py. The stub honors each type's contract so
# the golden exercises realistic classifier input and stays robust if a classifier
# later type-guards its argument.
LIST_RETURNING_TYPES = {"fastq", "fasta"}
EVIDENCE_KEYS = {"rule_id", "reason"}
FIELD_KEYS = {"value", "status", "evidence"}
RECORD_KEYS = {
    "file_name", "md5sum", "file_size", "file_format",
    "dataset_title", "classifications", "entry_id",
}


def _make_stub_fetcher(file_type: str):
    """A deterministic, network-free fetcher whose return type matches the real one."""
    payload = [STUB_HEADER] if file_type in LIST_RETURNING_TYPES else STUB_HEADER

    def _fetch(evidence_dir, md5, **kwargs):
        return payload

    return _fetch


def build_output(tmp_path: Path) -> dict:
    """Run the real classifiers for each file type with a stub fetcher (offline).

    Returns ``{file_type: pipeline_output_dict}``. Uses the production
    FileTypeConfig (real classifier + ``to_output_dict``) with the fetcher swapped
    out, so the shape is real but the run is deterministic and network-free.
    """
    out = {}
    for ftype, records in GOLDEN_INPUTS.items():
        config = dataclasses.replace(FILE_TYPE_REGISTRY[ftype], fetcher=_make_stub_fetcher(ftype))
        input_path = tmp_path / f"{ftype}_input.json"
        input_path.write_text(json.dumps({"results": records}))
        # workers=1 forces sequential processing so the record order in the output
        # is the input order (the parallel path writes in thread-completion order,
        # which is nondeterministic) — keeps the deep-equal golden stable even if
        # an input list ever grows beyond one record.
        pipeline = ClassifyPipeline(
            config, input_path, tmp_path / f"{ftype}_out.json",
            evidence_base=tmp_path / "evidence", workers=1,
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


def test_golden_inputs_cover_all_file_types():
    """Every registered file type must be pinned, or its output shape goes unguarded."""
    assert set(GOLDEN_INPUTS) == set(FILE_TYPE_REGISTRY), (
        "GOLDEN_INPUTS must cover every FILE_TYPE_REGISTRY type so no output shape is "
        f"unguarded. Missing: {set(FILE_TYPE_REGISTRY) - set(GOLDEN_INPUTS)}"
    )


def test_output_matches_golden(output):
    """The real pipeline output must deep-equal the committed golden fixture."""
    assert GOLDEN_PATH.exists(), (
        f"Golden fixture missing at {GOLDEN_PATH}. Regenerate with "
        "`python -m tests.test_output_shape`."
    )
    expected = json.loads(GOLDEN_PATH.read_text())
    assert output == expected, (
        "Classification output shape changed. If intentional, regenerate the golden "
        "with `python -m tests.test_output_shape` and review the diff."
    )


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
            assert set(entry) == FIELD_KEYS, f"{ftype}.{field}: {set(entry)}"
            assert entry["value"] is None or isinstance(entry["value"], str)
            # Stage 3 (#116) coherence: status is a schema-defined value (incl.
            # conflict, #88); sentinels live only in `status`; `value` is non-null
            # iff the field is CLASSIFIED.
            assert entry["status"] in schema_vocab.status_values(), \
                f"{ftype}.{field}: status={entry['status']!r}"
            assert (entry["status"] == CLASSIFIED) == (entry["value"] is not None), \
                f"{ftype}.{field}: incoherent value={entry['value']!r} status={entry['status']!r}"
            assert isinstance(entry["evidence"], list)
            for ev in entry["evidence"]:
                assert EVIDENCE_KEYS <= set(ev), f"{ftype}.{field} evidence: {set(ev)}"


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
        "Pipeline output emits dimension values not in the LinkML schema vocabulary:\n  "
        + "\n  ".join(violations)
    )


def _regenerate_golden():
    """Write the golden fixture from a fresh pipeline run (manual regen entry point)."""
    import tempfile

    FIXTURES.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        output = build_output(Path(tmp))
    GOLDEN_PATH.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(f"Wrote golden fixture to {GOLDEN_PATH}")


if __name__ == "__main__":
    _regenerate_golden()
