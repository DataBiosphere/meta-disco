"""Every term of every ``VOCABULARY_ENUMS`` enum has a ``title``, distinct within its enum and in the generated model (#755)."""

import pytest

from meta_disco import schema_vocab
from meta_disco.schema import classification_model


@pytest.mark.parametrize("field", sorted(schema_vocab.VOCABULARY_ENUMS))
def test_every_term_has_its_own_title(field):
    # The spec, not value_label: its fallback to the value would hide a missing title.
    titles = {v: schema_vocab._term_spec(field, v).get("title") for v in schema_vocab.dimension_values(field)}
    assert not [v for v, t in titles.items() if not (isinstance(t, str) and t.strip())]
    assert len(set(titles.values())) == len(titles)


@pytest.mark.parametrize("field", sorted(schema_vocab.VOCABULARY_ENUMS))
def test_the_generated_enum_keeps_every_value(field):
    # gen-pydantic names members after titles, and two titles it reads as one name keep one member.
    enum = getattr(
        classification_model, "".join(p.capitalize() for p in schema_vocab.VOCABULARY_ENUMS[field].split("_"))
    )
    assert {m.value for m in enum} == schema_vocab.dimension_values(field)


def test_value_label_reads_the_title():
    assert schema_vocab.value_label("data_modality", "epigenomic.methylation") == "DNA methylation"


def test_a_term_without_a_title_is_shown_as_its_value(monkeypatch):
    monkeypatch.setattr(schema_vocab, "_term_spec", lambda *_: {})
    assert schema_vocab.value_label("platform", "ILLUMINA") == "ILLUMINA"
