"""The expected side of a filename-only classification table.

`test_rule_engine` and `test_evals` both hold tables of "this name classifies to
that", where a cell is either a value the dimension takes or the status it ends in.
One assertion reads both, so a row says `{"data_type": "index", "platform":
NOT_APPLICABLE}` instead of spelling which accessor each cell needs.
"""

from meta_disco.models import CONFLICT, NOT_APPLICABLE, NOT_CLASSIFIED

# A cell holding one of these names a status; anything else is a value.
STATUS_CELLS = frozenset({NOT_APPLICABLE, NOT_CLASSIFIED, CONFLICT})


def assert_dimensions(result, expected: dict[str, str | None]) -> None:
    """Each dimension in ``expected`` resolved to the value or status named.

    ``result`` is an `ExtendedClassificationResult`: a value cell is read through
    the dimension's attribute, a status cell through `status_of`. The failure
    message names the dimension, so a multi-dimension row still says which cell
    missed.
    """
    for dimension, cell in expected.items():
        if cell in STATUS_CELLS:
            assert result.status_of(dimension) == cell, f"{dimension} should have status {cell}"
        else:
            assert getattr(result, dimension) == cell, f"{dimension} should be {cell}"
