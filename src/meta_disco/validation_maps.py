"""HPRC's catalog names and URL, and the maps from its values to ours, or to its own spelling where our vocabulary has no term."""

HPRC_CATALOG_NAMES = ["sequencing-data", "alignments", "annotations", "assemblies"]

HPRC_CATALOG_BASE_URL = "https://raw.githubusercontent.com/human-pangenomics/hprc-data-explorer/main/catalog/output"

HPRC_PLATFORM_MAP = {
    "PACBIO_SMRT": "PACBIO",
    "OXFORD_NANOPORE": "ONT",
    "ILLUMINA": "ILLUMINA",
}

# librarySource names the molecule sequenced. GENOMIC is no modality truth: SRA files WGS,
# bisulfite, ATAC, ChIP and Hi-C alike under it (#563). TRANSCRIPTOMIC (RNA) is.
HPRC_LIBRARY_SOURCE_MAP = {
    "TRANSCRIPTOMIC": "transcriptomic",
}

# `Hi-C` and `ISO-seq` have no assay_type_enum term yet (#399), so validate_against_hprc can never
# score them a match; they stay here as HPRC's spelling of what the catalog says.
HPRC_LIBRARY_STRATEGY_MAP = {
    "WGS": "WGS",
    "Hi-C": "Hi-C",
    "isoseq": "ISO-seq",
    "Iso-Seq": "ISO-seq",
}

HPRC_REF_COORDINATES_MAP = {
    "chm13": "CHM13",
    "grch38": "GRCh38",
    "grch37": "GRCh37",
}

# Annotation types that encode a reference assembly in their name.
# Types not listed here are per-sample de novo annotations (CenSat, Flagger, etc.)
# with no standard reference — these are skipped during validation.
_ANNOTATION_REF_PATTERNS: dict[str, str] = {
    "CAT_genes_chm13": "CHM13",
    "CAT_genes_hg38": "GRCh38",
    "chains CHM13": "CHM13",
    "chains GRCh38": "GRCh38",
    "Reference Mappings CHM13": "CHM13",
    "Reference Mappings GRCh38": "GRCh38",
    "ChromAlias T2T": "CHM13",
}


def extract_ref_from_annotation_type(annotation_type: str) -> str | None:
    """Extract reference assembly from an HPRC annotation type string.

    Returns the normalized reference assembly (CHM13, GRCh38, etc.) if the
    annotation type encodes a reference, or None for de novo assembly
    annotations where no standard reference applies.
    """
    if not annotation_type:
        return None
    return _ANNOTATION_REF_PATTERNS.get(annotation_type)
