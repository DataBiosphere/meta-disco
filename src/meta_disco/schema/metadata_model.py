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
                    '`data/anvil/anvil_files_metadata.json`, as derived by '
                    '`scripts/download_anvil_manifest.py` from the compact Azul '
                    'manifest (#368) or by `snapshot_input.derive_records` from a '
                    "TDR snapshot's tables (#499). The envelope's `input_source` "
                    'says which.\n'
                    'This is the *input* to classification, distinct from '
                    '`classification.yaml` which models the classified *output*.\n'
                    'It models what classification consumes, and nothing else. '
                    "AnVIL's own published `data_modality` / `reference_assembly` "
                    'are therefore deliberately **not** slots here (#424): they '
                    'are the published output — the answer AnVIL publishes today, '
                    'which this project diffs its own answer against — and the '
                    'published importer writes them as evidence (claims contract '
                    '4.1 kind 2, #497) from the `anvil_file` table (today via the '
                    'verbatim manifest, 7.12), which no run reads yet (#432), '
                    'never from this record. They were modeled here until #424 and '
                    'dropped one step before classification, which is the bug that '
                    'issue describes; modeling them as input slots is what invited '
                    'it. They still arrive on every record, as unmodeled extra '
                    'keys, and the output model is where they are modeled — '
                    "`classification.yaml`'s `Published` block, which is also "
                    'where their list shape and their vocabulary standing are '
                    'stated.\n'
                    'Authoring source of truth. `make gen-metadata` (schema/ '
                    'project) generates the Pydantic model '
                    '`src/meta_disco/schema/metadata_model.py` from this file via '
                    '`gen-pydantic`. Unlike the output model, that generated '
                    'module is committed and shipped as package data because the '
                    'runtime imports it: `metadata_schema.py` validates every '
                    'record against it at load (issue #161). The field constraints '
                    'below are the measured contract of the current corpus '
                    '(708,088 records, anvil15): `file_size >= 0` (three zero-size '
                    'files), md5 lowercase-hex, drs_uri `drs://`-prefixed.\n'
                    'Records may carry keys beyond those modeled here — the two '
                    'declarations above, and the `organism_type` / '
                    '`phenotypic_sex` the download script also emits; the runtime '
                    'validator tolerates them (validates with `extra="ignore"`), '
                    'so an unmodeled column never fails a record.',
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
    One raw AnVIL file metadata record, before classification. Every slot but `entry_id` is required; the string slots are additionally non-empty (`file_size` allows 0 and `is_supplementary` is a plain required boolean). AnVIL's own published `data_modality` / `reference_assembly` are not slots here — see the schema description for why (#424).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'from_schema': 'https://github.com/DataBiosphere/meta-disco/blob/main/src/meta_disco/schema/metadata.yaml',
         'tree_root': True})

    entry_id: Optional[str] = Field(default=None, description="""The AnVIL Explorer catalog entry identifier: Azul's document id for the file in one index, regenerated when the catalog is re-indexed. Only the compact-manifest path emits it (`files.document_id`); a record derived from a TDR snapshot's tables — read in place or through the verbatim manifest (#499) — has none, because the snapshot predates the index. Nothing in a run keys on it since the record key became `file_id` (#446), so no source is required to carry it. Where present it is non-empty.""", json_schema_extra = { "linkml_meta": {'domain_of': ['AnvilFileMetadataRecord']} })
    file_id: str = Field(default=..., description="""The repository's own identifier for the file, and the durable one: unlike `entry_id` it is not regenerated when the catalog is re-indexed, so it is what a consumer joins on (#433). The handle a DRS resolver takes is `drs_uri`, which is carried separately because it does not always wrap this id.""", json_schema_extra = { "linkml_meta": {'domain_of': ['AnvilFileMetadataRecord']} })
    file_name: str = Field(default=..., description="""The file name.""", json_schema_extra = { "linkml_meta": {'domain_of': ['AnvilFileMetadataRecord']} })
    file_format: str = Field(default=..., description="""File extension / format label (e.g. bam, vcf.gz). 62 distinct values in the current corpus, including the literal \"Other\".""", json_schema_extra = { "linkml_meta": {'domain_of': ['AnvilFileMetadataRecord']} })
    file_size: int = Field(default=..., description="""File size in bytes. Zero is valid (three zero-size files exist).""", ge=0, json_schema_extra = { "linkml_meta": {'domain_of': ['AnvilFileMetadataRecord']} })
    file_md5sum: str = Field(default=..., description="""MD5 checksum of the file, lowercase hex.""", json_schema_extra = { "linkml_meta": {'domain_of': ['AnvilFileMetadataRecord']} })
    drs_uri: str = Field(default=..., description="""DRS URI for the file, used for S3 mirror access.""", json_schema_extra = { "linkml_meta": {'domain_of': ['AnvilFileMetadataRecord']} })
    dataset_id: str = Field(default=..., description="""Identifier of the dataset the file belongs to.""", json_schema_extra = { "linkml_meta": {'domain_of': ['AnvilFileMetadataRecord']} })
    dataset_title: str = Field(default=..., description="""Title of the dataset the file belongs to.""", json_schema_extra = { "linkml_meta": {'domain_of': ['AnvilFileMetadataRecord']} })
    is_supplementary: bool = Field(default=..., description="""Whether AnVIL flags the file as supplementary.""", json_schema_extra = { "linkml_meta": {'domain_of': ['AnvilFileMetadataRecord']} })

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
