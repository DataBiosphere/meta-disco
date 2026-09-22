"""The expected side of a filename-only classification table.

`test_rule_engine` and `test_evals` both hold tables of "this name classifies to
that", where a cell is either a value the dimension takes or the status it ends in.
One assertion reads both, so a row says `{"data_type": "index", "platform":
NOT_APPLICABLE}` instead of spelling which accessor each cell needs.
"""

from meta_disco.models import STATUS_LABELS


def assert_dimensions(result, expected: dict[str, str]) -> None:
    """Each dimension in ``expected`` resolved to the value or status named.

    ``result`` is an `ExtendedClassificationResult`: a cell naming a status (one of
    `models.STATUS_LABELS`) is read through `status_of`, any other through the
    dimension's attribute. A ``None`` cell is refused: it would compare equal to the
    null value every unclassified dimension carries and so pin nothing. The failure
    message names the dimension, so a multi-dimension row still says which cell missed.
    """
    for dimension, cell in expected.items():
        assert cell is not None, f"{dimension}: name a value or a status, not None"
        if cell in STATUS_LABELS:
            assert result.status_of(dimension) == cell, f"{dimension} should have status {cell}"
        else:
            assert getattr(result, dimension) == cell, f"{dimension} should be {cell}"
