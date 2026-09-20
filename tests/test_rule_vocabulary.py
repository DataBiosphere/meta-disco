"""Validate the rules against the LinkML schema vocabulary (issue #111).

Two layers of protection:

1. The loader (rule_loader) rejects unknown ``when``/``then`` *keys* — catching
   typo'd condition/effect names that would otherwise be silently ignored.
2. This module checks that every classification *value* a rule emits is a member
   of the matching enum in the canonical LinkML schema
   (``src/meta_disco/schema/classification.yaml``) — catching typos, stale
   values, and new values introduced without updating the schema.

Together they keep the rules and the schema from drifting apart.
"""

import re
import sys
from pathlib import Path

import pytest
import yaml

try:  # the regex parser moved in 3.11; both spellings expose `parse`
    from re import _parser as _sre_mod  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - 3.10
    import sre_parse as _sre_mod  # type: ignore[no-redef]

_sre_parse = _sre_mod.parse

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from classify_index_files import _PARENT_KIND_BY_CATEGORY, INDEX_RELATION

from meta_disco import schema_vocab
from meta_disco.file_name import Format
from meta_disco.rule_loader import RuleLoader, get_unified_rules


def _when_value_violations(rules):
    """Enum-backed `when` condition values not in the schema vocabulary.

    The single detection path for the antecedent-value check — exercised by both
    the suite-wide test and the negative test, so the latter load-bears on the
    real logic rather than re-deriving the membership assertion.
    """
    violations = []
    for rule in rules.rules:
        for key, dimension in schema_vocab.ENUM_BACKED_WHEN_KEYS.items():
            value = (rule.when or {}).get(key)
            if value is not None and not schema_vocab.value_in_vocabulary(dimension, value):
                violations.append(f"{rule.id}: when.{key}={value!r}")
    return violations


def _when_format_violations(rules):
    """`when.format` values that are not real Format members.

    The format counterpart to _when_value_violations. Format is an in-code enum
    rather than a LinkML schema dimension, so it is checked directly against the
    enum instead of through schema_vocab (#243) — but it is the same antecedent-
    value drift check, in the same test layer (the loader validates when *keys*,
    values are checked here). Shared by the suite-wide and negative tests.

    A present `format` must be a string in the Format vocabulary; anything else
    is a violation — including ``null`` and non-string types (e.g. a list), which
    the ``isinstance`` guard reports rather than raising ``TypeError`` on the
    ``not in`` hash. Mirrors value_in_vocabulary's non-string handling.
    """
    valid = {f.value for f in Format}
    violations = []
    for rule in rules.rules:
        when = rule.when or {}
        if "format" not in when:
            continue
        value = when["format"]
        if not isinstance(value, str) or value not in valid:
            violations.append(f"{rule.id}: when.format={value!r}")
    return violations


def test_rule_then_values_in_vocabulary():
    """Every value a rule emits must be a real value in the schema vocabulary.

    Since #133, a field a rule declares non-classified is authored in
    ``then.status`` (see test_rule_then_status_values_are_schema_statuses), so a
    ``then``-value is always a real dimension value and the check is strict
    (``value_in_vocabulary``) — a sentinel in a value slot is now a violation.
    """
    rules = get_unified_rules()
    violations = []
    for rule in rules.rules:
        for field, value in (rule.then or {}).items():
            if field not in schema_vocab.DIMENSION_ENUMS or value is None:
                continue
            if not schema_vocab.value_in_vocabulary(field, value):
                violations.append(f"{rule.id}: {field}={value!r}")

    assert not violations, (
        "Rules emit classification values not in the LinkML schema vocabulary.\n"
        "Add them to classification.yaml or fix the rule:\n  " + "\n  ".join(violations)
    )


def test_rule_then_status_values_are_schema_statuses():
    """Every ``then.status`` value a rule authors must be a schema status value.

    The status counterpart to test_rule_then_values_in_vocabulary: rules author
    ``not_applicable`` / ``not_classified`` in ``then.status`` (#133), and those
    must be members of the schema's classification_status_enum — so the loader's
    authorable set and the schema stay in lockstep.
    """
    statuses = schema_vocab.status_values()
    violations = [
        f"{rule.id}: status.{field}={status!r}"
        for rule in get_unified_rules().rules
        for field, status in rule.then_status.items()
        if status not in statuses
    ]
    assert not violations, "Rules author then.status values not in the schema status enum:\n  " + "\n  ".join(
        violations
    )


def test_rule_when_values_in_vocabulary():
    """Enum-backed `when` condition values must also be in the schema vocabulary.

    Mirrors the `then`-value check for the antecedent side (issue #113). Only
    `when` keys in ENUM_BACKED_WHEN_KEYS are dimension-enum-backed; the rest
    (regexes, header codes, numeric bounds, booleans) are not checkable this way.
    """
    violations = _when_value_violations(get_unified_rules())
    assert not violations, (
        "Rules use `when` condition values not in the LinkML schema vocabulary.\n"
        "Add them to classification.yaml or fix the rule:\n  " + "\n  ".join(violations)
    )


def test_rule_when_format_values_valid():
    """Every `when.format` value must be a real Format member (#243).

    The in-code counterpart to test_rule_when_values_in_vocabulary: `format` is
    backed by the Format enum, not the schema, so it is drift-checked directly
    against the enum. Catches a typo'd format (which would silently never match)
    the same way the platform check catches a typo'd platform.
    """
    violations = _when_format_violations(get_unified_rules())
    assert not violations, (
        "Rules use `when.format` values that are not real Format members.\n"
        "Add the format to meta_disco.file_name.Format or fix the rule:\n  " + "\n  ".join(violations)
    )


def test_core_extensions_derivation():
    """`core_extensions` is the explicit set of producible core extensions (#249).

    Pins the derivation (#245: the parse peels every container first, so there is no
    compound-extension allowlist): the single-dot `extension_map` keys unioned with
    the `EXTENSION_TO_FORMAT` keys (where the one multi-dot core `.g.vcf` lives), all
    lower-cased.
    """
    rules = get_unified_rules()
    core = rules.core_extensions
    expected = {k.lower() for k in rules.extension_map if k.count(".") == 1}
    expected |= {k.lower() for k in rules.EXTENSION_TO_FORMAT}
    assert core == expected
    assert ".g.vcf" in core  # the multi-dot core
    # No core may carry — or be — a compression/archive container: nothing in the core
    # set may end with a wrapper suffix. A compound (".vcf.gz") or a bare container
    # (".tar"/".zip", removed as cores in #245) that appears here is a leak.
    leaked = sorted(c for c in core for w in rules.WRAPPER_SUFFIXES if c.endswith(w))
    assert not leaked, f"container/wrapper-bearing extensions leaked into the core set: {leaked}"


def test_every_format_mapped_extension_is_producible():
    """Every `EXTENSION_TO_FORMAT` key must be a producible core (#249).

    A format mapping for an extension the parser can never yield is a dead entry:
    `extension_to_format` would never be reached for it. Pinning this invariant is
    what makes `.g.vcf`'s format resolution robust — it must not rest on the
    coincidence that a compressed `.g.vcf.gz` spelling happens to exist.
    """
    rules = get_unified_rules()
    dead = sorted(k for k in rules.EXTENSION_TO_FORMAT if k.lower() not in rules.core_extensions)
    assert not dead, f"EXTENSION_TO_FORMAT keys not producible by parse_file_name: {dead}"


def test_rule_extensions_are_producible_cores():
    """Every extension a rule keys on must be a member of `core_extensions` (#249).

    A rule listing an extension the parser can never produce (e.g. a leftover
    compound `.vcf.gz`, or a typo) is a dead condition that silently never matches.
    This drift check ties the rule vocabulary to what `parse_file_name` yields.
    """
    rules = get_unified_rules()
    core = rules.core_extensions
    dead = sorted(
        f"{rule.id}: {ext!r}"
        for rule in rules.rules
        for ext in (rule.when.get("extensions") or [])
        if ext.lower() not in core
    )
    assert not dead, (
        "Rules key on extensions that parse_file_name can never produce "
        "(dead conditions). Use a core extension or fix the rule:\n  " + "\n  ".join(dead)
    )


# Real corpus filenames whose accession happens to spell a rule's token. Kept as
# named cases beside the generated probes below, because these are the ones that
# actually happened — `IGVFFI1310XKZG.fastq.gz` is the file #430 was filed for.
ACCESSION_FILENAMES = (
    "IGVFFI1310XKZG.fastq.gz",  # holds `10X`
    "IGVFFI5210XHHO.tar.gz",  # holds `10X`
    "IGVFFI4961CPGT.fastq.gz",  # holds `CPG`
    "IGVFFI0729UTMM.fastq.gz",  # holds `TMM`
)

# A maximal alphanumeric run long enough to be an accession rather than a word.
_ACCESSION_TOKEN = re.compile(r"[A-Za-z0-9]{8,}")

# Rules knowingly left unanchored, with the reason each was exempted (#430).
#
# The three reference rules are exempt on measurement, not oversight: an assembly name
# is routinely written into the middle of a word, and anchoring them costs real matches
# — 499 distinct filenames for GRCh38 (`…uncoveredByGRCh38WinnowmapAlignments…`,
# `Homo_sapiens_assembly38`) and 105 for CHM13 (`HG002vCHM13…`, where the `v` is
# "versus"), the latter 117 records. `grch37` is listed with them because `b37` and
# `hs37` are the same shape, though only one file matches it today. For these, an
# intra-word match is the wanted behavior.
#
# `signal_rnaseq` matches `rna` inside the gene symbol TRNAU1AP on 16 ENCORE signal
# tracks; whether to anchor the token or teach the series' naming is an open question
# there, so #430 left it alone rather than pre-empting the answer.
KNOWN_UNANCHORED = frozenset({"filename_ref_grch38", "filename_ref_grch37", "filename_ref_chm13", "signal_rnaseq"})


def _subdir(tmp_path, name):
    """A fresh directory under `tmp_path`, so two probe rules files can coexist."""
    path = tmp_path / name
    path.mkdir()
    return path


def _literal_runs(pattern):
    """Every run of literal characters ``pattern`` can match, via ``re``'s own parser.

    Parsed rather than split on ``|``, because a rule's alternatives nest
    (``(assembly|…|[._](pat|mat)(ernal)?[._])``) and string-splitting silently drops
    whatever it cannot read — the one failure a completeness check must not have.
    Private API, and deliberately: if it moves, this raises rather than quietly
    covering less.
    """
    runs = []

    def walk(seq):
        current = []
        for op, av in seq:
            name = str(op)
            if name.endswith("LITERAL"):
                current.append(chr(av))
                continue
            if current:
                runs.append("".join(current))
                current = []
            if name.endswith("BRANCH"):
                for branch in av[1]:
                    walk(branch)
            elif name.endswith("SUBPATTERN"):
                walk(av[3])
            elif name.endswith(("MAX_REPEAT", "MIN_REPEAT")):
                walk(av[2])
        if current:
            runs.append("".join(current))

    walk(_sre_parse(pattern))
    return runs


def accession_probes(rules):
    """One synthetic accession per literal token a rule could match on.

    The nine hand-listed names this replaced only covered tokens someone had already
    thought of, so a rule authored with an uncovered word passed the check without
    being safe (#430). Deriving the probes from the rules themselves removes that
    escape: a new bare token generates its own probe.

    A token already bounded in its pattern (``[._]paternal[._]``) yields a probe it
    cannot match inside, so it is not reported — the check is behavioural, and does
    not care how the boundary was written.
    """
    probes = []
    for rule in rules.rules:
        pattern = (rule.when or {}).get("filename_pattern")
        if not pattern or rule.id in KNOWN_UNANCHORED:
            continue
        for token in sorted({t for t in _literal_runs(pattern) if len(t) >= 3 and t.isalnum()}):
            probes.append(f"IGVFFI7{token.upper()}K2.fastq.gz")
    return tuple(dict.fromkeys(probes))


def _accession_internal_matches(rules, filenames):
    """Rule patterns that match strictly inside an accession-shaped token.

    Returns ``(rule_id, filename, matched_text)`` per hit. A match equal to the whole
    token is not reported — only one buried inside a longer run, which is the shape
    that makes the match a coincidence rather than a signal. The extension gate is
    deliberately *not* applied: a match a gate happens to block today is still a
    latent defect, waiting for the same three characters to land on a gated extension.

    A zero-width match is not a hit either. A pattern that is purely a lookaround
    consumes no characters, so it lands inside every token in the name while matching
    none of them — the containment test alone would report it on every accession.
    """
    hits = []
    # Accession runs are maximal, so "inside a longer one" is containment plus a
    # length difference. Scanned once per filename rather than once per rule pair.
    spans_by_filename = {f: [t.span() for t in _ACCESSION_TOKEN.finditer(f)] for f in filenames}
    for rule in rules.rules:
        pattern = (rule.when or {}).get("filename_pattern")
        if not pattern or rule.id in KNOWN_UNANCHORED:
            continue
        compiled = re.compile(pattern, re.IGNORECASE)
        for filename, spans in spans_by_filename.items():
            for match in compiled.finditer(filename):
                start, end = match.span()
                if end == start:
                    continue
                if any(s <= start and end <= e and (e - s) > (end - start) for s, e in spans):
                    hits.append((rule.id, filename, match.group(0)))
    return hits


def test_no_pattern_matches_inside_an_accession():
    """No `filename_pattern` fires on characters buried in an opaque identifier (#430).

    `reads_scrna_filename` matched `10X` inside the IGVF accession IGVFFI1310XKZG and
    classified that FASTQ `transcriptomic.single_cell` on three characters of an
    identifier. Anchoring one pattern fixes one rule; this check is what makes the fix
    hold for the next rule someone authors with a bare token.

    Scope, stated exactly: every *literal* run a pattern can match gets a probe, so a
    new bare word cannot slip past for want of a hand-written example. A token spelled
    with regex syntax (`hap[12]`) is not a literal run and is not covered, and neither
    is a rule in `KNOWN_UNANCHORED`. So this establishes "no literal token matches
    inside an accession", not "no pattern does" — the general form is #475, which moves
    the boundary into the engine and makes the question structural.
    """
    rules = get_unified_rules()
    hits = _accession_internal_matches(rules, ACCESSION_FILENAMES + accession_probes(rules))
    assert not hits, (
        "Rule patterns match inside an opaque accession — anchor the short token on "
        "its left with `(^|[._-])`:\n  "
        + "\n  ".join(f"{rule_id}: matched {text!r} in {filename}" for rule_id, filename, text in hits)
    )


def test_the_probes_are_generated_from_the_rules(tmp_path):
    """A bare token no hand-written filename covers is still caught.

    The nine names this replaced would have passed `hic` — the word appears in none
    of them — which is the hole that made the guard's claim untrue. The probe for it
    comes from the rule now, so the rule cannot supply a token and escape its own
    check.
    """

    def probe(pattern):
        return {
            "id": "probe",
            "tier": 2,
            "scope": "filename",
            "when": {"extensions": [".bam"], "filename_pattern": pattern},
            "then": {"data_modality": "genomic"},
        }

    bare = RuleLoader(_write_rules_file(_subdir(tmp_path, "bare"), probe("(?i)hic"))).load()
    assert "IGVFFI7HICK2.fastq.gz" in accession_probes(bare)
    assert _accession_internal_matches(bare, accession_probes(bare))

    anchored = RuleLoader(_write_rules_file(_subdir(tmp_path, "anchored"), probe("(?i)(^|[._-])hic"))).load()
    assert not _accession_internal_matches(anchored, accession_probes(anchored))


def test_an_already_bounded_token_is_not_reported():
    """A token whose pattern already bounds it needs no anchor and must not be flagged.

    `bed_assembly_qc` matches `[./_]paternal[./_]`, so `paternal` is a literal run and
    gets a probe — but the pattern cannot match it inside an accession, because the
    delimiters are part of the pattern. Anchoring it anyway would have cost 135 real
    filenames, which is how this check earns its place: the test is behavioural, and
    does not care how the boundary was spelled.
    """
    rules = get_unified_rules()
    assert "IGVFFI7PATERNALK2.fastq.gz" in accession_probes(rules)
    assert not _accession_internal_matches(rules, ("IGVFFI7PATERNALK2.fastq.gz",))


def test_known_unanchored_entries_still_exist():
    """Every exemption names a live rule, so anchoring or deleting one cannot leave a
    silent entry behind excusing a rule that is gone (#430)."""
    stale = sorted(KNOWN_UNANCHORED - {rule.id for rule in get_unified_rules().rules})
    assert not stale, "KNOWN_UNANCHORED exempts rules that no longer exist — drop the entry:\n  " + "\n  ".join(stale)


def test_accession_check_catches_an_unanchored_token(tmp_path):
    """The guard load-bears: an unanchored short token is reported, an anchored one is
    not. Without this, the check above could pass by matching nothing at all."""

    def probe(pattern):
        return {
            "id": "probe",
            "tier": 2,
            "scope": "filename",
            "when": {"extensions": [".fastq"], "filename_pattern": pattern},
            "then": {"data_modality": "transcriptomic.single_cell"},
        }

    names = ("IGVFFI1310XKZG.fastq.gz",)
    bare = _write_rules_file(tmp_path, probe("(?i)10x"))
    assert _accession_internal_matches(RuleLoader(bare).load(), names)
    # `_write_rules_file` reuses the one path, so the anchored probe replaces the bare
    # one — written after the assertion above has read it.
    anchored = _write_rules_file(tmp_path, probe("(?i)(^|[._-])10x"))
    assert not _accession_internal_matches(RuleLoader(anchored).load(), names)


def test_anchored_patterns_still_match_delimited_tokens():
    """Anchoring stops the accession match without costing the real spellings (#430).

    `scRNAseq` and `10xGenomics` are the cases a both-sided anchor
    (`([._-]|$)`) would have rejected, which is why the fix anchors on the left only.
    """
    rules = {rule.id: rule for rule in get_unified_rules().rules}
    pattern = re.compile(rules["reads_scrna_filename"].when["filename_pattern"], re.IGNORECASE)
    for filename in (
        "sample_10x_R1.fastq.gz",
        "SCRNA-seq.fastq",
        "single_cell.fq",
        "scRNAseq_R1.fastq.gz",
        "run.10xGenomics.fastq.gz",
    ):
        assert pattern.search(filename), filename
    assert not pattern.search("IGVFFI1310XKZG.fastq.gz")


def test_when_value_check_rejects_bogus_platform(tmp_path):
    """The when-value drift check catches a typo'd enum-backed value (issue #113).

    Runs the real scan (_when_value_violations) over a rule whose when.platform is
    bogus. The loader accepts the *key* (`platform` is a valid when key); this is
    the *value* gap #113 closes.
    """
    path = _write_rules_file(
        tmp_path,
        {
            "id": "bogus_when_platform",
            "tier": 2,
            "scope": "filename",
            "when": {"platform": "ILUMINA"},  # typo: should be ILLUMINA
            "then": {"data_modality": "genomic"},
        },
    )
    violations = _when_value_violations(RuleLoader(path).load())
    assert violations == ["bogus_when_platform: when.platform='ILUMINA'"]


def test_assay_type_inference_values_in_vocabulary():
    """assay_type_rules (the inference block) must also use vocabulary values."""
    rules = get_unified_rules()
    violations = [
        f"{r.id}: assay_type={r.assay_type!r}"
        for r in rules.assay_type_rules
        if r.assay_type and not schema_vocab.value_in_vocabulary("assay_type", r.assay_type)
    ]
    assert not violations, "assay_type inference rules emit values not in the schema vocabulary:\n  " + "\n  ".join(
        violations
    )


def test_reference_build_families_in_vocabulary():
    """reference_builds[*].family must be a reference_assembly_enum value (#340).

    The build table is non-rule data in the same YAML as the rules, and its
    generated comment asserts that `family` matches the enum — this is what makes
    that true rather than merely claimed. Same guard the assay_type inference
    block gets above, for the same reason: a value that drifts out of the
    vocabulary would surface as a build that resolves to a family no consumer
    recognises.
    """
    rules = get_unified_rules()
    violations = [
        f"{build.family}/{build.version}: family={build.family!r}"
        for build in rules.reference_builds
        if not schema_vocab.value_in_vocabulary("reference_assembly", build.family)
    ]
    assert not violations, "reference_builds families not in the schema vocabulary:\n  " + "\n  ".join(violations)


def _assay_condition_violations(rules):
    """Enum-backed assay_type_rules *condition* values not in the vocabulary.

    The antecedent side of the assay-inference block — the same class as
    _when_value_violations, for the conditions matched in infer_assay_type.
    """
    violations = []
    for rule in rules.assay_type_rules:
        conditions = rule.conditions or {}
        for key, (dimension, is_list) in schema_vocab.ENUM_BACKED_ASSAY_CONDITIONS.items():
            if key not in conditions:
                continue
            raw = conditions[key]
            values = raw if is_list and isinstance(raw, list) else [raw]
            for value in values:
                if not schema_vocab.value_in_vocabulary(dimension, value):
                    violations.append(f"{rule.id}: conditions.{key}={value!r}")
    return violations


def test_assay_type_condition_values_in_vocabulary():
    """Enum-backed assay_type_rules *conditions* must use vocabulary values too.

    The antecedent-value gap (#113) also exists in the assay-inference block:
    data_modality / platform / platform_in are matched against the schema enums
    in infer_assay_type, so a typo there silently never matches.
    """
    violations = _assay_condition_violations(get_unified_rules())
    assert not violations, (
        "assay_type_rules conditions use values not in the LinkML schema vocabulary:\n  " + "\n  ".join(violations)
    )


def test_assay_condition_check_rejects_bogus_platform(tmp_path):
    """The assay-condition drift check catches a typo'd enum-backed value (#113)."""
    path = tmp_path / "rules.yaml"
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump_all(
            [
                {"rules": []},
                {"validators": {}},
                {
                    "assay_type_rules": [
                        {
                            "id": "bogus_assay",
                            "priority": 1,
                            "conditions": {"platform_in": ["ILUMINA"]},  # typo: should be ILLUMINA
                            "assay_type": "WGS",
                        }
                    ]
                },
            ],
            f,
        )
    violations = _assay_condition_violations(RuleLoader(path).load())
    assert violations == ["bogus_assay: conditions.platform_in='ILUMINA'"]


def _write_assay_rules_file(tmp_path, assay_rule):
    """Write a rules file whose third document holds a single assay_type_rule."""
    path = tmp_path / "rules.yaml"
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump_all(
            [
                {"rules": []},
                {"validators": {}},
                {"assay_type_rules": [assay_rule]},
            ],
            f,
        )
    return path


@pytest.mark.parametrize("bad_conditions", ["always", "", [], 0])
def test_loader_rejects_non_mapping_assay_conditions(tmp_path, bad_conditions):
    # A non-mapping `conditions` must raise at load time rather than crash
    # infer_assay_type (which assumes a mapping). Mirrors the when/then guard.
    path = _write_assay_rules_file(
        tmp_path,
        {
            "id": "bad_conditions",
            "priority": 1,
            "conditions": bad_conditions,
            "assay_type": "WGS",
        },
    )
    with pytest.raises(ValueError, match="'conditions' must be a mapping"):
        RuleLoader(path).load()


def test_loader_accepts_null_assay_conditions(tmp_path):
    # A null `conditions` block is a catch-all rule; coerced to {}, not a crash.
    path = _write_assay_rules_file(
        tmp_path,
        {
            "id": "null_conditions",
            "priority": 1,
            "conditions": None,
            "assay_type": "WGS",
        },
    )
    loaded = RuleLoader(path).load()
    assert loaded.assay_type_rules[0].conditions == {}


@pytest.mark.parametrize("list_key", ["platform_in", "matched_rules_any"])
def test_loader_rejects_scalar_list_valued_assay_condition(tmp_path, list_key):
    # A scalar where a list is expected would be iterated char-by-char by
    # infer_assay_type and silently mis-match; the loader must reject it.
    path = _write_assay_rules_file(
        tmp_path,
        {
            "id": "scalar_list",
            "priority": 1,
            "conditions": {list_key: "ILLUMINA"},  # should be ["ILLUMINA"]
            "assay_type": "WGS",
        },
    )
    with pytest.raises(ValueError, match=f"condition '{list_key}' must be a list"):
        RuleLoader(path).load()


def test_loader_accepts_list_valued_assay_conditions(tmp_path):
    path = _write_assay_rules_file(
        tmp_path,
        {
            "id": "list_ok",
            "priority": 1,
            "conditions": {"platform_in": ["PACBIO", "ONT"], "matched_rules_any": ["r1"]},
            "assay_type": "WGS",
        },
    )
    loaded = RuleLoader(path).load()
    assert loaded.assay_type_rules[0].conditions["platform_in"] == ["PACBIO", "ONT"]


def test_dimension_values_unknown_field_raises_clear_error():
    with pytest.raises(ValueError, match="Unknown classification dimension"):
        schema_vocab.dimension_values("not_a_field")


def test_status_values_from_schema():
    # The permissible per-field `status` values, loaded from the schema enum —
    # incl. `conflict` (#88), which is not yet produced but is a valid status.
    assert schema_vocab.status_values() == frozenset({"classified", "not_applicable", "not_classified", "conflict"})


def test_marker_constants_match_schema_enum():
    # rule_engine emits synthetic markers whose `marker` kind must be a member of
    # the schema's evidence_marker_enum (else LinkML output validation rejects
    # them). Pin the Python constants to the schema so the two cannot drift (#228).
    from meta_disco.rule_engine import CONFLICT_MARKER, NOT_CLASSIFIED_MARKER

    assert {NOT_CLASSIFIED_MARKER, CONFLICT_MARKER} == schema_vocab.marker_values()


def test_name_source_constants_match_schema_enum():
    # The resolver stamps `build.name_source` with these constants; the schema's
    # reference_name_source_enum is what output validation checks them against.
    # Pin the two so they cannot drift (#354).
    from meta_disco.validators.reference_builds import NAME_SOURCE_COMMAND_LINE, NAME_SOURCE_REFERENCE_FIELD

    assert {NAME_SOURCE_REFERENCE_FIELD, NAME_SOURCE_COMMAND_LINE} == schema_vocab.name_source_values()


def test_derivation_edge_constants_match_schema_enums():
    # The index producer emits `relation` and `parent_kind` as literals, and nothing in
    # `make test` validates output against the LinkML enums. Pin both so a typo or a
    # schema rename cannot drift silently (#450).
    assert set(_PARENT_KIND_BY_CATEGORY.values()) <= schema_vocab.parent_kind_values()
    assert INDEX_RELATION in schema_vocab.relation_values()


@pytest.mark.parametrize(
    "constants,schema_values",
    [
        ("SOURCE_TYPES", schema_vocab.source_type_values),
        ("IMPORTER_SOURCE_TYPES", schema_vocab.importer_source_type_values),
        ("CLAIM_STATES", schema_vocab.claim_state_values),
        ("JOIN_KEYS", schema_vocab.join_key_values),
    ],
)
def test_claim_vocabularies_match_their_schema_enums(constants, schema_values):
    # make_claim validates against these in-code frozensets, so the schema is read
    # here and not in the classification path. That only stays safe while the two
    # agree — pin each pair so a value added on one side cannot drift (#392).
    from meta_disco import models

    assert getattr(models, constants) == schema_values()


def test_the_external_source_types_are_a_subset():
    # `importer_source_type_enum` lists its two values rather than deriving them,
    # because LinkML has no subset construct `gen-json-schema` honours. That is only
    # safe while it stays a subset: a kind added to `source_type_enum` and misspelled
    # here would let an evidence file declare a source_type no claim can carry (#421).
    # The gap between the two is deliberate: `wrangler_annotation` is a kind a *claim*
    # carries and an evidence file may not, because a curator enters as rules
    # (contract 1.6) — asserted separately below.
    assert schema_vocab.importer_source_type_values() < schema_vocab.source_type_values()


def test_claim_states_are_never_dimension_statuses():
    # The whole reason claim_state is its own slot: `declined` must never be a
    # status a dimension can carry (#392).
    from meta_disco.models import CLAIM_STATES

    assert not CLAIM_STATES & schema_vocab.status_values()


def test_every_authored_rule_scope_has_a_source_type():
    # _apply_rule looks up `_RULE_SOURCE_TYPES[rule.scope]`, so a rule authored
    # with a scope the map lacks would KeyError mid-classification. `file_size` is
    # deliberately absent — no source_type honestly describes a size-only match —
    # so authoring one fails here, where the question can be answered, rather than
    # in the middle of a corpus run (#392).
    from meta_disco.rule_engine import _RULE_SOURCE_TYPES

    authored = {rule.scope for rule in get_unified_rules().rules}
    assert authored <= set(_RULE_SOURCE_TYPES), f"scopes with no source_type: {authored - set(_RULE_SOURCE_TYPES)}"
    assert set(_RULE_SOURCE_TYPES) <= RuleLoader.VALID_SCOPES


def test_value_in_vocabulary_is_strict_dimension_only():
    # Antecedent/output check: a real dimension value passes; a status does NOT —
    # a status in a when/condition (or an output value) is a bug (#115, Stage 3).
    assert schema_vocab.value_in_vocabulary("reference_assembly", "GRCh38")
    assert not schema_vocab.value_in_vocabulary("reference_assembly", "not_applicable")
    assert not schema_vocab.value_in_vocabulary("data_modality", "not_classified")


def test_value_in_vocabulary_rejects_bogus_and_non_string():
    assert not schema_vocab.value_in_vocabulary("reference_assembly", "GRCh99")
    assert not schema_vocab.value_in_vocabulary("platform", ["ILLUMINA", "PACBIO"])


def test_value_in_vocabulary_rejects_all_statuses():
    # A status never belongs in a value slot — the emitted-value check is now
    # strict too (#133), so then/assay/output values reject every status.
    for status in ("not_applicable", "not_classified", "classified", "conflict"):
        assert not schema_vocab.value_in_vocabulary("platform", status)


def _write_rules_file(tmp_path, rule):
    """Write a minimal single-document rules file containing a single rule."""
    path = tmp_path / "rules.yaml"
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump_all([{"rules": [rule]}], f)
    return path


def test_loader_rejects_unknown_when_key(tmp_path):
    path = _write_rules_file(
        tmp_path,
        {
            "id": "typo_when",
            "tier": 2,
            "scope": "filename",
            "when": {"filename_patern": "x"},  # typo: should be filename_pattern
            "then": {"data_modality": "genomic"},
        },
    )
    with pytest.raises(ValueError, match="unknown 'when' condition key"):
        RuleLoader(path).load()


def test_format_value_check_rejects_bogus_format(tmp_path):
    """The format drift check catches a typo'd Format value (#243).

    The format analogue of test_when_value_check_rejects_bogus_platform. The
    loader accepts the `format` *key* (it is a valid when key); the *value* gap
    is closed by the _when_format_violations scan, so this exercises that scan
    over a rule whose when.format is bogus.
    """
    path = _write_rules_file(
        tmp_path,
        {
            "id": "bogus_format",
            "tier": 1,
            "scope": "extension",
            "when": {"format": "FASTAA"},  # typo: should be FASTA
            "then": {"data_type": "sequence"},
        },
    )
    violations = _when_format_violations(RuleLoader(path).load())
    assert violations == ["bogus_format: when.format='FASTAA'"]


@pytest.mark.parametrize("bad", [None, ["FASTA"]])
def test_format_check_flags_null_and_nonstring(tmp_path, bad):
    """A present `format` that is null or a non-string is flagged, not skipped or
    crashed on — the scan guards the hash with isinstance (#243)."""
    path = _write_rules_file(
        tmp_path,
        {
            "id": "bad_format",
            "tier": 1,
            "scope": "extension",
            "when": {"format": bad},
            "then": {"data_type": "sequence"},
        },
    )
    violations = _when_format_violations(RuleLoader(path).load())
    assert violations == [f"bad_format: when.format={bad!r}"]


def test_loader_rejects_unknown_then_key(tmp_path):
    path = _write_rules_file(
        tmp_path,
        {
            "id": "typo_then",
            "tier": 1,
            "scope": "extension",
            "when": {"extensions": [".bam"]},
            "then": {"data_modalty": "genomic"},  # typo: should be data_modality
        },
    )
    with pytest.raises(ValueError, match="unknown 'then' effect key"):
        RuleLoader(path).load()


def test_loader_parses_then_status(tmp_path):
    # A `then.status` sub-map is parsed into `then_status`; `then` keeps only the
    # real-value effects, with the `status` key stripped out (#133).
    path = _write_rules_file(
        tmp_path,
        {
            "id": "mixed",
            "tier": 2,
            "scope": "extension",
            "when": {"extensions": [".fast5"]},
            "then": {
                "data_type": "raw_signal",
                "platform": "ONT",
                "status": {"reference_assembly": "not_applicable"},
            },
        },
    )
    rule = RuleLoader(path).load().rules[0]
    assert rule.then == {"data_type": "raw_signal", "platform": "ONT"}
    assert rule.then_status == {"reference_assembly": "not_applicable"}


def test_loader_rejects_unknown_then_status_field(tmp_path):
    path = _write_rules_file(
        tmp_path,
        {
            "id": "bad_status_field",
            "tier": 1,
            "scope": "extension",
            "when": {"extensions": [".md5"]},
            "then": {"status": {"data_modalty": "not_applicable"}},  # typo
        },
    )
    with pytest.raises(ValueError, match=r"unknown 'then\.status' field"):
        RuleLoader(path).load()


@pytest.mark.parametrize("bad_status", ["classified", "conflict", "genomic", "typo"])
def test_loader_rejects_non_authorable_then_status_value(tmp_path, bad_status):
    # Only not_applicable / not_classified may be authored; classified is implied
    # by a real value and conflict is engine-derived.
    path = _write_rules_file(
        tmp_path,
        {
            "id": "bad_status_value",
            "tier": 1,
            "scope": "extension",
            "when": {"extensions": [".md5"]},
            "then": {"status": {"data_modality": bad_status}},
        },
    )
    with pytest.raises(ValueError, match=r"'then\.status' values must be one of"):
        RuleLoader(path).load()


def test_loader_rejects_field_in_both_then_and_status(tmp_path):
    # A field is either a real value or a status, never both.
    path = _write_rules_file(
        tmp_path,
        {
            "id": "field_conflict",
            "tier": 2,
            "scope": "extension",
            "when": {"extensions": [".bam"]},
            "then": {
                "data_modality": "genomic",
                "status": {"data_modality": "not_applicable"},
            },
        },
    )
    with pytest.raises(ValueError, match="appear in both 'then'"):
        RuleLoader(path).load()


@pytest.mark.parametrize("bad_status_block", ["not_applicable", [], 0])
def test_loader_rejects_non_mapping_then_status(tmp_path, bad_status_block):
    path = _write_rules_file(
        tmp_path,
        {
            "id": "bad_status_block",
            "tier": 1,
            "scope": "extension",
            "when": {"extensions": [".md5"]},
            "then": {"status": bad_status_block},
        },
    )
    with pytest.raises(ValueError, match=r"'then\.status' must be a mapping"):
        RuleLoader(path).load()


@pytest.mark.parametrize("bad_when", ["always", "", [], 0])
def test_loader_rejects_non_mapping_when(tmp_path, bad_when):
    # Any non-mapping `when` (scalar, empty string, empty list, ...) must raise a
    # clear error — not a TypeError, not a per-character "unknown key" message,
    # and crucially not silently coerce to {} (an unconditional match).
    path = _write_rules_file(
        tmp_path,
        {
            "id": "bad_when",
            "tier": 1,
            "scope": "extension",
            "when": bad_when,
            "then": {"data_modality": "genomic"},
        },
    )
    with pytest.raises(ValueError, match="'when' must be a mapping"):
        RuleLoader(path).load()


def test_loader_accepts_null_when_and_then(tmp_path):
    # Empty/null when/then blocks must not crash the load (set(None) TypeError).
    path = _write_rules_file(
        tmp_path,
        {
            "id": "null_blocks",
            "tier": 1,
            "scope": "extension",
            "when": None,
            "then": None,
        },
    )
    loaded = RuleLoader(path).load()
    assert loaded.rules[0].when == {} and loaded.rules[0].then == {}


def test_loader_accepts_known_keys(tmp_path):
    path = _write_rules_file(
        tmp_path,
        {
            "id": "good_rule",
            "tier": 2,
            "scope": "filename",
            "when": {"extensions": [".bam"], "filename_pattern": "rnaseq"},
            "then": {"data_modality": "transcriptomic.bulk", "data_type": "alignments"},
        },
    )
    loaded = RuleLoader(path).load()
    assert loaded.rules[0].id == "good_rule"
