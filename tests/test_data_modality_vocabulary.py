"""Hold ``data_modality_enum`` to AnVIL's recommended vocabulary (#563).

AnVIL's Findability Subset recommends the Broad's MODAL ontology for its
``data_modality`` field. The enum spells each MODAL term as a dotted path, names its
parent in ``is_a`` and its MODAL id in ``meaning``. These tests pin each value to its
MODAL id and each dotted path to its ``is_a`` chain, so a term cannot be added,
dropped, re-parented or given another term's id without a test failing.
"""

from meta_disco import schema_vocab

# Each value and the MODAL term it spells (github.com/broadinstitute/modal,
# DataModality.ttl). MODAL's root, "data modality" (0000001), is the enum itself.
MODAL_IDS = {
    "epigenomic": "0000002",
    "epigenomic.3d_contact_maps": "0000003",  # 3D contact maps
    "epigenomic.dna_binding": "0000004",  # DNA binding
    "epigenomic.dna_binding.histone_modification": "0000005",  # histone modification location
    "epigenomic.dna_binding.transcription_factor": "0000006",  # transcription factor location
    "epigenomic.chromatin_accessibility": "0000007",  # DNA chromatin accessibility
    "epigenomic.methylation": "0000008",  # DNA methylation
    "epigenomic.rna_binding": "0000009",  # RNA binding
    "genomic": "0000010",
    "genomic.assembly": "0000011",
    "genomic.exome": "0000012",
    "genomic.genotyping": "0000013",
    "genomic.whole_genome": "0000014",
    "imaging": "0000015",
    "imaging.electrophysiology": "0000016",
    "imaging.medical_imaging": "0000017",
    "imaging.medical_imaging.ct_scan": "0000018",
    "imaging.medical_imaging.electrocardiogram": "0000019",
    "imaging.medical_imaging.mri": "0000020",
    "imaging.medical_imaging.x_ray": "0000021",
    "imaging.microscopy": "0000022",
    "metabolomic": "0000023",
    "microbiome": "0000024",
    "proteomic": "0000025",
    "transcriptomic": "0000026",
    "transcriptomic.spatial": "0000027",  # spatial transcriptomics
    "transcriptomic.nontargeted": "0000028",  # transcriptomic nontargeted
    "transcriptomic.targeted": "0000029",  # transcriptomic targeted
}


def test_each_value_is_the_modal_term_it_spells():
    values = schema_vocab.dimension_values("data_modality")
    assert {v: schema_vocab.value_meaning("data_modality", v) for v in values} == {
        v: f"MODAL:{i}" for v, i in MODAL_IDS.items()
    }


def test_a_dotted_value_sits_under_the_path_it_spells():
    for value in schema_vocab.dimension_values("data_modality"):
        ancestors = schema_vocab.value_ancestors("data_modality", value)
        parts = value.split(".")
        assert ancestors == tuple(".".join(parts[:i]) for i in range(len(parts) - 1, 0, -1)), value
