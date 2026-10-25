from __future__ import annotations

import re
import sys
from datetime import (
    date,
    datetime,
    time
)
from decimal import Decimal
from enum import Enum
from typing import (
    Any,
    ClassVar,
    Literal,
    Optional,
    Union
)

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer
)


metamodel_version = "1.11.0"
version = "None"


class ConfiguredBaseModel(BaseModel):
    model_config = ConfigDict(
        serialize_by_alias = True,
        validate_by_name = True,
        validate_assignment = True,
        validate_default = True,
        extra = "forbid",
        arbitrary_types_allowed = True,
        use_enum_values = True,
        strict = False,
    )





class LinkMLMeta(RootModel):
    root: dict[str, Any] = {}
    model_config = ConfigDict(frozen=True)

    def __getattr__(self, key:str):
        return getattr(self.root, key)

    def __getitem__(self, key:str):
        return self.root[key]

    def __setitem__(self, key:str, value):
        self.root[key] = value

    def __contains__(self, key:str) -> bool:
        return key in self.root


linkml_meta = LinkMLMeta({'default_prefix': 'anvil',
     'default_range': 'string',
     'description': 'Full classification data model for meta-disco: the eight '
                    'metadata dimensions, per-field evidence, classification '
                    'status, and typed derivation edges. Supersedes the retired '
                    'anvil_file.yaml stub (issue #33) and realizes the data-model '
                    'decision record in docs/derived-file-data-model.md.\n'
                    'Authoring source of truth. `make gen` generates JSON Schema '
                    'and Pydantic from this file (via `gen-json-schema` / '
                    '`gen-pydantic`) — do not hand-edit the generated copies. The '
                    "schema's vocabulary backs the rule drift check "
                    '(tests/test_rule_vocabulary.py), and `ClassificationRecord` '
                    'now matches the pipeline output shape (`{..., '
                    '"classifications": {...}}`, see '
                    'docs/derived-file-data-model.md section 5a) so whole records '
                    'validate against it (schema/tests/test_output_validation.py, '
                    'run closed=False, so any unmodeled key is tolerated; in '
                    "practice the pipeline's only such extras are the fastq scalar "
                    'hints inside `classifications` — modeling them is a #134 '
                    'follow-up). Adopting typed records in the pipeline is done: '
                    '`run()` parses each routed record into a typed view at the '
                    'load boundary (`src/meta_disco/records.py`, #172).',
     'id': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
     'imports': ['linkml:types'],
     'name': 'meta_disco_classification',
     'prefixes': {'EDAM': {'prefix_prefix': 'EDAM',
                           'prefix_reference': 'http://edamontology.org/'},
                  'EFO': {'prefix_prefix': 'EFO',
                          'prefix_reference': 'http://www.ebi.ac.uk/efo/EFO_'},
                  'HANCESTRO': {'prefix_prefix': 'HANCESTRO',
                                'prefix_reference': 'http://purl.obolibrary.org/obo/HANCESTRO_'},
                  'MODAL': {'prefix_prefix': 'MODAL',
                            'prefix_reference': 'https://datamodel.terra.bio/BioCoreTerms#'},
                  'NCBITaxon': {'prefix_prefix': 'NCBITaxon',
                                'prefix_reference': 'http://purl.obolibrary.org/obo/NCBITaxon_'},
                  'OBI': {'prefix_prefix': 'OBI',
                          'prefix_reference': 'http://purl.obolibrary.org/obo/OBI_'},
                  'PATO': {'prefix_prefix': 'PATO',
                           'prefix_reference': 'http://purl.obolibrary.org/obo/PATO_'},
                  'SO': {'prefix_prefix': 'SO',
                         'prefix_reference': 'http://purl.obolibrary.org/obo/SO_'},
                  'TerraCore': {'prefix_prefix': 'TerraCore',
                                'prefix_reference': 'https://datamodel.terra.bio/TerraCore#'},
                  'anvil': {'prefix_prefix': 'anvil',
                            'prefix_reference': 'https://github.com/DataBiosphere/meta-disco/schema/'},
                  'insdc.gca': {'prefix_prefix': 'insdc.gca',
                                'prefix_reference': 'https://identifiers.org/insdc.gca:'},
                  'linkml': {'prefix_prefix': 'linkml',
                             'prefix_reference': 'https://w3id.org/linkml/'}},
     'source_file': '../src/meta_disco/schema/classification.yaml',
     'title': 'Meta-Disco File Classification Model'} )

class DataModalityEnum(str, Enum):
    """
    The biological signal a file carries: "the biological nature of the information gathered as the result of an Activity, independent of the technology or methods used to produce the information", in the words of AnVIL's Findability Subset (FSS), whose recommended values for its `data_modality` field are the Broad's MODAL ontology (github.com/broadinstitute/modal) term for term (#563). This enum is that tree: each value spells its MODAL term as a dotted path, `is_a` names its parent, and `meaning` is its MODAL id. `title` is FSS's wording, MODAL's label with its first letter capitalised ("DNA methylation" for `epigenomic.methylation`, #755). Single-cell versus bulk is not a modality here, since it is a property of the experiment, so `assay_type` records it (`sc/snRNA-seq`, `snRNA-seq`, #533). A record holds one term, the most specific its evidence supports, which may be a parent: nothing emits a `genomic` child yet, so a WGS library is `genomic`. A consumer that filters on a parent walks `is_a`.
    """
    Genomic = "genomic"
    Assembly = "genomic.assembly"
    Exome = "genomic.exome"
    Genotyping = "genomic.genotyping"
    Whole_genome = "genomic.whole_genome"
    Transcriptomic = "transcriptomic"
    Spatial_transcriptomics = "transcriptomic.spatial"
    Transcriptomic_nontargeted = "transcriptomic.nontargeted"
    Transcriptomic_targeted = "transcriptomic.targeted"
    Epigenomic = "epigenomic"
    number_3D_contact_maps = "epigenomic.3d_contact_maps"
    DNA_binding = "epigenomic.dna_binding"
    Histone_modification_location = "epigenomic.dna_binding.histone_modification"
    Transcription_factor_location = "epigenomic.dna_binding.transcription_factor"
    DNA_chromatin_accessibility = "epigenomic.chromatin_accessibility"
    DNA_methylation = "epigenomic.methylation"
    RNA_binding = "epigenomic.rna_binding"
    Imaging = "imaging"
    Electrophysiology = "imaging.electrophysiology"
    Medical_imaging = "imaging.medical_imaging"
    CT_scan = "imaging.medical_imaging.ct_scan"
    Electrocardiogram = "imaging.medical_imaging.electrocardiogram"
    MRI = "imaging.medical_imaging.mri"
    X_ray = "imaging.medical_imaging.x_ray"
    Microscopy = "imaging.microscopy"
    Metabolomic = "metabolomic"
    Microbiome = "microbiome"
    Proteomic = "proteomic"


class DataTypeEnum(str, Enum):
    """
    Content type, spanning two classes. BIOLOGICAL: the bytes are the signal. DESCRIPTIVE: the bytes are about another file. (See data-model doc 8c.) A dotted value is a child of the value before its last dot, and `is_a` names that parent (`annotations.coverage` is an `annotations`). A record holds one term. Inference settles its claims by tier; where reconcile meets two values that nest, the deeper one is the value. A consumer that filters on a parent walks `is_a`. A variant callset's kind and origin are not terms here: they are `variant_kind` and `variant_origin` (ADR-0003, #657).
    """
    Alignments = "alignments"
    Reads = "reads"
    Sequence = "sequence"
    Assembly = "assembly"
    Reference_genome = "assembly.reference"
    Pangenome_graph = "pangenome"
    Reference_pangenome_graph = "pangenome.reference"
    Variant_calls = "variants"
    """
    Variant calls, with nothing narrower stated in this tree. The unnarrowed parent, not "unknown": the file is known to hold variants. What kind they are is `variant_kind`'s to say, from the caller that made the file (#654).
    """
    gVCF = "variants.gvcf"
    """
    One sample's calls, with a reference-confidence record covering every other position: one record per position, or a block (`END=`) per run of positions, each with a `<NON_REF>` ALT. It is the input to joint calling (#607). No `meaning`: EDAM names gVCF a format (format_4018), beside VCF, and has no data term for it. Under ADR-0003 the format is the file's, not its data type's; it is the one format term in this tree, kept until a format slot exists (#657). Its calls' origin is `variant_origin`'s. Assigned by the content rule `vcf_gvcf`.
    """
    Genotypes = "genotypes"
    Expression_matrix = "expression_matrix"
    Quantification = "quantification"
    Annotations = "annotations"
    Coverage = "annotations.coverage"
    """
    Read depth along the genome, measured from an alignment: per base or per window, raw or normalized (e.g. a mosdepth `regions.bed.gz`, or a STAR `Signal.Unique.strand+.bw`). No `meaning`: EDAM has no data term for coverage or read depth, only the process (operation_3230).
    """
    Peaks = "peaks"
    Raw_signal = "raw_signal"
    Array_signal = "array_signal"
    Images = "images"
    Index = "index"
    Checksum = "checksum"
    QC_report = "qc_report"
    """
    A quality-control report about another file, such as samtools stats, a mosdepth summary or distribution, or bcftools stats.
    """
    Log = "log"
    Interval_set = "interval_set"
    Sample_map = "sample_map"
    """
    A list naming the files processed together, one per sample: a GATK sample-name map, each row a sample name and its gVCF's path (#621). No `meaning`: EDAM has no data term for it.
    """
    Sample_table = "sample_table"
    """
    A table of the samples a set of files holds, one row per sample: a PLINK 2 `.psam` (#751). No `meaning`.
    """


class ReferenceAssemblyEnum(str, Enum):
    """
    Reference assemblies, named as NCBI names them (issue #473). A file gets the most specific term its evidence supports, and `is_a` records the terms as a hierarchy. A record carries only its own term, so a filter on a parent includes the terms below it only where the consumer walks the hierarchy (`schema_vocab.value_ancestors`); `value == "CHM13"` alone does not.
GRC assemblies are named at the major release: contig lengths are identical across patch releases, so contig lengths can never tell a patch (#399). Where a header's declared reference name does tell one, the patch stays on `ReferenceBuild.version`. `CHM13` is every CHM13 release, and is also the term for a CHM13 file whose release cannot be told. Under it are NCBI's T2T releases, and under each release the references that graft another genome's chrY onto it. NCBI names none of those hybrids, so each is spelled as the reference FASTA that files declare, extension dropped. A hybrid is its own coordinate system on chrY and its parent release everywhere else, which is why it sits under that release.
`meaning` is recorded where one term is one NCBI assembly: the three T2T releases and the two monkey assemblies (#636). The GRC terms each span their patch releases, and `CHM13` spans the T2T releases.
    """
    GRCh37 = "GRCh37"
    GRCh38 = "GRCh38"
    CHM13 = "CHM13"
    """
    Any CHM13 release, or CHM13 whose release cannot be told.
    """
    T2T_CHM13v1FULL_STOP0 = "T2T-CHM13v1.0"
    T2T_CHM13v1FULL_STOP1 = "T2T-CHM13v1.1"
    T2T_CHM13v2FULL_STOP0 = "T2T-CHM13v2.0"
    T2T_CHM13v1FULL_STOP0_with_GRCh38_chrY = "t2t-chm13.20200921.withGRCh38chrY.chrEBV.chrYKI270740v1r"
    """
    T2T-CHM13v1.0 with GRCh38's chrY grafted on.
    """
    T2T_CHM13v1FULL_STOP1_with_GRCh38_chrY = "CHM13Y_EBV_v1.1"
    """
    T2T-CHM13v1.1 with GRCh38's chrY grafted on.
    """
    T2T_CHM13v1FULL_STOP0_with_HG002_chrY = "t2t-chm13.20200921.HG002chrY.chrEBV"
    """
    T2T-CHM13v1.0 with HG002's chrY grafted on.
    """
    Mmul_10_LEFT_PARENTHESISrhesus_macaqueRIGHT_PARENTHESIS = "Mmul_10"
    """
    Rhesus macaque (Macaca mulatta). Its RefSeq pair is GCF_003339765.1, which adds only chrM.
    """
    mCalJa1FULL_STOP2FULL_STOPpatFULL_STOPX_LEFT_PARENTHESISmarmosetRIGHT_PARENTHESIS = "mCalJa1.2.pat.X"
    """
    Common marmoset (Callithrix jacchus). Its RefSeq pair is GCF_011100555.1, which drops only chrM.
    """


class ReferenceFamilyEnum(str, Enum):
    """
    The assembly families: the `reference_assembly_enum` terms with no `is_a` parent, which `ReferenceBuild.base` ranges over (#473). A release or a hybrid is a value, never a family. `tests/test_rule_vocabulary.py` holds this list to those terms.
    """
    GRCh37 = "GRCh37"
    GRCh38 = "GRCh38"
    CHM13 = "CHM13"
    Mmul_10 = "Mmul_10"
    mCalJa1FULL_STOP2FULL_STOPpatFULL_STOPX = "mCalJa1.2.pat.X"


class ReferenceNameSourceEnum(str, Enum):
    """
    Which part of a file's header a declared reference name was read from (issue #354). See ``ReferenceBuild.name_source``.
    """
    reference_field = "reference_field"
    command_line = "command_line"


class AssayTypeEnum(str, Enum):
    """
    The experimental method that produced a file's data, in terms borrowed from EFO (#533), which CELLxGENE requires for assays. `meaning` is the EFO term a value names, recorded and never followed at run time; `Histology`'s is OBI's `histological assay` as EFO imports it. The values form an `is_a` tree of EFO's terms, each under its nearest EFO ancestor among the values; `is_a` names one parent, so where EFO gives a term two, the one outside the vocabulary is left out (`snRNA-seq`'s `transcription profiling by high throughput sequencing`). The loss that matters is `SHARE-seq`'s: EFO places it under single-cell RNA sequencing and scATAC-seq, so it sits under `sc/snRNA-seq`, the first's parent here, and a filter on the `ATAC-seq` subtree does not reach it (#567). Where EFO has no term as narrow as a source, the value is our own, carries no `meaning`, and sits under the EFO term it narrows: EFO has single-cell ATAC-seq terms but none for single-nucleus, so `snATAC-seq` sits under `sc/snATAC-seq`. A record holds one term, the most specific its evidence supports; a consumer that filters on a parent walks `is_a`.
    """
    Whole_genome_sequencing = "WGS"
    """
    EFO's whole genome shotgun sequencing: EFO has no term labelled whole genome sequencing, and OBI's whole genome sequencing assay is not among its imports.
    """
    Whole_exome_sequencing = "WES"
    RNA_seq = "RNA-seq"
    Single_cell_or_single_nucleus_RNA_seq = "sc/snRNA-seq"
    """
    Single-cell or single-nucleus RNA-seq, EFO's parent of both: the term for a file whose evidence says single-cell but not which.
    """
    Single_nucleus_RNA_seq = "snRNA-seq"
    SHARE_seq = "SHARE-seq"
    """
    Joint chromatin accessibility and RNA from the same nuclei.
    """
    ATAC_seq = "ATAC-seq"
    Single_cell_or_single_nucleus_ATAC_seq = "sc/snATAC-seq"
    Single_nucleus_ATAC_seq = "snATAC-seq"
    """
    Single-nucleus ATAC-seq. Our own term: EFO's children of sc/snATAC-seq are single-cell only, so no EFO term is as narrow, and it records none.
    """
    ChIP_seq = "ChIP-seq"
    Bisulfite_sequencing = "Bisulfite-seq"
    Methylation_array = "Methylation array"
    Genotyping_array = "Genotyping array"
    """
    EFO's genotyping by array: polymorphisms in DNA read on an array (an Illumina genotyping BeadChip, #603). None of EFO's parents of it (genotyping, DNA assay, assay by array) is a value here, so it names no `is_a`.
    """
    Histology = "Histology"


class PlatformEnum(str, Enum):
    Illumina = "ILLUMINA"
    PacBio = "PACBIO"
    Oxford_Nanopore = "ONT"
    MGI = "MGI"
    Element_Biosciences = "ELEMENT"
    Ultima_Genomics = "ULTIMA"


class InstrumentModelEnum(str, Enum):
    """
    Instrument models for the platforms in `platform_enum`. A sequencer's is spelled exactly as ENA/SRA's controlled `INSTRUMENT_MODEL` string (SRA.common.xsd, enasequence/schema); SRA's `unspecified` is not a model and is not here (a file whose model is unknown is `not_classified`). SRA lists no array scanner, so an array scanner's model is our own term, spelled after the vendor's product name (#603). `meaning` is the EFO term whose label names the same model, recorded where EFO has one and never followed at run time. Where EFO's nearest term is broader or narrower (its one `Illumina HiSeq X` for SRA's `HiSeq X Five` / `HiSeq X Ten`, its `ONT GridION X5` for SRA's `GridION`) no meaning is recorded.
    """
    HiSeq_X_Five = "HiSeq X Five"
    HiSeq_X_Ten = "HiSeq X Ten"
    Illumina_Genome_Analyzer = "Illumina Genome Analyzer"
    Illumina_Genome_Analyzer_II = "Illumina Genome Analyzer II"
    Illumina_Genome_Analyzer_IIx = "Illumina Genome Analyzer IIx"
    Illumina_HiScanSQ = "Illumina HiScanSQ"
    Illumina_HiSeq_1000 = "Illumina HiSeq 1000"
    Illumina_HiSeq_1500 = "Illumina HiSeq 1500"
    Illumina_HiSeq_2000 = "Illumina HiSeq 2000"
    Illumina_HiSeq_2500 = "Illumina HiSeq 2500"
    Illumina_HiSeq_3000 = "Illumina HiSeq 3000"
    Illumina_HiSeq_4000 = "Illumina HiSeq 4000"
    Illumina_HiSeq_X = "Illumina HiSeq X"
    Illumina_iSeq_100 = "Illumina iSeq 100"
    Illumina_MiSeq = "Illumina MiSeq"
    Illumina_MiniSeq = "Illumina MiniSeq"
    Illumina_NovaSeq_X = "Illumina NovaSeq X"
    Illumina_NovaSeq_X_Plus = "Illumina NovaSeq X Plus"
    Illumina_NovaSeq_6000 = "Illumina NovaSeq 6000"
    NextSeq_500 = "NextSeq 500"
    NextSeq_550 = "NextSeq 550"
    NextSeq_1000 = "NextSeq 1000"
    NextSeq_2000 = "NextSeq 2000"
    Illumina_iScan = "Illumina iScan"
    """
    Illumina's iScan System, the scanner that reads Infinium BeadChips into IDAT files. No ontology term names it (an OLS search finds none in EFO or OBI), so it records no meaning.
    """
    Onso = "Onso"
    PacBio_RS = "PacBio RS"
    PacBio_RS_II = "PacBio RS II"
    Revio = "Revio"
    Sequel = "Sequel"
    Sequel_II = "Sequel II"
    Sequel_IIe = "Sequel IIe"
    Vega = "Vega"
    MinION = "MinION"
    GridION = "GridION"
    PromethION = "PromethION"
    BGISEQ_50 = "BGISEQ-50"
    BGISEQ_500 = "BGISEQ-500"
    MGISEQ_2000RS = "MGISEQ-2000RS"
    DNBSEQ_T7 = "DNBSEQ-T7"
    DNBSEQ_G400 = "DNBSEQ-G400"
    DNBSEQ_G800 = "DNBSEQ-G800"
    DNBSEQ_G50 = "DNBSEQ-G50"
    DNBSEQ_G400_FAST = "DNBSEQ-G400 FAST"
    DNBSEQ_T10x4RS = "DNBSEQ-T10x4RS"
    Element_AVITI = "Element AVITI"
    AVITI_24 = "AVITI 24"
    UG_100 = "UG 100"
    UG_200 = "UG 200"


class VariantKindEnum(str, Enum):
    """
    The kinds of variant a callset holds (ADR-0003, #654), read from the caller that made it. EDAM states a callset's kind through the operation that made it, not as a data subtype, so each term records that operation as its `meaning` where EDAM has one.
    """
    Small_variants = "small"
    """
    Single-nucleotide variants and short insertions and deletions, as a small-variant caller (GATK HaplotypeCaller, DeepVariant) calls them. EDAM splits this between SNP detection (operation_0484) and indel detection (operation_0452) under Variant calling (operation_3227), whose own definition also takes in structural variants; no one EDAM term is exactly this, so none is recorded.
    """
    Structural_variants = "structural"
    """
    Structural variants (deletions, insertions, duplications, inversions, breakends, typically 50 bp or more), as a structural-variant caller (Sniffles, SVIM) calls them.
    """


class VariantOriginEnum(str, Enum):
    """
    Where a callset's variants arose (ADR-0003, #658), read from the caller that made it: Sequence Ontology's two children of variant_origin (SO:0001762).
    """
    Germline = "germline"
    """
    Variants present from the embryo on, in every cell, as a germline caller (GATK HaplotypeCaller and joint genotyping, DeepVariant, Sniffles in its default mode) calls them.
    """
    Somatic = "somatic"
    """
    Variants arisen after the embryo split, in some cells only, as a somatic caller (GATK Mutect2) calls them against a matched normal.
    """


class PhenotypicSexEnum(str, Enum):
    """
    A donor's phenotypic sex (#693), in AnVIL's values: AnVIL's published `anvil_donor.phenotypic_sex` writes `Female` and `Male`, and its data model's coding system for the slot is PATO's phenotypic sex (PATO:0001894), whose children are the `meaning`s. A value no source writes is not listed; one is added when a source does.
    """
    Female = "Female"
    Male = "Male"


class OrganismTypeEnum(str, Enum):
    """
    A donor's organism (#699), in AnVIL's values: AnVIL's published `anvil_donor.organism_type` writes `Human` and `Mouse`, and its data model suggests NCBITaxon for the slot, whose species terms are the `meaning`s. A value no source writes is not listed.
    """
    Human = "Human"
    """
    Homo sapiens
    """
    Mouse = "Mouse"
    """
    Mus musculus
    """


class ReportedEthnicityEnum(str, Enum):
    """
    A donor's reported ethnicity (#699), in AnVIL's values, which are the US census's categories. AnVIL's data model suggests HANCESTRO, but HANCESTRO has no term for these categories (its nearest, `European American`, `African American` and `Hispanic or Latin`, are narrower), so no value has a `meaning`. A value no source writes is not listed.
    """
    Black_or_African_American = "Black or African American"
    Hispanic_or_Latino = "Hispanic or Latino"
    White = "White"


class BiosampleTypeEnum(str, Enum):
    """
    What kind of material a sample is (#699), in AnVIL's values for `anvil_biosample.biosample_type`. AnVIL's `Unknown` is no value. A value no authored translation row reads is not listed: AnVIL's `Blood` is on three Coriell samples, whose record is the cell line (#706), and its `Tissue, Unknown` on IGVF's pools (#705).
    """
    Tissue = "Tissue"


class GeneticAncestryEnum(str, Enum):
    """
    A donor's genetic ancestry (#693), as AnVIL's data model suggests: HANCESTRO terms. The values are 1000 Genomes' population codes, as its tables and the datasets built on it write them, each under its superpopulation by `is_a` as HANCESTRO places it; `meaning` is the HANCESTRO term and `description` its label (HANCESTRO 2025-10-14). `title` is that label without the code or "(1KGP)" ("British in England and Scotland", "African"), and for `GWD` without " - Mandinka (GGVP)", the Gambian Genome Variation Project's part of its label (#755). A record holds the most specific term its evidence supports (`GBR` beside `EUR` is `GBR`), as the assay tree does; a consumer that filters on a superpopulation walks `is_a`. Other populations (SGDP's, #559; HPRC_R2's `ASL`, which HANCESTRO has no term for) are not values yet, and their names wait in the review queue.
    """
    African = "AFR"
    """
    African (AFR) reference superpopulation (1KGP)
    """
    American = "AMR"
    """
    American (AMR) reference superpopulation (1KGP)
    """
    East_Asian = "EAS"
    """
    East Asian (EAS) reference superpopulation (1KGP)
    """
    European = "EUR"
    """
    European (EUR) reference superpopulation (1KGP)
    """
    South_Asian = "SAS"
    """
    South Asian (SAS) reference superpopulation (1KGP)
    """
    African_Caribbean_in_Barbados = "ACB"
    """
    African Caribbean in Barbados (1KGP)
    """
    African_Ancestry_in_Southwest_US = "ASW"
    """
    African Ancestry in Southwest US (1KGP)
    """
    Bengali_in_Bangladesh = "BEB"
    """
    Bengali in Bangladesh (1KGP)
    """
    Chinese_Dai_in_Xishuangbanna_China = "CDX"
    """
    Chinese Dai in Xishuangbanna, China (1KGP)
    """
    Utah_residents_LEFT_PARENTHESISCEPHRIGHT_PARENTHESIS_with_Northern_and_Western_European_ancestry = "CEU"
    """
    Utah residents (CEPH) with Northern and Western European ancestry (1KGP)
    """
    Han_Chinese_in_Beijing_China = "CHB"
    """
    Han Chinese in Beijing, China (1KGP)
    """
    Han_Chinese_South = "CHS"
    """
    Han Chinese South (1KGP)
    """
    Colombian_in_Medellin_Colombia = "CLM"
    """
    Colombian in Medellin, Colombia (1KGP)
    """
    Esan_in_Nigeria = "ESN"
    """
    Esan in Nigeria (1KGP)
    """
    Finnish_in_Finland = "FIN"
    """
    Finnish in Finland (1KGP)
    """
    British_in_England_and_Scotland = "GBR"
    """
    British in England and Scotland (1KGP)
    """
    Gujarati_Indians_in_Houston_TX = "GIH"
    """
    Gujarati Indians in Houston, TX (1KGP)
    """
    Gambian_in_Western_Division_The_Gambia = "GWD"
    """
    Gambian in Western Division, The Gambia - Mandinka (GGVP). HANCESTRO's term for 1000 Genomes' GWD is the Gambian Genome Variation Project's, whose samples 1000 Genomes sequenced; its synonym is `GWD` and its parent the AFR superpopulation
    """
    Iberian_populations_in_Spain = "IBS"
    """
    Iberian populations in Spain (1KGP)
    """
    Indian_Telugu_in_the_UK = "ITU"
    """
    Indian Telugu in the UK (1KGP)
    """
    Japanese_in_Tokyo_Japan = "JPT"
    """
    Japanese in Tokyo, Japan (1KGP)
    """
    Kinh_in_Ho_Chi_Minh_City_Vietnam = "KHV"
    """
    Kinh in Ho Chi Minh City, Vietnam (1KGP)
    """
    Luhya_in_Webuye_Kenya = "LWK"
    """
    Luhya in Webuye, Kenya (1KGP)
    """
    Mende_in_Sierra_Leone = "MSL"
    """
    Mende in Sierra Leone (1KGP)
    """
    Mexican_Ancestry_in_Los_Angeles_California = "MXL"
    """
    Mexican Ancestry in Los Angeles, California (1KGP)
    """
    Peruvian_in_Lima_Peru = "PEL"
    """
    Peruvian in Lima, Peru (1KGP)
    """
    Punjabi_in_Lahore_Pakistan = "PJL"
    """
    Punjabi in Lahore, Pakistan (1KGP)
    """
    Puerto_Rican_in_Puerto_Rico = "PUR"
    """
    Puerto Rican in Puerto Rico (1KGP)
    """
    Sri_Lankan_Tamil_in_the_UK = "STU"
    """
    Sri Lankan Tamil in the UK (1KGP)
    """
    Toscani_in_Italy = "TSI"
    """
    Toscani in Italy (1KGP)
    """
    Yoruba_in_Ibadan_Nigeria = "YRI"
    """
    Yoruba in Ibadan, Nigeria (1KGP)
    """


class EntityKindEnum(str, Enum):
    """
    What an identifier names (#693): a sample, the material a file's data was read from, or a donor, the person or animal it was collected from. An identifier rule declares which (`IdentifierRule.names`).
    """
    sample = "sample"
    """
    A sample, as a file's `samples` names it.
    """
    donor = "donor"
    """
    A donor, as a `DonorRecord` is keyed.
    """


class ClassificationStatusEnum(str, Enum):
    """
    Why a field has (or lacks) a value. Replaces sentinel values that were previously smuggled into each dimension enum (not_applicable / not_classified). See issues #56, #88.
    """
    classified = "classified"
    """
    A value was determined.
    """
    not_applicable = "not_applicable"
    """
    The field has no meaning for this file.
    """
    not_classified = "not_classified"
    """
    The field is meaningful but no value could be determined.
    """
    conflict = "conflict"
    """
    Declarations disagreed and no curator rule has answered it (claims contract 4.3-4.7). On an inference record, rules at the same tier disagreed (#88), and the competing claims stay in the evidence beside a `conflict` marker naming them. On a reconciled record (#432), inputs declared different answers (inference and a source, or sources among themselves), or inference's own conflict stands, or the published source spoke with a value no authored row reads while another input declared an answer. The value is null either way.
    """


class UseEnum(str, Enum):
    """
    Which value the indexer takes for a reconciled slot (#432): this record's, or the one the repository already publishes (the not-worse path, until curator rules answer conflicts).
    """
    meta_disco = "meta_disco"
    """
    Take this record's value; its status is `classified` or `not_applicable`.
    """
    published = "published"
    """
    Keep the repository's published value; the status is `conflict` or `not_classified`.
    """


class CreditedToEnum(str, Enum):
    """
    Where a reconciled slot's answer is credited (#552): the reconcile report's slot categories, one per slot, so a dimension's counts sum to its files. Held to `reconcile.SLOT_CATEGORIES` by tests/test_reconcile.py.
    """
    filled_by_published = "filled_by_published"
    """
    The published source declared the value, verbatim.
    """
    filled_by_published_harmonized = "filled_by_published_harmonized"
    """
    The published source declared the value through a translation row.
    """
    filled_by_submitter = "filled_by_submitter"
    """
    A submitter table declared the value, verbatim.
    """
    filled_by_submitter_harmonized = "filled_by_submitter_harmonized"
    """
    A submitter table declared the value through a translation row.
    """
    filled_by_external = "filled_by_external"
    """
    An external catalog declared the value, verbatim.
    """
    filled_by_external_harmonized = "filled_by_external_harmonized"
    """
    An external catalog declared the value through a translation row.
    """
    filled_by_inference = "filled_by_inference"
    """
    No source declared the value; inference supplied it.
    """
    inherited = "inherited"
    """
    No source declared the value and inference did not either: it was inherited from the file's parents across its `generated_by` (contract 4.9, #571), whose record keys the inherited claim names.
    """
    conflict_inference = "conflict_inference"
    """
    Inference's own rules disagreed.
    """
    conflict_sources = "conflict_sources"
    """
    A conflict inference's rules did not cause, on a slot where the published source neither declared a value nor gave an unreviewed one.
    """
    conflict_published = "conflict_published"
    """
    A conflict on a slot where the published source declared a value or gave an unreviewed one — whichever inputs disagreed; the published value need not be the disputed one.
    """
    published_unreviewed = "published_unreviewed"
    """
    The published source gave a value no authored row reads, and no input answered.
    """
    not_applicable = "not_applicable"
    """
    The slot settled `not_applicable`.
    """
    not_classified = "not_classified"
    """
    The slot settled `not_classified`.
    """


class ActivityTypeEnum(str, Enum):
    """
    The kind of step that made a file (ADR-0002, #580): AnVIL FSS's `ActivityTypes` as its released LinkML schema spells them, plus ten of our own, each under the term it narrows. `meaning` is TerraCore's class, else EDAM's operation for the same step; a near EDAM operation is a close mapping. What each passes is in `rules/activities.yaml`.
    """
    Activity = "Activity"
    """
    A step whose kind the source does not state; nothing passes across it.
    """
    SampleCollectionActivity = "SampleCollectionActivity"
    """
    Taking a sample. Neither TerraCore nor EDAM has this class, so no id is recorded.
    """
    SampleTreatmentActivity = "SampleTreatmentActivity"
    SequenceActivity = "SequenceActivity"
    """
    Sequencing a sample into reads. TerraCore names the same class `SequencingActivity`.
    """
    AlignmentActivity = "AlignmentActivity"
    VariantCallActivity = "VariantCallActivity"
    """
    Calling variants or genotypes from alignments; a joint genotyping of gVCFs is JointGenotypingActivity. EDAM's Variant calling is a close step.
    """
    JointGenotypingActivity = "JointGenotypingActivity"
    """
    Genotyping many samples at once from the calls their gVCFs hold, gathered in one store: GATK's GenotypeGVCFs reading a GenomicsDB workspace or a CombineGVCFs file. It calls no variant the gVCFs did not hold, so the calls keep the kind and origin their caller gave them (#678). Our own term; TerraCore has no such class, and EDAM's Genotyping is a close step.
    """
    ExpressionActivity = "ExpressionActivity"
    """
    Quantifying expression. EDAM's RNA-Seq quantification is one kind of it, not the same step.
    """
    AnalysisActivity = "AnalysisActivity"
    ImageActivity = "ImageActivity"
    """
    Making an image. Neither TerraCore nor EDAM has this class, so no id is recorded.
    """
    IndexActivity = "IndexActivity"
    ChecksumActivity = "ChecksumActivity"
    """
    Computing a file's checksum. EDAM's only checksum operation is a molecular sequence's (operation_3348), not a file's, so no id is recorded.
    """
    QualityControlActivity = "QualityControlActivity"
    """
    A report on another file's content: samtools stats, mosdepth coverage. Our own term, under FSS's AnalysisActivity, which is too broad to say what passes.
    """
    CoverageActivity = "CoverageActivity"
    """
    The read coverage of one alignment file at each position, as a signal track: ENCORE's per-strand STAR signal bigWigs (#595). Our own term, under FSS's AnalysisActivity; it is not a report on the file, so not QualityControlActivity. EDAM's Read depth analysis analyses depth rather than writing it, so it is close.
    """
    LiftoverActivity = "LiftoverActivity"
    """
    Moving a file's coordinates to another reference. Our own term; TerraCore has no such class, and EDAM's Sequence coordinate conversion is the same step.
    """
    VariantProcessingActivity = "VariantProcessingActivity"
    """
    Variants in, variants out, every call kept made from the same reads against the same reference: filtering, annotating, normalizing or subsetting a callset (a subset drops samples). Our own term, under FSS's AnalysisActivity; a record names one of its children (#610). Neither TerraCore nor EDAM has this class, so no id is recorded.
    """
    VariantFilterActivity = "VariantFilterActivity"
    """
    Labelling a callset's rows by a filter (GATK's ApplyVQSR) or keeping only those that pass (`bcftools view -f PASS`). Our own term; TerraCore has no such class, and EDAM's Variant filtering is the same step.
    """
    MergeActivity = "MergeActivity"
    """
    Joining several files of one kind into one: window VCFs into a chromosome VCF, FASTQs into one. Our own term; EDAM's Sequence merging (operation_0232) merges sequences, not files.
    """
    CohortMergeActivity = "CohortMergeActivity"
    """
    Joining the files a cohort's list names into one, the list the step's input rather than each file: a GenomicsDB workspace built from the gVCFs of a GATK sample-name map (#621). Our own term; neither TerraCore nor EDAM has this class, so no id is recorded.
    """
    CohortDefinitionActivity = "CohortDefinitionActivity"
    """
    Listing the files that are processed together: a GATK sample-name map naming the gVCFs one GenomicsDB import joint-calls (#621). A processing cohort, who was computed together, not a research cohort a user builds. Our own term; neither TerraCore nor EDAM has this class, so no id is recorded.
    """
    AssemblyActivity = "AssemblyActivity"
    """
    Assembling reads into sequences. Not an FSS term; EDAM's Sequence assembly is the same step.
    """


class ActivityFormEnum(str, Enum):
    """
    Whether an activity's input or output is a file we hold or an identifier (#580).
    """
    file = "file"
    identifier = "identifier"
    """
    A sample or donor identifier (ADR-0002 decision 1), which has no record.
    """


class PassedDimensionEnum(str, Enum):
    """
    The dimensions an activity's output can take from an input (#580): the eight classification dimensions but `data_type`, which names a file's own kind and never passes (ADR-0002 decision 8: a VCF is not an alignment).
    """
    data_modality = "data_modality"
    platform = "platform"
    reference_assembly = "reference_assembly"
    assay_type = "assay_type"
    instrument_model = "instrument_model"
    variant_kind = "variant_kind"
    variant_origin = "variant_origin"


class ParentKindEnum(str, Enum):
    """
    The kind of file a derivation edge points at.
    """
    alignment = "alignment"
    variants = "variants"
    reads = "reads"
    sequence = "sequence"
    intervals = "intervals"
    signal = "signal"
    expression_matrix = "expression_matrix"
    genotypes = "genotypes"
    any = "any"


class SourceTypeEnum(str, Enum):
    """
    Kind of source behind a claim (provenance model, #90). Every claim carries one (#392). Distinct from `tier`, which is the resolution input: two kinds share `CONTENT_TIER`.
    """
    filename_rule = "filename_rule"
    """
    A rule matching on the file name or its extension (tiers 1-2 of unified_rules.yaml). The extension is part of the name, so both tiers are this kind.
    """
    header_rule = "header_rule"
    """
    A rule matching on fetched header content (tier 3 of unified_rules.yaml).
    """
    contig_detection = "contig_detection"
    """
    Read from the contig or sequence declarations in the file's own bytes — SAM ``@SQ``, VCF ``##contig``, FASTA sequence names, GFA ``SN`` segment tags, BED contig names and coordinates.
    """
    content_read = "content_read"
    """
    Read from the file's bytes, but not from contig declarations — today the member names in an archive head. Separate from `contig_detection` so neither has to describe the other.
    """
    derivation_inheritance = "derivation_inheritance"
    """
    Inherited from a related file rather than determined for this one, as an index file inherits its parent's classification.
    """
    external_ground_truth = "external_ground_truth"
    """
    An external catalog or authority published outside AnVIL, e.g. the HPRC Data Explorer.
    """
    repository_metadata = "repository_metadata"
    """
    A table the submitter wrote, carried by the repository — an AnVIL verbatim manifest's submitter table.
    """
    repository_activity = "repository_activity"
    """
    The repository's own record of a step — AnVIL's `anvil_activity` table, whose columns are FSS's and the same in every dataset (#583), or the typed `anvil_sequencingactivity` where a dataset's transform wrote that instead (#698): which files and samples a step used, which files it generated, and what the source calls the step. It says how a file was made, not what a file is, so it is written only as lineage evidence (`LineageRow`), never as slot evidence; at reconcile, the samples a step used are a source of the file's samples (#698).
    """
    published_value = "published_value"
    """
    The value the repository's own system of record publishes for the file (#497) — AnVIL's harmonized `anvil_file` columns, today read as the verbatim manifest copies that TDR table (claims contract 7.12). Distinct from `repository_metadata` so a reader of a conflict can tell the repository's official value from a submitter's opinion.
    """
    wrangler_annotation = "wrangler_annotation"
    """
    A human curator's decision, recorded deliberately rather than inferred.
    """
    identifier_rule = "identifier_rule"
    """
    One of our identifier rules (`rules/sample_namespaces.yaml`), from the identifier alone (#693): a rule naming a sample and a donor with one string says the sample was collected from the donor with the same identifier.
    """


class ImporterSourceTypeEnum(str, Enum):
    """
    The kinds of source an importer may write, and so the kinds an evidence file's envelope may declare (#421). A strict subset of `source_type_enum`, excluding two groups for two reasons.
The inference kinds, because a file declaring `filename_rule` would be naming our own rule engine as its publisher.
And `wrangler_annotation`, because a curator does not reach us as evidence. The claims contract 1.6 puts it plainly — a curator "is unlike every other in how it enters: as rules, not as evidence" — and 1.7 makes a decision about a single file a rule whose selection matches one file. Accepting one here would let the curator table (#397) be built as an importer against a format that takes it and a resolution stage with nowhere to put it.
Listed rather than derived because LinkML has no enum-subset construct that `gen-json-schema` honours; `test_the_external_source_types_are_a_subset` pins the two so a value can be added to one and not lost from the other. The values carry no description of their own for the same reason the pin exists: `source_type_enum` defines these terms, and a second copy of that prose could drift from it without any test noticing.
    """
    external_ground_truth = "external_ground_truth"
    """
    As in `source_type_enum`.
    """
    repository_metadata = "repository_metadata"
    """
    As in `source_type_enum`.
    """
    repository_activity = "repository_activity"
    """
    As in `source_type_enum`.
    """
    published_value = "published_value"
    """
    As in `source_type_enum`.
    """


class ClaimStateEnum(str, Enum):
    """
    Why a claim that consulted a source produced no vocabulary value (issue #392). The first three (`unmapped`, `no_vocabulary_term`, `declined`) were observed in the spike over three real producers on `AnVIL_HPRC_R2`; none of them declares a value, so none competes in resolution. `mixed` was added for inheritance (contract 4.9, #571): an inherited claim's only, and reconcile weighs it. `mapped` is not a member: a claim that mapped carries a `value`, and `not_applicable` / `not_classified` remain statuses, unchanged.
    """
    unmapped = "unmapped"
    """
    The source said something and no map entry covers it, e.g. `library_selection=RANDOM`. The review queue: a mapping may be owed.
    """
    no_vocabulary_term = "no_vocabulary_term"
    """
    The raw value was mapped deliberately to nothing because the vocabulary has no term for it, e.g. `Hi-C`, `CenSat`. A recorded decision, not a gap in the mapping.
    """
    declined = "declined"
    """
    This column is not an authority on this dimension, so no claim is made from it whatever it says. A property of the (source, column, dimension) triple, not of a value: `alignments_v2.location` points at pangenome graphs and at a VCF of variants under one column, so neither a value-level mapping nor a finer key can fix it.
    """
    mixed = "mixed"
    """
    An inherited claim only (contract 4.9, #571): the parents in one input role gave different answers, or one of them is itself mixed. It is the one state that takes part in resolution: alone it leaves the slot `not_classified`, and against a value or `not_applicable` from any other declaration it is a conflict.
    """


class JoinKeyEnum(str, Enum):
    """
    A key by which a claim is attached to a row in the target system (issue #392, extended in #401). One vocabulary in two positions: an evidence file's envelope declares which of these it is keyed by (`EvidenceFileEnvelope. target_key`), and a claim records which one actually attached it (`Evidence.join_key`) once the join has run.
These are keys of the *target*, not names a source publishes. A source keyed by an ENA run accession adds no term here: its importer maps that accession to one of these and writes the value in the target's space, which is what keeps corpus knowledge in the importer and transform logic out of the join.
Measured on the AnVIL corpus, 708,088 records. The keys differ enormously in how far they can be trusted, which is why the one used is recorded per claim (#390).
    """
    file_id = "file_id"
    """
    The target's own file identifier. Present on every AnVIL record and unique on every record — with `drs_uri`, a key that needs no scope, and the durable one across a re-index (#433).
    """
    entry_id = "entry_id"
    """
    The target's entry identifier, Azul's per-index document id. Present and unique on every record of the compact-derived corpus, where `(file_md5sum, entry_id)` and `(file_name, entry_id)` are each unique corpus-wide — but absent from a corpus derived from a TDR snapshot's tables (#499), where a target keyed on it joins nothing.
    """
    drs_uri = "drs_uri"
    """
    DRS URI. Present and unique on every record of the AnVIL corpus.
    """
    file_path = "file_path"
    """
    Full path, where the target publishes one.
    """
    file_md5sum = "file_md5sum"
    """
    Content checksum. Present on every record and non-unique on 1.72% of them (12,203 rows): 8,119 of those collide inside a single dataset and 4,084 across datasets, so a dataset scope narrows the ambiguity without removing it. Note that a record whose md5 was synthesized from its URL rather than its content can never match one carrying a real checksum.
    """
    file_name = "file_name"
    """
    Bare file name, and often the only key a catalog publishes. The weakest: present on every record but non-unique on 69.4%. Collisions are wildly per-dataset — 2 rows in 16,271 within `AnVIL_HPRC_R2`, against 99.3% within `ANVIL_1000G_PRIMED_data_model` — so it is usable only with a dataset scope, which is what `EvidenceTarget.dataset` is for.
    """
    entity_identifier = "entity_identifier"
    """
    A donor's or sample's identifier as the source wrote it (`HG00096`), the key of an entity evidence file (`EntityEvidenceRow`, #693) and of the claims made from it. Never a file's key: a slot or lineage evidence file keyed by it is refused. Read through `rules/sample_namespaces.yaml` at reconcile, in the envelope's target dataset.
    """


class LineageParentKeyEnum(str, Enum):
    """
    What kind of value a `LineageRow`'s `parent` is (#583). A locator says where a file is; an identifier says which file or sample.
    """
    drs_uri = "drs_uri"
    """
    A locator, the DRS URI, as a submitter table's file-link column holds it.
    """
    file_id = "file_id"
    """
    AnVIL's own file identifier, as `anvil_activity`'s `used_file_id` holds it.
    """
    biosample_id = "biosample_id"
    """
    A sample's identifier, as `anvil_activity`'s `used_biosample_id` holds it. A sample is not a file; reconcile builds no input from one (#577).
    """
    external_file = "external_file"
    """
    A file held outside AnVIL for the child's dataset, by its address (`github:<owner>/<repo>@<commit>/<path>`), as `sources/external_files.yaml` declares it (#710). A workaround until AnVIL holds the file (#624). Reconcile resolves it only to a file declared for the child's dataset.
    """


class IdentifierNamespaceEnum(str, Enum):
    """
    The authority that issued a sample or donor identifier (ADR-0002 decision 1, settled by #357). Which strings each recognises is `rules/sample_namespaces.yaml`'s.
    """
    coriell = "coriell"
    """
    The Coriell Institute's repository numbers (`HG`/`NA`/`GM` and five digits), as 1000 Genomes, HPRC and T2T name their samples. `GM` (a cell line) and `NA` (DNA extracted from it) with the same number are one sample.
    """
    giab = "giab"
    """
    Genome in a Bottle's names for its reference samples, `HG001` to `HG007`; the same people under other names in `coriell` are not joined to them here (#361).
    """
    sra_sample = "sra_sample"
    """
    An SRA, ENA or DDBJ sample accession (`SRS`/`ERS`/`DRS`).
    """
    biosample = "biosample"
    """
    An NCBI, EBI or DDBJ BioSample accession (`SAMN`/`SAMEA`/`SAMD`).
    """
    igvf = "igvf"
    """
    The IGVF Data Portal's donor and sample accessions (`IGVFDO` or `IGVFSM` and eight capitals or digits, #693, #669), as AnVIL_IGVF_Mouse_R1's `donor` and `sample` tables name its mice and their samples.
    """
    dataset_local = "dataset_local"
    """
    A name one dataset gives its samples, unique only within it; recognised only by a rule declared for that dataset.
    """
    sgdp = "sgdp"
    """
    The Simons Genome Diversity Project's names for its genomes (`S_Tuscan-2`, `B_Australian-3`), its metadata file's `SGDP_ID` and T2T_CHRY's `sgdp_id` (#559).
    """
    hgdp = "hgdp"
    """
    The CEPH-HGDP panel's cell line numbers (`HGDP` and five digits), as SGDP's metadata file names the person behind a genome in `Sample_ID` (#559).
    """


class EvidenceMarkerEnum(str, Enum):
    """
    Kind of synthetic resolution marker on an evidence entry (issue #228): a note that no claim was made or that claims conflicted, rather than a claim.
    """
    not_classified = "not_classified"
    """
    No rule or content classifier determined a value.
    """
    conflict = "conflict"
    """
    Claims disagreed at the top tier, so the field is ambiguous.
    """



class ClassificationRecord(ConfiguredBaseModel):
    """
    One classified file. `classifications` carries the file's identity (the eight dimension fields — what it is); generated_by names the step that made it and the files it used (where it came from; ADR-0002). Matches the pipeline output shape.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'tree_root': True})

    md5sum: str = Field(default=..., description="""MD5 checksum of the file; primary key for records.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClassificationRecord']} })
    file_name: Optional[str] = Field(default=None, description="""The file name.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClassificationRecord', 'ExternalList', 'RebuiltList']} })
    file_format: Optional[str] = Field(default=None, description="""File extension / compound extension (e.g. .bam, .vcf.gz).""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClassificationRecord']} })
    file_size: Optional[int] = Field(default=None, description="""File size in bytes.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClassificationRecord']} })
    entry_id: Optional[str] = Field(default=None, description="""Source catalog entry identifier the record was classified from: Azul's per-index document id. Where present it is unique within a run and regenerated when the catalog is re-indexed, so it scopes a weaker key rather than outliving a refresh (#433). Null on a record whose input came from a TDR snapshot's tables rather than the compact manifest (#499), and on every HPRC record. An AnVIL record's durable identity is `file_id`; an HPRC record's is the URL hash it carries in `md5sum` (`record_keys.SOURCE_RECORD_KEYS`).""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClassificationRecord']} })
    file_id: Optional[str] = Field(default=None, description="""The repository's own file identifier, and the durable one: it survives a catalog re-index, which `entry_id` does not (#433). It is the join key, not the handle a resolver takes — that is `drs_uri`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClassificationRecord']} })
    drs_uri: Optional[str] = Field(default=None, description="""The file's DRS URI: what a resolver dereferences to reach the bytes. Carried, never derived from `file_id` — thousands of records wrap a different object id, so a reconstructed URI resolves to the wrong file or to nothing (#433).""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClassificationRecord']} })
    dataset_title: Optional[str] = Field(default=None, description="""Title of the dataset the file belongs to.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClassificationRecord']} })
    classifications: Classifications = Field(default=..., description="""The eight classified dimensions for this file.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClassificationRecord']} })
    generated_by: Optional[GeneratedBy] = Field(default=None, description="""The step that made the file and the inputs it used, by role (ADR-0002 decisions 3, 6, #580); null where no step is recorded.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClassificationRecord', 'ExternalList', 'RebuiltList']} })
    samples: Optional[SampleReference] = Field(default=None, description="""The samples the file's data comes from (#357), as a pointer to the run's sample list; null where no source names a sample, or where its sources name different ones.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClassificationRecord', 'ExternalList']} })


class Classifications(ConfiguredBaseModel):
    """
    The eight metadata dimensions for one file, each a Classification entry. The pipeline also emits some file-type-specific scalar hints here (e.g. fastq's is_paired_end / instrument_hint); those are not modeled yet and pass under the gate's closed=False mode (see #134 follow-up).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'slot_usage': {'assay_type': {'name': 'assay_type',
                                       'range': 'AssayTypeClassification',
                                       'required': True},
                        'data_modality': {'name': 'data_modality',
                                          'range': 'DataModalityClassification',
                                          'required': True},
                        'data_type': {'name': 'data_type',
                                      'range': 'DataTypeClassification',
                                      'required': True},
                        'instrument_model': {'name': 'instrument_model',
                                             'range': 'InstrumentModelClassification',
                                             'required': True},
                        'platform': {'name': 'platform',
                                     'range': 'PlatformClassification',
                                     'required': True},
                        'reference_assembly': {'name': 'reference_assembly',
                                               'range': 'ReferenceAssemblyClassification',
                                               'required': True},
                        'variant_kind': {'name': 'variant_kind',
                                         'range': 'VariantKindClassification',
                                         'required': True},
                        'variant_origin': {'name': 'variant_origin',
                                           'range': 'VariantOriginClassification',
                                           'required': True}}})

    data_modality: DataModalityClassification = Field(default=..., description="""The biological signal the file carries.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classifications']} })
    data_type: DataTypeClassification = Field(default=..., description="""The content type of the file (biological or descriptive class).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classifications']} })
    reference_assembly: ReferenceAssemblyClassification = Field(default=..., description="""The reference genome the file's coordinates are expressed against.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classifications']} })
    assay_type: AssayTypeClassification = Field(default=..., description="""The experimental assay that produced the upstream data.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classifications']} })
    platform: PlatformClassification = Field(default=..., description="""The vendor whose sequencer or array scanner read the data, for example Illumina or PacBio.""", json_schema_extra = { "linkml_meta": {'comments': ['Array scanners added under #603.'],
         'domain_of': ['Classifications']} })
    instrument_model: InstrumentModelClassification = Field(default=..., description="""The instrument model that read the data, within its platform: for example Illumina NovaSeq 6000 or Illumina iScan under Illumina. Not applicable where the platform is not applicable.""", json_schema_extra = { "linkml_meta": {'comments': ['Vocabulary from ENA/SRA instrument-model strings, with EFO ids '
                      'where EFO has the same model (#532).',
                      'Illumina iScan, an array scanner SRA does not list, added under '
                      '#603.'],
         'domain_of': ['Classifications']} })
    variant_kind: VariantKindClassification = Field(default=..., description="""The kinds of variant a callset holds, small variants or structural ones, from the caller that made it. A list, since one callset can hold both. Not applicable to a file that holds no variants.""", json_schema_extra = { "linkml_meta": {'comments': ['Its own dimension under ADR-0003 (one slot per axis), #654.'],
         'domain_of': ['Classifications']} })
    variant_origin: VariantOriginClassification = Field(default=..., description="""Whether a callset's variants are germline (carried from conception, in every cell) or somatic (arisen later, in some cells), from the caller that made it. Not applicable to a file that holds no variants.""", json_schema_extra = { "linkml_meta": {'comments': ['Its own dimension under ADR-0003 (one slot per axis), #658; '
                      "named for Sequence Ontology's variant_origin (SO:0001762), "
                      'whose two children are its values.'],
         'domain_of': ['Classifications']} })


class Classification(ConfiguredBaseModel):
    """
    A single classified field: its resolved value (null unless status is 'classified'), a status sentinel, and the evidence behind it. Subclasses narrow `value` to the right enum per dimension. A reconciled record (#432) carries the same entry plus `use`, `inferred` and `credited_to` (#552); an inference record carries none of them. A donor's or sample's slot (#693, #699) carries `use` and neither of the other two, its subclass requiring it.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'abstract': True,
         'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml'})

    value: Optional[str] = Field(default=None, description="""The resolved value; null unless status is 'classified'.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    status: ClassificationStatusEnum = Field(default=..., description="""Whether the field was classified, is not applicable, etc.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    evidence: Optional[list[Evidence]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    use: Optional[UseEnum] = Field(default=None, description="""On a reconciled record only (#432), a file's or a donor's or sample's (#699): whether the indexer takes this record's value (`meta_disco`, when the status is `classified` or `not_applicable`) or keeps what the repository publishes (`published`, when it is `conflict` or `not_classified`). Computed by reconcile so an export is structure only.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    inferred: Optional[InferredConclusion] = Field(default=None, description="""On a reconciled record only (#432): what inference concluded for this slot.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    credited_to: Optional[CreditedToEnum] = Field(default=None, description="""On a reconciled record only (#552): where this slot's answer is credited, the per-slot category the reconcile report counts. The rule is `reconcile.credited_to`'s. It attributes and never decides: the value was settled before it is read.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })


class InferredConclusion(ConfiguredBaseModel):
    """
    What inference concluded for a slot before reconciliation (#432): its tier-resolved status and value, as the inference record states them. On a reconciled record so it reads alone (contract 6.10) — inference's evidence cannot rebuild it without re-running tier resolution. Subclasses narrow `value` to the dimension's enum, as the Classification subclasses do.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'abstract': True,
         'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml'})

    value: Optional[str] = Field(default=None, description="""The resolved value; null unless status is 'classified'.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    status: ClassificationStatusEnum = Field(default=..., description="""Whether the field was classified, is not applicable, etc.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })


class DataModalityInferred(InferredConclusion):
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'slot_usage': {'value': {'name': 'value', 'range': 'data_modality_enum'}}})

    value: Optional[DataModalityEnum] = Field(default=None, description="""The resolved value; null unless status is 'classified'.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    status: ClassificationStatusEnum = Field(default=..., description="""Whether the field was classified, is not applicable, etc.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })


class DataTypeInferred(InferredConclusion):
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'slot_usage': {'value': {'name': 'value', 'range': 'data_type_enum'}}})

    value: Optional[DataTypeEnum] = Field(default=None, description="""The resolved value; null unless status is 'classified'.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    status: ClassificationStatusEnum = Field(default=..., description="""Whether the field was classified, is not applicable, etc.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })


class ReferenceAssemblyInferred(InferredConclusion):
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'slot_usage': {'value': {'name': 'value', 'range': 'reference_assembly_enum'}}})

    value: Optional[ReferenceAssemblyEnum] = Field(default=None, description="""The resolved value; null unless status is 'classified'.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    status: ClassificationStatusEnum = Field(default=..., description="""Whether the field was classified, is not applicable, etc.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })


class AssayTypeInferred(InferredConclusion):
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'slot_usage': {'value': {'name': 'value', 'range': 'assay_type_enum'}}})

    value: Optional[AssayTypeEnum] = Field(default=None, description="""The resolved value; null unless status is 'classified'.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    status: ClassificationStatusEnum = Field(default=..., description="""Whether the field was classified, is not applicable, etc.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })


class PlatformInferred(InferredConclusion):
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'slot_usage': {'value': {'name': 'value', 'range': 'platform_enum'}}})

    value: Optional[PlatformEnum] = Field(default=None, description="""The resolved value; null unless status is 'classified'.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    status: ClassificationStatusEnum = Field(default=..., description="""Whether the field was classified, is not applicable, etc.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })


class InstrumentModelInferred(InferredConclusion):
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'slot_usage': {'value': {'name': 'value', 'range': 'instrument_model_enum'}}})

    value: Optional[InstrumentModelEnum] = Field(default=None, description="""The resolved value; null unless status is 'classified'.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    status: ClassificationStatusEnum = Field(default=..., description="""Whether the field was classified, is not applicable, etc.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })


class VariantKindInferred(InferredConclusion):
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'slot_usage': {'value': {'multivalued': True,
                                  'name': 'value',
                                  'range': 'variant_kind_enum'}}})

    value: Optional[list[VariantKindEnum]] = Field(default=None, description="""The resolved value; null unless status is 'classified'.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    status: ClassificationStatusEnum = Field(default=..., description="""Whether the field was classified, is not applicable, etc.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })


class VariantOriginInferred(InferredConclusion):
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'slot_usage': {'value': {'name': 'value', 'range': 'variant_origin_enum'}}})

    value: Optional[VariantOriginEnum] = Field(default=None, description="""The resolved value; null unless status is 'classified'.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    status: ClassificationStatusEnum = Field(default=..., description="""Whether the field was classified, is not applicable, etc.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })


class DataModalityClassification(Classification):
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'slot_usage': {'inferred': {'name': 'inferred',
                                     'range': 'DataModalityInferred'},
                        'value': {'name': 'value', 'range': 'data_modality_enum'}}})

    value: Optional[DataModalityEnum] = Field(default=None, description="""The resolved value; null unless status is 'classified'.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    status: ClassificationStatusEnum = Field(default=..., description="""Whether the field was classified, is not applicable, etc.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    evidence: Optional[list[Evidence]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    use: Optional[UseEnum] = Field(default=None, description="""On a reconciled record only (#432), a file's or a donor's or sample's (#699): whether the indexer takes this record's value (`meta_disco`, when the status is `classified` or `not_applicable`) or keeps what the repository publishes (`published`, when it is `conflict` or `not_classified`). Computed by reconcile so an export is structure only.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    inferred: Optional[DataModalityInferred] = Field(default=None, description="""On a reconciled record only (#432): what inference concluded for this slot.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    credited_to: Optional[CreditedToEnum] = Field(default=None, description="""On a reconciled record only (#552): where this slot's answer is credited, the per-slot category the reconcile report counts. The rule is `reconcile.credited_to`'s. It attributes and never decides: the value was settled before it is read.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })


class DataTypeClassification(Classification):
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'slot_usage': {'inferred': {'name': 'inferred', 'range': 'DataTypeInferred'},
                        'value': {'name': 'value', 'range': 'data_type_enum'}}})

    value: Optional[DataTypeEnum] = Field(default=None, description="""The resolved value; null unless status is 'classified'.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    status: ClassificationStatusEnum = Field(default=..., description="""Whether the field was classified, is not applicable, etc.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    evidence: Optional[list[Evidence]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    use: Optional[UseEnum] = Field(default=None, description="""On a reconciled record only (#432), a file's or a donor's or sample's (#699): whether the indexer takes this record's value (`meta_disco`, when the status is `classified` or `not_applicable`) or keeps what the repository publishes (`published`, when it is `conflict` or `not_classified`). Computed by reconcile so an export is structure only.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    inferred: Optional[DataTypeInferred] = Field(default=None, description="""On a reconciled record only (#432): what inference concluded for this slot.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    credited_to: Optional[CreditedToEnum] = Field(default=None, description="""On a reconciled record only (#552): where this slot's answer is credited, the per-slot category the reconcile report counts. The rule is `reconcile.credited_to`'s. It attributes and never decides: the value was settled before it is read.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })


class ReferenceAssemblyClassification(Classification):
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'slot_usage': {'inferred': {'name': 'inferred',
                                     'range': 'ReferenceAssemblyInferred'},
                        'value': {'name': 'value', 'range': 'reference_assembly_enum'}}})

    build: Optional[ReferenceBuild] = Field(default=None, description="""The specific reference build behind this dimension's coarse value. Named ``build`` rather than ``reference`` because ``Evidence.reference`` already means a provenance pointer. ReferenceBuild's own fields are class-local attributes, so they add nothing to the global slot namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ReferenceAssemblyClassification']} })
    value: Optional[ReferenceAssemblyEnum] = Field(default=None, description="""The resolved value; null unless status is 'classified'.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    status: ClassificationStatusEnum = Field(default=..., description="""Whether the field was classified, is not applicable, etc.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    evidence: Optional[list[Evidence]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    use: Optional[UseEnum] = Field(default=None, description="""On a reconciled record only (#432), a file's or a donor's or sample's (#699): whether the indexer takes this record's value (`meta_disco`, when the status is `classified` or `not_applicable`) or keeps what the repository publishes (`published`, when it is `conflict` or `not_classified`). Computed by reconcile so an export is structure only.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    inferred: Optional[ReferenceAssemblyInferred] = Field(default=None, description="""On a reconciled record only (#432): what inference concluded for this slot.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    credited_to: Optional[CreditedToEnum] = Field(default=None, description="""On a reconciled record only (#552): where this slot's answer is credited, the per-slot category the reconcile report counts. The rule is `reconcile.credited_to`'s. It attributes and never decides: the value was settled before it is read.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })


class AssayTypeClassification(Classification):
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'slot_usage': {'inferred': {'name': 'inferred', 'range': 'AssayTypeInferred'},
                        'value': {'name': 'value', 'range': 'assay_type_enum'}}})

    value: Optional[AssayTypeEnum] = Field(default=None, description="""The resolved value; null unless status is 'classified'.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    status: ClassificationStatusEnum = Field(default=..., description="""Whether the field was classified, is not applicable, etc.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    evidence: Optional[list[Evidence]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    use: Optional[UseEnum] = Field(default=None, description="""On a reconciled record only (#432), a file's or a donor's or sample's (#699): whether the indexer takes this record's value (`meta_disco`, when the status is `classified` or `not_applicable`) or keeps what the repository publishes (`published`, when it is `conflict` or `not_classified`). Computed by reconcile so an export is structure only.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    inferred: Optional[AssayTypeInferred] = Field(default=None, description="""On a reconciled record only (#432): what inference concluded for this slot.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    credited_to: Optional[CreditedToEnum] = Field(default=None, description="""On a reconciled record only (#552): where this slot's answer is credited, the per-slot category the reconcile report counts. The rule is `reconcile.credited_to`'s. It attributes and never decides: the value was settled before it is read.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })


class PlatformClassification(Classification):
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'slot_usage': {'inferred': {'name': 'inferred', 'range': 'PlatformInferred'},
                        'value': {'name': 'value', 'range': 'platform_enum'}}})

    value: Optional[PlatformEnum] = Field(default=None, description="""The resolved value; null unless status is 'classified'.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    status: ClassificationStatusEnum = Field(default=..., description="""Whether the field was classified, is not applicable, etc.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    evidence: Optional[list[Evidence]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    use: Optional[UseEnum] = Field(default=None, description="""On a reconciled record only (#432), a file's or a donor's or sample's (#699): whether the indexer takes this record's value (`meta_disco`, when the status is `classified` or `not_applicable`) or keeps what the repository publishes (`published`, when it is `conflict` or `not_classified`). Computed by reconcile so an export is structure only.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    inferred: Optional[PlatformInferred] = Field(default=None, description="""On a reconciled record only (#432): what inference concluded for this slot.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    credited_to: Optional[CreditedToEnum] = Field(default=None, description="""On a reconciled record only (#552): where this slot's answer is credited, the per-slot category the reconcile report counts. The rule is `reconcile.credited_to`'s. It attributes and never decides: the value was settled before it is read.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })


class InstrumentModelClassification(Classification):
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'slot_usage': {'inferred': {'name': 'inferred',
                                     'range': 'InstrumentModelInferred'},
                        'value': {'name': 'value', 'range': 'instrument_model_enum'}}})

    value: Optional[InstrumentModelEnum] = Field(default=None, description="""The resolved value; null unless status is 'classified'.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    status: ClassificationStatusEnum = Field(default=..., description="""Whether the field was classified, is not applicable, etc.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    evidence: Optional[list[Evidence]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    use: Optional[UseEnum] = Field(default=None, description="""On a reconciled record only (#432), a file's or a donor's or sample's (#699): whether the indexer takes this record's value (`meta_disco`, when the status is `classified` or `not_applicable`) or keeps what the repository publishes (`published`, when it is `conflict` or `not_classified`). Computed by reconcile so an export is structure only.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    inferred: Optional[InstrumentModelInferred] = Field(default=None, description="""On a reconciled record only (#432): what inference concluded for this slot.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    credited_to: Optional[CreditedToEnum] = Field(default=None, description="""On a reconciled record only (#552): where this slot's answer is credited, the per-slot category the reconcile report counts. The rule is `reconcile.credited_to`'s. It attributes and never decides: the value was settled before it is read.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })


class VariantKindClassification(Classification):
    """
    The one dimension whose value is a list (ADR-0003): a callset can hold small variants and structural ones at once, and a list names both without a combined term. Each claim in `evidence` declares one kind, a string; the list is the settled value.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'slot_usage': {'inferred': {'name': 'inferred',
                                     'range': 'VariantKindInferred'},
                        'value': {'multivalued': True,
                                  'name': 'value',
                                  'range': 'variant_kind_enum'}}})

    value: Optional[list[VariantKindEnum]] = Field(default=None, description="""The resolved value; null unless status is 'classified'.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    status: ClassificationStatusEnum = Field(default=..., description="""Whether the field was classified, is not applicable, etc.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    evidence: Optional[list[Evidence]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    use: Optional[UseEnum] = Field(default=None, description="""On a reconciled record only (#432), a file's or a donor's or sample's (#699): whether the indexer takes this record's value (`meta_disco`, when the status is `classified` or `not_applicable`) or keeps what the repository publishes (`published`, when it is `conflict` or `not_classified`). Computed by reconcile so an export is structure only.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    inferred: Optional[VariantKindInferred] = Field(default=None, description="""On a reconciled record only (#432): what inference concluded for this slot.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    credited_to: Optional[CreditedToEnum] = Field(default=None, description="""On a reconciled record only (#552): where this slot's answer is credited, the per-slot category the reconcile report counts. The rule is `reconcile.credited_to`'s. It attributes and never decides: the value was settled before it is read.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })


class VariantOriginClassification(Classification):
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'slot_usage': {'inferred': {'name': 'inferred',
                                     'range': 'VariantOriginInferred'},
                        'value': {'name': 'value', 'range': 'variant_origin_enum'}}})

    value: Optional[VariantOriginEnum] = Field(default=None, description="""The resolved value; null unless status is 'classified'.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    status: ClassificationStatusEnum = Field(default=..., description="""Whether the field was classified, is not applicable, etc.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    evidence: Optional[list[Evidence]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    use: Optional[UseEnum] = Field(default=None, description="""On a reconciled record only (#432), a file's or a donor's or sample's (#699): whether the indexer takes this record's value (`meta_disco`, when the status is `classified` or `not_applicable`) or keeps what the repository publishes (`published`, when it is `conflict` or `not_classified`). Computed by reconcile so an export is structure only.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    inferred: Optional[VariantOriginInferred] = Field(default=None, description="""On a reconciled record only (#432): what inference concluded for this slot.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    credited_to: Optional[CreditedToEnum] = Field(default=None, description="""On a reconciled record only (#552): where this slot's answer is credited, the per-slot category the reconcile report counts. The rule is `reconcile.credited_to`'s. It attributes and never decides: the value was settled before it is read.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })


class ReferenceBuild(ConfiguredBaseModel):
    """
    The specific reference build a file was aligned to (issue #340): the observations a header offers about its reference, and the build they identify, if any. Where the header's contig lengths detect a family, the build resolves inside it, and the build has a term of its own (the CHM13 releases and hybrids), that term is the value of ``reference_assembly`` (issue #473); the patch within a GRC release, which the vocabulary does not name, stays here.
    ``chr1_m5``, ``chry_m5``, ``name`` and ``name_source`` are OBSERVED, read from the file's own header. ``base`` and ``version`` are DERIVED by matching those observations against a table of known builds. ``version`` is null unless the evidence identifies exactly one build; ``base`` is filled whenever every candidate agrees on the family, which is often true when the version is not. An ambiguous file keeps its observations rather than being assigned a nearest match.
    Not a claim itself: it carries no tier and never competes in claim resolution. It sets the value only through the contig-detection claim, which takes the build's term in place of the family's. Absent entirely when nothing was observed.
    Declared as class-local ``attributes`` rather than global ``slots``: ``name``, ``base`` and ``version`` are the kind of identifier that collides across a shared namespace, and nothing outside this class needs them.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml'})

    base: Optional[ReferenceFamilyEnum] = Field(default=None, description="""Assembly family of the resolved build (``CHM13``, ``GRCh38``), derived by the resolver from exact signatures. Where both are known it is the value or an ancestor of it, since a contradicting one is dropped (#345); recorded here so a build is readable on its own; null when no single family was identified. Range-constrained to the families rather than merely documented as such, so a table entry naming a release, a hybrid or anything outside the vocabulary fails validation instead of passing.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ReferenceBuild']} })
    version: Optional[str] = Field(default=None, description="""Build version within the family. Free text by necessity: T2T releases (``v1.0``, ``v1.1``, ``v2.0``) and GRC patches (``p12``) are not the same kind of thing, and CHM13 has no patch concept. Where a build grafts a chromosome from elsewhere the origin is part of the version (``v1.0+GRCh38chrY``), because that is a real difference in the reference. Null unless the evidence identifies exactly one build.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ReferenceBuild', 'EvidenceTarget']} })
    chr1_m5: Optional[str] = Field(default=None, description="""MD5 of the chr1 sequence, from SAM ``@SQ M5``. Identifies the sequence, not the packaging: two references with different decoy or alt content share this value when their chr1 is the same. Null for VCF, whose ``##contig`` md5 attribute is optional in the specification and unpopulated in practice.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ReferenceBuild']} })
    chry_m5: Optional[str] = Field(default=None, description="""MD5 of the chrY sequence, from SAM ``@SQ M5``. Recorded because chr1 alone cannot separate some builds — CHM13 v2.0 is v1.1 plus a chrY, so their autosomes are identical. One build can appear with more than one value here at identical chrY length; the header cannot say why, so both are recorded as observations and neither is preferred.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ReferenceBuild']} })
    name: Optional[str] = Field(default=None, description="""Reference filename as the file declares it, from SAM ``@SQ UR`` or VCF ``##reference`` when present, else from a program command line in the header (``@PG CL``, ``##GATKCommandLine``; issue #354) — ``name_source`` says which. An observation about the file, not a statement about the reference's content: one name can denote references that differ, and differently-named references can be identical.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ReferenceBuild', 'ClaimSource']} })
    name_source: Optional[ReferenceNameSourceEnum] = Field(default=None, description="""Where ``name`` was read from. ``reference_field`` is the field that exists to carry it; ``command_line`` is the command line of the program that produced the file, one step further from the file, and taken only when the header declares contigs, every command line that names a reference names the same one, and (for VCF) the file carries no liftover INFO fields. Null when ``name`` is null.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ReferenceBuild']} })


class ClaimSource(ConfiguredBaseModel):
    """
    Identity of a source that produced a claim, for a source that is not one of our rules (issue #392): an external catalog, a submitter manifest, a curator table. Names the source, the table or file within it, and the column the raw value was read from — the granularity at which a mapping is reviewed and at which a column can be `declined` as an authority for a dimension.
    A claim from one of our own rules carries `rule_id` and no source object. An external claim carries this *and* a `rule_id`, which names the mapping entry that turned the raw value into one of ours — an identity mapping included, since a source value that happens to spell a vocabulary term is a coincidence of spelling rather than an agreement about meaning. The one external claim with no rule is `unmapped`, which means exactly that no entry exists for the raw value (#401).
    Declared as class-local ``attributes`` rather than global ``slots``: ``name``, ``url``, ``dataset``, ``table`` and ``column`` are words too generic to own in a shared namespace, and nothing outside this class needs them. Evidence files (#401) carry all of these but ``column`` once per file in their envelope, and put ``column`` on each claim — one shape, factored, not a second one.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml'})

    name: str = Field(default=..., description="""Name of the source, e.g. ``AnVIL`` or ``HPRC Data Explorer``. Required: a source object with no name identifies nothing, and ``to_dict`` omits null members, so an unnamed source would serialize as a bare url or column with no owner.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ReferenceBuild', 'ClaimSource']} })
    url: Optional[str] = Field(default=None, description="""URL the source was read from, if it has one. Null for a source with no published address, such as a curator table held in this repository.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClaimSource', 'EvidenceFileSource']} })
    dataset: Optional[str] = Field(default=None, description="""The collection within the source that the claim came from — an AnVIL dataset title, an HPRC release, an ENA study accession. Null for a source with no such level.
Carried on the claim and not only on the evidence file's envelope because it is what makes `column` legible: the same column name means different things in different datasets, and a consumer reading this evidence cannot go back to the file the claim arrived in (#401).""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClaimSource',
                       'EvidenceFileSource',
                       'EvidenceTarget',
                       'ExternalList',
                       'RebuiltList',
                       'EntityIdentifier',
                       'IdentifierRule',
                       'RepositoryIdentifier']} })
    table: Optional[str] = Field(default=None, description="""The table or file within the source that the claim came from, e.g. an AnVIL verbatim manifest table name. Null when the source is a single undivided file.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClaimSource', 'EvidenceFileSource', 'RepositoryIdentifier']} })
    column: Optional[str] = Field(default=None, description="""The column within that table the raw value was read from. Null when the source has no column structure.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClaimSource', 'EvidenceRow', 'EntityEvidenceRow']} })

    @field_validator('name')
    def pattern_name(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid name format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid name format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('url')
    def pattern_url(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid url format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid url format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('dataset')
    def pattern_dataset(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid dataset format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid dataset format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('table')
    def pattern_table(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid table format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid table format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('column')
    def pattern_column(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid column format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid column format: {v}"
            raise ValueError(err_msg)
        return v


class EvidenceFileSource(ConfiguredBaseModel):
    """
    Where a whole evidence file's claims were read from (issue #401) — the `source` on a `EvidenceFileEnvelope`.
    Three levels, because a source is not flat: a repository publishes datasets, and a dataset has tables. The AnVIL manifests are `AnVIL / AnVIL_HPRC_R2 / alignments_v2`; the HPRC Data Explorer is `HPRC Data Explorer / R2 / sequencing-data`; ENA is `ENA / <study accession> / read_run`, where `read_run` is literally the `result=` parameter its API takes and the fields it returns are the columns. A source with no middle level leaves `dataset` null, as `table` may be null.
    Distinct from `ClaimSource` rather than reusing it. A row's source carries a `column`, which belongs to the row because one table's rows are read from several columns; a file's source carries a `dataset`, which belongs to the file because every row in it came from the same one. Modeling them as one class would let an envelope name a column that could disagree with every line in the file.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml'})

    repository: str = Field(default=..., description="""What publishes the source — `AnVIL`, `HPRC Data Explorer`, `ENA`. Required and non-empty: a source that names no repository identifies nothing.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidenceFileSource', 'RepositoryIdentifier']} })
    dataset: Optional[str] = Field(default=None, description="""The collection within that repository the claims were read from. Null for a source with no such level.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClaimSource',
                       'EvidenceFileSource',
                       'EvidenceTarget',
                       'ExternalList',
                       'RebuiltList',
                       'EntityIdentifier',
                       'IdentifierRule',
                       'RepositoryIdentifier']} })
    table: Optional[str] = Field(default=None, description="""The table or file within the dataset — `alignments_v2`, `sequencing-data`, ENA's `read_run`. Null for a source with no table structure. The column within it stays on each claim.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClaimSource', 'EvidenceFileSource', 'RepositoryIdentifier']} })
    url: Optional[str] = Field(default=None, description="""Where the source was read from, if it has a public address. Null for a source with none, such as a curator table held in this repository.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClaimSource', 'EvidenceFileSource']} })

    @field_validator('repository')
    def pattern_repository(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid repository format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid repository format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('dataset')
    def pattern_dataset(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid dataset format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid dataset format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('table')
    def pattern_table(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid table format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid table format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('url')
    def pattern_url(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid url format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid url format: {v}"
            raise ValueError(err_msg)
        return v


class EvidenceTarget(ConfiguredBaseModel):
    """
    The system an evidence file's claims are *about* (issue #401) — the `target` on a `EvidenceFileEnvelope`.
    An evidence file says \"the row in this system whose this key is that value\". The target names the system, so an importer is not implicitly bound to AnVIL and the file records which system it resolved its keys against.
    The mapping from the source's own names to these is the importer's knowledge: the source calls its collection `R2`, the target calls the same thing `AnVIL_HPRC_R2`. The importer records both sides and the run performs equality lookup only.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml'})

    system: str = Field(default=..., description="""The system the claims are about — `anvil` today. Required: a claim with no target is about nothing.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidenceTarget']} })
    dataset: Optional[str] = Field(default=None, description="""The scope the join runs within, in the *target's* name for it. Not decoration: keyed by `file_name` alone, 69% of the AnVIL corpus's 708,088 rows carry a non-unique key, and 20% remain non-unique scoped by dataset title alone — but within `AnVIL_HPRC_R2` the collision rate is 2 rows in 16,271. A filename join is unusable without a dataset scope and reliable with one.
Null for a source whose key is unique across the whole target (`file_id`, `entry_id`, `drs_uri`), where a corpus-wide match is correct.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClaimSource',
                       'EvidenceFileSource',
                       'EvidenceTarget',
                       'ExternalList',
                       'RebuiltList',
                       'EntityIdentifier',
                       'IdentifierRule',
                       'RepositoryIdentifier']} })
    version: Optional[str] = Field(default=None, description="""Which generation of the target the importer resolved against — an AnVIL catalog such as `anvil15`. Null when the importer did not resolve against a particular generation, which is the ordinary case for a source that publishes names and values rather than reading our catalog.
Inference reports it and refuses nothing on it. The reconcile stage (#432) uses it as a gate: where the run's input envelope names a catalog, it reads only the files whose version equals that catalog, and leaves the rest (an older generation's history, or a null version) unread. Nothing offline establishes which generation is current beyond that — AnVIL deletes a superseded catalog rather than keeping it to be compared against.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ReferenceBuild', 'EvidenceTarget']} })

    @field_validator('system')
    def pattern_system(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid system format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid system format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('dataset')
    def pattern_dataset(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid dataset format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid dataset format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('version')
    def pattern_version(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid version format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid version format: {v}"
            raise ValueError(err_msg)
        return v


class EvidenceRow(ConfiguredBaseModel):
    """
    One line of an evidence file after the envelope (#401, amended by #421): an observation, not an answer. It reads \"about the row in the envelope's `target` whose `target_key` equals `target_key_value`, the source wrote `raw_value` for `field`\".
    **It declares nothing.** No `value`, no `status`, no `claim_state`, no `rule_id` and no `tier` — an importer maps structure and the rule engine maps meaning (contract 1.1, 1.3). The claim that reconcile eventually makes from this row is an `Evidence`, which is the class that carries those; this one is what the source said before anyone interpreted it. Validated `closed`, like the envelope, and `source_evidence._entry_from_line` refuses each retired member by name, so a producer written against #401's format is told what to write instead rather than having the member silently dropped.
    **Where this gate is weaker than the reader.** `column` is optional, LinkML models an optional slot as nullable (`gen-json-schema` emits `type: [string, null]`), so `{\"column\": null}` is valid here by construction — and `_entry_from_line` refuses it, because the writer omits a member it does not have and a written-out null is a line this writer could not have produced. The envelope, read through the model generated from this schema, accepts such a null as the absent member it means (#494); a row is read by hand, on the hot path, and keeps the stricter rule.
    The reader is deliberately the stricter of the two, which is the safe direction: a producer that validates here and writes explicit nulls is refused at read, rather than publishing a file we would later read as though the member were absent. Accepting it would be exactly the silent normalization every other member refuses. `test_a_line_whose_column_is_an_explicit_null_is_refused` pins it.
    Deliberately outside the `ClassificationRecord` tree and referenced by no slot in it, for the reason `EvidenceFileEnvelope` is: it describes an artefact exchanged *between* runs. Modeled here so that a producer can validate a whole evidence file — both its line kinds — against the schema rather than against the reader alone.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'slot_usage': {'raw_value': {'description': 'What the source wrote, verbatim '
                                                     '(contract 1.4) — not casefolded, '
                                                     'trimmed, corrected or '
                                                     'suppressed. The same slot an '
                                                     '`Evidence` claim carries beside '
                                                     'its mapped value; on a row it is '
                                                     'the whole content, because a row '
                                                     'maps nothing.\n'
                                                     'No pattern and no enum, '
                                                     "deliberately: a source's "
                                                     'spellings are its own, a value '
                                                     'our vocabulary has no word for '
                                                     "is the review queue's input "
                                                     'rather than an error (contract '
                                                     '3.7), and an empty cell is '
                                                     'something the source published, '
                                                     "whose meaning is a rule's to "
                                                     'decide.',
                                      'name': 'raw_value',
                                      'required': True}}})

    raw_value: str = Field(default=..., description="""What the source wrote, verbatim (contract 1.4) — not casefolded, trimmed, corrected or suppressed. The same slot an `Evidence` claim carries beside its mapped value; on a row it is the whole content, because a row maps nothing.
No pattern and no enum, deliberately: a source's spellings are its own, a value our vocabulary has no word for is the review queue's input rather than an error (contract 3.7), and an empty cell is something the source published, whose meaning is a rule's to decide.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidenceRow', 'EntityEvidenceRow', 'Evidence']} })
    field: str = Field(default=..., description="""The slot this row speaks to, spelled `field` on the wire and in the code (contract 2.1). One of the eight classification dimensions, or `samples` (#357): which sample a submitter table says the file's data comes from, read through `rules/sample_namespaces.yaml` and never the value map.
Pinned by pattern rather than by an enum because the dimension names are slot *names* in this schema and not a vocabulary it declares; `test_the_row_field_pattern_lists_every_dimension` holds it to `models.EVIDENCE_FIELDS`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidenceRow', 'EntityEvidenceRow']} })
    target_key_value: str = Field(default=..., description="""The value to match against the envelope's `target_key`, already in the target's value space — the importer owns the mapping between its own key and the target's. Empty is refused: a row with nothing to match on can attach to no file.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidenceRow', 'LineageRow', 'EntityEvidenceRow']} })
    column: Optional[str] = Field(default=None, description="""The column the raw value was read from. The one member of the source that varies within a file — repository, dataset, table and url are on the envelope — and absent for a source whose table has no columns to name.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClaimSource', 'EvidenceRow', 'EntityEvidenceRow']} })

    @field_validator('field')
    def pattern_field(cls, v):
        pattern=re.compile(r"^(data_modality|data_type|platform|reference_assembly|assay_type|instrument_model|variant_kind|variant_origin|samples)\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid field format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid field format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('target_key_value')
    def pattern_target_key_value(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid target_key_value format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid target_key_value format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('column')
    def pattern_column(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid column format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid column format: {v}"
            raise ValueError(err_msg)
        return v


class LineageRow(ConfiguredBaseModel):
    """
    One line of a lineage evidence file after the envelope (#583): a source saying one file was made from one parent. It reads \"the row in the envelope's `target` whose `target_key` equals `target_key_value` was made from `parent`, a `parent_key_type`\". The envelope is an `EvidenceFileEnvelope`, as a slot evidence file's is; the lines differ, so the two are written under separate roots, and the readers of each root read only that root.
    **It declares nothing**, as an `EvidenceRow` declares nothing: no activity, no role, no value, no status, no rule id. `raw_activity` is what the source calls the step, verbatim; which activity and role that means is the activity translation table's (#584), and finding the parent among our files is reconcile's (#577).
    One line per (child, parent) pair: a source row naming two parents, or two generated files, is written as one line for each pair.
    **At least one of `parent` and `parent_source_identifier`.** A parent named by a locator, by AnVIL's identifier or by a sample's identifier is written as `parent`. One named by the source's own identifier is written as the locator the source's own table gives it, with the identifier kept as `parent_source_identifier`; when that table has no row for it, or rows naming several locators, the line carries the identifier alone, so the link is still reported. `parent_key_type` is present exactly when `parent` is, `raw_activity_column` exactly when `raw_activity` is, and `parent_dataset` only with `parent` and never the envelope's own target dataset. gen-pydantic emits no class rules, so `lineage_evidence` enforces them at write and at read (`check_row`, and `_check_row_in` for the one that needs the envelope).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml'})

    target_key_value: str = Field(default=..., description="""The child, as the envelope's `target_key` names it: AnVIL's `file_id` for `anvil_activity`, the DRS URI for a submitter table.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidenceRow', 'LineageRow', 'EntityEvidenceRow']} })
    parent: Optional[str] = Field(default=None, description="""The parent, in the form `parent_key_type` names. Written whether or not it is one of the dataset's files: reconcile (#577) will report a parent outside the dataset, and dropping it here would hide it.""", json_schema_extra = { "linkml_meta": {'domain_of': ['LineageRow']} })
    parent_key_type: Optional[LineageParentKeyEnum] = Field(default=None, description="""Which kind of value `parent` is. Named `_type` because `ActivityInput.parent_key` is a value, the parent's record key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['LineageRow']} })
    parent_source_identifier: Optional[str] = Field(default=None, description="""The source's own identifier for the parent, where the source named the parent by one (IGVF's `derived_from` accessions, or the ENA run whose reads a T2T_CHRY CRAM holds), kept beside the locator the importer found for it.""", json_schema_extra = { "linkml_meta": {'domain_of': ['LineageRow']} })
    parent_dataset: Optional[str] = Field(default=None, description="""The dataset the parent is in, where it is not the child's own (#594). Absent on every line whose parent is looked for in the child's dataset. Written only by the ENA run lineage importer (`ena_lineage`), for a pair of datasets its map declares (`sources/ena_run_lineage_map.yaml`); reconcile resolves a line carrying it only where that map declares the child's dataset taking its reads from this one, and counts any other as `undeclared_dataset`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['LineageRow', 'ActivityInput']} })
    raw_activity: Optional[str] = Field(default=None, description="""What the source calls the step, verbatim (contract 1.4), where the source names it — `anvil_activity`'s `activity_type`, e.g. `Indexing` or `Quantificatioin: salmon`. The empty string is kept; a null or empty-list cell is omitted. No pattern and no enum, for `EvidenceRow.raw_value`'s reason.""", json_schema_extra = { "linkml_meta": {'domain_of': ['LineageRow']} })
    activity_id: Optional[str] = Field(default=None, description="""The source's id for the step, where it has one (`anvil_activity`'s `activity_id`, `anvil_sequencingactivity`'s `sequencingactivity_id`), so lines from one step can be told apart from another's.""", json_schema_extra = { "linkml_meta": {'domain_of': ['LineageRow', 'Attribution']} })
    child_column: str = Field(default=..., description="""The column the child was read from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['LineageRow']} })
    parent_column: str = Field(default=..., description="""The column the parent (or its source identifier) was read from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['LineageRow']} })
    raw_activity_column: Optional[str] = Field(default=None, description="""The column `raw_activity` was read from; present exactly when it is.""", json_schema_extra = { "linkml_meta": {'domain_of': ['LineageRow']} })

    @field_validator('target_key_value')
    def pattern_target_key_value(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid target_key_value format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid target_key_value format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('parent')
    def pattern_parent(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid parent format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid parent format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('parent_source_identifier')
    def pattern_parent_source_identifier(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid parent_source_identifier format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid parent_source_identifier format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('parent_dataset')
    def pattern_parent_dataset(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid parent_dataset format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid parent_dataset format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('activity_id')
    def pattern_activity_id(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid activity_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid activity_id format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('child_column')
    def pattern_child_column(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid child_column format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid child_column format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('parent_column')
    def pattern_parent_column(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid parent_column format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid parent_column format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('raw_activity_column')
    def pattern_raw_activity_column(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid raw_activity_column format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid raw_activity_column format: {v}"
            raise ValueError(err_msg)
        return v


class EntityEvidenceRow(ConfiguredBaseModel):
    """
    One line of an entity evidence file after the envelope (#693): a source saying, about one donor, what it wrote for one of the donor's slots, or, about one donor or sample, the repository's own identifier for it (#669). It reads \"about the donor (or sample) the source names `target_key_value` (read from `identifier_column`), the source wrote `raw_value` in `column`\". The envelope is an `EvidenceFileEnvelope` keyed by `entity_identifier`; the lines are written under their own root, `data/entity_evidence/`, because every reader of `data/source_evidence/` takes each file there as a file's slot lines.
    **It declares nothing**, as an `EvidenceRow` declares nothing: the identifier is the string as written, recognised through `rules/sample_namespaces.yaml` at reconcile, and the value is the value map's to translate. `entity_evidence` refuses an answer on a line by name.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'slot_usage': {'raw_value': {'description': 'What the source wrote, verbatim, '
                                                     'as on an `EvidenceRow`.',
                                      'name': 'raw_value',
                                      'required': True}}})

    raw_value: str = Field(default=..., description="""What the source wrote, verbatim, as on an `EvidenceRow`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidenceRow', 'EntityEvidenceRow', 'Evidence']} })
    field: str = Field(default=..., description="""The donor slot this line speaks to (a `mother`, `father` or `family_id` line's `raw_value` read as written at reconcile, never translated, #582), a sample's slot (`biosample_type`, `anatomical_site`, #699; the line is then about the sample the source names), or `donor_repository_id` / `sample_repository_id` where `raw_value` is the repository's own identifier for the donor or sample (#669), which reconcile lists on the record and never translates. `collected_from` (about a sample) and `same_donor_as` (about a donor) name another identifier in `raw_value`, which reconcile recognises as a donor (#559): the donor the sample was collected from, and another identifier for the donor, followed to the end of the chain to the main identifier, under which the others are kept as synonyms. Pinned to `models.DONOR_FIELDS`, `models.FAMILY_FIELDS`, `models.SAMPLE_SLOTS`, `models.REPOSITORY_ID_FIELDS` and `models.IDENTITY_LINK_FIELDS` by `test_the_entity_row_field_pattern_lists_every_entity_field`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidenceRow', 'EntityEvidenceRow']} })
    target_key_value: str = Field(default=..., description="""The identifier the source wrote for the donor, or for the sample on a sample's slot, `sample_repository_id` or `collected_from` line, verbatim.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidenceRow', 'LineageRow', 'EntityEvidenceRow']} })
    column: str = Field(default=..., description="""The column `raw_value` was read from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClaimSource', 'EvidenceRow', 'EntityEvidenceRow']} })
    identifier_column: str = Field(default=..., description="""The column `target_key_value` was read from.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EntityEvidenceRow']} })
    identifier_table: Optional[str] = Field(default=None, description="""The table `target_key_value` was read from, where it is not the envelope's: AnVIL's published `anvil_donor` and `anvil_biosample` name their donor or sample only through the submitter row each was made from (`source_datarepo_row_ids`), so their lines take the identifier from that row's table.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EntityEvidenceRow']} })

    @field_validator('field')
    def pattern_field(cls, v):
        pattern=re.compile(r"^(phenotypic_sex|genetic_ancestry|organism_type|reported_ethnicity|mother|father|family_id|biosample_type|anatomical_site|donor_repository_id|sample_repository_id|collected_from|same_donor_as)\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid field format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid field format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('target_key_value')
    def pattern_target_key_value(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid target_key_value format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid target_key_value format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('column')
    def pattern_column(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid column format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid column format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('identifier_column')
    def pattern_identifier_column(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid identifier_column format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid identifier_column format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('identifier_table')
    def pattern_identifier_table(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid identifier_table format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid identifier_table format: {v}"
            raise ValueError(err_msg)
        return v


class EvidenceFileEnvelope(ConfiguredBaseModel):
    """
    What an evidence file records once, for every row in it (issue #401, amended by #421). An importer runs out of band from classification — when a catalog refreshes, with network — and writes an evidence file of `EvidenceRow`s; a run reads it and reports this provenance, so that what a run found, and how old it was, is on the record. Inference reads each file's envelope and none of its rows; the reconcile stage (#432) reads the rows and joins them to the run's records.
    It names both sides of the join, symmetrically: `source` / `source_version` / `source_key`, and `target` / `target.version` / `target_key`. A line then reads \"this row is about the row in `target` whose `target_key` equals its `target_key_value`; about that row's `field`, the source wrote its `raw_value`.\"
    **The reader is this class.** `source_evidence` reads line 1 through the pydantic model gen-pydantic emits from this schema (#494), so what this gate refuses and what the reader refuses are one definition rather than two kept in step. An explicit null on an optional member, such as `source: {repository: HPRC, table: null}`, is valid here — LinkML models an optional slot as nullable — and the reader accepts it as the absent member it means, though the writer never emits one. The one known divergence is a calendar-invalid `fetched_at` (see that slot).
    The key *names* are here rather than on each line because they do not change within a file — every claim an importer writes is keyed the same way — so repeating them on a few million lines would be this block written out again. Only the key value varies, so only that is on the line. It is the same factoring that keeps a source's repository, url and table here while `column` stays on each claim.
    Deliberately outside the `ClassificationRecord` tree, and referenced by no slot in it: an envelope describes an artefact exchanged *between* runs and never appears in a classified record. It is modeled here so that the file a claim arrives in is defined where the claim itself is, rather than in an importer. On disk the file is NDJSON — this envelope wrapped in a `evidence_file` key on line 1, one row per line after it — because millions of claims must not be read through a whole-file parse (#374); `src/meta_disco/source_evidence.py` is the reader and writer.
    Declared as class-local `attributes` for the reason `ClaimSource` is: these are words too generic to own in a shared namespace.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'rules': [{'description': 'A file keyed by `file_name` must name the dataset '
                                   'that scopes it. The key is non-unique on 69.4% of '
                                   "the AnVIL corpus's 708,088 rows and on 20% even "
                                   'scoped by dataset title, against 2 rows in 16,271 '
                                   'within `AnVIL_HPRC_R2` — so an unscoped filename '
                                   'claim attaches to rows a join cannot choose '
                                   'between. `source_evidence.require_scoped_target` '
                                   'refuses the same envelope at write and at read, '
                                   'because gen-pydantic does not emit class rules; '
                                   'this rule is what stops a producer validating '
                                   'against the schema alone and publishing a file the '
                                   'reader will not read (#401 review).',
                    'postconditions': {'slot_conditions': {'target': {'name': 'target',
                                                                      'range_expression': {'slot_conditions': {'dataset': {'name': 'dataset',
                                                                                                                           'required': True}}}}}},
                    'preconditions': {'slot_conditions': {'target_key': {'equals_string': 'file_name',
                                                                         'name': 'target_key'}}}}]})

    source: EvidenceFileSource = Field(default=..., description="""Where the claims were read from — repository, dataset and table. `inlined` for the reason `Evidence.source` is: line 1 carries the whole object, and without the declaration a class-valued slot is read as a reference rather than as the object the file holds.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidenceFileEnvelope', 'Evidence', 'Attribution']} })
    source_type: ImporterSourceTypeEnum = Field(default=..., description="""Which kind of external source this file was read from. On the envelope rather than on every row for the reason the key names are: one repository, dataset and table is one kind of source, so it is checked once per file rather than a few million times, and reconcile reads it from here when it stamps the claim it makes from a row (#421).
Restricted to the kinds an importer may write. A file declaring `filename_rule` would be naming our own rule engine as its publisher, and one declaring `wrangler_annotation` would be a curator arriving as evidence, which contract 1.6 routes to rules instead.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidenceFileEnvelope', 'Evidence', 'Attribution']} })
    source_version: str = Field(default=..., description="""The version of the source the claims were taken from — a release tag, a publication date, a catalog generation. Required even where the source publishes no version of its own: an evidence file that cannot say what it was built from cannot be reasoned about later.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidenceFileEnvelope']} })
    source_key: str = Field(default=..., description="""The key the *source* publishes its rows by, in the source's own name for it — `filename`, `run_accession`, `object_id`. Recorded as provenance: the values on each line are already in the target's space, so the run never reads this, but a person auditing the file needs to know which column of the source produced them.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidenceFileEnvelope']} })
    target: EvidenceTarget = Field(default=..., description="""The system the claims are about, the scope within it, and the generation resolved against.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidenceFileEnvelope']} })
    target_key: JoinKeyEnum = Field(default=..., description="""Which key of the target each line's `target_key_value` is to be matched against. Drawn from `join_key_enum`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidenceFileEnvelope']} })
    fetched_at: str = Field(default=..., description="""When the importer read the source, ISO 8601, with a time of day and not a date alone. A run reports the age of every evidence file it finds from this, so that a person can see an artefact going stale before it is wrong — and two imports on the same day, which is where that report matters most, are only distinguishable if the time is recorded. A date-only value is refused rather than read as midnight, which would be a precision the file never stated.
Constrained by pattern rather than `range: datetime`, which was measured and does not do the job: LinkML coerces the value before matching, so a bare `2026-09-01` is accepted under a datetime range — and the pattern is then never applied. An evidence file would pass this schema and be reported unreadable by the reader, which is the mismatch this class's tests exist to prevent.
The trade is deliberate: a consumer generating models from this schema gets a string rather than a datetime. The reader parses it either way, and the pattern says what the string must look like, so what is given up is a type hint and what is bought is that both sides refuse the same files.
The pattern spells out the field ranges rather than accepting any non-newline text after the separator, because the loose form let `2026-09-01Tfoo` and `2026-13-45T99:99:99` through the gate for the reader to refuse. Measured across seventeen shapes, the two sides now agree on sixteen. The one that remains is a date no regex can rule out: `2026-02-30T09:14:03` is well-formed and not a day, so the reader stays the authority on whether a well-shaped timestamp is a real instant (#401 review).
The offset is `±HH:MM` or `Z` and nothing more. An offset carrying seconds, `+01:00:30`, is a shape `datetime.fromisoformat` happens to take and RFC 3339 does not have; the reader parses with pydantic, which refuses it, and no source emits one — so the pattern refuses it too rather than admitting a file the reader will not read (#494 review).""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidenceFileEnvelope']} })

    @field_validator('source_version')
    def pattern_source_version(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid source_version format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid source_version format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('source_key')
    def pattern_source_key(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid source_key format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid source_key format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('fetched_at')
    def pattern_fetched_at(cls, v):
        pattern=re.compile(r"^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])[T ]([01]\d|2[0-3]):[0-5]\d(:[0-5]\d(\.\d+)?)?([+-]([01]\d|2[0-3]):[0-5]\d|Z)?\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid fetched_at format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid fetched_at format: {v}"
            raise ValueError(err_msg)
        return v


class Evidence(ConfiguredBaseModel):
    """
    One piece of supporting evidence. Either a claim (declares a value, a status, or a claim_state, and carries a source_type), or a synthetic resolution marker (carries marker, no rule_id) recording that no claim was made or that claims conflicted.
    A claim from one of our rules or content classifiers carries rule_id + tier, except an inherited one (`derivation_inheritance`, made at reconcile, contract 4.9, #571), which carries no tier — it never reaches the rule ladder — and names the step it crossed in `activity`, `parent_role` and `parent_keys`. A claim from an external source (issue #392) carries `source` as well as a rule_id — the mapping entry it fired, not a rule of ours — and no tier, because an import does not compete on the rule ladder (#401). It carries the raw value it read and, once the join has run, how it was matched to our file. Evidence that is neither — the note left when a fetch or the input contract failed — carries a rule_id and a reason but declares nothing.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'slot_usage': {'activity': {'name': 'activity', 'required': False},
                        'status': {'name': 'status', 'required': False}}})

    rule_id: Optional[str] = Field(default=None, description="""Identifier of the rule or content classifier that produced this evidence. Absent on synthetic resolution markers, which carry `marker` instead.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence', 'Attribution']} })
    marker: Optional[EvidenceMarkerEnum] = Field(default=None, description="""Kind of synthetic resolution marker, when this entry is not a claim but a note about the outcome: `not_classified` (no rule determined a value) or `conflict` (claims disagreed at the top tier). The marker's `status` is the status the field resolved to — `conflict` on a conflict marker (#88). Absent on real claims.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence']} })
    reason: Optional[str] = Field(default=None, description="""Human-readable rationale.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence', 'ActivityDeclaration']} })
    value: Optional[str] = Field(default=None, description="""The resolved value; null unless status is 'classified'.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    status: Optional[ClassificationStatusEnum] = Field(default=None, description="""Whether the field was classified, is not applicable, etc.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    claim_state: Optional[ClaimStateEnum] = Field(default=None, description="""The state of a claim that produced no vocabulary value — see `claim_state_enum` for what each state means. Present instead of `value` or `status`, and only on such a claim: one that mapped successfully carries a `value`, and the two sentinels are carried in `status` as before.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence']} })
    tier: Optional[int] = Field(default=None, description="""The tier at which this evidence fired.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence']} })
    competing_values: Optional[list[str]] = Field(default=None, description="""On a `conflict` marker, the disagreeing top-tier values that made the field ambiguous. Absent on claims and on the `not_classified` marker.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence']} })
    source_type: Optional[SourceTypeEnum] = Field(default=None, description="""Kind of source that produced this claim (provenance, #90; populated on every claim by #392) — see `source_type_enum` for the kinds. Absent on a synthetic marker and on the note left by a failed fetch or input contract, neither of which is a claim.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidenceFileEnvelope', 'Evidence', 'Attribution']} })
    source: Optional[ClaimSource] = Field(default=None, description="""The external source that produced this claim, for a claim that is not from one of our rules. Absent on a rule or content claim, which carries `rule_id`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidenceFileEnvelope', 'Evidence', 'Attribution']} })
    raw_value: Optional[str] = Field(default=None, description="""What the source actually said, before mapping — `Revio` beside a mapped `PACBIO`. The mapping is the reviewable decision, and storing only the mapped value makes it unauditable. Also present on an `unmapped` or `no_vocabulary_term` claim, where it is the whole content of the claim.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidenceRow', 'EntityEvidenceRow', 'Evidence']} })
    join_key: Optional[JoinKeyEnum] = Field(default=None, description="""Which key attached this claim to our record: a file's, or for a donor's slot the identifier the source wrote (`entity_identifier`, #693). Recorded per claim rather than per source because identity is the risky step and sources publish different keys: md5 collides on 1.72% of the corpus's rows and the HPRC catalog publishes only file names (#390). Absent on a claim our own inference produced, which was never joined to anything.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence']} })
    match_exact: Optional[bool] = Field(default=None, description="""Whether the join on `join_key` was an exact match rather than a normalized or partial one. Absent whenever `join_key` is.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence']} })
    activity: Optional[ActivityTypeEnum] = Field(default=None, description="""The kind of step that made the file (`activity_type_enum`); what passes from each input role is declared per term in `rules/activities.yaml`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence', 'GeneratedBy', 'Attribution']} })
    parent_role: Optional[str] = Field(default=None, description="""On an inherited claim (contract 4.9, #571), or an inherited sample attribution (#668): the input role of the step whose parents gave the claim or the samples, a role its `activity` declares in `rules/activities.yaml`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence', 'Attribution']} })
    parent_keys: Optional[list[str]] = Field(default=None, description="""On an inherited claim (contract 4.9, #571), or an inherited sample attribution (#668): the record keys of the parents, in that role, whose settled answers or samples gave it — each one's record in the same run, or, for a list held outside AnVIL for the dataset (#710), its address, its line in the reconciled `external_lists.ndjson.gz`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence', 'Attribution']} })


class GeneratedBy(ConfiguredBaseModel):
    """
    The one step that made a file and the inputs it used (PROV's `wasGeneratedBy` and `used`, ADR-0002 decision 3, #580). `named_by` lists every source that named the step; each input lists its own.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml'})

    activity: ActivityTypeEnum = Field(default=..., description="""The kind of step that made the file (`activity_type_enum`); what passes from each input role is declared per term in `rules/activities.yaml`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence', 'GeneratedBy', 'Attribution']} })
    named_by: list[Attribution] = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['GeneratedBy',
                       'ActivityInput',
                       'SampleReference',
                       'Synonym',
                       'CollectedFrom']} })
    inputs: list[ActivityInput] = Field(default=..., description="""The inputs the step used, each in one of the roles its activity declares.""", json_schema_extra = { "linkml_meta": {'domain_of': ['GeneratedBy', 'ActivityDeclaration']} })


class ActivityInput(ConfiguredBaseModel):
    """
    One input a step used, in one role (PROV's `hadRole`). With `parent_key` it is `internal`, without it `external` (ADR-0002 decision 2). An external input with a `parent_ref` is a file held outside AnVIL for the dataset (#710), which a role that reads through its parents reads through as it does a catalog file.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'slot_usage': {'parent_file': {'name': 'parent_file', 'required': True}}})

    parent_file: str = Field(default=..., description="""The input file's name: the matched record's own spelling where the input resolves (a file-name rule matches case-insensitively, so it may differ in case from the name worked out from the child), otherwise as the source that names the input wrote it.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityInput']} })
    parent_key: Optional[str] = Field(default=None, description="""The parent's record key (`record_keys.SOURCE_RECORD_KEYS`: AnVIL's `file_id`, HPRC's URL hash in `md5sum`), set only when the parent resolves to exactly one record of the child's dataset (ADR-0002 decision 2), or of the dataset an input's `parent_dataset` names under that decision's declared exception (#594). Named for the key rather than `parent_file_id` because HPRC's key is not a `file_id`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityInput']} })
    parent_ref: Optional[str] = Field(default=None, description="""The parent as a source wrote it when that is not a bare name (ADR-0002 decision 2). Written today for a file held outside AnVIL for the child's dataset (#710, a workaround until #624): its address, `github:<owner>/<repo>@<commit>/<path>`, as `sources/external_files.yaml` declares it, and its record in the reconciled `external_lists.ndjson.gz`; and for a sample map inference rebuilt (#726): its address, `rebuilt:<dataset>/<reference folder>/<map>#<digest>`, and its record in the reconciled `rebuilt_lists.ndjson.gz`. Such an input has no `parent_key`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityInput']} })
    parent_kind: Optional[ParentKindEnum] = Field(default=None, description="""The kind of file the parent is.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityInput']} })
    role: str = Field(default=..., description="""One of the roles its activity declares in `rules/activities.yaml`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityInput', 'InputRole']} })
    named_by: list[Attribution] = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['GeneratedBy',
                       'ActivityInput',
                       'SampleReference',
                       'Synonym',
                       'CollectedFrom']} })
    parent_dataset: Optional[str] = Field(default=None, description="""The dataset `parent_key`'s record is in, where it is not the child's own: only an input resolved through the run lineage map's declared exception (#594, ADR-0002 decision 2), such as a T2T_CHRY CRAM's reads in ANVIL_T2T. Absent on every input whose parent is in the child's dataset.""", json_schema_extra = { "linkml_meta": {'domain_of': ['LineageRow', 'ActivityInput']} })

    @field_validator('parent_ref')
    def pattern_parent_ref(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid parent_ref format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid parent_ref format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('parent_dataset')
    def pattern_parent_dataset(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid parent_dataset format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid parent_dataset format: {v}"
            raise ValueError(err_msg)
        return v


class Attribution(ConfiguredBaseModel):
    """
    One source that named a step, an input (ADR-0002 decision 6) or a file's samples (#357): sources that agree are each listed. Samples inherited from a parent (#668) name the step crossed and the parent, as an inherited claim does; samples a PLINK fileset's sample table gave (#751) name the table.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'slot_usage': {'activity': {'name': 'activity', 'required': False},
                        'rule_id': {'description': 'The rule or translation row that '
                                                   'turned what the source says into '
                                                   'this step, input or sample list: '
                                                   "for inference's, a "
                                                   '`code_rules.EDGE_RULES` id for a '
                                                   'step or input and a '
                                                   '`code_rules.SAMPLE_RULES` id for '
                                                   "samples; for a submitter table's "
                                                   'samples, the identifier rule '
                                                   '(`rules/sample_namespaces.yaml`) '
                                                   'that read the cell; for inherited '
                                                   'samples, '
                                                   "`code_rules.SAMPLES_INHERITED_FROM_PARENT`'s "
                                                   "id; for samples the repository's "
                                                   'record of the step names (#698), '
                                                   "`code_rules.SAMPLES_FROM_ACTIVITY_BIOSAMPLE`'s "
                                                   "id; for samples a PLINK fileset's "
                                                   'sample table gave (#751), '
                                                   "`code_rules.SAMPLES_FROM_FILESET_SAMPLE_TABLE`'s "
                                                   'id.',
                                    'name': 'rule_id',
                                    'required': True},
                        'source_type': {'name': 'source_type', 'required': True}}})

    source_type: SourceTypeEnum = Field(default=..., description="""Kind of source that produced this claim (provenance, #90; populated on every claim by #392) — see `source_type_enum` for the kinds. Absent on a synthetic marker and on the note left by a failed fetch or input contract, neither of which is a claim.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidenceFileEnvelope', 'Evidence', 'Attribution']} })
    rule_id: str = Field(default=..., description="""The rule or translation row that turned what the source says into this step, input or sample list: for inference's, a `code_rules.EDGE_RULES` id for a step or input and a `code_rules.SAMPLE_RULES` id for samples; for a submitter table's samples, the identifier rule (`rules/sample_namespaces.yaml`) that read the cell; for inherited samples, `code_rules.SAMPLES_INHERITED_FROM_PARENT`'s id; for samples the repository's record of the step names (#698), `code_rules.SAMPLES_FROM_ACTIVITY_BIOSAMPLE`'s id; for samples a PLINK fileset's sample table gave (#751), `code_rules.SAMPLES_FROM_FILESET_SAMPLE_TABLE`'s id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence', 'Attribution']} })
    activity_id: Optional[str] = Field(default=None, description="""The source's own id for the step (`anvil_activity.activity_id`, or `anvil_sequencingactivity.sequencingactivity_id`), where it gives one.""", json_schema_extra = { "linkml_meta": {'domain_of': ['LineageRow', 'Attribution']} })
    source: Optional[ClaimSource] = Field(default=None, description="""The external source that produced this claim, for a claim that is not from one of our rules. Absent on a rule or content claim, which carries `rule_id`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidenceFileEnvelope', 'Evidence', 'Attribution']} })
    activity: Optional[ActivityTypeEnum] = Field(default=None, description="""The kind of step that made the file (`activity_type_enum`); what passes from each input role is declared per term in `rules/activities.yaml`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence', 'GeneratedBy', 'Attribution']} })
    parent_role: Optional[str] = Field(default=None, description="""On an inherited claim (contract 4.9, #571), or an inherited sample attribution (#668): the input role of the step whose parents gave the claim or the samples, a role its `activity` declares in `rules/activities.yaml`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence', 'Attribution']} })
    parent_keys: Optional[list[str]] = Field(default=None, description="""On an inherited claim (contract 4.9, #571), or an inherited sample attribution (#668): the record keys of the parents, in that role, whose settled answers or samples gave it — each one's record in the same run, or, for a list held outside AnVIL for the dataset (#710), its address, its line in the reconciled `external_lists.ndjson.gz`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence', 'Attribution']} })
    sample_table_key: Optional[str] = Field(default=None, description="""On a sample attribution a PLINK fileset's sample table gave (#751): the record key of the `.psam` whose settled samples the file took, a record of the same run.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Attribution']} })


class SampleReference(ConfiguredBaseModel):
    """
    Which samples a file's data comes from (#357): the run's sample list it points to, how many members that list has, and every source that named it. A joint VCF names thousands of samples, so the members are written as a `SampleList` and each file points to one: once in each producer file that points to it (`sample_lists`), and once across the run in the reconciled `sample_lists.ndjson.gz`.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml'})

    list_id: str = Field(default=..., description="""The `SampleList` this file points to: a digest of its sorted members, so two files naming the same samples point to the same list.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SampleReference', 'SampleList']} })
    count: int = Field(default=..., description="""How many members the list has.""", ge=1, json_schema_extra = { "linkml_meta": {'domain_of': ['SampleReference']} })
    named_by: list[Attribution] = Field(default=..., description="""Every source that named these samples: the file's own content, a header or a sample map's rows (`code_rules.SAMPLE_RULES`), a submitter-table column, the file's parent across a step that passes samples (#668), or each of them where they agree.""", json_schema_extra = { "linkml_meta": {'domain_of': ['GeneratedBy',
                       'ActivityInput',
                       'SampleReference',
                       'Synonym',
                       'CollectedFrom']} })

    @field_validator('list_id')
    def pattern_list_id(cls, v):
        pattern=re.compile(r"^[0-9a-f]{16}\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid list_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid list_id format: {v}"
            raise ValueError(err_msg)
        return v


class ExternalList(ConfiguredBaseModel):
    """
    A list of files held outside AnVIL for a dataset, as reconcile read it (#710, a workaround until AnVIL holds the list, #624): a GATK sample-name map that `sources/external_files.yaml` declares, the step listing the dataset's files it names as members, and the samples its rows name. Written once per run in the reconciled `external_lists.ndjson.gz`; an `ActivityInput.parent_ref` points here.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml'})

    ref: str = Field(default=..., description="""The list's address, `github:<owner>/<repo>@<commit>/<path>`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ExternalList', 'RebuiltList']} })
    dataset: str = Field(default=..., description="""The dataset the list is held for, the only one whose files it names.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClaimSource',
                       'EvidenceFileSource',
                       'EvidenceTarget',
                       'ExternalList',
                       'RebuiltList',
                       'EntityIdentifier',
                       'IdentifierRule',
                       'RepositoryIdentifier']} })
    file_name: str = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ClassificationRecord', 'ExternalList', 'RebuiltList']} })
    sha256: str = Field(default=..., description="""The sha256 of the list's text, as declared and as read.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ExternalList']} })
    generated_by: Optional[GeneratedBy] = Field(default=None, description="""The list's members, each a file of the dataset carrying the name a row gives. Absent where a row's name is carried by no file of the dataset or by several, or two rows give one name: a cohort missing a member is not the cohort.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClassificationRecord', 'ExternalList', 'RebuiltList']} })
    samples: Optional[SampleReference] = Field(default=None, description="""The samples the list's rows name, where every one is recognised and a reconciled file settles to them (so the list they point to is in `sample_lists.ndjson.gz`).""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClassificationRecord', 'ExternalList']} })

    @field_validator('ref')
    def pattern_ref(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid ref format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid ref format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('dataset')
    def pattern_dataset(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid dataset format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid dataset format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('file_name')
    def pattern_file_name(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid file_name format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid file_name format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('sha256')
    def pattern_sha256(cls, v):
        pattern=re.compile(r"^[0-9a-f]{64}\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid sha256 format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid sha256 format: {v}"
            raise ValueError(err_msg)
        return v


class RebuiltList(ConfiguredBaseModel):
    """
    A GATK sample-name map no one holds, rebuilt by inference from the GenomicsDB workspace tars that read it (#726): a tar in a folder `cohort_steps.REBUILT_MAP_FOLDERS` declares names the map in its own vcfheader.vcf and its samples in its own callset.json, and each sample's gVCF is the one file of the dataset the run's layout places for that map under the tar's reference folder. Written once under the tar producer file's `rebuilt_lists` and once per run in the reconciled `rebuilt_lists.ndjson.gz`; an `ActivityInput.parent_ref` points here. It names no samples: they are the tars' own callset.json, which each tar names as its own.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml'})

    ref: str = Field(default=..., description="""The list's address, `rebuilt:<dataset>/<reference folder>/<map>#<digest>`, the digest the first 16 hex of the sha256 of its members' record keys, sorted, one per line.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ExternalList', 'RebuiltList']} })
    dataset: str = Field(default=..., description="""The dataset whose files the list names.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClaimSource',
                       'EvidenceFileSource',
                       'EvidenceTarget',
                       'ExternalList',
                       'RebuiltList',
                       'EntityIdentifier',
                       'IdentifierRule',
                       'RepositoryIdentifier']} })
    file_name: str = Field(default=..., description="""The map's base name, as the tars' headers write it.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClassificationRecord', 'ExternalList', 'RebuiltList']} })
    generated_by: GeneratedBy = Field(default=..., description="""The list's members, each the one file of the dataset carrying a sample's gVCF. A list is rebuilt only where every sample's resolves.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClassificationRecord', 'ExternalList', 'RebuiltList']} })

    @field_validator('ref')
    def pattern_ref(cls, v):
        pattern=re.compile(r"^rebuilt:[^\r\n#]+#[0-9a-f]{16}\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid ref format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid ref format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('dataset')
    def pattern_dataset(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid dataset format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid dataset format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('file_name')
    def pattern_file_name(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid file_name format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid file_name format: {v}"
            raise ValueError(err_msg)
        return v


class Fileset(ConfiguredBaseModel):
    """
    A PLINK 2 fileset inference paired with its sample table (#751): the `.psam`, and the `.pgen`, `.pvar` and `.log` beside it in its folder under its stem, which one `plink2 --make-pgen` writes together. Written under the psam producer file's `filesets`; reconcile gives each member the `.psam`'s settled samples (`Attribution.sample_table_key`).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml'})

    sample_table: str = Field(default=..., description="""The `.psam`'s record key.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Fileset']} })
    members: list[str] = Field(default=..., description="""The record key of each member paired, at most one per extension.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Fileset', 'SampleList']} })

    @field_validator('sample_table')
    def pattern_sample_table(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid sample_table format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid sample_table format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('members')
    def pattern_members(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid members format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid members format: {v}"
            raise ValueError(err_msg)
        return v


class SampleList(ConfiguredBaseModel):
    """
    One distinct set of samples files point to (#357): written once in each producer file that points to it, so two producer files may each hold the same list, and once across the whole run in the reconciled `sample_lists.ndjson.gz`.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml'})

    list_id: str = Field(default=..., description="""A digest of the sorted members; `SampleReference.list_id` points here.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SampleReference', 'SampleList']} })
    members: list[EntityIdentifier] = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['Fileset', 'SampleList']} })

    @field_validator('list_id')
    def pattern_list_id(cls, v):
        pattern=re.compile(r"^[0-9a-f]{16}\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid list_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid list_id format: {v}"
            raise ValueError(err_msg)
        return v


class EntityIdentifier(ConfiguredBaseModel):
    """
    A sample or donor, named by the authority that issued its identifier (ADR-0002 decision 1). Two identifiers name the same sample only when namespace and id match, and, for `dataset_local`, the dataset too.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'rules': [{'description': 'A `dataset_local` identifier names its dataset: '
                                   'without it, a name like `simons_data_sample_12` '
                                   'would match the same name in any dataset. '
                                   'gen-pydantic does not emit class rules; '
                                   '`sample_identity` builds identifiers only from '
                                   'rules its loader holds to the same pairing.',
                    'postconditions': {'slot_conditions': {'dataset': {'name': 'dataset',
                                                                       'required': True}}},
                    'preconditions': {'slot_conditions': {'namespace': {'equals_string': 'dataset_local',
                                                                        'name': 'namespace'}}}},
                   {'description': 'Only a `dataset_local` identifier names a dataset: '
                                   'a `coriell` identifier with one would not equal '
                                   'the same sample named elsewhere.',
                    'postconditions': {'slot_conditions': {'namespace': {'equals_string': 'dataset_local',
                                                                         'name': 'namespace'}}},
                    'preconditions': {'slot_conditions': {'dataset': {'name': 'dataset',
                                                                      'required': True}}}}]})

    id: str = Field(default=..., description="""The identifier, as its namespace writes it: a source's string as written, except where an identifier rule declares a rewrite (`GM19908` is written `NA19908`, #357).""", json_schema_extra = { "linkml_meta": {'domain_of': ['EntityIdentifier', 'IdentifierRule', 'RepositoryIdentifier']} })
    namespace: IdentifierNamespaceEnum = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['EntityIdentifier', 'IdentifierRule']} })
    dataset: Optional[str] = Field(default=None, description="""The dataset the identifier is local to: set exactly when the namespace is `dataset_local`, and then part of its identity.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClaimSource',
                       'EvidenceFileSource',
                       'EvidenceTarget',
                       'ExternalList',
                       'RebuiltList',
                       'EntityIdentifier',
                       'IdentifierRule',
                       'RepositoryIdentifier']} })

    @field_validator('id')
    def pattern_id(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid id format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('dataset')
    def pattern_dataset(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid dataset format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid dataset format: {v}"
            raise ValueError(err_msg)
        return v


class IdentifierRules(ConfiguredBaseModel):
    """
    The shape of `rules/sample_namespaces.yaml` (#357): how a source's string becomes an `EntityIdentifier`. Read through the generated model by `meta_disco.sample_identity`.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml'})

    rules: list[IdentifierRule] = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['IdentifierRules']} })


class IdentifierRule(ConfiguredBaseModel):
    """
    One way a string is recognised as an identifier: a pattern matched against the whole string, the namespace it is in, and, for a `dataset_local` rule, the one dataset it applies in.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml'})

    id: str = Field(default=..., description="""The rule's id, cited as `rule_id` by a source the rule recognised.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EntityIdentifier', 'IdentifierRule', 'RepositoryIdentifier']} })
    namespace: IdentifierNamespaceEnum = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['EntityIdentifier', 'IdentifierRule']} })
    match: str = Field(default=..., description="""A regular expression the whole string must match.""", json_schema_extra = { "linkml_meta": {'domain_of': ['IdentifierRule']} })
    write: Optional[str] = Field(default=None, description="""A replacement template giving the identifier from the match, where it is not the string as written: literal text and numbered group references (a backslash and a digit 1 to 9), nothing else. Absent: the string as written.""", json_schema_extra = { "linkml_meta": {'domain_of': ['IdentifierRule']} })
    dataset: Optional[str] = Field(default=None, description="""The one dataset a `dataset_local` rule applies in; set exactly on those.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClaimSource',
                       'EvidenceFileSource',
                       'EvidenceTarget',
                       'ExternalList',
                       'RebuiltList',
                       'EntityIdentifier',
                       'IdentifierRule',
                       'RepositoryIdentifier']} })
    names: list[EntityKindEnum] = Field(default=..., description="""What a string the rule recognises names: a sample, a donor, or both (#693). A rule naming both says one string is a sample and the donor it was collected from, as a Coriell number names a cell line and the person it came from; the sample's `collected_from` is then that donor. A file's samples are read only through rules naming `sample`, and a donor's identifier only through rules naming `donor`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['IdentifierRule']} })
    rationale: str = Field(default=..., description="""Why a string matching the pattern names one sample or donor in this namespace.""", json_schema_extra = { "linkml_meta": {'domain_of': ['IdentifierRule']} })

    @field_validator('id')
    def pattern_id(cls, v):
        pattern=re.compile(r"^[a-z][a-z0-9_]*\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid id format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('dataset')
    def pattern_dataset(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid dataset format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid dataset format: {v}"
            raise ValueError(err_msg)
        return v


class DonorRecord(ConfiguredBaseModel):
    """
    One donor (#693, ADR-0002 decision 1 as amended): the person or animal samples were collected from, keyed by its identifier, so one record gathers what every dataset's tables say about one person, and each property is settled once, by the rule a file's dimensions are settled by (`reconcile.settle`). Reconcile writes one per donor that entity evidence names, a sample's `collected_from` points to, a repository's own identifier ties to, or another donor's `mother` or `father` claim names (#582), in `reconciled/donors.ndjson.gz`. A file reaches its donors through its `samples` and each sample's `collected_from`; no donor property is copied onto a file (epic #692, decision 5). Each slot carries `use` (#699), as a reconciled file's does: `meta_disco` where it is `classified` or `not_applicable`, else `published`, where a reader shows what the repository publishes: its own rows' values are in the slot's `evidence` where it has any (AnVIL has no field for a family, and its `Unknown` leaves no claim).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml'})

    identifier: EntityIdentifier = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['DonorRecord', 'Synonym', 'SampleRecord']} })
    phenotypic_sex: PhenotypicSexClassification = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['DonorRecord']} })
    genetic_ancestry: GeneticAncestryClassification = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['DonorRecord']} })
    organism_type: OrganismTypeClassification = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['DonorRecord']} })
    reported_ethnicity: ReportedEthnicityClassification = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['DonorRecord']} })
    mother: ParentClassification = Field(default=..., description="""The donor's mother (#582), from every source that names her.""", json_schema_extra = { "linkml_meta": {'domain_of': ['DonorRecord']} })
    father: ParentClassification = Field(default=..., description="""The donor's father (#582), from every source that names him.""", json_schema_extra = { "linkml_meta": {'domain_of': ['DonorRecord']} })
    family_id: FamilyIdClassification = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['DonorRecord']} })
    repository_ids: Optional[list[RepositoryIdentifier]] = Field(default=None, description="""Every identifier a repository gave a record of its own for this donor (#669), AnVIL's `donor_id`s: a person has an AnVIL donor in each dataset whose donors are made from a row naming them, and the datasets give them one or more distinct ids (PRIMED's and T2T's are one). Absent where none ties to the donor.""", json_schema_extra = { "linkml_meta": {'domain_of': ['DonorRecord', 'SampleRecord']} })
    synonyms: Optional[list[Synonym]] = Field(default=None, description="""Every other identifier joined to this donor by a chain of `same_donor_as` links that neither branches nor comes back on itself (#559): SGDP's own name (`sgdp:S_Spanish-2`) on the record its metadata file keys by the cell line's repository number (`coriell:HG01504`). What a source said under a synonym is settled on this record. Absent where none does.""", json_schema_extra = { "linkml_meta": {'domain_of': ['DonorRecord']} })


class Synonym(ConfiguredBaseModel):
    """
    Another identifier for a donor, and every source that said so (#559): a source's `same_donor_as` line, about the donor it names by `identifier`, naming another identifier for it, followed to the end of the chain (the record's own identifier). Each synonym is cited by its own line. The record is listed under the identifier at the end of the chain (for SGDP, the cell line's repository number) and carries the synonyms, so a reader can find it by either; the explorer's search on synonyms is a follow-up.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml'})

    identifier: EntityIdentifier = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['DonorRecord', 'Synonym', 'SampleRecord']} })
    named_by: list[Attribution] = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['GeneratedBy',
                       'ActivityInput',
                       'SampleReference',
                       'Synonym',
                       'CollectedFrom']} })


class RepositoryIdentifier(ConfiguredBaseModel):
    """
    A repository's own identifier for a donor or sample (#669): AnVIL's `donor_id` or `biosample_id`, the key of the explorer's donor and biosample pages. It ties to our record through the submitter row AnVIL made its record from (`source_datarepo_row_ids`), read in that row's table's identifier column (`sources/anvil_entity_map.yaml`). Many may tie to one record; one tying to two records is refused at reconcile, and an AnVIL record whose source rows name two identifier strings is counted and skipped at import. A UUID can be both a donor's and a sample's: a tie is per kind.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml'})

    id: str = Field(default=..., description="""The repository's identifier, as it wrote it.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EntityIdentifier', 'IdentifierRule', 'RepositoryIdentifier']} })
    repository: str = Field(default=..., description="""The repository that issued it (`anvil`).""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidenceFileSource', 'RepositoryIdentifier']} })
    dataset: str = Field(default=..., description="""The dataset whose table holds it. The same identifier in two datasets is listed once for each.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClaimSource',
                       'EvidenceFileSource',
                       'EvidenceTarget',
                       'ExternalList',
                       'RebuiltList',
                       'EntityIdentifier',
                       'IdentifierRule',
                       'RepositoryIdentifier']} })
    table: str = Field(default=..., description="""The repository's table holding it (`anvil_donor`, `anvil_biosample`).""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClaimSource', 'EvidenceFileSource', 'RepositoryIdentifier']} })

    @field_validator('id')
    def pattern_id(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid id format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('repository')
    def pattern_repository(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid repository format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid repository format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('dataset')
    def pattern_dataset(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid dataset format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid dataset format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('table')
    def pattern_table(cls, v):
        pattern=re.compile(r"^[^\r\n]+\Z")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid table format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid table format: {v}"
            raise ValueError(err_msg)
        return v


class PhenotypicSexClassification(Classification):
    """
    A donor's phenotypic sex, settled from every source that states it (#693).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'slot_usage': {'use': {'name': 'use', 'required': True},
                        'value': {'name': 'value', 'range': 'phenotypic_sex_enum'}}})

    value: Optional[PhenotypicSexEnum] = Field(default=None, description="""The resolved value; null unless status is 'classified'.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    status: ClassificationStatusEnum = Field(default=..., description="""Whether the field was classified, is not applicable, etc.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    evidence: Optional[list[Evidence]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    use: UseEnum = Field(default=..., description="""On a reconciled record only (#432), a file's or a donor's or sample's (#699): whether the indexer takes this record's value (`meta_disco`, when the status is `classified` or `not_applicable`) or keeps what the repository publishes (`published`, when it is `conflict` or `not_classified`). Computed by reconcile so an export is structure only.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    inferred: Optional[InferredConclusion] = Field(default=None, description="""On a reconciled record only (#432): what inference concluded for this slot.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    credited_to: Optional[CreditedToEnum] = Field(default=None, description="""On a reconciled record only (#552): where this slot's answer is credited, the per-slot category the reconcile report counts. The rule is `reconcile.credited_to`'s. It attributes and never decides: the value was settled before it is read.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })


class GeneticAncestryClassification(Classification):
    """
    A donor's genetic ancestry, settled from every source that states it (#693): the most specific term the sources support, where they nest.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'slot_usage': {'use': {'name': 'use', 'required': True},
                        'value': {'name': 'value', 'range': 'genetic_ancestry_enum'}}})

    value: Optional[GeneticAncestryEnum] = Field(default=None, description="""The resolved value; null unless status is 'classified'.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    status: ClassificationStatusEnum = Field(default=..., description="""Whether the field was classified, is not applicable, etc.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    evidence: Optional[list[Evidence]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    use: UseEnum = Field(default=..., description="""On a reconciled record only (#432), a file's or a donor's or sample's (#699): whether the indexer takes this record's value (`meta_disco`, when the status is `classified` or `not_applicable`) or keeps what the repository publishes (`published`, when it is `conflict` or `not_classified`). Computed by reconcile so an export is structure only.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    inferred: Optional[InferredConclusion] = Field(default=None, description="""On a reconciled record only (#432): what inference concluded for this slot.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    credited_to: Optional[CreditedToEnum] = Field(default=None, description="""On a reconciled record only (#552): where this slot's answer is credited, the per-slot category the reconcile report counts. The rule is `reconcile.credited_to`'s. It attributes and never decides: the value was settled before it is read.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })


class OrganismTypeClassification(Classification):
    """
    A donor's organism (#699), settled from every source that states it.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'slot_usage': {'use': {'name': 'use', 'required': True},
                        'value': {'name': 'value', 'range': 'organism_type_enum'}}})

    value: Optional[OrganismTypeEnum] = Field(default=None, description="""The resolved value; null unless status is 'classified'.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    status: ClassificationStatusEnum = Field(default=..., description="""Whether the field was classified, is not applicable, etc.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    evidence: Optional[list[Evidence]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    use: UseEnum = Field(default=..., description="""On a reconciled record only (#432), a file's or a donor's or sample's (#699): whether the indexer takes this record's value (`meta_disco`, when the status is `classified` or `not_applicable`) or keeps what the repository publishes (`published`, when it is `conflict` or `not_classified`). Computed by reconcile so an export is structure only.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    inferred: Optional[InferredConclusion] = Field(default=None, description="""On a reconciled record only (#432): what inference concluded for this slot.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    credited_to: Optional[CreditedToEnum] = Field(default=None, description="""On a reconciled record only (#552): where this slot's answer is credited, the per-slot category the reconcile report counts. The rule is `reconcile.credited_to`'s. It attributes and never decides: the value was settled before it is read.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })


class ReportedEthnicityClassification(Classification):
    """
    A donor's reported ethnicity (#699), settled from every source that states it.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'slot_usage': {'use': {'name': 'use', 'required': True},
                        'value': {'name': 'value', 'range': 'reported_ethnicity_enum'}}})

    value: Optional[ReportedEthnicityEnum] = Field(default=None, description="""The resolved value; null unless status is 'classified'.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    status: ClassificationStatusEnum = Field(default=..., description="""Whether the field was classified, is not applicable, etc.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    evidence: Optional[list[Evidence]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    use: UseEnum = Field(default=..., description="""On a reconciled record only (#432), a file's or a donor's or sample's (#699): whether the indexer takes this record's value (`meta_disco`, when the status is `classified` or `not_applicable`) or keeps what the repository publishes (`published`, when it is `conflict` or `not_classified`). Computed by reconcile so an export is structure only.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    inferred: Optional[InferredConclusion] = Field(default=None, description="""On a reconciled record only (#432): what inference concluded for this slot.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    credited_to: Optional[CreditedToEnum] = Field(default=None, description="""On a reconciled record only (#552): where this slot's answer is credited, the per-slot category the reconcile report counts. The rule is `reconcile.credited_to`'s. It attributes and never decides: the value was settled before it is read.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })


class BiosampleTypeClassification(Classification):
    """
    What kind of material a sample is (#699), settled from every source that states it.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'slot_usage': {'use': {'name': 'use', 'required': True},
                        'value': {'name': 'value', 'range': 'biosample_type_enum'}}})

    value: Optional[BiosampleTypeEnum] = Field(default=None, description="""The resolved value; null unless status is 'classified'.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    status: ClassificationStatusEnum = Field(default=..., description="""Whether the field was classified, is not applicable, etc.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    evidence: Optional[list[Evidence]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    use: UseEnum = Field(default=..., description="""On a reconciled record only (#432), a file's or a donor's or sample's (#699): whether the indexer takes this record's value (`meta_disco`, when the status is `classified` or `not_applicable`) or keeps what the repository publishes (`published`, when it is `conflict` or `not_classified`). Computed by reconcile so an export is structure only.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    inferred: Optional[InferredConclusion] = Field(default=None, description="""On a reconciled record only (#432): what inference concluded for this slot.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    credited_to: Optional[CreditedToEnum] = Field(default=None, description="""On a reconciled record only (#552): where this slot's answer is credited, the per-slot category the reconcile report counts. The rule is `reconcile.credited_to`'s. It attributes and never decides: the value was settled before it is read.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })


class AnatomicalSiteClassification(Classification):
    """
    Where in the body a sample was taken (#699): the source's string as written, as AnVIL's `anvil_biosample.anatomical_site` writes it, an `Unknown` making no claim. A pooled sample's site is the repository's join of its members' (`Brain, Heart`, IGVF's `MultiplexedSample`); mapping sites to an ontology, as a list, is #702.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'slot_usage': {'use': {'name': 'use', 'required': True}}})

    value: Optional[str] = Field(default=None, description="""The resolved value; null unless status is 'classified'.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    status: ClassificationStatusEnum = Field(default=..., description="""Whether the field was classified, is not applicable, etc.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    evidence: Optional[list[Evidence]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    use: UseEnum = Field(default=..., description="""On a reconciled record only (#432), a file's or a donor's or sample's (#699): whether the indexer takes this record's value (`meta_disco`, when the status is `classified` or `not_applicable`) or keeps what the repository publishes (`published`, when it is `conflict` or `not_classified`). Computed by reconcile so an export is structure only.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    inferred: Optional[InferredConclusion] = Field(default=None, description="""On a reconciled record only (#432): what inference concluded for this slot.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    credited_to: Optional[CreditedToEnum] = Field(default=None, description="""On a reconciled record only (#552): where this slot's answer is credited, the per-slot category the reconcile report counts. The rule is `reconcile.credited_to`'s. It attributes and never decides: the value was settled before it is read.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })


class ParentClassification(Classification):
    """
    A donor's mother or father (#582): the parent's identifier, so the parent's own `DonorRecord` is found by equality with its `identifier`. The relation is the Kinship Ontology's `isBiologicalChildOf` (KIN:032), child to parent, as a PED file states it; a parent's children and a donor's siblings are derived from it, never stored. Each source's parent string is recognised as a donor through `rules/sample_namespaces.yaml` in the source's dataset, and its claim cites the rule that recognised it; PED's `0` (\"not known\") makes no claim. Two sources naming different identifiers are a `conflict`, even where the two are one person in two namespaces (GIAB's `HG004` is Coriell's `NA24143`), until a crosswalk between namespaces exists (#674).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'slot_usage': {'evidence': {'name': 'evidence', 'range': 'ParentEvidence'},
                        'use': {'name': 'use', 'required': True},
                        'value': {'inlined': True,
                                  'name': 'value',
                                  'range': 'EntityIdentifier'}}})

    value: Optional[EntityIdentifier] = Field(default=None, description="""The resolved value; null unless status is 'classified'.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    status: ClassificationStatusEnum = Field(default=..., description="""Whether the field was classified, is not applicable, etc.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    evidence: Optional[list[ParentEvidence]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    use: UseEnum = Field(default=..., description="""On a reconciled record only (#432), a file's or a donor's or sample's (#699): whether the indexer takes this record's value (`meta_disco`, when the status is `classified` or `not_applicable`) or keeps what the repository publishes (`published`, when it is `conflict` or `not_classified`). Computed by reconcile so an export is structure only.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    inferred: Optional[InferredConclusion] = Field(default=None, description="""On a reconciled record only (#432): what inference concluded for this slot.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    credited_to: Optional[CreditedToEnum] = Field(default=None, description="""On a reconciled record only (#552): where this slot's answer is credited, the per-slot category the reconcile report counts. The rule is `reconcile.credited_to`'s. It attributes and never decides: the value was settled before it is read.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })


class ParentEvidence(Evidence):
    """
    A claim on a donor's `mother` or `father` (#582): its `value` is the parent's identifier, the shape `ParentClassification.value` takes, where every other claim's is a string.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'slot_usage': {'value': {'inlined': True,
                                  'name': 'value',
                                  'range': 'EntityIdentifier'}}})

    rule_id: Optional[str] = Field(default=None, description="""Identifier of the rule or content classifier that produced this evidence. Absent on synthetic resolution markers, which carry `marker` instead.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence', 'Attribution']} })
    marker: Optional[EvidenceMarkerEnum] = Field(default=None, description="""Kind of synthetic resolution marker, when this entry is not a claim but a note about the outcome: `not_classified` (no rule determined a value) or `conflict` (claims disagreed at the top tier). The marker's `status` is the status the field resolved to — `conflict` on a conflict marker (#88). Absent on real claims.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence']} })
    reason: Optional[str] = Field(default=None, description="""Human-readable rationale.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence', 'ActivityDeclaration']} })
    value: Optional[EntityIdentifier] = Field(default=None, description="""The resolved value; null unless status is 'classified'.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    status: Optional[ClassificationStatusEnum] = Field(default=None, description="""Whether the field was classified, is not applicable, etc.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    claim_state: Optional[ClaimStateEnum] = Field(default=None, description="""The state of a claim that produced no vocabulary value — see `claim_state_enum` for what each state means. Present instead of `value` or `status`, and only on such a claim: one that mapped successfully carries a `value`, and the two sentinels are carried in `status` as before.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence']} })
    tier: Optional[int] = Field(default=None, description="""The tier at which this evidence fired.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence']} })
    competing_values: Optional[list[str]] = Field(default=None, description="""On a `conflict` marker, the disagreeing top-tier values that made the field ambiguous. Absent on claims and on the `not_classified` marker.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence']} })
    source_type: Optional[SourceTypeEnum] = Field(default=None, description="""Kind of source that produced this claim (provenance, #90; populated on every claim by #392) — see `source_type_enum` for the kinds. Absent on a synthetic marker and on the note left by a failed fetch or input contract, neither of which is a claim.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidenceFileEnvelope', 'Evidence', 'Attribution']} })
    source: Optional[ClaimSource] = Field(default=None, description="""The external source that produced this claim, for a claim that is not from one of our rules. Absent on a rule or content claim, which carries `rule_id`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidenceFileEnvelope', 'Evidence', 'Attribution']} })
    raw_value: Optional[str] = Field(default=None, description="""What the source actually said, before mapping — `Revio` beside a mapped `PACBIO`. The mapping is the reviewable decision, and storing only the mapped value makes it unauditable. Also present on an `unmapped` or `no_vocabulary_term` claim, where it is the whole content of the claim.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidenceRow', 'EntityEvidenceRow', 'Evidence']} })
    join_key: Optional[JoinKeyEnum] = Field(default=None, description="""Which key attached this claim to our record: a file's, or for a donor's slot the identifier the source wrote (`entity_identifier`, #693). Recorded per claim rather than per source because identity is the risky step and sources publish different keys: md5 collides on 1.72% of the corpus's rows and the HPRC catalog publishes only file names (#390). Absent on a claim our own inference produced, which was never joined to anything.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence']} })
    match_exact: Optional[bool] = Field(default=None, description="""Whether the join on `join_key` was an exact match rather than a normalized or partial one. Absent whenever `join_key` is.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence']} })
    activity: Optional[ActivityTypeEnum] = Field(default=None, description="""The kind of step that made the file (`activity_type_enum`); what passes from each input role is declared per term in `rules/activities.yaml`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence', 'GeneratedBy', 'Attribution']} })
    parent_role: Optional[str] = Field(default=None, description="""On an inherited claim (contract 4.9, #571), or an inherited sample attribution (#668): the input role of the step whose parents gave the claim or the samples, a role its `activity` declares in `rules/activities.yaml`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence', 'Attribution']} })
    parent_keys: Optional[list[str]] = Field(default=None, description="""On an inherited claim (contract 4.9, #571), or an inherited sample attribution (#668): the record keys of the parents, in that role, whose settled answers or samples gave it — each one's record in the same run, or, for a list held outside AnVIL for the dataset (#710), its address, its line in the reconciled `external_lists.ndjson.gz`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence', 'Attribution']} })


class FamilyIdClassification(Classification):
    """
    The family a donor belongs to (#582), as a PED file's family id names it: the string as the source wrote it, so it means something only among datasets that share a numbering (1000 Genomes' family ids, which HPRC and HPRC_R2 reuse). It groups relatives no parent link joins, such as siblings whose parents were not sequenced; a person with no relative listed often has their own id as their family id, as PED files do. Two sources writing different ids are a `conflict`.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'slot_usage': {'use': {'name': 'use', 'required': True}}})

    value: Optional[str] = Field(default=None, description="""The resolved value; null unless status is 'classified'.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    status: ClassificationStatusEnum = Field(default=..., description="""Whether the field was classified, is not applicable, etc.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    evidence: Optional[list[Evidence]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    use: UseEnum = Field(default=..., description="""On a reconciled record only (#432), a file's or a donor's or sample's (#699): whether the indexer takes this record's value (`meta_disco`, when the status is `classified` or `not_applicable`) or keeps what the repository publishes (`published`, when it is `conflict` or `not_classified`). Computed by reconcile so an export is structure only.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    inferred: Optional[InferredConclusion] = Field(default=None, description="""On a reconciled record only (#432): what inference concluded for this slot.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    credited_to: Optional[CreditedToEnum] = Field(default=None, description="""On a reconciled record only (#552): where this slot's answer is credited, the per-slot category the reconcile report counts. The rule is `reconcile.credited_to`'s. It attributes and never decides: the value was settled before it is read.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })


class SampleRecord(ConfiguredBaseModel):
    """
    One sample (#693): every sample a reconciled file names, and every sample a repository's own sample record ties to (#669), in `reconciled/samples.ndjson.gz`, with the donor it was collected from where a rule says, and what the repository's own record of it says (#699), each slot settled and carrying `use` as a donor's does.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml'})

    identifier: EntityIdentifier = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['DonorRecord', 'Synonym', 'SampleRecord']} })
    collected_from: Optional[CollectedFrom] = Field(default=None, description="""Absent where nothing names the sample's donor.""", json_schema_extra = { "linkml_meta": {'domain_of': ['SampleRecord']} })
    biosample_type: BiosampleTypeClassification = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SampleRecord']} })
    anatomical_site: AnatomicalSiteClassification = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['SampleRecord']} })
    repository_ids: Optional[list[RepositoryIdentifier]] = Field(default=None, description="""Every identifier a repository gave a record of its own for this sample (#669), AnVIL's `biosample_id`s. Absent where none ties to the sample.""", json_schema_extra = { "linkml_meta": {'domain_of': ['DonorRecord', 'SampleRecord']} })


class CollectedFrom(ConfiguredBaseModel):
    """
    The donor a sample was collected from, and every source that said so (#693): an identifier rule naming both a sample and a donor (`IdentifierRule.names`), cited by its id with `source_type: identifier_rule`, and an entity evidence line naming the sample's donor (`collected_from`, #559), cited by the identifier rule that recognised the donor, with the line's source. Sources naming different donors give none.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml'})

    donor: EntityIdentifier = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['CollectedFrom']} })
    named_by: list[Attribution] = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['GeneratedBy',
                       'ActivityInput',
                       'SampleReference',
                       'Synonym',
                       'CollectedFrom']} })


class ActivityDeclarations(ConfiguredBaseModel):
    """
    The shape of `rules/activities.yaml` (#580): per activity, its output and its input roles. Read through the generated model by `meta_disco.activities`.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml'})

    activities: list[ActivityDeclaration] = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityDeclarations']} })


class ActivityDeclaration(ConfiguredBaseModel):
    """
    One kind of step, its output, and its inputs by role.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml'})

    term: ActivityTypeEnum = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityDeclaration']} })
    output: Optional[ActivityEnd] = Field(default=None, description="""What the step makes. Absent: taken with `inputs` from the nearest `is_a` ancestor that declares both, which must be `abstract`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityDeclaration']} })
    inputs: Optional[list[InputRole]] = Field(default=None, description="""The step's input roles. Absent, with `output`: the term takes both from its nearest `is_a` ancestor that declares both, which must be `abstract` (#610).""", json_schema_extra = { "linkml_meta": {'domain_of': ['GeneratedBy', 'ActivityDeclaration']} })
    abstract: Optional[bool] = Field(default=None, description="""True for a term that only declares what its children pass; no step is written with it.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityDeclaration']} })
    reason: str = Field(default=..., description="""Why the step passes what it passes.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence', 'ActivityDeclaration']} })


class ActivityEnd(ConfiguredBaseModel):
    """
    An input or output of a step, a file or an identifier, and a file's kinds.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml'})

    form: list[ActivityFormEnum] = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityEnd']} })
    kind: Optional[list[DataTypeEnum]] = Field(default=None, description="""The `data_type` terms a file here may carry, dotted children included. Absent: any kind.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityEnd']} })


class InputRole(ActivityEnd):
    """
    One input role a kind of step declares, in `rules/activities.yaml`.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml'})

    role: str = Field(default=..., description="""The part the input plays (`reads`, `reference`, `indexed`).""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityInput', 'InputRole']} })
    required: bool = Field(default=..., description="""Whether the step always has this input.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InputRole']} })
    many: bool = Field(default=..., description="""Whether an output has several inputs in this role.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InputRole']} })
    passes: Optional[list[PassedDimensionEnum]] = Field(default=None, description="""What the output takes from an input in this role. Absent: nothing.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InputRole']} })
    read_through: Optional[str] = Field(default=None, description="""A role of the parent's own step whose inputs this role takes its values from, in place of the parent's own (#621): a sample map passes nothing itself, and a GenomicsDB workspace's `input_list` takes what the map's `member`s settle to. Absent: the parents' own answers.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InputRole']} })
    passes_samples: Optional[bool] = Field(default=None, description="""Whether the output takes its parent's settled `samples` (#668): an index, checksum, QC report or coverage track describes exactly its parent's samples, and a cohort's merge exactly its list's. Taken from the parent itself, never read through it. Absent: no samples pass.""", json_schema_extra = { "linkml_meta": {'domain_of': ['InputRole']} })
    form: list[ActivityFormEnum] = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityEnd']} })
    kind: Optional[list[DataTypeEnum]] = Field(default=None, description="""The `data_type` terms a file here may carry, dotted children included. Absent: any kind.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityEnd']} })


# Model rebuild
# see https://pydantic-docs.helpmanual.io/usage/models/#rebuilding-a-model
ClassificationRecord.model_rebuild()
Classifications.model_rebuild()
Classification.model_rebuild()
InferredConclusion.model_rebuild()
DataModalityInferred.model_rebuild()
DataTypeInferred.model_rebuild()
ReferenceAssemblyInferred.model_rebuild()
AssayTypeInferred.model_rebuild()
PlatformInferred.model_rebuild()
InstrumentModelInferred.model_rebuild()
VariantKindInferred.model_rebuild()
VariantOriginInferred.model_rebuild()
DataModalityClassification.model_rebuild()
DataTypeClassification.model_rebuild()
ReferenceAssemblyClassification.model_rebuild()
AssayTypeClassification.model_rebuild()
PlatformClassification.model_rebuild()
InstrumentModelClassification.model_rebuild()
VariantKindClassification.model_rebuild()
VariantOriginClassification.model_rebuild()
ReferenceBuild.model_rebuild()
ClaimSource.model_rebuild()
EvidenceFileSource.model_rebuild()
EvidenceTarget.model_rebuild()
EvidenceRow.model_rebuild()
LineageRow.model_rebuild()
EntityEvidenceRow.model_rebuild()
EvidenceFileEnvelope.model_rebuild()
Evidence.model_rebuild()
GeneratedBy.model_rebuild()
ActivityInput.model_rebuild()
Attribution.model_rebuild()
SampleReference.model_rebuild()
ExternalList.model_rebuild()
RebuiltList.model_rebuild()
Fileset.model_rebuild()
SampleList.model_rebuild()
EntityIdentifier.model_rebuild()
IdentifierRules.model_rebuild()
IdentifierRule.model_rebuild()
DonorRecord.model_rebuild()
Synonym.model_rebuild()
RepositoryIdentifier.model_rebuild()
PhenotypicSexClassification.model_rebuild()
GeneticAncestryClassification.model_rebuild()
OrganismTypeClassification.model_rebuild()
ReportedEthnicityClassification.model_rebuild()
BiosampleTypeClassification.model_rebuild()
AnatomicalSiteClassification.model_rebuild()
ParentClassification.model_rebuild()
ParentEvidence.model_rebuild()
FamilyIdClassification.model_rebuild()
SampleRecord.model_rebuild()
CollectedFrom.model_rebuild()
ActivityDeclarations.model_rebuild()
ActivityDeclaration.model_rebuild()
ActivityEnd.model_rebuild()
InputRole.model_rebuild()
