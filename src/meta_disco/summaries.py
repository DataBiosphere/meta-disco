"""Summary printers for classification results."""

import re
from typing import Literal

from .models import field_label, field_value


def escape_md_cell(text: str) -> str:
    """Escape characters that break a markdown table cell.

    A pipe closes the cell and a line ending closes the row — CommonMark reads a
    carriage return as one too — so a value carrying any of them (a catalog-supplied
    dataset title, an evidence reason, a verbatim raw value) would silently reshape
    the table. Shared by every report that renders one.
    """
    return text.replace("|", "\\|").replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def md_code(value: str) -> str:
    """Catalog or evidence text for a markdown report, as a code span.

    Pages builds ``docs/`` with Jekyll, which renders markdown syntax and passes raw HTML
    through, so a catalog value holding markup or a link (``![x](https://…)``) would render
    as one. A code span is shown literally. Its fence is one backtick longer than the
    longest run in the value, padded with a space where the value starts or ends with a
    backtick, and line breaks become spaces. :func:`md_table` still escapes a pipe.
    """
    value = value.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
    fence = "`" * (max((len(run) for run in re.findall("`+", value)), default=0) + 1)
    pad = " " if value.startswith("`") or value.endswith("`") else ""
    return f"{fence}{pad}{value}{pad}{fence}"


def md_table(header: list[str], rows: list[list[str]], align: Literal["left", "right"] = "left") -> list[str]:
    """One markdown table as a list of lines: header, separator rule, then the rows.

    Every cell goes through :func:`escape_md_cell`. ``align`` sets the alignment
    of the columns after the first, which stays left — the leading column is a
    label in every report that uses this, and the rest are usually counts.
    Callers pass rows already formatted as strings; this does no number
    formatting of its own.

    ``align`` is a :data:`~typing.Literal` so that a misspelling is a type error
    at the call site rather than a table that quietly renders the other way: the
    two spellings are indistinguishable at runtime, since anything that is not
    ``"left"`` right-aligns.
    """
    # Three characters either way. GFM accepts a single hyphen, but a three-dash
    # cell is what every other report in this repo emits and what the stricter
    # markdown parsers require, so it costs nothing to stay in that dialect.
    rule = "---" if align == "left" else "---:"
    lines = ["| " + " | ".join(escape_md_cell(cell) for cell in header) + " |"]
    lines.append("|" + "|".join([" --- "] + [f" {rule} "] * (len(header) - 1)) + "|")
    lines.extend("| " + " | ".join(escape_md_cell(cell) for cell in row) + " |" for row in rows)
    return lines


def _print_field_table(title: str, counts: dict, width: int = 35):
    print(f"\n{title}:")
    for key, count in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {key:<{width}} {count:>5}")


def _print_sample_evidence(classifications: list[dict], fields: list[tuple[str, str]]):
    """Print sample evidence for first 3 files."""
    print("\n" + "-" * 70)
    print("SAMPLE EVIDENCE (first 3 files):")
    print("-" * 70)

    for c in classifications[:3]:
        print(f"\nFile: {c.get('file_name', 'unknown')}")
        for label, field in fields:
            val = field_value(c, field)
            if val is not None:
                print(f"  {label}: {val}")

    print("=" * 70)


def print_bam_summary(classifications: list[dict]):
    """Print summary statistics of BAM/CRAM classifications."""
    print("\n" + "=" * 70)
    print("BAM/CRAM HEADER CLASSIFICATION SUMMARY")
    print("=" * 70)

    if not classifications:
        print("No classifications to summarize.")
        return

    modalities = {}
    references = {}
    platforms = {}
    instrument_models = {}

    for c in classifications:
        mod = field_label(c, "data_modality")
        modalities[mod] = modalities.get(mod, 0) + 1

        model = field_label(c, "instrument_model")
        instrument_models[model] = instrument_models.get(model, 0) + 1

        ref = field_label(c, "reference_assembly")
        references[ref] = references.get(ref, 0) + 1

        plat = field_label(c, "platform")
        platforms[plat] = platforms.get(plat, 0) + 1

    print(f"\nTotal files classified: {len(classifications)}")

    _print_field_table("Data Modalities", modalities)
    _print_field_table("Reference Assemblies", references)
    _print_field_table("Platforms", platforms)
    _print_field_table("Instrument Models", instrument_models)

    _print_sample_evidence(
        classifications,
        [
            ("Modality", "data_modality"),
            ("Reference", "reference_assembly"),
            ("Platform", "platform"),
            ("Instrument", "instrument_model"),
        ],
    )


def print_vcf_summary(classifications: list[dict]):
    """Print summary statistics of VCF classifications."""
    print("\n" + "=" * 70)
    print("VCF HEADER CLASSIFICATION SUMMARY")
    print("=" * 70)

    if not classifications:
        print("No classifications to summarize.")
        return

    modalities = {}
    data_types = {}
    references = {}

    for c in classifications:
        mod = field_label(c, "data_modality")
        modalities[mod] = modalities.get(mod, 0) + 1

        dtype = field_label(c, "data_type")
        data_types[dtype] = data_types.get(dtype, 0) + 1

        ref = field_label(c, "reference_assembly")
        references[ref] = references.get(ref, 0) + 1

    print(f"\nTotal files classified: {len(classifications)}")

    _print_field_table("Data Modalities", modalities, width=40)
    _print_field_table("Data Types", data_types, width=40)
    _print_field_table("Reference Assemblies", references, width=40)

    _print_sample_evidence(
        classifications,
        [
            ("Modality", "data_modality"),
            ("Data Type", "data_type"),
            ("Reference", "reference_assembly"),
        ],
    )


def print_fastq_summary(classifications: list[dict]):
    """Print summary statistics of FASTQ classifications."""
    print("\n" + "=" * 70)
    print("FASTQ HEADER CLASSIFICATION SUMMARY")
    print("=" * 70)

    if not classifications:
        print("No classifications to summarize.")
        return

    platforms = {}
    modalities = {}
    paired_count = 0
    archive_sources = {}

    for c in classifications:
        plat = field_label(c, "platform")
        platforms[plat] = platforms.get(plat, 0) + 1

        mod = field_label(c, "data_modality")
        modalities[mod] = modalities.get(mod, 0) + 1

        # Dimensions above use field_label so unclassified files bucket as a
        # sentinel; these scalar metadata fields have no sentinel convention, so
        # they use field_value and are simply skipped when absent. No FASTQ has an
        # instrument_model: no rule reads one from a read name (#532).
        if field_value(c, "is_paired_end"):
            paired_count += 1

        source = field_value(c, "archive_source")
        if source:
            archive_sources[source] = archive_sources.get(source, 0) + 1

    print(f"\nTotal files classified: {len(classifications)}")
    print(f"  Paired-end detected: {paired_count}")

    _print_field_table("Platforms", platforms, width=30)
    _print_field_table("Data Modalities", modalities, width=30)

    if archive_sources:
        _print_field_table("Archive Sources", archive_sources, width=30)

    _print_sample_evidence(
        classifications,
        [
            ("Platform", "platform"),
            ("Modality", "data_modality"),
            ("Paired-end", "is_paired_end"),
            ("Archive", "archive_accession"),
        ],
    )
