import unittest
import tempfile
import json

from ai import PermanentAIError
from ai.gemini_provider import GeminiProvider
from analysis_engine import (
    ChapterAnalysis,
    adapt_chapter_analysis_wire_payload,
    chapter_analysis_wire_schema,
    chapter_analysis_request,
    normalize_event_record,
    validate_chapter_analysis,
)
from config import AIConfig, load_config


def find_schema_keyword(value, keyword, path="$"):
    matches = []
    if isinstance(value, dict):
        if keyword in value:
            matches.append(path)
        for key, child in value.items():
            matches.extend(find_schema_keyword(child, keyword, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            matches.extend(find_schema_keyword(child, keyword, f"{path}[{index}]"))
    return matches


def find_empty_enum_values(value, path="$"):
    matches = []
    if isinstance(value, dict):
        if isinstance(value.get("enum"), list) and "" in value["enum"]:
            matches.append(path)
        for key, child in value.items():
            matches.extend(find_empty_enum_values(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            matches.extend(find_empty_enum_values(child, f"{path}[{index}]"))
    return matches


class GeminiSchemaCompatibilityTests(unittest.TestCase):
    def test_gemini_36_flash_is_the_default_for_every_capability(self):
        defaults = AIConfig()
        self.assertEqual("gemini-3.6-flash", defaults.chapter_model)
        self.assertEqual("gemini-3.6-flash", defaults.dictionary_model)
        self.assertEqual("gemini-3.6-flash", defaults.vision_model)
        with tempfile.TemporaryDirectory() as root:
            loaded = load_config(root, {})
        self.assertEqual("gemini-3.6-flash", loaded.ai.chapter_model)
        self.assertEqual("gemini-3.6-flash", loaded.ai.dictionary_model)
        self.assertEqual("gemini-3.6-flash", loaded.ai.vision_model)

    def test_chapter_analysis_requests_compact_wire_schema_and_validates_locally(self):
        request = chapter_analysis_request("prompt", book="Book", chapter_index=3)
        self.assertFalse(request.response_json)
        self.assertEqual(chapter_analysis_wire_schema(), request.response_schema)
        self.assertEqual({"book": "Book", "chapter_index": 3}, request.metadata)

    def test_compact_wire_schema_keeps_keys_without_expensive_constraints(self):
        schema = chapter_analysis_wire_schema()
        encoded = json.dumps(schema)
        self.assertIn("pov_character_found", schema["properties"])
        self.assertIn("entities_present", schema["properties"])
        self.assertIn("major_events", schema["properties"])
        self.assertEqual([], find_schema_keyword(schema, "enum"))
        self.assertEqual([], find_schema_keyword(schema, "description"))
        self.assertEqual([], find_schema_keyword(schema, "minimum"))
        self.assertEqual([], find_schema_keyword(schema, "maximum"))
        self.assertLess(len(encoded), 16000)

    def test_chapter_analysis_schema_has_no_arbitrary_object_properties(self):
        schema = ChapterAnalysis.model_json_schema()
        self.assertEqual([], find_schema_keyword(schema, "additionalProperties"))
        self.assertEqual([], find_empty_enum_values(schema))

    def test_fixed_importance_schema_preserves_dictionary_ingestion_contract(self):
        payload = ChapterAnalysis.model_validate({
            "pov_character_found": "",
            "new_aliases_discovered": [],
            "new_group_aliases_discovered": [],
            "entities_present": [],
            "relationships": [],
            "major_events": [{
                "summary": "A political incident occurs.",
                "importance": {"political": 0.8, "historical": None},
            }],
        }).model_dump()
        record = normalize_event_record(payload["major_events"][0])
        self.assertEqual({"political": 0.8}, record["importance"])
        self.assertEqual(payload, validate_chapter_analysis(payload))

    def test_live_gemini_vocabulary_is_adapted_before_strict_validation(self):
        payload = {
            "pov_character_found": "Carl",
            "new_aliases_discovered": [],
            "new_group_aliases_discovered": [],
            "entities_present": [],
            "relationships": [],
            "major_events": [{
                "summary": "The transformation begins.",
                "landmark_type": "world_event",
                "lifecycle": "occurred",
                "event_reliability": "observed",
                "reader_visibility": "direct",
                "outcome": "Buildings collapse worldwide.",
                "historical_memory": "A new era begins.",
                "name_status": "informal",
                "causal_relation_type": "execution",
                "landmark_names": [{
                    "name": "The Collapse",
                    "name_role": "descriptive",
                    "name_source_type": "narrator",
                }],
                "importance": {"political": 10, "personal": 8},
                "perspectives": [{
                    "summary": "Carl sees it happen.",
                    "perspective_type": "first_person",
                    "reader_visibility": "direct",
                    "reliability": "reliable",
                }],
            }],
            "life_status_events": [{
                "subject": "Carl",
                "evidence": "Carl survives.",
                "identity_continuity_mode": "original",
            }],
            "legacy_signals": [{
                "subject": "Someone",
                "signal_type": "decapitation_evidence",
                "evidence": "A severed head is observed.",
                "emotional_importance": 7,
                "memory_strength": 9,
            }],
        }
        adapted = adapt_chapter_analysis_wire_payload(payload)
        self.assertEqual("event", adapted["major_events"][0]["landmark_type"])
        self.assertEqual("candidate", adapted["major_events"][0]["lifecycle"])
        self.assertEqual("unknown", adapted["major_events"][0]["outcome"])
        self.assertEqual("unknown", adapted["major_events"][0]["name_status"])
        self.assertEqual("precedes", adapted["major_events"][0]["causal_relation_type"])
        self.assertEqual("public", adapted["major_events"][0]["landmark_names"][0]["name_role"])
        self.assertEqual("unknown", adapted["major_events"][0]["landmark_names"][0]["name_source_type"])
        self.assertEqual(0.8, adapted["major_events"][0]["importance"]["personal"])
        self.assertEqual("narrator", adapted["major_events"][0]["perspectives"][0]["perspective_type"])
        self.assertEqual("same_identity", adapted["life_status_events"][0]["identity_continuity_mode"])
        self.assertEqual("legacy", adapted["legacy_signals"][0]["signal_type"])
        self.assertEqual(0.9, adapted["legacy_signals"][0]["memory_strength"])
        validate_chapter_analysis(payload)

    def test_unsupported_schema_error_is_actionable_and_sanitized(self):
        provider = object.__new__(GeminiProvider)
        error = provider._mapped_error(
            ValueError(
                "additionalProperties is only supported in Gemini Enterprise Agent Platform mode, "
                "not in Gemini Developer API mode."
            ),
            "text",
            "encrypted-key-1",
        )
        self.assertIsInstance(error, PermanentAIError)
        self.assertEqual("unsupported_response_schema", error.code)
        self.assertEqual("encrypted-key-1", error.credential_id)
        self.assertNotIn("Unexpected", str(error))

        invalid_enum = provider._mapped_error(
            ValueError(
                "400 INVALID_ARGUMENT: GenerateContentRequest.generation_config.response_schema."
                "properties[missing_subtype].enum[6]: cannot be empty"
            ),
            "text",
            "encrypted-key-1",
        )
        self.assertEqual("unsupported_response_schema", invalid_enum.code)
        self.assertNotIn("API key", str(invalid_enum))

        oversized = provider._mapped_error(
            ValueError("The specified schema produces a constraint that has too many states for serving"),
            "text",
            "encrypted-key-1",
        )
        self.assertEqual("unsupported_response_schema", oversized.code)


if __name__ == "__main__":
    unittest.main()
