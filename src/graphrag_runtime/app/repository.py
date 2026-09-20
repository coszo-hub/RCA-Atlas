from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator, Protocol, Sequence


class Repository(Protocol):
    def health(self) -> bool: ...
    def search(self, query: str, embedding: Sequence[float], *, limit: int,
               lexical_weight: float, vector_weight: float,
               collection_ids: Sequence[str]) -> list[dict[str, Any]]: ...
    def neighbors(self, seeds: Sequence[dict[str, str]], *, hops: int, limit: int) -> list[dict[str, Any]]: ...
    def route_tools(self, query: str, *, limit: int) -> list[dict[str, Any]]: ...
    def close(self) -> None: ...


class PostgresRepository:
    """Calls bounded SECURITY DEFINER functions and never queries base tables."""

    def __init__(self, database_url: str, *, min_size: int = 1, max_size: int = 10,
                 statement_timeout_ms: int = 4_000,
                 embedding_model: str = "BAAI/bge-small-en-v1.5") -> None:
        try:
            from pgvector.psycopg import register_vector
            from psycopg_pool import ConnectionPool
        except ImportError as error:  # pragma: no cover
            raise RuntimeError("install psycopg, psycopg-pool, and pgvector") from error

        def configure(connection: Any) -> None:
            register_vector(connection)

        self.statement_timeout_ms = statement_timeout_ms
        self.embedding_model = embedding_model
        self.pool = ConnectionPool(database_url, min_size=min_size, max_size=max_size,
                                   kwargs={"autocommit": False}, configure=configure, open=True)

    @contextmanager
    def _cursor(self) -> Iterator[Any]:
        with self.pool.connection() as connection:
            with connection.transaction():
                with connection.cursor() as cursor:
                    cursor.execute("SELECT set_config('statement_timeout', %s, true)",
                                   (f"{self.statement_timeout_ms}ms",))
                    yield cursor

    def close(self) -> None:
        self.pool.close()

    def health(self) -> bool:
        try:
            with self._cursor() as cursor:
                cursor.execute("SELECT ready FROM graphrag_api.runtime_health()")
                row = cursor.fetchone()
                return bool(row and row[0])
        except Exception:
            return False

    @staticmethod
    def _dict_rows(cursor: Any) -> list[dict[str, Any]]:
        columns = [column.name for column in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def search(self, query: str, embedding: Sequence[float], *, limit: int,
               lexical_weight: float, vector_weight: float,
               collection_ids: Sequence[str]) -> list[dict[str, Any]]:
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT * FROM graphrag_api.hybrid_search(%s,%s,%s,%s,%s,%s,%s)",
                (query, list(embedding), limit, list(collection_ids) or None,
                 self.embedding_model, lexical_weight, vector_weight),
            )
            rows = self._dict_rows(cursor)
        result = []
        for row in rows:
            vector_rank, lexical_rank = row.pop("vector_rank"), row.pop("lexical_rank")
            row["text"] = row.pop("body")
            row["lexical_score"] = 0.0 if lexical_rank is None else 1.0 / (60.0 + lexical_rank)
            row["vector_score"] = 0.0 if vector_rank is None else 1.0 / (60.0 + vector_rank)
            citation_url = row.pop("citation_url")
            chunk_source_url = row.pop("source_url")
            source_url = citation_url or chunk_source_url
            row["citations"] = [{
                "source_id": row.pop("citation_source_id"),
                "title": row.pop("citation_title"),
                "url": source_url,
            }]
            row["metadata"] = {"node_local_id": row.pop("node_local_id"), "locator": row.pop("locator")}
            result.append(row)
        return result

    def neighbors(self, seeds: Sequence[dict[str, str]], *, hops: int, limit: int) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        remaining = limit
        for seed in seeds[:20]:
            if remaining <= 0:
                break
            with self._cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM graphrag_api.graph_neighbors(%s,%s,%s,%s,NULL)",
                    (seed["collection_id"], seed["local_id"], hops, remaining),
                )
                rows = self._dict_rows(cursor)
            for row in rows:
                if row["depth"] == 0:
                    continue
                output.append({
                    "collection_id": row["collection_id"], "local_id": row["local_id"],
                    "name": row["display_name"], "depth": row["depth"],
                    "direction": row["direction"], "predicate": row["predicate"],
                    "source_url": row["source_url"],
                })
                remaining -= 1
                if remaining <= 0:
                    break
        return output

    def route_tools(self, query: str, *, limit: int) -> list[dict[str, Any]]:
        with self._cursor() as cursor:
            cursor.execute("SELECT * FROM graphrag_api.route_tools(%s,%s)", (query, limit))
            rows = self._dict_rows(cursor)
        for row in rows:
            row.pop("runtime", None)
            schema = row.pop("input_schema") or {}
            row["required_arguments"] = schema.get("required", [])
            row["input_schema"] = schema
        return rows
