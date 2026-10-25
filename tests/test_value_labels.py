"""Every term of every ``VOCABULARY_ENUMS`` enum has a ``title``, distinct within its enum (#755)."""

import pytest

from meta_disco import schema_vocab


@pytest.mark.parametrize("field", sorted(schema_vocab.VOCABULARY_ENUMS))
def test_every_term_has_its_own_title(field):
    # The spec, not value_label: its fallback to the value would hide a missing title.
    titles = {v: schema_vocab._term_spec(field, v).get("title") for v in schema_vocab.dimension_values(field)}
    assert not [v for v, t in titles.items() if not (isinstance(t, str) and t.strip())]
    assert len(set(titles.values())) == len(titles)


def test_value_label_reads_the_title():
    assert schema_vocab.value_label("data_modality", "epigenomic.methylation") == "DNA methylation"


def test_a_term_without_a_title_is_shown_as_its_value(monkeypatch):
    monkeypatch.setattr(schema_vocab, "_term_spec", lambda *_: {})
    assert schema_vocab.value_label("platform", "ILLUMINA") == "ILLUMINA"
