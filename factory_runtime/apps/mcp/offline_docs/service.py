from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..repo_fundamentals.path_guard import RepoPathGuard


class OfflineDocsServiceError(RuntimeError):
    """Raised when offline docs index/search operations fail."""


@dataclass
class OfflineDocsService:
    repo_root: Path
    index_db_path: Path
    source_paths: list[str]

    def __post_init__(self) -> None:
        self.repo_root = self.repo_root.resolve()
        self.index_db_path = self.index_db_path.resolve()
        self.index_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.path_guard = RepoPathGuard(self.repo_root)
        self.text_extensions = {".md", ".txt", ".rst", ".j2", ".yml", ".yaml", ".json"}
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.index_db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS docs (
                  path TEXT PRIMARY KEY,
                  content TEXT NOT NULL,
                  line_count INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts
                USING fts5(path UNINDEXED, content)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS index_meta (
                  key TEXT PRIMARY KEY,
                  value TEXT NOT NULL
                )
                """
            )

    def _compute_sources_fingerprint(self) -> str:
        digest = hashlib.sha256()
        for file_path in self._iter_source_files():
            relative = file_path.relative_to(self.repo_root).as_posix()
            stat = file_path.stat()
            digest.update(relative.encode("utf-8"))
            digest.update(b"\0")
            digest.update(str(stat.st_size).encode("utf-8"))
            digest.update(b"\0")
            digest.update(str(stat.st_mtime_ns).encode("utf-8"))
            digest.update(b"\0")
        return digest.hexdigest()

    def _get_meta(self, key: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM index_meta WHERE key = ?", (key,)
            ).fetchone()
        return str(row[0]) if row else None

    def _iter_source_files(self) -> list[Path]:
        files: list[Path] = []
        for source in self.source_paths:
            resolved = self.path_guard.resolve_relative_path(
                source, allow_nonexistent=False
            )
            if resolved.is_file():
                files.append(resolved)
                continue

            for candidate in resolved.rglob("*"):
                if not candidate.is_file():
                    continue
                if candidate.suffix.lower() not in self.text_extensions:
                    continue
                files.append(candidate)

        unique_files: dict[str, Path] = {}
        for file_path in files:
            relative = file_path.relative_to(self.repo_root).as_posix()
            unique_files[relative] = file_path

        return [unique_files[key] for key in sorted(unique_files.keys())]

    def _load_file(self, file_path: Path) -> tuple[str, int]:
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return "", 0
        return content, len(content.splitlines())

    def rebuild_index(self) -> dict[str, Any]:
        indexed = 0
        skipped = 0
        fingerprint = self._compute_sources_fingerprint()

        with self._connect() as conn:
            conn.execute("DELETE FROM docs")
            conn.execute("DELETE FROM docs_fts")

            for file_path in self._iter_source_files():
                relative = file_path.relative_to(self.repo_root).as_posix()
                content, line_count = self._load_file(file_path)
                if not content:
                    skipped += 1
                    continue

                conn.execute(
                    "INSERT INTO docs(path, content, line_count) VALUES (?, ?, ?)",
                    (relative, content, line_count),
                )
                conn.execute(
                    "INSERT INTO docs_fts(path, content) VALUES (?, ?)",
                    (relative, content),
                )
                indexed += 1

            conn.execute(
                "INSERT OR REPLACE INTO index_meta(key, value) VALUES (?, ?)",
                ("sources_fingerprint", fingerprint),
            )

        return {
            "indexed_files": indexed,
            "skipped_files": skipped,
            "index_db": str(self.index_db_path),
        }

    def ensure_index(self) -> None:
        current_fingerprint = self._compute_sources_fingerprint()
        stored_fingerprint = self._get_meta("sources_fingerprint")
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM docs").fetchone()
            doc_count = int(row[0]) if row else 0
        if doc_count == 0 or stored_fingerprint != current_fingerprint:
            self.rebuild_index()

    def stats(self) -> dict[str, Any]:
        self.ensure_index()
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM docs").fetchone()
            doc_count = int(row[0]) if row else 0

        return {
            "doc_count": doc_count,
            "index_db": str(self.index_db_path),
            "source_paths": self.source_paths,
        }

    def _line_number_for_match(self, content: str, query: str) -> int:
        query_lower = query.lower()
        for line_no, line in enumerate(content.splitlines(), start=1):
            if query_lower in line.lower():
                return line_no
        return 1

    def search(self, query: str, max_results: int = 20) -> dict[str, Any]:
        query_text = query.strip()
        if not query_text:
            raise ValueError("query is required")
        if max_results <= 0 or max_results > 200:
            raise ValueError("max_results must be between 1 and 200")

        self.ensure_index()

        with self._connect() as conn:
            try:
                rows = conn.execute(
                    """
                    SELECT docs.path, docs.content
                    FROM docs_fts
                    JOIN docs ON docs.path = docs_fts.path
                    WHERE docs_fts MATCH ?
                    LIMIT ?
                    """,
                    (query_text, max_results),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = conn.execute(
                    "SELECT path, content FROM docs WHERE content LIKE ? LIMIT ?",
                    (f"%{query_text}%", max_results),
                ).fetchall()

        matches: list[dict[str, Any]] = []
        for path, content in rows:
            line_no = self._line_number_for_match(content, query_text)
            lines = content.splitlines()
            snippet = lines[line_no - 1] if 1 <= line_no <= len(lines) else ""
            matches.append(
                {
                    "path": path,
                    "line": line_no,
                    "snippet": snippet,
                }
            )

        return {
            "query": query_text,
            "count": len(matches),
            "matches": matches,
        }

    def read_document(
        self, path: str, start_line: int = 1, end_line: int = 200
    ) -> dict[str, Any]:
        if start_line <= 0 or end_line <= 0:
            raise ValueError("start_line and end_line must be >= 1")
        if end_line < start_line:
            raise ValueError("end_line must be >= start_line")

        resolved = self.path_guard.resolve_relative_path(path, allow_nonexistent=False)
        relative = resolved.relative_to(self.repo_root).as_posix()

        with self._connect() as conn:
            row = conn.execute(
                "SELECT content, line_count FROM docs WHERE path = ?", (relative,)
            ).fetchone()

        if not row:
            raise OfflineDocsServiceError(
                f"Document not indexed: {relative}. Run offline_docs_index_rebuild first."
            )

        content, line_count = row
        lines = str(content).splitlines()
        selected = lines[start_line - 1 : end_line]

        return {
            "path": relative,
            "start_line": start_line,
            "end_line": min(end_line, int(line_count)),
            "content": "\n".join(selected),
        }
