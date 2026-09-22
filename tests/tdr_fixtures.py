"""A fake BigQuery client for the TDR query layer (#498) and the readers over it (#499).

Tables → rows, in memory. It records every query issued, its page size and the
result handed out, so a test can assert what was asked and how much of a result
was pulled before the first row reached the caller.
"""


def table_of(query: str) -> str:
    """The table a query names, undoing `tdr.Snapshot.table_ref`'s quoting — the fake's
    one notion of which table a query is about."""
    return query.rsplit(".", 1)[1].rstrip("`")


class FakeTableItem:
    def __init__(self, table_id: str):
        self.table_id = table_id


class FakeResult:
    """Rows handed out lazily, with a count of how many were pulled."""

    def __init__(self, rows):
        self._rows = rows
        self.pulled = 0

    def __iter__(self):
        for row in self._rows:
            self.pulled += 1
            yield row


class FakeClient:
    """Tables → rows. Records every query issued, its page size, and the result handed out."""

    def __init__(self, tables: dict[str, list[dict]]):
        self._tables = tables
        self.queries: list[str] = []
        self.page_sizes: list = []
        self.results: list[FakeResult] = []
        self.listed: list[str] = []

    def list_tables(self, dataset: str):
        self.listed.append(dataset)
        return [FakeTableItem(name) for name in self._tables]

    def query_and_wait(self, query: str, page_size=None):
        self.queries.append(query)
        self.page_sizes.append(page_size)
        rows = self._tables[table_of(query)]
        result = FakeResult([{"n": len(rows)}] if query.startswith("SELECT COUNT(*)") else rows)
        self.results.append(result)
        return result


class DisagreeingClient(FakeClient):
    """A client whose ``COUNT(*)`` for ``table`` (every table, if None) says ``count``
    whatever it streams."""

    def __init__(self, tables: dict[str, list[dict]], count: int = 99, table: str | None = None):
        super().__init__(tables)
        self.count = count
        self.table = table

    def query_and_wait(self, query, page_size=None):
        result = super().query_and_wait(query, page_size)
        if query.startswith("SELECT COUNT(*)") and self.table in (None, table_of(query)):
            result._rows = [{"n": self.count}]
        return result
