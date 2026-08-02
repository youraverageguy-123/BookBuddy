"""Non-destructive real-library acceptance for the dictionary subsystem."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import tempfile
from pathlib import Path

from db_manager import BookDatabase
from dictionary_subsystem.providers import EnglishWordNetProvider, OfflinePronunciationProvider
from dictionary_subsystem.terminology import GlossaryResolver, TerminologyDiscovery


ROOT = Path(__file__).resolve().parent
LIBRARY = ROOT / "library"


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def discover_session() -> tuple[Path, Path]:
    for graph in sorted(LIBRARY.glob("*/*/database/graph.db")):
        if graph.stat().st_size <= 0:
            continue
        book_dir = graph.parents[2]
        if not next(book_dir.glob("*.epub"), None):
            continue
        conn = sqlite3.connect(f"file:{graph.as_posix()}?mode=ro", uri=True)
        try:
            table = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'chapter_evidence_revisions'").fetchone()
            active = conn.execute("SELECT 1 FROM chapter_evidence_revisions WHERE is_active = 1 LIMIT 1").fetchone() if table else None
        finally:
            conn.close()
        if active or next(graph.parent.glob("chapter_*.json"), None):
            return graph, book_dir
    raise RuntimeError("No analyzed library session with an EPUB was found")


def copy_database(source: Path, target: Path):
    source_conn = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    target_conn = sqlite3.connect(target)
    try:
        source_conn.backup(target_conn)
    finally:
        target_conn.close()
        source_conn.close()


def run() -> dict:
    source_graph, book_dir = discover_session()
    source_before = file_hash(source_graph)
    with tempfile.TemporaryDirectory() as temp:
        temp_dir = Path(temp)
        copy_database(source_graph, temp_dir / "graph.db")
        for cache_file in source_graph.parent.glob("chapter_*.json"):
            (temp_dir / cache_file.name).write_bytes(cache_file.read_bytes())
        db = BookDatabase(str(temp_dir))
        try:
            conn = db._get_connection()
            from snapshot_manager import EvidenceStore
            EvidenceStore.import_legacy_caches(db, str(temp_dir))
            chapters = conn.execute("""SELECT chapter, payload_json FROM chapter_evidence_revisions
                WHERE is_active = 1 ORDER BY chapter""").fetchall()
            if not chapters:
                raise RuntimeError("Session has no active chapter evidence")
            as_of = int(chapters[-1][0])
            entity = conn.execute("""SELECT canonical_name FROM entities
                WHERE first_seen_chapter <= ? AND canonical_name NOT LIKE '[%'
                ORDER BY confidence DESC, mention_count DESC LIMIT 1""", (as_of,)).fetchone()
            if not entity:
                raise RuntimeError("Session has no visible entity for glossary acceptance")
            glossary = GlossaryResolver(db)
            entity_result = glossary.lookup(entity[0], as_of)
            dictionary = EnglishWordNetProvider()
            ordinary_result = None
            ordinary_word = None
            for _chapter, payload_json in chapters:
                for word in re.findall(r"\b[a-z]{5,}\b", payload_json.lower()):
                    if glossary.lookup(word, as_of).status == "not_found":
                        candidate = dictionary.lookup(word)
                        if candidate.status == "ok":
                            ordinary_word, ordinary_result = word, candidate
                            break
                if ordinary_result:
                    break
            if not ordinary_result:
                raise RuntimeError("No ordinary dictionary word could be discovered from active evidence")

            terminology_discovery = TerminologyDiscovery(db)
            for chapter, payload_json in chapters:
                payload = json.loads(payload_json)
                observations = payload.get("terminology_observations") or TerminologyDiscovery.discover(payload_json)
                terminology_discovery.process_observations(int(chapter), observations, "acceptance_evidence")
            confirmed_terms = conn.execute("SELECT COUNT(*) FROM terminology_objects WHERE status = 'confirmed'").fetchone()[0]
            pronunciation = OfflinePronunciationProvider().lookup(ordinary_word)
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            required_tables = {"terminology_objects", "terminology_evidence", "knowledge_object_relations"}
            result = {
                "session": str(source_graph.parent.parent.relative_to(LIBRARY)),
                "book_directory": book_dir.name,
                "as_of_chapter": as_of,
                "entity": entity[0],
                "entity_glossary_status": entity_result.status,
                "ordinary_word": ordinary_word,
                "dictionary_status": ordinary_result.status,
                "pronunciation_status": pronunciation.status,
                "confirmed_terminology_objects": int(confirmed_terms),
                "schema_complete": required_tables.issubset(tables),
            }
        finally:
            db.close()
    result["source_database_unchanged"] = source_before == file_hash(source_graph)
    result["passed"] = all([
        result["entity_glossary_status"] == "ok",
        result["dictionary_status"] == "ok",
        result["pronunciation_status"] == "ok",
        result["schema_complete"],
        result["source_database_unchanged"],
    ])
    return result


if __name__ == "__main__":
    outcome = run()
    print(json.dumps(outcome, indent=2, ensure_ascii=False))
    raise SystemExit(0 if outcome["passed"] else 1)
