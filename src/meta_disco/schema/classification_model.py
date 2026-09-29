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
     'description': 'Full classification data model for meta-disco: the six '
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
                  'MODAL': {'prefix_prefix': 'MODAL',
                            'prefix_reference': 'https://datamodel.terra.bio/BioCoreTerms#'},
                  'OBI': {'prefix_prefix': 'OBI',
                          'prefix_reference': 'http://purl.obolibrary.org/obo/OBI_'},
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
    The biological signal a file carries: "the biological nature of the information gathered as the result of an Activity, independent of the technology or methods used to produce the information", in the words of AnVIL's Findability Subset (FSS), whose recommended values for its `data_modality` field are the Broad's MODAL ontology (github.com/broadinstitute/modal) term for term (#563). This enum is that tree: each value spells its MODAL term as a dotted path, `is_a` names its parent, and `meaning` is its MODAL id. The dotted value stands in for FSS's wording ("DNA methylation" for `epigenomic.methylation`) until labels are added. Single-cell versus bulk is not a modality here, since it is a property of the experiment, so `assay_type` records it (`sc/snRNA-seq`, `snRNA-seq`, #533). A record holds one term, the most specific its evidence supports, which may be a parent: nothing emits a `genomic` child yet, so a WGS library is `genomic`. A consumer that filters on a parent walks `is_a`.
    """
    genomic = "genomic"
    genomicFULL_STOPassembly = "genomic.assembly"
    genomicFULL_STOPexome = "genomic.exome"
    genomicFULL_STOPgenotyping = "genomic.genotyping"
    genomicFULL_STOPwhole_genome = "genomic.whole_genome"
    transcriptomic = "transcriptomic"
    transcriptomicFULL_STOPspatial = "transcriptomic.spatial"
    transcriptomicFULL_STOPnontargeted = "transcriptomic.nontargeted"
    transcriptomicFULL_STOPtargeted = "transcriptomic.targeted"
    epigenomic = "epigenomic"
    epigenomicFULL_STOP3d_contact_maps = "epigenomic.3d_contact_maps"
    epigenomicFULL_STOPdna_binding = "epigenomic.dna_binding"
    epigenomicFULL_STOPdna_bindingFULL_STOPhistone_modification = "epigenomic.dna_binding.histone_modification"
    epigenomicFULL_STOPdna_bindingFULL_STOPtranscription_factor = "epigenomic.dna_binding.transcription_factor"
    epigenomicFULL_STOPchromatin_accessibility = "epigenomic.chromatin_accessibility"
    epigenomicFULL_STOPmethylation = "epigenomic.methylation"
    epigenomicFULL_STOPrna_binding = "epigenomic.rna_binding"
    imaging = "imaging"
    imagingFULL_STOPelectrophysiology = "imaging.electrophysiology"
    imagingFULL_STOPmedical_imaging = "imaging.medical_imaging"
    imagingFULL_STOPmedical_imagingFULL_STOPct_scan = "imaging.medical_imaging.ct_scan"
    imagingFULL_STOPmedical_imagingFULL_STOPelectrocardiogram = "imaging.medical_imaging.electrocardiogram"
    imagingFULL_STOPmedical_imagingFULL_STOPmri = "imaging.medical_imaging.mri"
    imagingFULL_STOPmedical_imagingFULL_STOPx_ray = "imaging.medical_imaging.x_ray"
    imagingFULL_STOPmicroscopy = "imaging.microscopy"
    metabolomic = "metabolomic"
    microbiome = "microbiome"
    proteomic = "proteomic"


class DataTypeEnum(str, Enum):
    """
    Content type, spanning two classes. BIOLOGICAL: the bytes are the signal. DESCRIPTIVE: the bytes are about another file. (See data-model doc 8c.)
    """
    alignments = "alignments"
    reads = "reads"
    sequence = "sequence"
    assembly = "assembly"
    assemblyFULL_STOPreference = "assembly.reference"
    pangenome = "pangenome"
    pangenomeFULL_STOPreference = "pangenome.reference"
    variants = "variants"
    variantsFULL_STOPgermline = "variants.germline"
    variantsFULL_STOPsomatic = "variants.somatic"
    variantsFULL_STOPstructural = "variants.structural"
    variantsFULL_STOPcnv = "variants.cnv"
    genotypes = "genotypes"
    expression_matrix = "expression_matrix"
    quantification = "quantification"
    annotations = "annotations"
    annotationsFULL_STOPcoverage = "annotations.coverage"
    """
    Read depth along the genome, measured from an alignment: per base or per window, raw or normalized (e.g. a mosdepth `regions.bed.gz`, or a STAR `Signal.Unique.strand+.bw`). No `meaning`: EDAM has no data term for coverage or read depth, only the process (operation_3230).
    """
    peaks = "peaks"
    raw_signal = "raw_signal"
    array_signal = "array_signal"
    images = "images"
    index = "index"
    checksum = "checksum"
    qc_report = "qc_report"
    """
    A quality-control report about another file, such as samtools stats, a mosdepth summary or distribution, or bcftools stats.
    """
    log = "log"
    interval_set = "interval_set"


class ReferenceAssemblyEnum(str, Enum):
    """
    Reference assemblies, named as NCBI names them (issue #473). A file gets the most specific term its evidence supports, and `is_a` records the terms as a hierarchy. A record carries only its own term, so a filter on a parent includes the terms below it only where the consumer walks the hierarchy (`schema_vocab.value_ancestors`); `value == "CHM13"` alone does not.
GRC assemblies are named at the major release: contig lengths are identical across patch releases, so contig lengths can never tell a patch (#399). Where a header's declared reference name does tell one, the patch stays on `ReferenceBuild.version`. `CHM13` is every CHM13 release, and is also the term for a CHM13 file whose release cannot be told. Under it are NCBI's T2T releases, and under each release the references that graft another genome's chrY onto it. NCBI names none of those hybrids, so each is spelled as the reference FASTA that files declare, extension dropped. A hybrid is its own coordinate system on chrY and its parent release everywhere else, which is why it sits under that release.
`meaning` is recorded where one term is one NCBI assembly: the three T2T releases. The GRC terms each span their patch releases, and `CHM13` spans the T2T releases.
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
    t2t_chm13FULL_STOP20200921FULL_STOPwithGRCh38chrYFULL_STOPchrEBVFULL_STOPchrYKI270740v1r = "t2t-chm13.20200921.withGRCh38chrY.chrEBV.chrYKI270740v1r"
    """
    T2T-CHM13v1.0 with GRCh38's chrY grafted on.
    """
    CHM13Y_EBV_v1FULL_STOP1 = "CHM13Y_EBV_v1.1"
    """
    T2T-CHM13v1.1 with GRCh38's chrY grafted on.
    """
    t2t_chm13FULL_STOP20200921FULL_STOPHG002chrYFULL_STOPchrEBV = "t2t-chm13.20200921.HG002chrY.chrEBV"
    """
    T2T-CHM13v1.0 with HG002's chrY grafted on.
    """


class ReferenceFamilyEnum(str, Enum):
    """
    The assembly families: the `reference_assembly_enum` terms with no `is_a` parent, which `ReferenceBuild.base` ranges over (#473). A release or a hybrid is a value, never a family. `tests/test_rule_vocabulary.py` holds this list to those terms.
    """
    GRCh37 = "GRCh37"
    GRCh38 = "GRCh38"
    CHM13 = "CHM13"


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
    WGS = "WGS"
    """
    EFO's whole genome shotgun sequencing: EFO has no term labelled whole genome sequencing, and OBI's whole genome sequencing assay is not among its imports.
    """
    WES = "WES"
    RNA_seq = "RNA-seq"
    scSOLIDUSsnRNA_seq = "sc/snRNA-seq"
    """
    Single-cell or single-nucleus RNA-seq, EFO's parent of both: the term for a file whose evidence says single-cell but not which.
    """
    snRNA_seq = "snRNA-seq"
    SHARE_seq = "SHARE-seq"
    """
    Joint chromatin accessibility and RNA from the same nuclei.
    """
    ATAC_seq = "ATAC-seq"
    scSOLIDUSsnATAC_seq = "sc/snATAC-seq"
    snATAC_seq = "snATAC-seq"
    """
    Single-nucleus ATAC-seq. Our own term: EFO's children of sc/snATAC-seq are single-cell only, so no EFO term is as narrow, and it records none.
    """
    ChIP_seq = "ChIP-seq"
    Bisulfite_seq = "Bisulfite-seq"
    Methylation_array = "Methylation array"
    Histology = "Histology"


class PlatformEnum(str, Enum):
    ILLUMINA = "ILLUMINA"
    PACBIO = "PACBIO"
    ONT = "ONT"
    MGI = "MGI"
    ELEMENT = "ELEMENT"
    ULTIMA = "ULTIMA"


class InstrumentModelEnum(str, Enum):
    """
    Sequencing instrument models, spelled exactly as ENA/SRA's controlled `INSTRUMENT_MODEL` strings (SRA.common.xsd, enasequence/schema) for the platforms in `platform_enum`; SRA's `unspecified` is not a model and is not here (a file whose model is unknown is `not_classified`). `meaning` is the EFO term whose label names the same model, recorded where EFO has one and never followed at run time. Where EFO's nearest term is broader or narrower (its one `Illumina HiSeq X` for SRA's `HiSeq X Five` / `HiSeq X Ten`, its `ONT GridION X5` for SRA's `GridION`) no meaning is recorded.
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
    The kind of step that made a file (ADR-0002, #580): AnVIL FSS's `ActivityTypes` as its released LinkML schema spells them, plus four of our own, each under the FSS term it narrows. `meaning` is TerraCore's class, else EDAM's operation for the same step; a near EDAM operation is a close mapping. What each passes is in `rules/activities.yaml`.
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
    LiftoverActivity = "LiftoverActivity"
    """
    Moving a file's coordinates to another reference. Our own term; neither TerraCore nor EDAM has one.
    """
    MergeActivity = "MergeActivity"
    """
    Joining several files of one kind into one: window VCFs into a chromosome VCF, FASTQs into one. Our own term; EDAM's Sequence merging (operation_0232) merges sequences, not files.
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
    The dimensions an activity's output can take from an input (#580): the six classification dimensions but `data_type`, which names a file's own kind and never passes (ADR-0002 decision 8: a VCF is not an alignment).
    """
    data_modality = "data_modality"
    platform = "platform"
    reference_assembly = "reference_assembly"
    assay_type = "assay_type"
    instrument_model = "instrument_model"


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
    published_value = "published_value"
    """
    The value the repository's own system of record publishes for the file (#497) — AnVIL's harmonized `anvil_file` columns, today read as the verbatim manifest copies that TDR table (claims contract 7.12). Distinct from `repository_metadata` so a reader of a conflict can tell the repository's official value from a submitter's opinion.
    """
    wrangler_annotation = "wrangler_annotation"
    """
    A human curator's decision, recorded deliberately rather than inferred.
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
    published_value = "published_value"
    """
    As in `source_type_enum`.
    """


class ClaimStateEnum(str, Enum):
    """
    Why a claim that consulted a source produced no vocabulary value (issue #392). Each state was observed in the spike over three real producers on `AnVIL_HPRC_R2`. None of them declares a value, so none competes in resolution. `mapped` is not a member: a claim that mapped carries a `value`, and `not_applicable` / `not_classified` remain statuses, unchanged.
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
    archive_accession = "archive_accession"
    """
    Sequence-archive run accession (ENA, SRA). Not a field of the input record but a fact classification *derives*, read from a fastq's read headers — accessions appear in no input file name at all. A claim from an archive can be attached only by this, which is why the join runs after inference rather than over the input corpus.
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
    One classified file. `classifications` carries the file's identity (the six dimension fields — what it is); generated_by names the step that made it and the files it used (where it came from; ADR-0002). Matches the pipeline output shape.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'tree_root': True})

    md5sum: str = Field(default=..., description="""MD5 checksum of the file; primary key for records.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClassificationRecord']} })
    file_name: Optional[str] = Field(default=None, description="""The file name.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClassificationRecord']} })
    file_format: Optional[str] = Field(default=None, description="""File extension / compound extension (e.g. .bam, .vcf.gz).""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClassificationRecord']} })
    file_size: Optional[int] = Field(default=None, description="""File size in bytes.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClassificationRecord']} })
    entry_id: Optional[str] = Field(default=None, description="""Source catalog entry identifier the record was classified from: Azul's per-index document id. Where present it is unique within a run and regenerated when the catalog is re-indexed, so it scopes a weaker key rather than outliving a refresh (#433). Null on a record whose input came from a TDR snapshot's tables rather than the compact manifest (#499), and on every HPRC record. An AnVIL record's durable identity is `file_id`; an HPRC record's is the URL hash it carries in `md5sum` (`pipeline.SOURCE_RECORD_KEYS`).""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClassificationRecord']} })
    file_id: Optional[str] = Field(default=None, description="""The repository's own file identifier, and the durable one: it survives a catalog re-index, which `entry_id` does not (#433). It is the join key, not the handle a resolver takes — that is `drs_uri`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClassificationRecord']} })
    drs_uri: Optional[str] = Field(default=None, description="""The file's DRS URI: what a resolver dereferences to reach the bytes. Carried, never derived from `file_id` — thousands of records wrap a different object id, so a reconstructed URI resolves to the wrong file or to nothing (#433).""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClassificationRecord']} })
    dataset_title: Optional[str] = Field(default=None, description="""Title of the dataset the file belongs to.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClassificationRecord']} })
    classifications: Classifications = Field(default=..., description="""The six classified dimensions for this file.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClassificationRecord']} })
    generated_by: Optional[GeneratedBy] = Field(default=None, description="""The step that made the file and the inputs it used, by role (ADR-0002 decisions 3, 6, #580); null where no parent resolves.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClassificationRecord']} })


class Classifications(ConfiguredBaseModel):
    """
    The six metadata dimensions for one file, each a Classification entry. The pipeline also emits some file-type-specific scalar hints here (e.g. fastq's is_paired_end / instrument_hint); those are not modeled yet and pass under the gate's closed=False mode (see #134 follow-up).
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
                                               'required': True}}})

    data_modality: DataModalityClassification = Field(default=..., description="""The biological signal the file carries.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classifications']} })
    data_type: DataTypeClassification = Field(default=..., description="""The content type of the file (biological or descriptive class).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classifications']} })
    reference_assembly: ReferenceAssemblyClassification = Field(default=..., description="""The reference genome the file's coordinates are expressed against.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classifications']} })
    assay_type: AssayTypeClassification = Field(default=..., description="""The experimental assay that produced the upstream data.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classifications']} })
    platform: PlatformClassification = Field(default=..., description="""The sequencing platform / instrument family.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classifications']} })
    instrument_model: InstrumentModelClassification = Field(default=..., description="""The sequencing instrument's model, refining `platform` (#532): `Illumina NovaSeq 6000` where `platform` says `ILLUMINA`. Not applicable wherever `platform` is not.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classifications']} })


class Classification(ConfiguredBaseModel):
    """
    A single classified field: its resolved value (null unless status is 'classified'), a status sentinel, and the evidence behind it. Subclasses narrow `value` to the right enum per dimension. A reconciled record (#432) carries the same entry plus `use`, `inferred` and `credited_to` (#552); an inference record carries none of them.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'abstract': True,
         'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml'})

    value: Optional[str] = Field(default=None, description="""The resolved value; null unless status is 'classified'.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    status: ClassificationStatusEnum = Field(default=..., description="""Whether the field was classified, is not applicable, etc.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    evidence: Optional[list[Evidence]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    use: Optional[UseEnum] = Field(default=None, description="""On a reconciled record only (#432): whether the indexer takes this record's value (`meta_disco`, when the status is `classified` or `not_applicable`) or keeps the repository's published value (`published`, when it is `conflict` or `not_classified`). Computed by reconcile so an export is structure only.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
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


class DataModalityClassification(Classification):
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'slot_usage': {'inferred': {'name': 'inferred',
                                     'range': 'DataModalityInferred'},
                        'value': {'name': 'value', 'range': 'data_modality_enum'}}})

    value: Optional[DataModalityEnum] = Field(default=None, description="""The resolved value; null unless status is 'classified'.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    status: ClassificationStatusEnum = Field(default=..., description="""Whether the field was classified, is not applicable, etc.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    evidence: Optional[list[Evidence]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    use: Optional[UseEnum] = Field(default=None, description="""On a reconciled record only (#432): whether the indexer takes this record's value (`meta_disco`, when the status is `classified` or `not_applicable`) or keeps the repository's published value (`published`, when it is `conflict` or `not_classified`). Computed by reconcile so an export is structure only.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    inferred: Optional[DataModalityInferred] = Field(default=None, description="""On a reconciled record only (#432): what inference concluded for this slot.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    credited_to: Optional[CreditedToEnum] = Field(default=None, description="""On a reconciled record only (#552): where this slot's answer is credited, the per-slot category the reconcile report counts. The rule is `reconcile.credited_to`'s. It attributes and never decides: the value was settled before it is read.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })


class DataTypeClassification(Classification):
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'slot_usage': {'inferred': {'name': 'inferred', 'range': 'DataTypeInferred'},
                        'value': {'name': 'value', 'range': 'data_type_enum'}}})

    value: Optional[DataTypeEnum] = Field(default=None, description="""The resolved value; null unless status is 'classified'.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    status: ClassificationStatusEnum = Field(default=..., description="""Whether the field was classified, is not applicable, etc.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    evidence: Optional[list[Evidence]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    use: Optional[UseEnum] = Field(default=None, description="""On a reconciled record only (#432): whether the indexer takes this record's value (`meta_disco`, when the status is `classified` or `not_applicable`) or keeps the repository's published value (`published`, when it is `conflict` or `not_classified`). Computed by reconcile so an export is structure only.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
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
    use: Optional[UseEnum] = Field(default=None, description="""On a reconciled record only (#432): whether the indexer takes this record's value (`meta_disco`, when the status is `classified` or `not_applicable`) or keeps the repository's published value (`published`, when it is `conflict` or `not_classified`). Computed by reconcile so an export is structure only.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    inferred: Optional[ReferenceAssemblyInferred] = Field(default=None, description="""On a reconciled record only (#432): what inference concluded for this slot.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    credited_to: Optional[CreditedToEnum] = Field(default=None, description="""On a reconciled record only (#552): where this slot's answer is credited, the per-slot category the reconcile report counts. The rule is `reconcile.credited_to`'s. It attributes and never decides: the value was settled before it is read.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })


class AssayTypeClassification(Classification):
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'slot_usage': {'inferred': {'name': 'inferred', 'range': 'AssayTypeInferred'},
                        'value': {'name': 'value', 'range': 'assay_type_enum'}}})

    value: Optional[AssayTypeEnum] = Field(default=None, description="""The resolved value; null unless status is 'classified'.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    status: ClassificationStatusEnum = Field(default=..., description="""Whether the field was classified, is not applicable, etc.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    evidence: Optional[list[Evidence]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    use: Optional[UseEnum] = Field(default=None, description="""On a reconciled record only (#432): whether the indexer takes this record's value (`meta_disco`, when the status is `classified` or `not_applicable`) or keeps the repository's published value (`published`, when it is `conflict` or `not_classified`). Computed by reconcile so an export is structure only.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    inferred: Optional[AssayTypeInferred] = Field(default=None, description="""On a reconciled record only (#432): what inference concluded for this slot.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    credited_to: Optional[CreditedToEnum] = Field(default=None, description="""On a reconciled record only (#552): where this slot's answer is credited, the per-slot category the reconcile report counts. The rule is `reconcile.credited_to`'s. It attributes and never decides: the value was settled before it is read.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })


class PlatformClassification(Classification):
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'slot_usage': {'inferred': {'name': 'inferred', 'range': 'PlatformInferred'},
                        'value': {'name': 'value', 'range': 'platform_enum'}}})

    value: Optional[PlatformEnum] = Field(default=None, description="""The resolved value; null unless status is 'classified'.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    status: ClassificationStatusEnum = Field(default=..., description="""Whether the field was classified, is not applicable, etc.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification', 'InferredConclusion', 'Evidence']} })
    evidence: Optional[list[Evidence]] = Field(default=None, json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    use: Optional[UseEnum] = Field(default=None, description="""On a reconciled record only (#432): whether the indexer takes this record's value (`meta_disco`, when the status is `classified` or `not_applicable`) or keeps the repository's published value (`published`, when it is `conflict` or `not_classified`). Computed by reconcile so an export is structure only.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
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
    use: Optional[UseEnum] = Field(default=None, description="""On a reconciled record only (#432): whether the indexer takes this record's value (`meta_disco`, when the status is `classified` or `not_applicable`) or keeps the repository's published value (`published`, when it is `conflict` or `not_classified`). Computed by reconcile so an export is structure only.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
    inferred: Optional[InstrumentModelInferred] = Field(default=None, description="""On a reconciled record only (#432): what inference concluded for this slot.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Classification']} })
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
Carried on the claim and not only on the evidence file's envelope because it is what makes `column` legible: the same column name means different things in different datasets, and a consumer reading this evidence cannot go back to the file the claim arrived in (#401).""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClaimSource', 'EvidenceFileSource', 'EvidenceTarget']} })
    table: Optional[str] = Field(default=None, description="""The table or file within the source that the claim came from, e.g. an AnVIL verbatim manifest table name. Null when the source is a single undivided file.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClaimSource', 'EvidenceFileSource']} })
    column: Optional[str] = Field(default=None, description="""The column within that table the raw value was read from. Null when the source has no column structure.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClaimSource', 'EvidenceRow']} })

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

    repository: str = Field(default=..., description="""What publishes the source — `AnVIL`, `HPRC Data Explorer`, `ENA`. Required and non-empty: a source that names no repository identifies nothing.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidenceFileSource']} })
    dataset: Optional[str] = Field(default=None, description="""The collection within that repository the claims were read from. Null for a source with no such level.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClaimSource', 'EvidenceFileSource', 'EvidenceTarget']} })
    table: Optional[str] = Field(default=None, description="""The table or file within the dataset — `alignments_v2`, `sequencing-data`, ENA's `read_run`. Null for a source with no table structure. The column within it stays on each claim.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClaimSource', 'EvidenceFileSource']} })
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
Null for a source whose key is unique across the whole target (`file_id`, `entry_id`, `drs_uri`), where a corpus-wide match is correct.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClaimSource', 'EvidenceFileSource', 'EvidenceTarget']} })
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
No pattern and no enum, deliberately: a source's spellings are its own, a value our vocabulary has no word for is the review queue's input rather than an error (contract 3.7), and an empty cell is something the source published, whose meaning is a rule's to decide.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidenceRow', 'Evidence']} })
    field: str = Field(default=..., description="""The slot this row speaks to, spelled `field` on the wire and in the code (contract 2.1). One of the six classification dimensions.
Pinned by pattern rather than by an enum because the dimension names are slot *names* in this schema and not a vocabulary it declares; `test_the_row_field_pattern_lists_every_dimension` holds it to `CLASSIFICATION_FIELDS`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidenceRow']} })
    target_key_value: str = Field(default=..., description="""The value to match against the envelope's `target_key`, already in the target's value space — the importer owns the mapping between its own key and the target's. Empty is refused: a row with nothing to match on can attach to no file.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidenceRow']} })
    column: Optional[str] = Field(default=None, description="""The column the raw value was read from. The one member of the source that varies within a file — repository, dataset, table and url are on the envelope — and absent for a source whose table has no columns to name.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ClaimSource', 'EvidenceRow']} })

    @field_validator('field')
    def pattern_field(cls, v):
        pattern=re.compile(r"^(data_modality|data_type|platform|reference_assembly|assay_type|instrument_model)\Z")
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
    target_key: JoinKeyEnum = Field(default=..., description="""Which key of the target each line's `target_key_value` is to be matched against. Drawn from `join_key_enum`, which spans the target's own record fields *and* facts classification derives — `archive_accession` is read from a fastq's read headers, so a claim keyed by it can only be joined after inference has run.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidenceFileEnvelope']} })
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
    A claim from one of our rules or content classifiers carries rule_id + tier. A claim from an external source (issue #392) carries `source` as well as a rule_id — the mapping entry it fired, not a rule of ours — and no tier, because an import does not compete on the rule ladder (#401). It carries the raw value it read and, once the join has run, how it was matched to our file. Evidence that is neither — the note left when a fetch or the input contract failed — carries a rule_id and a reason but declares nothing.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'slot_usage': {'status': {'name': 'status', 'required': False}}})

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
    raw_value: Optional[str] = Field(default=None, description="""What the source actually said, before mapping — `Revio` beside a mapped `PACBIO`. The mapping is the reviewable decision, and storing only the mapped value makes it unauditable. Also present on an `unmapped` or `no_vocabulary_term` claim, where it is the whole content of the claim.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidenceRow', 'Evidence']} })
    join_key: Optional[JoinKeyEnum] = Field(default=None, description="""Which key attached this claim to our file. Recorded per claim rather than per source because identity is the risky step and sources publish different keys: md5 collides on 1.72% of the corpus's rows and the HPRC catalog publishes only file names (#390). Absent on a claim our own inference produced, which was never joined to anything.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence']} })
    match_exact: Optional[bool] = Field(default=None, description="""Whether the join on `join_key` was an exact match rather than a normalized or partial one. Absent whenever `join_key` is.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence']} })


class GeneratedBy(ConfiguredBaseModel):
    """
    The one step that made a file and the inputs it used (PROV's `wasGeneratedBy` and `used`, ADR-0002 decision 3, #580). `named_by` lists every source that named the step; each input lists its own.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml'})

    activity: ActivityTypeEnum = Field(default=..., description="""The kind of step that made the file (`activity_type_enum`); what passes from each input role is declared per term in `rules/activities.yaml`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['GeneratedBy']} })
    named_by: list[Attribution] = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['GeneratedBy', 'ActivityInput']} })
    inputs: list[ActivityInput] = Field(default=..., description="""The inputs the step used, each in one of the roles its activity declares.""", json_schema_extra = { "linkml_meta": {'domain_of': ['GeneratedBy', 'ActivityDeclaration']} })


class ActivityInput(ConfiguredBaseModel):
    """
    One input a step used, in one role (PROV's `hadRole`). With `parent_key` it is `internal`, without it `external` (ADR-0002 decision 2).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'slot_usage': {'parent_file': {'name': 'parent_file', 'required': True}}})

    parent_file: str = Field(default=..., description="""The input file's name: the matched record's own spelling where the input resolves (a file-name rule matches case-insensitively, so it may differ in case from the name worked out from the child), otherwise as the source that names the input wrote it.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityInput']} })
    parent_key: Optional[str] = Field(default=None, description="""The parent's record key (`pipeline.SOURCE_RECORD_KEYS`: AnVIL's `file_id`, HPRC's URL hash in `md5sum`), set only when the parent resolves to exactly one record of the child's dataset (ADR-0002 decision 2). Named for the key rather than `parent_file_id` because HPRC's key is not a `file_id`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityInput']} })
    parent_kind: Optional[ParentKindEnum] = Field(default=None, description="""The kind of file the parent is.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityInput']} })
    role: str = Field(default=..., description="""One of the roles its activity declares in `rules/activities.yaml`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityInput', 'InputRole']} })
    named_by: list[Attribution] = Field(default=..., json_schema_extra = { "linkml_meta": {'domain_of': ['GeneratedBy', 'ActivityInput']} })


class Attribution(ConfiguredBaseModel):
    """
    One source that named a step or an input (ADR-0002 decision 6): sources that agree are each listed.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/classification.yaml',
         'slot_usage': {'rule_id': {'description': 'The rule or translation row that '
                                                   'turned what the source says into '
                                                   'this step or input '
                                                   '(`code_rules.EDGE_RULES` for '
                                                   "inference's).",
                                    'name': 'rule_id',
                                    'required': True},
                        'source_type': {'name': 'source_type', 'required': True}}})

    source_type: SourceTypeEnum = Field(default=..., description="""Kind of source that produced this claim (provenance, #90; populated on every claim by #392) — see `source_type_enum` for the kinds. Absent on a synthetic marker and on the note left by a failed fetch or input contract, neither of which is a claim.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidenceFileEnvelope', 'Evidence', 'Attribution']} })
    rule_id: str = Field(default=..., description="""The rule or translation row that turned what the source says into this step or input (`code_rules.EDGE_RULES` for inference's).""", json_schema_extra = { "linkml_meta": {'domain_of': ['Evidence', 'Attribution']} })
    activity_id: Optional[str] = Field(default=None, description="""The source's own id for the step (`anvil_activity.activity_id`), where it gives one.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Attribution']} })
    source: Optional[ClaimSource] = Field(default=None, description="""The external source that produced this claim, for a claim that is not from one of our rules. Absent on a rule or content claim, which carries `rule_id`.""", json_schema_extra = { "linkml_meta": {'domain_of': ['EvidenceFileEnvelope', 'Evidence', 'Attribution']} })


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
    output: ActivityEnd = Field(default=..., description="""What the step makes.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ActivityDeclaration']} })
    inputs: list[InputRole] = Field(default=..., description="""The step's input roles.""", json_schema_extra = { "linkml_meta": {'domain_of': ['GeneratedBy', 'ActivityDeclaration']} })
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
DataModalityClassification.model_rebuild()
DataTypeClassification.model_rebuild()
ReferenceAssemblyClassification.model_rebuild()
AssayTypeClassification.model_rebuild()
PlatformClassification.model_rebuild()
InstrumentModelClassification.model_rebuild()
ReferenceBuild.model_rebuild()
ClaimSource.model_rebuild()
EvidenceFileSource.model_rebuild()
EvidenceTarget.model_rebuild()
EvidenceRow.model_rebuild()
EvidenceFileEnvelope.model_rebuild()
Evidence.model_rebuild()
GeneratedBy.model_rebuild()
ActivityInput.model_rebuild()
Attribution.model_rebuild()
ActivityDeclarations.model_rebuild()
ActivityDeclaration.model_rebuild()
ActivityEnd.model_rebuild()
InputRole.model_rebuild()
