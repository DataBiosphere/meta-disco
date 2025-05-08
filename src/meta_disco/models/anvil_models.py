# Auto generated from anvil_file.yaml by pythongen.py version: 0.0.1
# Generation date: 2025-04-27T02:47:57
# Schema: anvil_file
#
# id: http://example.org/anvil_file
# description:
# license: https://creativecommons.org/publicdomain/zero/1.0/

import dataclasses
import re
from dataclasses import dataclass
from datetime import (
    date,
    datetime,
    time
)
from typing import (
    Any,
    ClassVar,
    Dict,
    List,
    Optional,
    Union
)

from jsonasobj2 import (
    JsonObj,
    as_dict
)
from linkml_runtime.linkml_model.meta import (
    EnumDefinition,
    PermissibleValue,
    PvFormulaOptions
)
from linkml_runtime.utils.curienamespace import CurieNamespace
from linkml_runtime.utils.enumerations import EnumDefinitionImpl
from linkml_runtime.utils.formatutils import (
    camelcase,
    sfx,
    underscore
)
from linkml_runtime.utils.metamodelcore import (
    bnode,
    empty_dict,
    empty_list
)
from linkml_runtime.utils.slot import Slot
from linkml_runtime.utils.yamlutils import (
    YAMLRoot,
    extended_float,
    extended_int,
    extended_str
)
from rdflib import (
    Namespace,
    URIRef
)

from linkml_runtime.linkml_model.types import String, Uriorcurie
from linkml_runtime.utils.metamodelcore import URIorCURIE

metamodel_version = "1.7.0"
version = None

# Namespaces
EX = CurieNamespace('ex', 'http://anvilproject.org/')
LINKML = CurieNamespace('linkml', 'https://w3id.org/linkml/')
DEFAULT_ = EX


# Types

# Class references



@dataclass(repr=False)
class File(YAMLRoot):
    """
    A file associated with biological data
    """
    _inherited_slots: ClassVar[list[str]] = []

    class_class_uri: ClassVar[URIRef] = EX["File"]
    class_class_curie: ClassVar[str] = "ex:File"
    class_name: ClassVar[str] = "File"
    class_model_uri: ClassVar[URIRef] = EX.File

    id: Union[str, URIorCURIE] = None
    reference_assembly: Union[str, "ReferenceAssemblyEnum"] = None
    data_modality: Union[str, "DataModalityEnum"] = None
    filename: Optional[str] = None

    def __post_init__(self, *_: str, **kwargs: Any):
        if self._is_empty(self.id):
            self.MissingRequiredField("id")
        if not isinstance(self.id, URIorCURIE):
            self.id = URIorCURIE(self.id)

        if self._is_empty(self.reference_assembly):
            self.MissingRequiredField("reference_assembly")
        if not isinstance(self.reference_assembly, ReferenceAssemblyEnum):
            self.reference_assembly = ReferenceAssemblyEnum(self.reference_assembly)

        if self._is_empty(self.data_modality):
            self.MissingRequiredField("data_modality")
        if not isinstance(self.data_modality, DataModalityEnum):
            self.data_modality = DataModalityEnum(self.data_modality)

        if self.filename is not None and not isinstance(self.filename, str):
            self.filename = str(self.filename)

        super().__post_init__(**kwargs)


# Enumerations
class ReferenceAssemblyEnum(EnumDefinitionImpl):

    GRCh37 = PermissibleValue(text="GRCh37")
    GRCh38 = PermissibleValue(text="GRCh38")
    CHM13 = PermissibleValue(text="CHM13")

    _defn = EnumDefinition(
        name="ReferenceAssemblyEnum",
    )

class DataModalityEnum(EnumDefinitionImpl):

    genomic = PermissibleValue(text="genomic")
    transcriptomic = PermissibleValue(text="transcriptomic")

    _defn = EnumDefinition(
        name="DataModalityEnum",
    )

# Slots
class slots:
    pass

slots.id = Slot(uri=EX.id, name="id", curie=EX.curie('id'),
                   model_uri=EX.id, domain=None, range=Union[str, URIorCURIE])

slots.filename = Slot(uri=EX.filename, name="filename", curie=EX.curie('filename'),
                   model_uri=EX.filename, domain=None, range=Optional[str])

slots.reference_assembly = Slot(uri=EX.reference_assembly, name="reference_assembly", curie=EX.curie('reference_assembly'),
                   model_uri=EX.reference_assembly, domain=None, range=Optional[Union[str, "ReferenceAssemblyEnum"]])

slots.data_modality = Slot(uri=EX.data_modality, name="data_modality", curie=EX.curie('data_modality'),
                   model_uri=EX.data_modality, domain=None, range=Optional[Union[str, "DataModalityEnum"]])

slots.File_reference_assembly = Slot(uri=EX.reference_assembly, name="File_reference_assembly", curie=EX.curie('reference_assembly'),
                   model_uri=EX.File_reference_assembly, domain=File, range=Union[str, "ReferenceAssemblyEnum"])

slots.File_data_modality = Slot(uri=EX.data_modality, name="File_data_modality", curie=EX.curie('data_modality'),
                   model_uri=EX.File_data_modality, domain=File, range=Union[str, "DataModalityEnum"])
