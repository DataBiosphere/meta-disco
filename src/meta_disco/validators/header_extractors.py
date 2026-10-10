"""Header field extraction from BAM/VCF files.

These functions extract specific fields from SAM/BAM headers and VCF headers
for use in classification rules.
"""

import re
from dataclasses import dataclass
from functools import cached_property

from ..evidence import VcfHead, VcfRecord, records_of
from .command_lines import VcfCommand, split_command_line, vcf_commands


@dataclass
class SAMHeader:
    """Parsed SAM/BAM header."""

    hd: dict[str, str] | None = None  # @HD header line
    sq: list[dict[str, str]] | None = None  # @SQ sequence dictionary
    rg: list[dict[str, str]] | None = None  # @RG read groups
    pg: list[dict[str, str]] | None = None  # @PG programs
    co: list[str] | None = None  # @CO comments


@dataclass(frozen=True)
class VcfSimpleMeta:
    """A ``##key=value`` VCF header line (e.g. ``##fileformat``, ``##reference``).

    ``type`` is the key; ``value`` is everything after the ``=``. Distinct from
    ``VcfStructuredMeta`` so that ``parse_vcf_header`` can dispatch on the concrete
    type instead of a reserved ``_type`` key sharing the field namespace.
    """

    type: str
    value: str


@dataclass(frozen=True)
class VcfStructuredMeta:
    """A ``##TYPE=<key=value,...>`` VCF header line (e.g. ``##contig``, ``##INFO``).

    ``type`` is the discriminator (``contig``/``INFO``/``FORMAT``/``FILTER``);
    ``fields`` holds the parsed inner key=value pairs. Keeping ``fields`` separate
    from ``type`` isolates the open-ended VCF key space from the discriminator, so
    readers no longer need to skip reserved keys.
    """

    type: str
    fields: dict[str, str]


# A single parsed ``##`` VCF header line: a key=value line or a structured ``<...>`` line.
VcfHeaderLine = VcfSimpleMeta | VcfStructuredMeta


@dataclass
class VCFHeader:
    """Parsed VCF header."""

    fileformat: str | None = None  # ##fileformat
    reference: str | None = None  # ##reference
    contigs: list[VcfStructuredMeta] | None = None  # ##contig lines
    source: str | None = None  # ##source: the last such line, which the YAML rules match
    # Every ##source line's value, in header order (#654); ``source`` keeps only the last.
    # A header can carry several (T2T's joint-called files name GenomicsDBImport and
    # SelectVariants), and a merged one may keep only one input's.
    sources: tuple[str, ...] = ()
    info_fields: list[VcfStructuredMeta] | None = None  # ##INFO fields
    format_fields: list[VcfStructuredMeta] | None = None  # ##FORMAT fields
    filter_fields: list[VcfStructuredMeta] | None = None  # ##FILTER fields
    alt_fields: list[VcfStructuredMeta] | None = None  # ##ALT declarations (#654)
    other_meta: list[str] | None = None  # Other ## lines the line parser accepted
    # The key of each simple ``##key=value`` line in ``other_meta``, in header order (#654),
    # so a reader looking for a key (``##DeepVariant_version``) does not parse the lines
    # again. A structured ``##key=<...>`` line in ``other_meta`` adds no key here.
    meta_keys: tuple[str, ...] = ()
    # ``##`` lines the line parser rejected (a key it cannot match, such as GATK3's
    # dotted ``##GATKCommandLine.<Tool>``), verbatim. Kept apart from
    # ``other_meta`` because ``match_vcf_header_pattern`` falls back to a prefix
    # scan of that list, and these must not widen what a rule can match (#354).
    unkeyed_meta: list[str] | None = None
    # Each record the read head held (``VcfHead.record_lines``, #630); None where the records
    # were not read, as for a header given as text.
    records: tuple[VcfRecord, ...] | None = None

    @cached_property
    def commands(self) -> list[VcfCommand]:
        """The command lines recorded under ``##<key containing "command">=`` lines (#615).

        Read once, on first use, from ``other_meta`` and then ``unkeyed_meta`` — together,
        every ``##`` line :func:`parse_vcf_header` does not route to a named field. The
        order is grouped, not the header's: each list keeps its own lines in header order,
        but every ``unkeyed_meta`` line (one whose key the line parser rejects, such as
        GATK 3's dotted ``##GATKCommandLine.<Tool>``) comes after every ``other_meta``
        line, however they interleave in the header. Its readers do not
        depend on the order. Each gives its words and its step (``command_lines.VcfCommand``).
        """
        return vcf_commands((self.other_meta or []) + (self.unkeyed_meta or []))


def parse_sam_header_line(line: str) -> tuple[str, dict[str, str]] | None:
    """
    Parse a single SAM header line into its components.

    Args:
        line: A SAM header line starting with @

    Returns:
        Tuple of (record_type, fields_dict) or None if invalid
    """
    if not line.startswith("@"):
        return None

    parts = line.split("\t")
    record_type = parts[0]  # e.g., @HD, @SQ, @RG, @PG

    fields = {}
    for part in parts[1:]:
        if ":" in part:
            key, value = part.split(":", 1)
            fields[key] = value

    return record_type, fields


def parse_sam_header(header_text: str) -> SAMHeader:
    """
    Parse a complete SAM/BAM header.

    Args:
        header_text: The full header text with newline-separated lines

    Returns:
        SAMHeader object with parsed fields
    """
    header = SAMHeader()
    sq_list = []
    rg_list = []
    pg_list = []
    co_list = []

    for line in header_text.splitlines():
        if not line.startswith("@"):
            continue

        result = parse_sam_header_line(line)
        if result is None:
            continue

        record_type, fields = result

        if record_type == "@HD":
            header.hd = fields
        elif record_type == "@SQ":
            sq_list.append(fields)
        elif record_type == "@RG":
            rg_list.append(fields)
        elif record_type == "@PG":
            pg_list.append(fields)
        elif record_type == "@CO":
            # Comments don't have key:value format
            co_list.append(line[4:])  # Skip "@CO\t"

    if sq_list:
        header.sq = sq_list
    if rg_list:
        header.rg = rg_list
    if pg_list:
        header.pg = pg_list
    if co_list:
        header.co = co_list

    return header


def extract_sam_field(header: SAMHeader, section: str, field: str) -> list[str]:
    """
    Extract all values of a specific field from a SAM header section.

    Args:
        header: Parsed SAMHeader object
        section: Section name (@HD, @SQ, @RG, @PG)
        field: Field name (e.g., PL, PN, SN, AS)

    Returns:
        List of field values found (may be empty)
    """
    return [record[field] for record in _section_records(header, section) if field in record]


def _section_records(header: SAMHeader, section: str) -> list[dict[str, str]]:
    """The records of one tag-value section (@HD, @SQ, @RG, @PG); empty for any other."""
    if section == "@HD":
        return [header.hd] if header.hd else []
    return {"@SQ": header.sq, "@RG": header.rg, "@PG": header.pg}.get(section) or []


def match_sam_header_pattern(header: SAMHeader, section: str, field: str, pattern: str, every: bool = False) -> bool:
    """
    Check whether a SAM header field's values match a regex pattern.

    Args:
        header: Parsed SAMHeader object
        section: Section name (@HD, @SQ, @RG, @PG)
        field: Field name (e.g., PL, PN, SN)
        pattern: Regex pattern to match
        every: If True, every record of the section must carry the field and match,
            and there must be at least one record; otherwise one matching value is
            enough. A record without the field fails it: an @RG with no PM leaves
            that read group's model unknown.

    Returns:
        True if any value matches (``every=False``), or if the section has records
        and each carries a matching value (``every=True``)
    """
    compiled = re.compile(pattern, re.IGNORECASE)
    if every:
        records = _section_records(header, section)
        return bool(records) and all(field in r and compiled.search(r[field]) for r in records)
    return any(compiled.search(v) for v in extract_sam_field(header, section, field))


def has_sam_section(header: SAMHeader, section: str) -> bool:
    """
    Check if a SAM header has a specific section.

    Args:
        header: Parsed SAMHeader object
        section: Section name (@HD, @SQ, @RG, @PG)

    Returns:
        True if the section exists and has entries
    """
    if section == "@HD":
        return header.hd is not None
    if section == "@SQ":
        return header.sq is not None and len(header.sq) > 0
    if section == "@RG":
        return header.rg is not None and len(header.rg) > 0
    if section == "@PG":
        return header.pg is not None and len(header.pg) > 0
    if section == "@CO":
        return header.co is not None and len(header.co) > 0
    return False


# Compiled once: the line parser runs on every ``##`` line of every VCF header in
# the corpus, and module-level ``re.match`` on a string pays a cache lookup per
# call (#488).
_VCF_STRUCTURED_LINE_RE = re.compile(r"^##(\w+)=<(.*)>$")
_VCF_SIMPLE_LINE_RE = re.compile(r"^##(\w+)=(.*)$")
# key=value or key="value with spaces"
_VCF_FIELD_RE = re.compile(r'(\w+)=("[^"]*"|[^,]*)')


def parse_vcf_header_line(line: str) -> VcfHeaderLine | None:
    """
    Parse a VCF header line into a typed simple or structured record.

    Args:
        line: A VCF header line like ##INFO=<ID=DP,Number=1,Type=Integer,...>

    Returns:
        A VcfStructuredMeta for ``##TYPE=<...>`` lines, a VcfSimpleMeta for simple
        ``##key=value`` lines, or None if not parseable.
    """
    # Match ##TYPE=<...> format
    match = _VCF_STRUCTURED_LINE_RE.match(line)
    if not match:
        # Handle simple key=value format like ##fileformat=VCFv4.2
        simple_match = _VCF_SIMPLE_LINE_RE.match(line)
        if simple_match:
            return VcfSimpleMeta(type=simple_match.group(1), value=simple_match.group(2))
        return None

    header_type = match.group(1)
    content = match.group(2)

    # Parse key=value pairs (handling quoted values)
    fields: dict[str, str] = {}
    for key, value in _VCF_FIELD_RE.findall(content):
        # Remove quotes if present
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        fields[key] = value

    return VcfStructuredMeta(type=header_type, fields=fields)


def parse_vcf_header(header_text: str) -> VCFHeader:
    """
    Parse VCF header lines into a structured object.

    Args:
        header_text: VCF header text (lines starting with ##)

    Returns:
        VCFHeader object with parsed fields
    """
    header = VCFHeader()
    contigs = []
    info_fields = []
    format_fields = []
    filter_fields = []
    alt_fields = []
    other_meta = []
    meta_keys = []
    unkeyed_meta = []

    for line in header_text.splitlines():
        if not line.startswith("##"):
            continue

        parsed = parse_vcf_header_line(line)
        if parsed is None:
            unkeyed_meta.append(line)
            continue

        if isinstance(parsed, VcfSimpleMeta):
            if parsed.type == "fileformat":
                header.fileformat = parsed.value
            elif parsed.type == "reference":
                header.reference = parsed.value
            elif parsed.type == "source":
                header.source = parsed.value
                header.sources += (parsed.value,)
            else:
                other_meta.append(line)
                meta_keys.append(parsed.type)
        elif parsed.type == "contig":
            contigs.append(parsed)
        elif parsed.type == "INFO":
            info_fields.append(parsed)
        elif parsed.type == "FORMAT":
            format_fields.append(parsed)
        elif parsed.type == "FILTER":
            filter_fields.append(parsed)
        elif parsed.type == "ALT":
            alt_fields.append(parsed)
        else:
            other_meta.append(line)

    if contigs:
        header.contigs = contigs
    if info_fields:
        header.info_fields = info_fields
    if format_fields:
        header.format_fields = format_fields
    if filter_fields:
        header.filter_fields = filter_fields
    if alt_fields:
        header.alt_fields = alt_fields
    if other_meta:
        header.other_meta = other_meta
        header.meta_keys = tuple(meta_keys)
    if unkeyed_meta:
        header.unkeyed_meta = unkeyed_meta

    return header


def parse_vcf_head(head: VcfHead) -> VCFHeader:
    """A VCF fetcher's head parsed: its header text by :func:`parse_vcf_header`, with its records."""
    header = parse_vcf_header(head.header_text)
    header.records = records_of(head.record_lines)
    return header


# INFO fields Picard's LiftoverVcf adds: the two swap flags on every run, the
# three ``Original*`` fields only with its opt-in WRITE_ORIGINAL_* options. Any
# one marks a lifted file (issue #354).
LIFTOVER_INFO_IDS = frozenset(
    {"SwappedAlleles", "ReverseComplementedAlleles", "OriginalContig", "OriginalStart", "OriginalAlleles"}
)


def sam_command_words(header: SAMHeader) -> list[list[str]]:
    """The arguments of the ``CL`` of each ``@PG`` record, in header order; empty when none carry one."""
    return [split_command_line(pg["CL"]) for pg in header.pg or [] if pg.get("CL")]


# INFO fields that describe a structural variant (VCF 4.3, section 3): a header declaring
# one says structural variants may appear among its records (#630).
SV_INFO_IDS = frozenset({"SVTYPE", "SVLEN", "CIPOS", "CIEND", "MATEID", "IMPRECISE"})


def declared_info_ids(header: VCFHeader, ids: frozenset[str]) -> set[str]:
    """Which of ``ids`` the header's ``##INFO`` lines declare."""
    return {info.fields.get("ID", "") for info in header.info_fields or []} & ids


def declared_alt_ids(header: VCFHeader, ids: frozenset[str]) -> set[str]:
    """Which of ``ids`` the header's ``##ALT`` lines declare, a subtype (``DEL:ME``) read as its type (``DEL``)."""
    return {alt.fields.get("ID", "").split(":", 1)[0] for alt in header.alt_fields or []} & ids


def is_lifted(header: VCFHeader) -> bool:
    """Whether the header declares any of ``LIFTOVER_INFO_IDS``."""
    return bool(declared_info_ids(header, LIFTOVER_INFO_IDS))


def match_vcf_header_pattern(header: VCFHeader, header_type: str, pattern: str) -> bool:
    """
    Check if any VCF header line of a given type matches a pattern.

    Args:
        header: Parsed VCFHeader object
        header_type: Type of header line (##reference, ##source, ##contig, ##INFO,
            ##FORMAT, ##FILTER, ##ALT)
        pattern: Regex pattern to match

    Returns:
        True if a matching header line satisfies the pattern. What the pattern is
        tested against depends on the type: the value for ##reference/##source,
        the ID for ##INFO/##FORMAT/##FILTER/##ALT, the ``assembly`` subfield for
        ##contig, and the raw line for any other (##-prefixed) type.
    """
    compiled = re.compile(pattern, re.IGNORECASE)

    if header_type == "##reference" and header.reference:
        return bool(compiled.search(header.reference))
    if header_type == "##source" and header.source:
        return bool(compiled.search(header.source))
    if header_type == "##contig" and header.contigs:
        # Match the parsed ``assembly`` subfield directly — the value is already
        # isolated in ``fields``, so the rule pattern is a bare name, not ``assembly=``.
        for contig in header.contigs:
            assembly = contig.fields.get("assembly")
            if assembly and compiled.search(assembly):
                return True
    elif header_type == "##INFO" and header.info_fields:
        for info in header.info_fields:
            info_id = info.fields.get("ID")
            if info_id and compiled.search(info_id):
                return True
    elif header_type == "##FORMAT" and header.format_fields:
        for fmt in header.format_fields:
            fmt_id = fmt.fields.get("ID")
            if fmt_id and compiled.search(fmt_id):
                return True
    elif header_type == "##FILTER" and header.filter_fields:
        for flt in header.filter_fields:
            flt_id = flt.fields.get("ID")
            if flt_id and compiled.search(flt_id):
                return True
    elif header_type == "##ALT" and header.alt_fields:
        for alt in header.alt_fields:
            alt_id = alt.fields.get("ID")
            if alt_id and compiled.search(alt_id):
                return True
    elif header.other_meta:
        # header_type already includes ## prefix (e.g., "##reference")
        for line in header.other_meta:
            if line.startswith(header_type) and compiled.search(line):
                return True

    return False


def get_contig_lines(header: VCFHeader) -> list[str]:
    """
    Get contig lines from a VCF header in the original format.

    Args:
        header: Parsed VCFHeader object

    Returns:
        List of ##contig=<...> lines
    """
    if not header.contigs:
        return []

    lines = []
    for contig in header.contigs:
        # Reconstruct the line
        parts = [f"{key}={value}" for key, value in contig.fields.items()]
        lines.append(f"##contig=<{','.join(parts)}>")

    return lines
