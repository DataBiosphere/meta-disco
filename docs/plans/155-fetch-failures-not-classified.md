# Plan — #155: Fetch failures become `not_classified` rows, not dropped records

**Outcome:** when a fetcher cannot read a file, the record is written as a
`not_classified` row naming the cause, instead of vanishing from the output. A
missing row is indistinguishable from a file that was never seen; that is worse
than an honest `not_classified` and cuts against *accuracy over coverage*.

## Background

#151 converted `fetch_gfa_segment_tags` to raise `fetchers.FetchError(reason)`
instead of returning `None`. `_fetch_and_classify` catches it and emits a row whose
five dimensions are all `not_classified`, each carrying the cause as evidence
(`{"rule_id": "fetch_failed", "reason": "HTTP 404 …"}`). The other four header
fetchers still `return None` on failure, so `_fetch_and_classify` returns
`(None, False)` and `_process_single_record` drops the record entirely.

The GFA fetcher (`fetchers.py`) is the template. Its failure block:

```python
except FetchError:
    raise                       # already carries its reason — don't re-wrap
except requests.Timeout as e:
    raise FetchError(f"Timeout reading GFA head: {e}") from e
except Exception as e:
    raise FetchError(f"{type(e).__name__}: {e}") from e   # bug surfaces as a row, not a vanish
```

The four to convert (each with a `return None` failure shape):
`fetch_bam_header`, `fetch_vcf_header`, `fetch_fastq_reads`, `fetch_fasta_headers`.

Note: `fetch_vcf_header` / `fetch_fastq_reads` / `fetch_fasta_headers` already
`except FetchError: return None` — they catch the non-2xx `FetchError` that
`_fetch_range` raises and **swallow** it. Converting them is partly *deleting* that
swallow so the `FetchError` propagates (as GFA's `except FetchError: raise` does),
plus turning `Timeout`/`Exception`/empty-content `return None` into raises.

## Impact (measured, warm cache)

From the #172 verification runs (evidence cache warm, so only genuinely
unfetchable files fail):

| type | records currently **dropped** → would become `not_classified` |
|------|--------------------------------------------------------------|
| bam | 1 |
| vcf | 23 |
| fastq | 0 |
| fasta | 0 |
| gfa | 0 (already converted; 14 surface as `content_unreadable`) |

These are a **floor**: a full run over the network (not warm cache) fails more
uncached fetches, so the real count is higher and is the number task 4 must report.

## Key decisions to make deliberately (issue task 3)

1. **`samtools` not found = crash, not `FetchError`.** `fetch_bam_header`'s
   `except FileNotFoundError` ("samtools not found") is an *environment* failure that
   affects **every** BAM record. It must fail the run loudly, not silently mark all
   BAMs `not_classified`. Keep it as a raised, non-`FetchError` error (or let it
   propagate). Only per-file read failures (`returncode != 0`, `TimeoutExpired`,
   parse errors) become `FetchError`. **Recommendation: crash on missing samtools.**
2. **`except Exception` → `FetchError` (wrap, per #151).** A parser/programming bug
   becomes a `not_classified` row whose evidence names the cause (`TypeError: …`) —
   visible and resumable — rather than crashing the whole run. This is #151's choice;
   follow it for consistency. Trade-off: a bug hides as data rather than a stack
   trace, but the row names it, so it is diagnosable in the output.
   **Recommendation: wrap, matching GFA.** (CLAUDE.md's "fail loud" applies to
   *internal* contract violations; a fetch is a network/IO boundary, so a caught,
   reported failure is the boundary-appropriate behavior.)
3. **Drop the now-dead `None` contract.** Once no fetcher returns `None`, change the
   four signatures `-> str | None` → `-> str` (and `fetch_fastq_reads`'s return type
   likewise), remove `if raw_data is None: return None, False` in `_fetch_and_classify`
   (return type `tuple[dict | None, bool]` → `tuple[dict, bool]`), and remove the dead
   `if classifications is None` branches in `_process_single_record` and
   `classify_single`. Let a `None` slipping through be a loud bug, not a silent drop.

## Design / implementation steps

1. **Convert the four fetchers** (`fetchers.py`) to the GFA failure shape:
   - `fetch_vcf_header` / `fetch_fastq_reads` / `fetch_fasta_headers`: delete
     `except FetchError: return None` (let it propagate); convert `Timeout` and
     `Exception` and any empty/non-2xx `return None` into `raise FetchError(reason)`.
   - `fetch_bam_header`: `returncode != 0` → `raise FetchError` with the samtools
     stderr as reason; `TimeoutExpired` → `FetchError`; **`FileNotFoundError` (samtools
     missing) → crash** per decision 1; other `Exception` → `FetchError`.
   - Decide the empty-but-successful case (bam `returncode == 0` with empty stdout →
     currently returns `""`): leave as a readable-but-empty header the classifier
     handles, or treat as `FetchError`. Note it explicitly; do not leave it ambiguous.
2. **Update return types** `-> str | None` → `-> str` on the four (and the return
   type of `_fetch_and_classify`), matching the new no-`None` contract.
3. **Remove dead `None` handling** in `_fetch_and_classify`, `_process_single_record`,
   and `classify_single` (step from decision 3).
4. **The `dropped` counter becomes vestigial.** With no drops, `_run_parallel`'s
   `dropped` is always 0 and `RecordOutcome.result` is never `None`. Decide:
   - **Keep** `dropped` in `_save_final` metadata as a literal `0` (with a comment)
     for output-schema stability, OR
   - **Remove** the drop path (`RecordOutcome.result: dict`, drop the `else: dropped`
     branch) and the `dropped` metadata key, updating consumers.
   `errored` stays meaningful (a non-`FetchError` bug can still crash a worker).
   **Recommendation:** keep `dropped: 0` in the metadata for back-compat, remove the
   unreachable `result is None` branch in `update_progress`. Flag for review.
5. **Fix the direct caller** `scripts/classify_hprc_files.py` — it calls
   `fetch_bam_header` / `fetch_fastq_reads` / `fetch_fasta_headers` directly and
   checks `raw_data is None`. Those calls now raise `FetchError`; wrap them (or route
   through the same `classify_without_content` fallback) so the HPRC path doesn't
   crash on a fetch failure.
6. **Fix stale docs.** The `fetchers.py` module docstring says "`fetch_bam_header`
   never raises FetchError" — update it. Grep the module docstring and per-fetcher
   docstrings for "return None"/"silently"/"drops the record" and correct each.

## Coverage / report denominators (issue task 5)

`scripts/generate_coverage_report.py` and `scripts/generate_classification_report.py`
consume the run metadata / classification rows. A `not_classified` spike must not
misreport denominators: verify these scripts count total emitted rows (a
`not_classified` row is a *present* row with a status, not a missing one) and that
`dropped`/`failed` going to ~0 doesn't skew a "classified / total" ratio. Inspect
both before/after and confirm the numbers move the expected way.

## Verification (issue task 4 — the number that matters)

- Full run per header type on `main` vs branch (warm cache + a real network pass),
  and report, per file type, **how many `not_classified` rows appear that previously
  vanished** — the delta in emitted record count plus the `content_unreadable`/
  `dropped` shift. This is currently unknown and is the core deliverable.
- Confirm the reasons are real (`HTTP 404 …`, timeouts), not masked programming bugs
  — spot-check a sample of the new rows' evidence.
- `make test-all`, `make lint`, `make format-check`, `make type` green.
- Unit tests: each converted fetcher raises `FetchError` (not returns `None`) on a
  non-2xx / timeout / parse error; `fetch_bam_header` **raises (crashes)** on missing
  samtools; `_fetch_and_classify` turns a `FetchError` into a `content_unreadable`
  row and no longer has a `None`-drop path.

## Out of scope

- #149 (BGZF multi-member truncation) and #153 (off-by-one `end_byte`) — separate
  fetch-correctness bugs.
- #156 (mirror availability report — HEAD every md5 to find missing objects).
- #154 (fact model — fetch failure as a fact) — this issue is the direct fix; the
  fact-model refactor would subsume it later.

## Definition of done

- [ ] The four fetchers raise `FetchError(reason)` on read failure; none return `None`.
- [ ] `samtools`-missing crashes the run (decision 1); parser bugs surface as
      `not_classified` rows (decision 2) — both covered by tests.
- [ ] Dead `None` branches removed; fetcher/`_fetch_and_classify` return types tightened.
- [ ] `scripts/classify_hprc_files.py` handles the new raising behavior.
- [ ] Stale "never raises / returns None / drops the record" docstrings corrected.
- [ ] Coverage + classification reports verified to handle the `not_classified` spike.
- [ ] Before/after corpus comparison reported per file type (the previously-unknown
      count of records that stop vanishing).
- [ ] `make test-all` / `lint` / `format-check` / `type` green.
