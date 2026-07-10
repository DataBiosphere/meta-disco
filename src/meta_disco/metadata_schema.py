"""Shape validation for AnVIL file-metadata records.

Nothing between the AnVIL API and the classifiers checks the shape of a record.
A renamed key, a newly-nullable column, or a stringified size flows silently into
758k records and surfaces as a crash — or a wrong classification — somewhere deep
in a multi-hour run.

Two contracts, deliberately separate:

* :data:`ANVIL_RECORD_SCHEMA` — the full 12-field record the download script
  produces. Checked by ``scripts/validate_metadata.py`` and at download time.
* :func:`validate_pipeline_records` — the far smaller promise ``ClassifyPipeline``
  relies on. Derived inputs (a filtered subset, a hand-built test fixture) carry
  only a few fields, so requiring the full AnVIL record here would be wrong.

Nothing here mutates a record. A ``None`` is never coerced to ``""``: that would
hide the drift this exists to catch, and it is what makes ``rec.get(k, "")``
dangerous — the default fires only when the key is *absent*, so a present-but-null
value returns ``None`` and crashes the first ``.lower()`` downstream.
"""

import re
from collections import Counter
from dataclasses import dataclass, field

MD5_PATTERN = re.compile(r"^[0-9a-f]{32}$")

# Bounded so a systematically broken download reports a summary, not 758k lines.
MAX_SAMPLES_PER_PROBLEM = 3


@dataclass(frozen=True)
class FieldSpec:
    """The contract for one record field."""

    types: tuple[type, ...]
    nullable: bool = False
    allow_empty: bool = False
    pattern: re.Pattern | None = None
    min_value: int | None = None


# Measured against the 758,658-record corpus. Two constraints are easy to get
# wrong and are called out rather than inferred:
#   * file_size may be 0 — three records are. `min_value=0`, not 1.
#   * data_modality and reference_assembly are AnVIL's own declarations and are
#     null for ~99% of files. They are nullable by design, not by accident.
ANVIL_RECORD_SCHEMA: dict[str, FieldSpec] = {
    "entry_id": FieldSpec((str,)),
    "file_id": FieldSpec((str,)),
    "file_name": FieldSpec((str,)),
    "file_format": FieldSpec((str,)),
    "file_size": FieldSpec((int,), min_value=0),
    "file_md5sum": FieldSpec((str,), pattern=MD5_PATTERN),
    "drs_uri": FieldSpec((str,)),
    "dataset_id": FieldSpec((str,)),
    "dataset_title": FieldSpec((str,)),
    "is_supplementary": FieldSpec((bool,)),
    "data_modality": FieldSpec((str,), nullable=True),
    "reference_assembly": FieldSpec((str,), nullable=True),
}

# Fields ClassifyPipeline reads. Each may be absent (a derived input need not
# carry it) but must never be present-and-null, which is the failure this guards.
PIPELINE_STRING_FIELDS = ("file_md5sum", "file_name", "file_format", "dataset_title")


@dataclass
class ValidationReport:
    """Problems found, counted by kind, with a bounded sample of each."""

    total: int = 0
    counts: Counter = field(default_factory=Counter)
    samples: dict[str, list[str]] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        return not self.counts

    @property
    def problem_records(self) -> int:
        """Number of distinct problems recorded, not of distinct records.

        One record may contribute several problems, so this is an upper bound on
        the number of bad records — it is a signal of scale, not a count.
        """
        return sum(self.counts.values())

    def add(self, kind: str, detail: str) -> None:
        self.counts[kind] += 1
        bucket = self.samples.setdefault(kind, [])
        if len(bucket) < MAX_SAMPLES_PER_PROBLEM:
            bucket.append(detail)

    def summary(self) -> str:
        if self.is_valid:
            return f"{self.total:,} records, no problems."
        lines = [f"{self.total:,} records, {len(self.counts)} kinds of problem:"]
        for kind, n in self.counts.most_common():
            lines.append(f"  {kind}: {n:,}")
            for detail in self.samples.get(kind, []):
                lines.append(f"      e.g. {detail}")
        return "\n".join(lines)


def _check_value(name: str, value, spec: FieldSpec) -> str | None:
    """The problem this value has against its spec, or None."""
    if value is None:
        return None if spec.nullable else "null"

    # bool is a subclass of int, so an `is_supplementary` in a `file_size` slot
    # would silently pass an isinstance(int) check.
    if isinstance(value, bool) and bool not in spec.types:
        return "type"
    if not isinstance(value, spec.types):
        return "type"

    if isinstance(value, str):
        if not value and not spec.allow_empty:
            return "empty"
        if spec.pattern and not spec.pattern.match(value):
            return "pattern"
    if spec.min_value is not None and value < spec.min_value:
        return "range"
    return None


def validate_anvil_records(
    records: list[dict], schema: dict[str, FieldSpec] = ANVIL_RECORD_SCHEMA
) -> ValidationReport:
    """Validate records against the full AnVIL contract.

    Unknown fields are *not* a problem: the API may add a column, and that should
    not fail a download. A renamed column shows up as `missing:<old_name>`.
    """
    report = ValidationReport(total=len(records))
    for i, rec in enumerate(records):
        if not isinstance(rec, dict):
            report.add("not_an_object", f"record {i}: {type(rec).__name__}")
            continue
        for name, spec in schema.items():
            if name not in rec:
                report.add(f"missing:{name}", f"record {i}")
                continue
            problem = _check_value(name, rec[name], spec)
            if problem:
                report.add(f"{problem}:{name}", f"record {i}: {rec[name]!r}")
    return report


def validate_pipeline_records(records: list[dict]) -> ValidationReport:
    """Validate the small promise ClassifyPipeline relies on.

    Each of PIPELINE_STRING_FIELDS may be absent, but must not be present-and-null:
    `rec.get("file_name", "")` returns None for a null, and the first `.lower()` or
    slice downstream then raises. `file_size`, when present, must be a non-negative
    int (or null — some derived inputs omit the size rather than the key).
    """
    report = ValidationReport(total=len(records))
    for i, rec in enumerate(records):
        if not isinstance(rec, dict):
            report.add("not_an_object", f"record {i}: {type(rec).__name__}")
            continue
        for name in PIPELINE_STRING_FIELDS:
            if name in rec and not isinstance(rec[name], str):
                kind = "null" if rec[name] is None else "type"
                report.add(f"{kind}:{name}", f"record {i}: {rec[name]!r}")
        size = rec.get("file_size")
        if size is not None and (isinstance(size, bool) or not isinstance(size, int)):
            report.add("type:file_size", f"record {i}: {size!r}")
        elif isinstance(size, int) and not isinstance(size, bool) and size < 0:
            report.add("range:file_size", f"record {i}: {size!r}")
    return report
