"""The six dimension slots' descriptions are user-facing text (issue #643).

The meta-disco explorer shows each dimension slot's ``description`` from
``classification.yaml`` to end users, word for word: as a plain-text tooltip and on
its Data Dictionary page. A ticket reference (``#603``) means nothing there and a
code span's backticks show literally, so neither may appear in one; a slot keeps
its ticket references in ``comments:``.
"""

import re

import pytest
import yaml

from meta_disco import schema_vocab
from meta_disco.models import CLASSIFICATION_FIELDS

_TICKET = re.compile(r"#\d+")


@pytest.fixture(scope="module")
def schema_slots() -> dict:
    return yaml.safe_load(schema_vocab.default_schema_path().read_text())["slots"]


@pytest.mark.parametrize("field", CLASSIFICATION_FIELDS)
def test_dimension_description_is_user_facing(schema_slots, field):
    description = (schema_slots.get(field) or {}).get("description")
    assert description, f"slot {field!r} has no description"
    assert not _TICKET.search(description), (
        f"slot {field!r}'s description carries a ticket reference; move it to the slot's comments: {description!r}"
    )
    assert "`" not in description, f"slot {field!r}'s description carries a code span: {description!r}"
