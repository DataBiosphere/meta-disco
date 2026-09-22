"""Read a TDR snapshot's tables from BigQuery: list, count, stream (issue #498).

A Terra Data Repository snapshot is a BigQuery dataset in TDR's *data project*,
named after the snapshot, with one view per table. This module is the query
layer over that dataset — the three calls a reader of the snapshot needs — built
once for the direct input reader (#499) and, later, the evidence importer
(#369):

- :func:`list_tables` names the snapshot's tables, an empty one included;
- :func:`count_rows` counts one with ``SELECT COUNT(*)``. Snapshot tables are
  views, so the ``__TABLES__`` metadata view reports ``row_count`` 0 for each;
  nothing here reads it;
- :func:`iter_rows` streams one table's rows one at a time, in TDR's own column
  names, as the client delivers them — arrays as lists, nulls as ``None``,
  timestamps as ``datetime`` — converted by whoever writes them, not here. Given
  the ``COUNT(*)`` it may expect, it raises after the last row if the two
  disagree, naming the table and both counts.

**Identity comes from the environment, never from this module.** The client is
injected, and the only place a real one is built, :func:`default_client`, takes
no credential: it constructs the BigQuery client bare, so Application Default
Credentials decide who is calling — the workspace's own identity inside Terra,
``gcloud auth application-default login`` on a laptop. No key file is read, no
credential argument exists, and nothing is stored. Everything else in the repo
that mentions identity cites this paragraph rather than restating it.

The client library, ``google-cloud-bigquery``, is the ``tdr`` extra
(``uv sync --extra tdr``) and is imported inside :func:`default_client` only, so
this module imports — and its tests run against a fake client — in the runtime
environment, where the extra is absent. Only building a live client needs it.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any, Protocol

#: Rows per page when streaming a table. The client fetches a page at a time and
#: yields row by row, so this bounds what is in memory, not what is read.
PAGE_SIZE = 10_000

#: What :meth:`Snapshot.table_ref` will splice into SQL. A table reference
#: cannot be a query parameter, so the three names are wrapped in backticks and
#: whitelisted to this pattern first. The whitelist is the guard, not the
#: backticks: it admits no backtick, so a name cannot close the reference.
_IDENTIFIER = re.compile(r"[A-Za-z0-9_-]+")


class BigQueryClient(Protocol):
    """The two client calls this module makes; ``bigquery.Client`` satisfies it,
    and so can a test fake. Results are typed ``Any``: a listed table needs
    ``table_id``; ``query_and_wait`` returns an iterable of rows, each supporting
    ``keys()`` and ``[key]`` — ``bigquery.table.Row`` and a plain dict both do."""

    def list_tables(self, dataset: str) -> Iterable[Any]: ...
    def query_and_wait(self, query: str, *, page_size: int | None = None) -> Iterable[Any]: ...


@dataclass(frozen=True)
class Snapshot:
    """A TDR snapshot's address in BigQuery: the data project that holds it and
    the snapshot name, which is the dataset id. Together they fix the input — a
    snapshot is immutable. The same address reaches the repo in one other
    spelling, the Azul envelope's ``sources.source_spec``
    (``tdr:bigquery:gcp:<project>:<snapshot>``, see
    :func:`meta_disco.azul_manifest.dataset_source`). No conversion between the
    two exists yet; the first reader that needs one (#499) should add it here,
    as a constructor, rather than split the string where it is read."""

    project: str
    name: str

    @property
    def dataset(self) -> str:
        """The dataset reference, ``project.snapshot``."""
        return f"{self.project}.{self.name}"

    def table_ref(self, table: str) -> str:
        """The backtick-quoted table reference for SQL, ``\\`project.snapshot.table\\```.
        The one place a name enters query text: each of the three must match
        :data:`_IDENTIFIER` in full, or is refused with ``ValueError``; only then is
        it wrapped in backticks."""
        for kind, value in (("project", self.project), ("snapshot", self.name), ("table", table)):
            if not _IDENTIFIER.fullmatch(value):
                raise ValueError(f"not a {kind} name this module will put in SQL: {value!r}")
        return f"`{self.dataset}.{table}`"


class RowCountMismatch(RuntimeError):
    """A streamed table did not hold the number of rows its ``COUNT(*)`` said."""


def _as_dict(row: Any) -> dict[str, Any]:
    # dict() reads a non-dict through keys() and [key], never items() — which on
    # the client's Row deep-copies every cell. Each Row is built fresh from JSON,
    # so sharing the cell objects aliases nothing across rows.
    return dict(row)


def list_tables(client: BigQueryClient, snapshot: Snapshot) -> list[str]:
    """The snapshot's table names, in the order the client lists them. Every
    table is named whether or not it holds rows."""
    return [item.table_id for item in client.list_tables(snapshot.dataset)]


def count_rows(client: BigQueryClient, snapshot: Snapshot, table: str) -> int:
    """The table's row count, by ``SELECT COUNT(*)``. Never ``__TABLES__``: the
    snapshot's tables are views, whose metadata row count is 0."""
    (row,) = client.query_and_wait(f"SELECT COUNT(*) AS n FROM {snapshot.table_ref(table)}")
    return int(_as_dict(row)["n"])


def iter_rows(
    client: BigQueryClient,
    snapshot: Snapshot,
    table: str,
    page_size: int = PAGE_SIZE,
    expect: int | None = None,
) -> Iterator[dict[str, Any]]:
    """Stream the table's rows one at a time, each a dict keyed by TDR's own
    column names holding the client's own value types. The result is paged
    ``page_size`` rows at a time and yielded row by row, so the table is never
    held whole. With ``expect`` — the table's :func:`count_rows` — the stream
    raises :class:`RowCountMismatch` after its last row if it yielded a
    different number, naming the table and both counts."""
    # Built here, not in the generator, so a refused name raises at the call
    # rather than at the first row, when a consumer may already be writing.
    sql = f"SELECT * FROM {snapshot.table_ref(table)}"

    def rows() -> Iterator[dict[str, Any]]:
        streamed = 0
        for row in client.query_and_wait(sql, page_size=page_size):
            streamed += 1
            yield _as_dict(row)
        if expect is not None and streamed != expect:
            raise RowCountMismatch(f"{table}: streamed {streamed} row(s) but COUNT(*) said {expect}")

    return rows()


def default_client(billing_project: str | None = None) -> BigQueryClient:
    """A live BigQuery client whose identity is the environment's Application
    Default Credentials (the module docstring says how); no credential is taken.

    ``billing_project`` is where query jobs run and are billed, not who runs
    them; left ``None``, the client takes it from the environment (inside Terra,
    the workspace's own Google project). Needs the ``tdr`` extra — this is the
    only import of the client library.
    """
    try:
        from google.cloud import bigquery  # pyright: ignore[reportAttributeAccessIssue]
    except ImportError as exc:
        raise ImportError("google-cloud-bigquery is not installed; it is the `tdr` extra: uv sync --extra tdr") from exc
    return bigquery.Client(project=billing_project)
