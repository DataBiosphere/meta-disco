"""Hold ``assay_type_enum`` to the EFO terms it borrows (#533).

Each value is an assay term taken from EFO, with its id in ``meaning``, arranged as
an ``is_a`` tree. ``snATAC-seq`` is our own term: EFO has no single-nucleus ATAC-seq,
so it carries no ``meaning`` and sits under the EFO term it narrows. These tests pin
each value to its id and to its parent, so a term cannot be added, dropped,
re-parented or given another term's id without a test failing.
"""

from meta_disco import schema_vocab

# Each value, the id of the term it borrows (None for a term of our own), and its parent.
TERMS = {
    "WGS": ("EFO:0003744", None),  # whole genome shotgun sequencing
    "WES": ("EFO:0005396", None),  # exome sequencing
    "RNA-seq": ("EFO:0008896", None),  # RNA-Seq
    "sc/snRNA-seq": ("EFO:0920118", "RNA-seq"),
    "snRNA-seq": ("EFO:0009809", "sc/snRNA-seq"),  # single nucleus RNA sequencing
    "SHARE-seq": ("EFO:0022962", "sc/snRNA-seq"),
    "ATAC-seq": ("EFO:0007045", None),
    "sc/snATAC-seq": ("EFO:0920117", "ATAC-seq"),
    "snATAC-seq": (None, "sc/snATAC-seq"),
    "ChIP-seq": ("EFO:0002692", None),
    "Bisulfite-seq": ("EFO:0003753", None),
    "Methylation array": ("EFO:0002759", None),  # methylation profiling by array
    "Histology": ("OBI:0600020", None),  # histological assay, as EFO imports it
}


def _spec(value):
    # `meaning` has no public accessor; the spec is read here and nowhere else
    return schema_vocab._load_schema_enums()[schema_vocab.DIMENSION_ENUMS["assay_type"]][value] or {}


def test_each_value_is_the_efo_term_it_borrows():
    values = schema_vocab.dimension_values("assay_type")
    assert {v: _spec(v).get("meaning") for v in values} == {v: m for v, (m, _) in TERMS.items()}


def test_each_value_sits_under_its_parent():
    values = schema_vocab.dimension_values("assay_type")
    assert {v: _spec(v).get("is_a") for v in values} == {v: p for v, (_, p) in TERMS.items()}


def test_a_single_nucleus_term_nests_with_the_generic_single_cell_term():
    # the matrix rule says sc/snRNA-seq and a source says snRNA-seq: one answer, told twice (#533)
    assert schema_vocab.most_specific("assay_type", {"sc/snRNA-seq", "snRNA-seq"}) == "snRNA-seq"
    assert schema_vocab.most_specific("assay_type", {"RNA-seq", "SHARE-seq"}) == "SHARE-seq"
    assert schema_vocab.most_specific("assay_type", {"snRNA-seq", "snATAC-seq"}) is None
