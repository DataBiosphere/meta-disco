"""Hold each vocabulary term to a display label (#755).

A term's value is the key filters, rules and joins use; its ``title`` is what a reader
is shown. These tests require a title on every term of every enum
``schema_vocab.VOCABULARY_ENUMS`` names, and a distinct one within each enum, so a term
cannot be added without words for it or share another term's words in a filter list.
The words themselves are the schema's to say, and are not restated here.
"""

import pytest

from meta_disco import schema_vocab


@pytest.mark.parametrize("field", sorted(schema_vocab.VOCABULARY_ENUMS))
def test_every_term_has_its_own_title(field):
    enum = schema_vocab._load_schema_enums()[schema_vocab.VOCABULARY_ENUMS[field]]
    titles = {value: (spec or {}).get("title") for value, spec in enum.items()}
    assert not [v for v, t in titles.items() if not (isinstance(t, str) and t.strip())]
    assert len(set(titles.values())) == len(titles)


def test_value_label_reads_the_title():
    field = "data_modality"
    value = "epigenomic.methylation"
    title = schema_vocab._load_schema_enums()[schema_vocab.VOCABULARY_ENUMS[field]][value]["title"]
    assert title != value
    assert schema_vocab.value_label(field, value) == title


def test_a_term_without_a_title_is_shown_as_its_value(monkeypatch):
    monkeypatch.setattr(schema_vocab, "_term_spec", lambda *_: {})
    assert schema_vocab.value_label("platform", "ILLUMINA") == "ILLUMINA"


def test_an_unknown_dimension_or_term_is_a_value_error():
    with pytest.raises(ValueError):
        schema_vocab.value_label("platforms", "ILLUMINA")
    with pytest.raises(ValueError):
        schema_vocab.value_label("platform", "illumina")
