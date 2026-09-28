"""Hold ``data_modality_enum`` to AnVIL's recommended vocabulary (#563).

AnVIL's Findability Subset recommends the Broad's MODAL ontology for its
``data_modality`` field. The enum spells each MODAL term as a dotted path, names its
parent in ``is_a`` and its MODAL id in ``meaning``. These tests pin all three, so a
term cannot be added, dropped or re-parented without the change showing here.
"""

from meta_disco import schema_vocab

# MODAL's terms (github.com/broadinstitute/modal, DataModality.ttl), less its root,
# "data modality" (0000001), which is the enum itself rather than a value.
MODAL_TERMS = {
    "0000002": "epigenomic",
    "0000003": "3D contact maps",
    "0000004": "DNA binding",
    "0000005": "histone modification location",
    "0000006": "transcription factor location",
    "0000007": "DNA chromatin accessibility",
    "0000008": "DNA methylation",
    "0000009": "RNA binding",
    "0000010": "genomic",
    "0000011": "assembly",
    "0000012": "exome",
    "0000013": "genotyping",
    "0000014": "whole genome",
    "0000015": "imaging",
    "0000016": "electrophysiology",
    "0000017": "medical imaging",
    "0000018": "CT scan",
    "0000019": "electrocardiogram",
    "0000020": "MRI",
    "0000021": "X ray",
    "0000022": "microscopy",
    "0000023": "metabolomic",
    "0000024": "microbiome",
    "0000025": "proteomic",
    "0000026": "transcriptomic",
    "0000027": "spatial transcriptomics",
    "0000028": "transcriptomic nontargeted",
    "0000029": "transcriptomic targeted",
}


def _values():
    return schema_vocab._load_schema_enums()["data_modality_enum"]


def test_every_value_is_one_modal_term_and_every_modal_term_has_a_value():
    meanings = {}
    for value, spec in _values().items():
        meaning = (spec or {}).get("meaning", "")
        assert meaning.startswith("MODAL:"), f"{value!r} has no MODAL meaning"
        assert meaning not in meanings, f"{value!r} and {meanings[meaning]!r} share {meaning}"
        meanings[meaning] = value
    assert {m.removeprefix("MODAL:") for m in meanings} == set(MODAL_TERMS)


def test_a_dotted_value_names_its_parent_in_is_a():
    values = _values()
    for value, spec in values.items():
        parent = (spec or {}).get("is_a")
        if "." in value:
            assert parent == value.rsplit(".", 1)[0], f"{value!r} is_a {parent!r}"
        else:
            assert parent is None, f"top-level {value!r} has is_a {parent!r}"


def test_the_hierarchy_walks_to_a_top_level_term():
    assert schema_vocab.value_ancestors("data_modality", "epigenomic.dna_binding.histone_modification") == (
        "epigenomic.dna_binding",
        "epigenomic",
    )
    for value in _values():
        schema_vocab.value_ancestors("data_modality", value)


def test_the_retired_terms_are_gone():
    # bulk / single-cell is an assay fact, and histology is MODAL's microscopy (#563)
    for retired in ("transcriptomic.bulk", "transcriptomic.single_cell", "imaging.histology"):
        assert retired not in _values()
