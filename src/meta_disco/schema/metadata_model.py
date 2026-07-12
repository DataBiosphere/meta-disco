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
     'description': 'The contract for a raw AnVIL file metadata record — one entry '
                    'in the `files` array of '
                    '`data/anvil/anvil_files_metadata.json`, as produced by '
                    '`scripts/download_anvil_metadata.py` from the AnVIL Explorer '
                    'API.\n'
                    'This is the *input* to classification, distinct from '
                    '`classification.yaml` which models the classified *output*. '
                    'Kept in a separate schema so the input contract does not '
                    "entangle with the output's narrowed dimension ranges "
                    '(`data_modality` / `reference_assembly` are plain nullable '
                    'strings here — the values AnVIL itself declared — but object '
                    'ranges in the output model).\n'
                    'Authoring source of truth. `make gen-metadata` (schema/ '
                    'project) generates the Pydantic model '
                    '`src/meta_disco/schema/metadata_model.py` from this file via '
                    '`gen-pydantic`. Unlike the output model, that generated '
                    'module is committed and shipped as package data because the '
                    'runtime imports it: `metadata_schema.py` validates every '
                    'record against it at load (issue #161). The field constraints '
                    'below are the measured contract of the current corpus '
                    '(758,658 records): `file_size >= 0` (three zero-size files), '
                    '`data_modality` / `reference_assembly` nullable by design '
                    '(~99% null), md5 lowercase-hex, drs_uri `drs://`-prefixed.\n'
                    'Records may carry keys beyond those modeled here (e.g. the '
                    'download script also emits `organism_type` / '
                    '`phenotypic_sex`); the runtime validator tolerates them '
                    '(validates with `extra="ignore"`), so an unmodeled column '
                    'never fails a record.',
     'id': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/metadata.yaml',
     'imports': ['linkml:types'],
     'name': 'meta_disco_input_metadata',
     'prefixes': {'anvil': {'prefix_prefix': 'anvil',
                            'prefix_reference': 'https://github.com/DataBiosphere/meta-disco/schema/'},
                  'linkml': {'prefix_prefix': 'linkml',
                             'prefix_reference': 'https://w3id.org/linkml/'}},
     'source_file': '../src/meta_disco/schema/metadata.yaml',
     'title': 'Meta-Disco AnVIL Input Metadata Model'} )


class AnvilFileMetadataRecord(ConfiguredBaseModel):
    """
    One raw AnVIL file metadata record, before classification. Every slot but the nullable AnVIL declarations (`data_modality`, `reference_assembly`) is required; the string slots are additionally non-empty (`file_size` allows 0 and `is_supplementary` is a plain required boolean).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/metadata.yaml',
         'tree_root': True})

    entry_id: str = Field(default=..., description="""The AnVIL Explorer catalog entry identifier.""", json_schema_extra = { "linkml_meta": {'domain_of': ['AnvilFileMetadataRecord']} })
    file_id: str = Field(default=..., description="""The file identifier within the entry.""", json_schema_extra = { "linkml_meta": {'domain_of': ['AnvilFileMetadataRecord']} })
    file_name: str = Field(default=..., description="""The file name.""", json_schema_extra = { "linkml_meta": {'domain_of': ['AnvilFileMetadataRecord']} })
    file_format: str = Field(default=..., description="""File extension / format label (e.g. bam, vcf.gz). 62 distinct values in the current corpus, including the literal \"Other\".""", json_schema_extra = { "linkml_meta": {'domain_of': ['AnvilFileMetadataRecord']} })
    file_size: int = Field(default=..., description="""File size in bytes. Zero is valid (three zero-size files exist).""", ge=0, json_schema_extra = { "linkml_meta": {'domain_of': ['AnvilFileMetadataRecord']} })
    file_md5sum: str = Field(default=..., description="""MD5 checksum of the file, lowercase hex.""", json_schema_extra = { "linkml_meta": {'domain_of': ['AnvilFileMetadataRecord']} })
    drs_uri: str = Field(default=..., description="""DRS URI for the file, used for S3 mirror access.""", json_schema_extra = { "linkml_meta": {'domain_of': ['AnvilFileMetadataRecord']} })
    dataset_id: str = Field(default=..., description="""Identifier of the dataset the file belongs to.""", json_schema_extra = { "linkml_meta": {'domain_of': ['AnvilFileMetadataRecord']} })
    dataset_title: str = Field(default=..., description="""Title of the dataset the file belongs to.""", json_schema_extra = { "linkml_meta": {'domain_of': ['AnvilFileMetadataRecord']} })
    is_supplementary: bool = Field(default=..., description="""Whether AnVIL flags the file as supplementary.""", json_schema_extra = { "linkml_meta": {'domain_of': ['AnvilFileMetadataRecord']} })
    data_modality: Optional[str] = Field(default=None, description="""AnVIL's own declared data modality, or null. Nullable by design — absent for most files (~99% of the corpus).""", json_schema_extra = { "linkml_meta": {'domain_of': ['AnvilFileMetadataRecord']} })
    reference_assembly: Optional[str] = Field(default=None, description="""AnVIL's own declared reference assembly, or null. Nullable by design — absent for most files (~99% of the corpus).""", json_schema_extra = { "linkml_meta": {'domain_of': ['AnvilFileMetadataRecord']} })

    @field_validator('entry_id')
    def pattern_entry_id(cls, v):
        pattern=re.compile(r"^.+$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid entry_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid entry_id format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('file_id')
    def pattern_file_id(cls, v):
        pattern=re.compile(r"^.+$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid file_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid file_id format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('file_name')
    def pattern_file_name(cls, v):
        pattern=re.compile(r"^.+$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid file_name format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid file_name format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('file_format')
    def pattern_file_format(cls, v):
        pattern=re.compile(r"^.+$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid file_format format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid file_format format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('file_md5sum')
    def pattern_file_md5sum(cls, v):
        pattern=re.compile(r"^[0-9a-f]{32}$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid file_md5sum format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid file_md5sum format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('drs_uri')
    def pattern_drs_uri(cls, v):
        pattern=re.compile(r"^drs://")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid drs_uri format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid drs_uri format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('dataset_id')
    def pattern_dataset_id(cls, v):
        pattern=re.compile(r"^.+$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid dataset_id format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid dataset_id format: {v}"
            raise ValueError(err_msg)
        return v

    @field_validator('dataset_title')
    def pattern_dataset_title(cls, v):
        pattern=re.compile(r"^.+$")
        if isinstance(v, list):
            for element in v:
                if isinstance(element, str) and not pattern.match(element):
                    err_msg = f"Invalid dataset_title format: {element}"
                    raise ValueError(err_msg)
        elif isinstance(v, str) and not pattern.match(v):
            err_msg = f"Invalid dataset_title format: {v}"
            raise ValueError(err_msg)
        return v


# Model rebuild
# see https://pydantic-docs.helpmanual.io/usage/models/#rebuilding-a-model
AnvilFileMetadataRecord.model_rebuild()
