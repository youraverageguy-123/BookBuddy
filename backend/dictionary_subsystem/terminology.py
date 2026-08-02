from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from config import TERMINOLOGY_CANDIDATE_CONFIDENCE, TERMINOLOGY_CONFIRMED_CONFIDENCE, TERMINOLOGY_MIN_CHAPTERS, TERMINOLOGY_MIN_SUPPORT

from .models import KnowledgeObjectRef, ServiceResult


VISIBLE_STATUSES = ("confirmed", "accepted", "probable")


def normalize_term(value: str) -> str:
    return " ".join(re.sub(r"[^\w\s-]", "", str(value or "").lower()).replace("-", " ").split())


class TerminologyDiscovery:
    """Deterministic candidate discovery over source text, never highlight lookup."""

    _CAMEL = re.compile(r"\b[a-z]+[A-Z][A-Za-z0-9]*\b")
    _PHRASE = re.compile(r"\b(?:[A-Z][\w'-]+(?:\s+|$)){2,4}")

    def __init__(self, db):
        self.db = db

    @classmethod
    def discover(cls, text: str) -> list[dict]:
        surfaces = {match.group(0).strip() for match in cls._CAMEL.finditer(text or "")}
        surfaces.update(match.group(0).strip() for match in cls._PHRASE.finditer(text or ""))
        observations = []
        for surface in sorted(surfaces):
            context, start, end = cls._context(text or "", surface)
            observations.append({"surface": surface, "context": context, "start": start, "end": end, "source_type": "text"})
        return observations

    @staticmethod
    def discover_images(image_evidence: list[dict]) -> list[dict]:
        observations = []
        for image in image_evidence or []:
            descriptor = image.get("descriptor") or {}
            context = " ".join(str(descriptor.get("caption_text") or descriptor.get("alt_text") or "").split())[:500]
            candidates = [*(image.get("detected_symbols") or [])]
            for candidate in candidates:
                surface = candidate.get("name") or candidate.get("surface") or candidate.get("label") if isinstance(candidate, dict) else candidate
                surface = " ".join(str(surface or "").split())
                if surface:
                    observations.append({"surface": surface, "context": context, "start": 0, "end": 0, "source_type": "image", "source_ref": descriptor.get("source_locator", "")})
        return observations

    def process(self, chapter: int, text: str, source_ref: str = "chapter_text") -> dict:
        return self.process_observations(chapter, self.discover(text), source_ref)

    def process_observations(self, chapter: int, observations: list[dict], source_ref: str = "chapter_text") -> dict:
        accepted = 0
        processed = 0
        for observation in observations or []:
            surface = str(observation.get("surface", "")).strip()
            normalized = normalize_term(surface)
            if len(normalized) < 3 or self._is_existing_entity(normalized, chapter):
                continue
            processed += 1
            term_id = self._ensure_candidate(surface, normalized, chapter)
            context = str(observation.get("context", ""))[:500]
            start, end = int(observation.get("start", 0)), int(observation.get("end", 0))
            source_type = str(observation.get("source_type", "text"))
            observation_source_ref = str(observation.get("source_ref") or source_ref)
            conn = self.db._get_connection()
            evidence = conn.execute(
                """INSERT INTO terminology_evidence
                   (term_id, chapter, source_type, source_ref, sentence_reference, context, payload_json, confidence)
                   VALUES (?, ?, ?, ?, ?, ?, '{}', ?)""",
                (term_id, chapter, source_type, observation_source_ref, f"chapter:{chapter}:{start}", context, TERMINOLOGY_CANDIDATE_CONFIDENCE),
            )
            evidence_id = int(evidence.lastrowid)
            conn.execute(
                """INSERT OR IGNORE INTO terminology_occurrences
                   (term_id, chapter, sentence_reference, start_offset, end_offset, context, evidence_id, source_type)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (term_id, chapter, f"chapter:{chapter}:{start}", start, end, context, evidence_id, source_type),
            )
            conn.commit()
            if self._promote(term_id, chapter):
                accepted += 1
        return {"candidates": processed, "confirmed": accepted}

    def _is_existing_entity(self, normalized: str, chapter: int) -> bool:
        row = self.db._get_connection().execute(
            """SELECT 1 FROM entities e LEFT JOIN aliases a ON a.entity_id = e.id
               WHERE e.first_seen_chapter <= ? AND
                 (lower(e.canonical_name) = ? OR (a.alias_key = ? AND a.first_seen <= ?)) LIMIT 1""",
            (chapter, normalized, normalized, chapter),
        ).fetchone()
        return bool(row)

    def _ensure_candidate(self, surface: str, normalized: str, chapter: int) -> int:
        conn = self.db._get_connection()
        conn.execute(
            """INSERT INTO terminology_objects
               (canonical_name, normalized_name, first_seen_chapter, last_seen_chapter, existence_confidence, status)
               VALUES (?, ?, ?, ?, ?, 'candidate')
               ON CONFLICT(normalized_name) DO UPDATE SET
                 last_seen_chapter = MAX(last_seen_chapter, excluded.last_seen_chapter), updated_at = CURRENT_TIMESTAMP""",
            (surface, normalized, chapter, chapter, TERMINOLOGY_CANDIDATE_CONFIDENCE),
        )
        row = conn.execute("SELECT id FROM terminology_objects WHERE normalized_name = ?", (normalized,)).fetchone()
        return int(row[0])

    def _promote(self, term_id: int, chapter: int) -> bool:
        conn = self.db._get_connection()
        support, chapters = conn.execute(
            "SELECT COUNT(*), COUNT(DISTINCT chapter) FROM terminology_occurrences WHERE term_id = ? AND source_type = 'text'",
            (term_id,),
        ).fetchone()
        confirmed = support >= TERMINOLOGY_MIN_SUPPORT and chapters >= TERMINOLOGY_MIN_CHAPTERS
        if confirmed:
            confidence = min(0.99, TERMINOLOGY_CONFIRMED_CONFIDENCE + 0.03 * (support - TERMINOLOGY_MIN_SUPPORT))
            conn.execute("""UPDATE terminology_objects SET status = 'confirmed', existence_confidence = ?,
                confirmed_chapter = COALESCE(confirmed_chapter, ?), updated_at = CURRENT_TIMESTAMP WHERE id = ?""", (confidence, chapter, term_id))
            conn.commit()
        return confirmed

    @staticmethod
    def _context(text: str, surface: str) -> tuple[str, int, int]:
        start = text.find(surface)
        end = start + len(surface)
        if start < 0:
            return "", 0, 0
        left = max(text.rfind(".", 0, start), text.rfind("\n", 0, start)) + 1
        right_candidates = [pos for pos in (text.find(".", end), text.find("\n", end)) if pos >= 0]
        right = min(right_candidates) + 1 if right_candidates else min(len(text), end + 240)
        return " ".join(text[left:right].split())[:500], start, end


class TerminologyResolver:
    """Evidence-gated writer for canonical terminology facts and relations."""

    CANONICAL_SOURCES = {"text", "deterministic_parser", "resolver"}

    def __init__(self, db):
        self.db = db

    def _eligible(self, evidence_id: int) -> bool:
        row = self.db._get_connection().execute("SELECT source_type FROM terminology_evidence WHERE id = ?", (evidence_id,)).fetchone()
        return bool(row and row[0] in self.CANONICAL_SOURCES)

    def record_attribute(self, term_id: int, attribute: str, value: str, confidence: float, evidence_id: int) -> int:
        if not self._eligible(evidence_id):
            raise ValueError("canonical terminology facts require deterministic text evidence")
        cursor = self.db._get_connection().execute("""INSERT OR IGNORE INTO terminology_attributes
            (term_id, attribute, value, confidence, evidence_id, status) VALUES (?, ?, ?, ?, ?, 'confirmed')""",
            (term_id, attribute.strip(), value.strip(), max(0.0, min(1.0, confidence)), evidence_id))
        self.db._get_connection().commit()
        return int(cursor.lastrowid or 0)

    def record_function(self, term_id: int, function_name: str, value: str, confidence: float, evidence_id: int) -> int:
        if not self._eligible(evidence_id):
            raise ValueError("canonical terminology facts require deterministic text evidence")
        cursor = self.db._get_connection().execute("""INSERT OR IGNORE INTO terminology_functions
            (term_id, function_name, value, confidence, evidence_id, status) VALUES (?, ?, ?, ?, ?, 'confirmed')""",
            (term_id, function_name.strip(), value.strip(), max(0.0, min(1.0, confidence)), evidence_id))
        self.db._get_connection().commit()
        return int(cursor.lastrowid or 0)

    def record_relation(self, source: KnowledgeObjectRef, target: KnowledgeObjectRef, relation_type: str, chapter: int, confidence: float, evidence_id: int) -> int:
        if not self._eligible(evidence_id):
            raise ValueError("canonical knowledge relations require deterministic text evidence")
        cursor = self.db._get_connection().execute("""INSERT OR IGNORE INTO knowledge_object_relations
            (source_kind, source_id, target_kind, target_id, relation_type, confidence, first_seen_chapter, last_seen_chapter, evidence_id, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'confirmed')""",
            (source.kind, source.object_id, target.kind, target.object_id, relation_type.strip(), max(0.0, min(1.0, confidence)), chapter, chapter, evidence_id))
        self.db._get_connection().commit()
        return int(cursor.lastrowid or 0)


@dataclass(frozen=True)
class DefinitionTemplate:
    category: str
    template: str


class GlossaryRenderer:
    def __init__(self, templates: dict[str, str] | None = None):
        self.templates = templates or {
            "technology": "{name} is a {category} used for {functions}.",
            "weapon": "{name} is a {subcategory} capable of {functions}.",
            "organization": "{name} is a {subcategory} known for {attributes}.",
            "unknown": "{name} is a story-specific {category}.",
        }

    def render(self, facts: dict[str, Any]) -> dict:
        name = facts.get("canonical_name", "This term")
        category = str(facts.get("category") or "concept").lower()
        attributes = [item["value"] for item in facts.get("attributes", []) if item.get("value")]
        functions = [item["value"] for item in facts.get("functions", []) if item.get("value")]
        values = {
            "name": name, "category": category.replace("_", " "),
            "subcategory": str(facts.get("subcategory") or category).replace("_", " "),
            "attributes": ", ".join(attributes), "functions": ", ".join(functions),
        }
        template_key = category if category in self.templates else "unknown"
        if template_key in {"technology", "weapon"} and not functions:
            template_key = "unknown"
        if template_key == "organization" and not attributes:
            template_key = "unknown"
        text = self.templates[template_key].format(**values)
        evidence_ids = []
        seen_evidence = set()
        for item in [*facts.get("attributes", []), *facts.get("functions", [])]:
            reference = item.get("evidence_id")
            if not reference:
                continue
            key = json.dumps(reference, sort_keys=True) if isinstance(reference, (dict, list)) else str(reference)
            if key not in seen_evidence:
                seen_evidence.add(key)
                evidence_ids.append(reference)
        confidences = [float(item.get("confidence", 0)) for item in [*facts.get("attributes", []), *facts.get("functions", [])]]
        base = float(facts.get("confidence", {}).get("existence", 0.0))
        definition_confidence = sum([base, *confidences]) / max(1, 1 + len(confidences))
        return {"text": text, "confidence": round(definition_confidence, 4), "evidence_ids": evidence_ids, "stored": False}


class KnowledgeObjectResolver:
    def __init__(self, db):
        self.db = db

    def resolve(self, query: str, chapter: int) -> dict:
        normalized = normalize_term(query)
        candidates = [*self._entities(normalized, chapter), *self._terms(normalized, chapter)]
        candidates.sort(key=lambda item: (-item["match_score"], -item["confidence"], item["object_kind"], item["object_id"]))
        if not candidates:
            return {"status": "not_found", "candidates": []}
        ambiguous = len(candidates) > 1 and candidates[0]["match_score"] - candidates[1]["match_score"] < 0.05
        return {"status": "ambiguous" if ambiguous else "ok", "match": None if ambiguous else candidates[0], "candidates": candidates[:8]}

    def _entities(self, query: str, chapter: int) -> list[dict]:
        rows = self.db._get_connection().execute(
            """SELECT e.id, e.canonical_name, e.entity_category, e.species_or_kind, e.confidence,
                      e.first_seen_chapter, a.alias_key, a.status
               FROM entities e LEFT JOIN aliases a ON a.entity_id = e.id AND a.first_seen <= ? AND a.status IN ('accepted','probable')
               WHERE e.first_seen_chapter <= ? AND
                 (lower(e.canonical_name) = ? OR lower(e.canonical_name) LIKE ? OR a.alias_key = ? OR a.alias_key LIKE ?)""",
            (chapter, chapter, query, query + "%", query, query + "%"),
        ).fetchall()
        found = {}
        for row in rows:
            canonical = normalize_term(row[1])
            alias = row[6] or ""
            score = 1.0 if canonical == query else 0.95 if alias == query else 0.8 if canonical.startswith(query) else 0.7
            item = {"object_kind": "entity", "object_id": int(row[0]), "canonical_name": row[1], "category": row[2] or "unknown", "subcategory": row[3] or "unknown", "confidence": float(row[4] or 0), "match_score": score}
            if row[0] not in found or score > found[row[0]]["match_score"]:
                found[row[0]] = item
        return list(found.values())

    def _terms(self, query: str, chapter: int) -> list[dict]:
        placeholders = ",".join("?" for _ in VISIBLE_STATUSES)
        rows = self.db._get_connection().execute(
            f"""SELECT t.id, t.canonical_name, t.category, t.subcategory, t.existence_confidence,
                       t.normalized_name, a.normalized_alias
                FROM terminology_objects t LEFT JOIN terminology_aliases a
                  ON a.term_id = t.id AND a.first_seen_chapter <= ? AND a.status IN ({placeholders})
                WHERE t.first_seen_chapter <= ? AND COALESCE(t.confirmed_chapter, t.first_seen_chapter) <= ?
                  AND t.status IN ({placeholders}) AND
                  (t.normalized_name = ? OR t.normalized_name LIKE ? OR a.normalized_alias = ? OR a.normalized_alias LIKE ?)""",
            (chapter, *VISIBLE_STATUSES, chapter, chapter, *VISIBLE_STATUSES, query, query + "%", query, query + "%"),
        ).fetchall()
        found = {}
        for row in rows:
            score = 1.0 if row[5] == query else 0.95 if row[6] == query else 0.8 if row[5].startswith(query) else 0.7
            item = {"object_kind": "terminology", "object_id": int(row[0]), "canonical_name": row[1], "category": row[2], "subcategory": row[3], "confidence": float(row[4] or 0), "match_score": score}
            if row[0] not in found or score > found[row[0]]["match_score"]:
                found[row[0]] = item
        return list(found.values())


class GlossaryResolver:
    provider = "book_graph"
    provider_version = "knowledge_object_v1"

    def __init__(self, db, renderer: GlossaryRenderer | None = None):
        self.db = db
        self.objects = KnowledgeObjectResolver(db)
        self.renderer = renderer or GlossaryRenderer()

    def lookup(self, query: str, chapter: int) -> ServiceResult:
        resolution = self.objects.resolve(query, chapter)
        if resolution["status"] == "not_found":
            return ServiceResult("not_found", {"candidates": []}, self.provider, self.provider_version)
        if resolution["status"] == "ambiguous":
            return ServiceResult("ok", {"ambiguous": True, "candidates": resolution["candidates"]}, self.provider, self.provider_version)
        match = resolution["match"]
        facts = self._term(match, chapter) if match["object_kind"] == "terminology" else self._entity(match, chapter)
        facts["definition"] = self.renderer.render(facts)
        return ServiceResult("ok", facts, self.provider, self.provider_version)

    def _term(self, match: dict, chapter: int) -> dict:
        conn, term_id = self.db._get_connection(), match["object_id"]
        aliases = conn.execute("SELECT alias, confidence, first_seen_chapter, evidence_id FROM terminology_aliases WHERE term_id = ? AND first_seen_chapter <= ? AND status IN ('confirmed','accepted','probable') ORDER BY confidence DESC", (term_id, chapter)).fetchall()
        attrs = conn.execute("SELECT attribute, value, confidence, evidence_id FROM terminology_attributes WHERE term_id = ? AND status IN ('confirmed','accepted','probable') AND (evidence_id IS NULL OR evidence_id IN (SELECT id FROM terminology_evidence WHERE chapter <= ?)) ORDER BY confidence DESC", (term_id, chapter)).fetchall()
        funcs = conn.execute("SELECT function_name, value, confidence, evidence_id FROM terminology_functions WHERE term_id = ? AND status IN ('confirmed','accepted','probable') AND (evidence_id IS NULL OR evidence_id IN (SELECT id FROM terminology_evidence WHERE chapter <= ?)) ORDER BY confidence DESC", (term_id, chapter)).fetchall()
        occurrences = conn.execute("SELECT id, chapter, sentence_reference, context, evidence_id, source_type FROM terminology_occurrences WHERE term_id = ? AND chapter <= ? ORDER BY chapter, id", (term_id, chapter)).fetchall()
        evidence = conn.execute("SELECT id, chapter, source_type, source_ref, context, confidence FROM terminology_evidence WHERE term_id = ? AND chapter <= ? ORDER BY chapter, id", (term_id, chapter)).fetchall()
        relations = self._relations("terminology", term_id, chapter)
        timeline = [{"type": "introduced", "chapter": match.get("first_seen_chapter", occurrences[0][1] if occurrences else chapter), "evidence_ids": [occurrences[0][4]] if occurrences else []}]
        if occurrences:
            timeline.append({"type": "last_mentioned", "chapter": occurrences[-1][1], "evidence_ids": [occurrences[-1][4]] if occurrences[-1][4] else []})
        return {
            **match, "object_status": "confirmed", "aliases": [{"alias": r[0], "confidence": r[1], "first_seen_chapter": r[2], "evidence_id": r[3]} for r in aliases],
            "attributes": [{"attribute": r[0], "value": r[1], "confidence": r[2], "evidence_id": r[3]} for r in attrs],
            "functions": [{"function": r[0], "value": r[1], "confidence": r[2], "evidence_id": r[3]} for r in funcs],
            "occurrences": [{"id": r[0], "chapter": r[1], "sentence_reference": r[2], "context": r[3], "evidence_id": r[4], "source_type": r[5]} for r in occurrences],
            "evidence": [{"id": r[0], "chapter": r[1], "source_type": r[2], "source_ref": r[3], "context": r[4], "confidence": r[5]} for r in evidence],
            "relationships": relations, "related_concepts": relations, "timeline": timeline,
            "images": [{"evidence_id": r[0], "chapter": r[1], "source_ref": r[3], "context": r[4], "confidence": r[5]} for r in evidence if r[2] == "image"],
            "confidence": {"existence": match["confidence"], "category": match.get("category_confidence", 0.0), "attribute": max([r[2] for r in attrs], default=0.0), "function": max([r[2] for r in funcs], default=0.0), "relationship": max([r["confidence"] for r in relations], default=0.0)},
        }

    def _entity(self, match: dict, chapter: int) -> dict:
        conn, entity_id = self.db._get_connection(), match["object_id"]
        aliases = conn.execute("SELECT alias_name, confidence, first_seen, id FROM aliases WHERE entity_id = ? AND first_seen <= ? AND status IN ('accepted','probable') ORDER BY confidence DESC", (entity_id, chapter)).fetchall()
        attrs = conn.execute("SELECT ontology_field, new_value, confidence, id FROM entity_ontology_evidence WHERE entity_id = ? AND chapter <= ? ORDER BY chapter, id", (entity_id, chapter)).fetchall()
        latest = {}
        for row in attrs:
            latest[row[0]] = row
        relations = self._relations("entity", entity_id, chapter)
        first_seen = conn.execute("SELECT first_seen_chapter FROM entities WHERE id = ?", (entity_id,)).fetchone()[0]
        mentions = conn.execute("SELECT chapter, id FROM mention_occurrences WHERE linked_entity_id = ? AND chapter <= ? ORDER BY chapter, id", (entity_id, chapter)).fetchall()
        timeline = [{"type": "introduced", "chapter": first_seen, "evidence_ids": []}]
        if mentions:
            timeline.append({"type": "last_mentioned", "chapter": mentions[-1][0], "evidence_ids": [{"table": "mention_occurrences", "id": mentions[-1][1]}]})
        data = {**match, "object_status": "confirmed", "aliases": [{"alias": r[0], "confidence": r[1], "first_seen_chapter": r[2], "evidence_id": {"table": "aliases", "id": r[3]}} for r in aliases], "attributes": [{"attribute": r[0], "value": r[1], "confidence": r[2], "evidence_id": {"table": "entity_ontology_evidence", "id": r[3]}} for r in latest.values()], "functions": [], "relationships": relations, "related_concepts": relations, "timeline": timeline, "images": [], "evidence": [], "confidence": {"existence": match["confidence"], "category": max([r[2] for r in latest.values()], default=match["confidence"]), "attribute": max([r[2] for r in latest.values()], default=0.0), "function": 0.0, "relationship": max([r["confidence"] for r in relations], default=0.0)}}
        return data

    def _relations(self, kind: str, object_id: int, chapter: int) -> list[dict]:
        rows = self.db._get_connection().execute("""SELECT source_kind, source_id, target_kind, target_id, relation_type, confidence, evidence_id FROM knowledge_object_relations WHERE status IN ('confirmed','accepted','probable') AND first_seen_chapter <= ? AND ((source_kind = ? AND source_id = ?) OR (target_kind = ? AND target_id = ?)) ORDER BY confidence DESC LIMIT 20""", (chapter, kind, object_id, kind, object_id)).fetchall()
        return [{"source": {"kind": r[0], "id": r[1]}, "target": {"kind": r[2], "id": r[3]}, "relation_type": r[4], "confidence": r[5], "evidence_id": r[6]} for r in rows]
