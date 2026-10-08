"""The explorer shows each dimension slot's description to users, some as plain text (#643).

A ticket reference means nothing there and a backtick shows literally; ticket
references belong in the slot's ``comments:``.
"""

import re

import pytest
import yaml

from meta_disco import schema_vocab
from meta_disco.models import CLASSIFICATION_FIELDS

_TICKET = re.compile(r"#\d+")
_SLOTS = yaml.safe_load(schema_vocab.default_schema_path().read_text())["slots"]


@pytest.mark.parametrize("field", CLASSIFICATION_FIELDS)
def test_dimension_description_is_user_facing(field):
    description = _SLOTS[field].get("description")
    assert description and description.strip(), f"slot {field!r} has no description"
    assert not _TICKET.search(description), (
        f"slot {field!r}'s description carries a ticket reference; move it to the slot's comments: {description!r}"
    )
    assert "`" not in description, f"slot {field!r}'s description carries a backtick: {description!r}"
