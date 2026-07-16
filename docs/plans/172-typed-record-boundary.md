# Plan — #172: Parse AnVIL records into a typed model at the load boundary

> **As shipped (see PR #201):** this is the original plan; two details changed
> during implementation. (1) The invalid stream is a single `InvalidRecord`
> dataclass carrying the coerced identity fields *and* the reasons — the separate
> `LenientIdentityView` the plan describes was merged into it during `/simplify`,
> so there is no `(LenientIdentityView, reasons)` tuple. (2) `ClassifierRecord.file_size`
> is `int` (a missing/null `file_size` is classifier-relevant and diverts), not
> `int | None`. (3) `_process_single_record` takes the `ClassifierRecord | InvalidRecord`
> union and dispatches on it, rather than handling only the valid stream. The
> sections below retain the original wording.

**Outcome:** the pipeline stops passing raw `dict`s around and re-deriving field
safety at every consumer. Records become typed at the boundary — a valid record's
classifier fields are `str`/`int` by construction — so the scattered
`str(... or "")` guards added in #171 can be deleted.

## Background

#171 (issue #161) added input-metadata validation, then discovered a recurring
corner case: we validate a record with the Pydantic model and *throw the model
away, keeping the dict*. Every consumer then re-guards field type. `x or ""` guards
`None` but not type, so a drifted non-string (`file_size` as `"123"`, a non-string
`file_name`) slips into `.endswith` / slicing / the output row. #171 patched each
site with a targeted `str(... or "")` coercion. The five guard sites at plan time:

- `_filter_records` routing (`str()` before `.endswith`)
- `_build_record` output echo (`str()` on name/format)
- `update_progress` label (`str()` before slicing)
- `_is_cached` md5 type/format guard
- `_process_single_record`'s `assert isinstance(md5, str)` post-condition assert

Root cause is one thing: *parse, don't validate* — construct a typed record at the
boundary and pass that.

## The one design decision to confirm first

The issue's proposal says "valid → the typed model instance." But today's divert
criterion is **narrower than full strict validation**:
`classification_blocking_reasons` (metadata_schema.py) diverts a record to
`validation_failed` **only** when a *classifier-relevant* field
(`file_md5sum`, `file_name`, `file_size`, `file_format`) is invalid. A record that
fails the full strict contract on a non-classifier field (e.g. `drs_uri`,
`is_supplementary`) **still classifies today** — #161 deliberately marks only what
it genuinely cannot classify and leaves the rest to the whole-corpus gate.

So "valid == constructs the full strict `_ValidatedRecord`" would **change
behavior**: records bad only on a provenance field would newly divert to
`validation_failed`. That contradicts #161.

**Recommendation — a strict "classifier view", not the full model.** Keep
`classification_blocking_reasons` as the split criterion (behavior unchanged).
Model only what the classifier actually reads. Rejected alternative: use the full
`_ValidatedRecord` as the valid stream — simpler typing but silently widens the
divert set, contradicting #161. This is the only choice that affects the whole
shape; the rest of the plan assumes the classifier-view approach.

## Design

Split at the load boundary (in `run()`, after `_filter_records`) into two streams,
each carrying a typed view instead of a raw dict:

1. **Valid** (no blocking reasons) → a `ClassifierRecord`: a small typed record
   over the classifier-relevant fields as strict types, plus the pass-through
   identity fields `_build_record` echoes (`file_md5sum`, `dataset_title`,
   `entry_id`). Because it is built only from a record that already passed
   `classification_blocking_reasons`, its `file_name`/`file_format` are `str`,
   `file_size` is `int | None`, `file_md5sum` is a valid md5 `str` — no guards.

2. **Invalid** (has blocking reasons) → carried as `(view, reasons)` where `view`
   is a `LenientIdentityView`: a dataclass whose `__post_init__` coerces
   (`file_name = str(file_name or "")`, etc.). The coercion lives in one
   constructor instead of at every echo site. This view is used only to build the
   `validation_failed` output row and the progress label.

Both views expose the same identity attributes (`file_name`, `file_format`,
`file_md5sum`, `file_size`, `dataset_title`, `entry_id`) so `_build_record` and the
progress label read `.attr` uniformly regardless of stream.

### `_filter_records` runs before the split

Routing (extension match) precedes parsing, so `_filter_records` still receives raw
dicts and non-dict elements. Per the issue, it either reads through a lenient view
or keeps its guard. **Recommendation:** keep its `str(... or "")` guard as-is — it
is the routing boundary and must tolerate a non-dict/garbage element that never
becomes either typed view. Document that this one guard is intentionally retained;
remove the other four.

## Implementation steps

1. **Add the typed views.** In a new `src/meta_disco/records.py` (or extend
   `metadata_schema.py`):
   - `ClassifierRecord` — frozen dataclass (or pydantic model) with the four
     classifier fields + identity pass-throughs. A `from_valid(record: dict)`
     constructor; may `assert` the post-conditions the blocking check guarantees.
   - `LenientIdentityView` — dataclass with `__post_init__` coercion of
     `file_name`/`file_format` to `str`.
   - Decide together whether both share a small `Protocol`/base exposing the
     identity attrs, so `_build_record` is stream-agnostic.

2. **Split in `run()`** (pipeline.py): after `_filter_records`, partition into
   `valid: list[ClassifierRecord]` and `invalid: list[tuple[LenientIdentityView,
   list[str]]]` using `classification_blocking_reasons`. Thread both into
   `_run_parallel` (adjust its signature / a combined work-list that preserves the
   pre-classify ordering and the cache-stats/limit/skip-cached steps, which
   currently operate on `records`).

3. **Rework `_process_single_record`** to take a `ClassifierRecord` (valid path
   only). Drop the in-function `classification_blocking_reasons` call and the
   `assert isinstance(md5, str)` (now guaranteed by the type). Read typed attrs.
   The invalid stream no longer flows through here — its `validation_failed` row is
   built directly from the `LenientIdentityView` + reasons.

4. **Rework `_build_record`** to accept a view (typed or lenient) and read typed
   attrs. Remove the `str(record.get(...) or "")` coercions and the docstring
   paragraph that calls whole-row normalization "#172's job" (this *is* that job).

5. **Rework `update_progress` / `_run_parallel`** to take the view's `file_name`
   (already a `str`); drop the `str(file_name or "")[:45]` coercion, keep the
   `[:45]` slice.

6. **`_is_cached`** — md5 reaching it on the valid path is a valid md5 by
   construction. Decide whether to keep the `isinstance/_MD5_RE` guard (it is also
   called from `_print_cache_stats` over raw `r.get("file_md5sum")`, before the
   split). Likely keep it, since that call site still
   sees raw dicts — or move cache-stats to run on the typed valid stream and then
   the guard can go. Resolve during implementation; note whichever in the docstring.

7. **Keep `_filter_records`'s guard** (routing boundary, see above). Remove the
   other four #171 guards (steps 3–5).

8. **Fix the stale doc reference.** `src/meta_disco/schema/classification.yaml`
   says pipeline-Pydantic adoption is "a planned follow-up (#33)". #33 is closed and
   was about enum coverage, not pipeline adoption. Repoint to #172 (or drop the line
   once this lands). Grep for any other `#33` pipeline-adoption references.

## Tests

- `tests/test_pipeline.py` — add/extend: a drifted-but-classifier-relevant record
  diverts to `validation_failed` (unchanged behavior); a record drifted only on a
  non-classifier field (`drs_uri`) **still classifies** (guards the #161 behavior
  the classifier-view design preserves); a valid record produces the same output
  row as before (byte-for-byte on the echoed identity fields).
- Unit tests for `ClassifierRecord.from_valid` and `LenientIdentityView` coercion
  (null/non-string name/format → `str`).
- Confirm no regression in `tests/test_metadata_schema.py` (validate_record /
  blocking-reasons semantics unchanged — only the pipeline's *use* of them moves).
- `make test-all` from repo root before pushing (root + schema suites).

## Out of scope

- The `validate_metadata` gate's `OSError` handling (an I/O boundary, not a
  field-type issue) — noted in the issue.
- Modeling the fastq scalar-hint extras inside `classifications` (#134 follow-up).
- Changing what counts as a blocking violation — the divert *set* stays identical.

## Definition of done

- [ ] `ClassifierRecord` + `LenientIdentityView` typed views exist and are the only
      things passed past the load boundary.
- [ ] Valid/invalid split uses `classification_blocking_reasons`; divert behavior is
      unchanged (non-classifier-field drift still classifies — test proves it).
- [ ] The four #171 guards (steps 3–5) and the md5 `assert` are removed;
      `_filter_records`'s routing guard is retained and documented as intentional.
- [ ] `classification.yaml` stale #33 reference repointed to #172 (or removed).
- [ ] Docstrings updated to match new behavior (`_build_record`, `_is_cached`,
      `_process_single_record`); no docstring still claims normalization is "#172's
      job".
- [ ] `make test-all` green; new tests cover both streams and the #161 behavior.
