import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from analysis_engine import process_single_chapter
from config import IMAGE_EVIDENCE_SCHEMA_VERSION
from db_manager import BookDatabase
from epub_parser import parse_epub
from epub_test_fixture import build_image_fixture
from graph_sanity import run_graph_sanity
from image_pipeline.descriptor import ImageDescriptor
from image_pipeline.adapters.epub import extract_epub_image_descriptors
from image_pipeline.fallback import GeminiVisionFallback, maybe_run_fallback
from image_pipeline.parser import parse_chapter_images
from image_pipeline.replay_adapter import ingest_image_evidence
from image_pipeline.classifier import Classification
from key_manager import GeminiKeyManager
from image_pipeline.router import ImageRouter
from snapshot_manager import EvidenceStore, ReplayCoordinator, SnapshotStore


def descriptor(
    *,
    occurrence_order=1,
    member_path="images/map.png",
    caption_text="",
    image_hash=None,
    perceptual_hash="near-duplicate-hint",
):
    raw_bytes = b"stable image bytes"
    return ImageDescriptor(
        source_locator="fixture.epub",
        member_path=member_path,
        chapter_index=0,
        document_item_id="chapter-1",
        occurrence_order=occurrence_order,
        mime_type="image/png",
        image_hash=image_hash or hashlib.sha256(raw_bytes).hexdigest(),
        perceptual_hash=perceptual_hash,
        caption_text=caption_text,
        metadata={"width": 640, "height": 320, "byte_size": len(raw_bytes)},
        raw_bytes=raw_bytes,
    )


def parse_artifact():
    return {
        "visual_classification": {
            "category": "DIAGRAM",
            "subcategory": "wide_visual",
            "confidence": 0.4,
            "reason": "fixture",
        },
        "ocr": {"text": "Eastwatch", "blocks": [], "confidence": 0.5, "engine": "fixture"},
        "diagnostics": [],
        "failure_state": {"state": "none", "stage": "", "code": "", "recoverable": True},
        "provenance": {"parser_version": "fixture", "source_independent": True},
    }


def replay_payload(image_evidence=None):
    return {
        "pov_character_found": "",
        "new_aliases_discovered": [],
        "new_group_aliases_discovered": [],
        "entities_present": [],
        "relationships": [],
        "major_events": [],
        "entity_semantic_relations": [],
        "language_observations": [],
        "life_status_events": [],
        "legacy_signals": [],
        "image_evidence": image_evidence or [],
        "image_evidence_schema_version": IMAGE_EVIDENCE_SCHEMA_VERSION,
        "_metadata": {},
    }


class ImageEvidencePipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_dir = self.temp_dir.name

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_exact_hash_cache_reuse_is_independent_of_occurrence_and_fingerprint(self):
        db = BookDatabase(self.db_dir)
        first = descriptor(caption_text="First caption")
        second = descriptor(occurrence_order=2, caption_text="Second caption", perceptual_hash="different-hint")
        parsed_artifacts = []

        def fake_artifact(item):
            parsed_artifacts.append(item.member_path)
            return parse_artifact()

        with mock.patch("image_pipeline.parser.parser_fingerprint", return_value="fingerprint-a"), mock.patch(
            "image_pipeline.parser._source_independent_artifact", side_effect=fake_artifact
        ):
            first_result = parse_chapter_images([first], db=db)
            second_result = parse_chapter_images([second], db=db)

        self.assertEqual(["images/map.png"], parsed_artifacts)
        self.assertEqual("exact_hash_miss", first_result[0]["cache_status"])
        self.assertEqual("exact_hash_hit", second_result[0]["cache_status"])
        self.assertEqual("Second caption", second_result[0]["descriptor"]["caption_text"])

        with mock.patch("image_pipeline.parser.parser_fingerprint", return_value="fingerprint-b"), mock.patch(
            "image_pipeline.parser._source_independent_artifact", side_effect=fake_artifact
        ):
            changed_fingerprint = parse_chapter_images([second], db=db)

        self.assertEqual(["images/map.png", "images/map.png"], parsed_artifacts)
        self.assertEqual("exact_hash_miss", changed_fingerprint[0]["cache_status"])
        self.assertEqual(2, db._get_connection().execute("SELECT COUNT(*) FROM image_parse_cache").fetchone()[0])
        db.close()

    def test_decoration_is_classified_before_ocr_and_is_ignored(self):
        db = BookDatabase(self.db_dir)
        ornament = descriptor(member_path="images/chapter-ornament.png", caption_text="Do not parse")
        classification = Classification("DECORATION", "chapter_ornament", 0.95, "fixture")

        with mock.patch("image_pipeline.parser.ImageClassifier.classify", return_value=classification), mock.patch(
            "image_pipeline.parser._source_independent_artifact"
        ) as artifact, mock.patch("image_pipeline.parser.extract_ocr") as ocr:
            result = parse_chapter_images([ornament], db=db)

        self.assertFalse(artifact.called)
        self.assertFalse(ocr.called)
        self.assertEqual("skipped_decoration", result[0]["cache_status"])
        self.assertEqual("ignored", result[0]["failure_state"]["state"])
        self.assertEqual([], result[0]["observations"]["literal_text"])
        db.close()

    def test_fallback_is_opt_in_and_injectable(self):
        calls = []

        def fallback_callable(item, classification):
            calls.append((item.member_path, classification["category"]))
            return {"text": "candidate"}

        item = descriptor()
        disabled, disabled_diagnostics = maybe_run_fallback(
            item,
            {"category": "UNKNOWN"},
            0.1,
            enabled=False,
            threshold=0.62,
            fallback_callable=fallback_callable,
        )
        enabled, enabled_diagnostics = maybe_run_fallback(
            item,
            {"category": "UNKNOWN"},
            0.1,
            enabled=True,
            threshold=0.62,
            fallback_callable=fallback_callable,
        )

        self.assertIsNone(disabled)
        self.assertEqual("fallback_disabled", disabled_diagnostics[0]["code"])
        self.assertEqual({"text": "candidate"}, enabled)
        self.assertEqual("fallback_complete", enabled_diagnostics[0]["code"])
        self.assertEqual([("images/map.png", "UNKNOWN")], calls)

    def test_parser_never_calls_vision_without_explicit_authorization(self):
        calls = []
        item = descriptor()
        classification = Classification("UNKNOWN", "unknown", 0.1, "fixture")

        def fallback_callable(_item, _classification):
            calls.append(True)
            return {"observations": {}}

        with mock.patch("image_pipeline.parser.ImageClassifier.classify", return_value=classification), mock.patch(
            "image_pipeline.parser._source_independent_artifact", return_value=parse_artifact()
        ):
            without_consent = parse_chapter_images([item], fallback_callable=fallback_callable)
            parse_chapter_images([item], fallback_callable=fallback_callable, use_gemini_vision=True)

        self.assertEqual([True], calls)
        self.assertIn("fallback_not_authorized", [item["code"] for item in without_consent[0]["diagnostics"]])

    def test_parser_asks_after_local_parse_and_honors_declined_consent(self):
        calls = []
        prompts = []
        item = descriptor()
        classification = Classification("UNKNOWN", "unknown", 0.1, "fixture")

        def fallback_callable(_item, _classification):
            calls.append(True)
            return {"observations": {}}

        def decline(descriptor_arg, classification_arg, confidence):
            prompts.append((descriptor_arg.member_path, classification_arg["category"], confidence))
            return False

        with mock.patch("image_pipeline.parser.ImageClassifier.classify", return_value=classification), mock.patch(
            "image_pipeline.parser._source_independent_artifact", return_value=parse_artifact()
        ):
            result = parse_chapter_images(
                [item],
                fallback_callable=fallback_callable,
                use_gemini_vision=True,
                vision_consent_callback=decline,
            )

        self.assertEqual([], calls)
        self.assertEqual([("images/map.png", "UNKNOWN", 0.22)], prompts)
        self.assertIn("fallback_declined_by_user", [item["code"] for item in result[0]["diagnostics"]])

    def test_vision_key_pool_is_separate_and_round_robin(self):
        created_keys = []

        with mock.patch.dict(
            "os.environ",
            {
                "TEST_GEMINI_VISION_API_KEY_2": "vision-key-2",
                "TEST_GEMINI_VISION_API_KEY_1": "vision-key-1",
                "GEMINI_API_KEY_TEXT": "text-key",
            },
            clear=False,
        ), mock.patch("key_manager.genai.Client", side_effect=lambda api_key: created_keys.append(api_key) or object()):
            manager = GeminiKeyManager(
                key_prefix="TEST_GEMINI_VISION_API_KEY",
                required=False,
                pool_name="test vision",
            )
            _, first_key = manager.get_available_client()
            _, second_key = manager.get_available_client()
            _, wrapped_key = manager.get_available_client()

        self.assertEqual(["vision-key-1", "vision-key-2"], created_keys)
        self.assertEqual(
            ["TEST_GEMINI_VISION_API_KEY_1", "TEST_GEMINI_VISION_API_KEY_2", "TEST_GEMINI_VISION_API_KEY_1"],
            [first_key, second_key, wrapped_key],
        )

    def test_existing_key_manager_exposes_an_isolated_vision_pool(self):
        created_keys = []

        with mock.patch.dict(
            "os.environ",
            {
                "GEMINI_API_KEY_TEXT": "text-key",
                "GEMINI_VISION_API_KEY_2": "vision-key-2",
                "GEMINI_VISION_API_KEY_1": "vision-key-1",
            },
            clear=True,
        ), mock.patch("key_manager.load_dotenv"), mock.patch(
            "key_manager.genai.Client", side_effect=lambda api_key: created_keys.append(api_key) or object()
        ):
            text_manager = GeminiKeyManager()
            vision_manager = text_manager.get_vision_key_manager()
            _, text_key = text_manager.get_available_client()
            _, first_vision_key = vision_manager.get_available_client()
            _, second_vision_key = vision_manager.get_available_client()

        self.assertEqual(["text-key", "vision-key-1", "vision-key-2"], created_keys)
        self.assertEqual("GEMINI_API_KEY_TEXT", text_key)
        self.assertEqual(
            ["GEMINI_VISION_API_KEY_1", "GEMINI_VISION_API_KEY_2"],
            [first_vision_key, second_vision_key],
        )

    def test_vision_fallback_reports_quota_and_rotates_to_next_managed_key(self):
        exhausted_client = SimpleNamespace(
            models=SimpleNamespace(generate_content=mock.Mock(side_effect=RuntimeError("429 quota exhausted")))
        )
        successful_client = SimpleNamespace(
            models=SimpleNamespace(generate_content=mock.Mock(return_value=SimpleNamespace(parsed={"observations": {}})))
        )
        vision_manager = SimpleNamespace(
            has_keys=True,
            get_available_client=mock.Mock(
                side_effect=[
                    (exhausted_client, "GEMINI_VISION_API_KEY_1"),
                    (successful_client, "GEMINI_VISION_API_KEY_2"),
                ]
            ),
            report_exhaustion=mock.Mock(),
        )

        with mock.patch("image_pipeline.fallback.API_PACING_SECONDS", 0):
            result = GeminiVisionFallback(vision_manager)(descriptor(), {"category": "UNKNOWN"})

        self.assertEqual("GEMINI_VISION_API_KEY_2", result["source_key_id"])
        self.assertEqual("user_authorized_local_parse_below_confidence_threshold", result["source_reason"])
        self.assertEqual(2, vision_manager.get_available_client.call_count)
        vision_manager.report_exhaustion.assert_called_once_with("GEMINI_VISION_API_KEY_1")

    def test_vision_fallback_does_not_spend_another_key_on_a_permanent_error(self):
        invalid_request_client = SimpleNamespace(
            models=SimpleNamespace(generate_content=mock.Mock(side_effect=ValueError("unsupported image format")))
        )
        vision_manager = SimpleNamespace(
            has_keys=True,
            get_available_client=mock.Mock(return_value=(invalid_request_client, "GEMINI_VISION_API_KEY_1")),
            report_exhaustion=mock.Mock(),
        )

        with mock.patch("image_pipeline.fallback.API_PACING_SECONDS", 0), self.assertRaisesRegex(
            RuntimeError, "gemini_vision_failed:ValueError"
        ):
            GeminiVisionFallback(vision_manager)(descriptor(), {"category": "UNKNOWN"})

        vision_manager.get_available_client.assert_called_once()
        vision_manager.report_exhaustion.assert_not_called()

    def test_router_has_a_safe_plugin_for_every_declared_category(self):
        router = ImageRouter()
        expected = {
            "UNKNOWN": "unknown", "DECORATION": "unknown", "PORTRAIT": "portrait",
            "MAP": "map", "FAMILY_TREE": "family_tree", "TABLE": "table",
            "DIAGRAM": "diagram", "TIMELINE": "timeline", "SYMBOL": "symbol",
            "HERALDRY": "symbol", "HANDWRITTEN": "handwritten",
            "PAGE_SCAN": "handwritten", "FICTIONAL_ALPHABET": "glyph", "MIXED": "diagram",
        }
        self.assertEqual(expected, router.mapping)
        for category, plugin in expected.items():
            result = router.parse(category, ocr={"text": "", "blocks": [], "confidence": 0.0}, metadata={})
            self.assertEqual(plugin, result["plugin"])
            self.assertIn("literal_text", result["observations"])

    def test_corrupt_image_becomes_degraded_evidence_without_aborting_chapter(self):
        db = BookDatabase(self.db_dir)
        corrupt = descriptor(member_path="images/map.png")
        corrupt.raw_bytes = b"not a decodable image"
        corrupt.extraction_error = "image_metadata_failed:UnidentifiedImageError"
        result = parse_chapter_images([corrupt], db=db)
        self.assertEqual(1, len(result))
        self.assertEqual("degraded", result[0]["failure_state"]["state"])
        self.assertEqual("extraction", result[0]["failure_state"]["stage"])
        self.assertTrue(result[0]["failure_state"]["recoverable"])
        db.close()

    def test_epub_adapter_preserves_order_caption_alt_and_missing_member_failure(self):
        class Item:
            def __init__(self, name, content, item_id=""):
                self.name = name
                self.content = content
                self.id = item_id
                self.media_type = "image/png"

            def get_name(self):
                return self.name

            def get_content(self):
                return self.content

        class Book:
            def __init__(self, items):
                self.items = items

            def get_items(self):
                return self.items

        document = Item(
            "Text/chapter.xhtml",
            b'<figure><img src="../images/one.png" alt="First map"/><figcaption>Map caption</figcaption></figure>'
            b'<img src="../images/missing.png" alt="Missing image"/>',
            "chapter-one",
        )
        image = Item("images/one.png", b"not a real PNG")
        descriptors = extract_epub_image_descriptors(Book([document, image]), document, 7, "fixture.epub")
        self.assertEqual([1, 2], [item.occurrence_order for item in descriptors])
        self.assertEqual("images/one.png", descriptors[0].member_path)
        self.assertEqual("Map caption", descriptors[0].caption_text)
        self.assertEqual("First map", descriptors[0].alt_text)
        self.assertEqual("chapter-one", descriptors[0].document_item_id)
        self.assertEqual("fixture.epub", descriptors[0].source_locator)
        self.assertEqual("image_member_not_found", descriptors[1].extraction_error)
        self.assertEqual([], extract_epub_image_descriptors(Book([document, image]), Item("Text/empty.xhtml", b"", "empty"), 8, "fixture.epub"))

    def test_image_adapter_never_creates_canonical_graph_truth(self):
        db = BookDatabase(self.db_dir)
        evidence = {
            "descriptor": descriptor().to_dict(),
            "category": "FAMILY_TREE",
            "confidence_breakdown": {"overall": 0.9},
            "observations": {
                "literal_text": [{"text": "Unverified Name", "confidence": 0.9}],
                "locations": [{"surface_text": "Unverified Place", "confidence": 0.9}],
                "language": [{"surface_text": "Untranslated mark", "confidence": 0.9}],
                "entities": [{"identity": "Unverified Name", "confidence": 0.9}],
                "relationships": [{"relationship_type": "parent", "confidence": 0.9}],
            },
        }

        summary = ingest_image_evidence(replay_payload([evidence]), 0, db)
        conn = db._get_connection()
        self.assertEqual(1, summary["images"])
        self.assertEqual(0, summary["canonical_mutations"])
        self.assertEqual(0, conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0])
        self.assertEqual(0, conn.execute("SELECT COUNT(*) FROM relationships").fetchone()[0])
        self.assertEqual(0, conn.execute("SELECT COUNT(*) FROM events").fetchone()[0])
        self.assertEqual(0, conn.execute("SELECT COUNT(*) FROM aliases").fetchone()[0])
        self.assertEqual(1, conn.execute("SELECT COUNT(*) FROM reference_mentions").fetchone()[0])
        self.assertEqual(1, conn.execute("SELECT COUNT(*) FROM resolver_decisions WHERE resolver_key = 'image_evidence'").fetchone()[0])
        db.close()

    def test_legacy_cache_enrichment_appends_an_immutable_evidence_revision(self):
        legacy_payload = replay_payload()
        legacy_payload.pop("image_evidence")
        legacy_payload.pop("image_evidence_schema_version")
        cache_path = f"{self.db_dir}/chapter_0.json"
        with open(cache_path, "w", encoding="utf-8") as handle:
            json.dump(legacy_payload, handle, sort_keys=True)
        db = BookDatabase(self.db_dir)
        try:
            EvidenceStore.record(db, 0, legacy_payload, trigger_reason="legacy_import")
            evidence = {"descriptor": descriptor().to_dict(), "category": "UNKNOWN", "observations": {}}
            book = SimpleNamespace(chapters=[SimpleNamespace(image_descriptors=[descriptor()], image_diagnostics=[])])

            with mock.patch("analysis_engine.parse_chapter_images", return_value=[evidence]) as parse_images:
                returned = process_single_chapter(None, 0, book, self.db_dir, db=db)

            rows = db._get_connection().execute(
                "SELECT revision, payload_json FROM chapter_evidence_revisions WHERE chapter = 0 ORDER BY revision"
            ).fetchall()
            with open(cache_path, "r", encoding="utf-8") as handle:
                persisted_cache = json.load(handle)
            self.assertEqual(1, parse_images.call_count)
            self.assertEqual(2, len(rows))
            self.assertNotIn("image_evidence", json.loads(rows[0][1]))
            self.assertEqual([evidence], json.loads(rows[1][1])["image_evidence"])
            self.assertEqual(IMAGE_EVIDENCE_SCHEMA_VERSION, json.loads(rows[1][1])["image_evidence_schema_version"])
            self.assertNotIn("image_evidence", persisted_cache)
            self.assertEqual([evidence], returned["image_evidence"])
        finally:
            db.close()

    def test_staged_replay_promotion_retains_operational_image_cache(self):
        db = BookDatabase(self.db_dir)
        evidence = {
            "descriptor": descriptor().to_dict(),
            "category": "PORTRAIT",
            "confidence_breakdown": {"overall": 0.25},
            "observations": {"entities": [{"identity": None, "confidence": 0.25}]},
        }
        image_hash = evidence["descriptor"]["image_hash"]
        db.put_image_parse_cache(image_hash, "fixture-fingerprint", {"failure_state": {"state": "degraded"}})
        EvidenceStore.record(db, 0, replay_payload([evidence]), trigger_reason="test")
        db.close()

        result = ReplayCoordinator(self.db_dir).run(mode="full", reason="image_cache_retention")
        db = BookDatabase(self.db_dir)
        cache_entry = db.get_image_parse_cache(image_hash, "fixture-fingerprint")
        self.assertTrue(result["promoted"])
        self.assertEqual({"failure_state": {"state": "degraded"}}, cache_entry)
        self.assertEqual(0, db._get_connection().execute("SELECT COUNT(*) FROM entities").fetchone()[0])
        db.close()

    def test_authoritative_image_persistence_separates_occurrence_provenance(self):
        db = BookDatabase(self.db_dir)
        try:
            first = {"descriptor": descriptor(caption_text="First").to_dict(), "parser_fingerprint": "fp", "observations": {}}
            second = {"descriptor": descriptor(occurrence_order=2, caption_text="Second").to_dict(), "parser_fingerprint": "fp", "observations": {}}
            record = EvidenceStore.record(db, 0, replay_payload([first, second]), trigger_reason="test")
            rows = db.active_image_evidence(0)
            self.assertEqual([1, 2], [row["occurrence_order"] for row in rows])
            self.assertTrue(all(row["payload"].get("descriptor") for row in rows))
            provenance = db._get_connection().execute(
                "SELECT caption_text FROM image_occurrence_provenance ORDER BY occurrence_order"
            ).fetchall()
            self.assertEqual([("First",), ("Second",)], provenance)
            self.assertTrue(all(row["payload"].get("descriptor", {}).get("source_locator") for row in rows))
            self.assertGreater(record["id"], 0)
        finally:
            db.close()

    def test_explicit_empty_deactivates_images_but_legacy_missing_preserves_them(self):
        db = BookDatabase(self.db_dir)
        try:
            evidence = {"descriptor": descriptor().to_dict(), "observations": {}}
            EvidenceStore.record(db, 0, replay_payload([evidence]), trigger_reason="first")
            legacy = replay_payload()
            legacy.pop("image_evidence")
            legacy.pop("image_evidence_schema_version")
            EvidenceStore.record(db, 0, legacy, trigger_reason="legacy")
            self.assertEqual(1, len(db.active_image_evidence(0)))
            EvidenceStore.record(db, 0, replay_payload([]), trigger_reason="authoritative_empty")
            self.assertEqual([], db.active_image_evidence(0))
        finally:
            db.close()

    def test_same_payload_reconciles_missing_normalized_rows_and_reopen_backfills(self):
        db = BookDatabase(self.db_dir)
        payload = replay_payload([{"descriptor": descriptor().to_dict(), "observations": {}}])
        try:
            record = EvidenceStore.record(db, 0, payload, trigger_reason="first")
            db._get_connection().execute("DELETE FROM image_occurrence_provenance")
            db._get_connection().execute("DELETE FROM image_evidence_revisions")
            db._get_connection().commit()
            repeated = EvidenceStore.record(db, 0, payload, trigger_reason="same")
            self.assertFalse(repeated["changed"])
            self.assertEqual(1, len(db.active_image_evidence(0)))
            db._get_connection().execute("DELETE FROM image_occurrence_provenance")
            db._get_connection().execute("DELETE FROM image_evidence_revisions")
            db._get_connection().commit()
        finally:
            db.close()
        reopened = BookDatabase(self.db_dir)
        try:
            rows = reopened.active_image_evidence(0)
            self.assertEqual(1, len(rows))
            linked_revision = reopened._get_connection().execute(
                "SELECT chapter_evidence_revision_id FROM image_evidence_revisions WHERE is_active = 1"
            ).fetchone()[0]
            self.assertEqual(record["id"], linked_revision)
        finally:
            reopened.close()

    def test_cache_failures_degrade_without_changing_extraction_state(self):
        item = descriptor()
        with mock.patch("image_pipeline.parser.ImageParseCache.get", side_effect=ValueError("bad cache")), mock.patch(
            "image_pipeline.parser.ImageParseCache.put", side_effect=OSError("read only")
        ), mock.patch("image_pipeline.parser._source_independent_artifact", return_value=parse_artifact()):
            result = parse_chapter_images([item], db=object())
        codes = {entry["code"] for entry in result[0]["diagnostics"]}
        self.assertIn("cache_read_exception", codes)
        self.assertIn("cache_write_exception", codes)
        self.assertEqual("", item.extraction_error)

    def test_vision_fallback_is_not_reused_from_exact_hash_cache(self):
        db = BookDatabase(self.db_dir)
        calls = []

        def fallback(item, _classification):
            calls.append(item.caption_text)
            return {"observations": {}}

        classification = Classification("UNKNOWN", "unknown", 0.1, "fixture")
        try:
            with mock.patch("image_pipeline.parser.ImageClassifier.classify", return_value=classification), mock.patch(
                "image_pipeline.parser._source_independent_artifact", return_value=parse_artifact()
            ):
                parse_chapter_images([descriptor(caption_text="First")], db=db, fallback_callable=fallback, use_gemini_vision=True)
                parse_chapter_images([descriptor(caption_text="Second")], db=db, fallback_callable=fallback, use_gemini_vision=True)
            self.assertEqual(["First", "Second"], calls)
            cached_json = db._get_connection().execute(
                "SELECT parse_output_json FROM image_parse_cache"
            ).fetchone()[0]
            self.assertNotIn("vision_fallback", json.loads(cached_json))
        finally:
            db.close()

    def test_committed_fixture_exercises_order_duplicates_missing_and_no_image_chapter(self):
        fixture = build_image_fixture(Path(self.db_dir) / "fixture.epub")
        book = parse_epub(str(fixture))
        self.assertEqual(2, len(book.chapters))
        images = book.chapters[0].image_descriptors
        self.assertEqual([1, 2, 3, 4], [item.occurrence_order for item in images])
        self.assertEqual(images[0].image_hash, images[1].image_hash)
        self.assertEqual("image_member_not_found", images[3].extraction_error)
        self.assertEqual([], book.chapters[1].image_descriptors)

    def test_export_and_sanity_include_consistent_byte_free_image_state(self):
        db = BookDatabase(self.db_dir)
        try:
            evidence = {"descriptor": descriptor().to_dict(), "parser_fingerprint": "fp", "observations": {}}
            EvidenceStore.record(db, 0, replay_payload([evidence]), trigger_reason="test")
            exported = db.export_graph_state()
            self.assertEqual(1, len(exported["image_evidence_revisions"]))
            self.assertEqual(1, len(exported["image_occurrence_provenance"]))
            self.assertNotIn("raw_bytes", json.dumps(exported))
            self.assertEqual(IMAGE_EVIDENCE_SCHEMA_VERSION, exported["_metadata"]["image_evidence_schema_version"])
        finally:
            db.close()
        sanity = run_graph_sanity(str(Path(self.db_dir) / "graph.db"))
        image_issues = [issue for issue in sanity["issues"] if "image" in issue["type"]]
        self.assertEqual([], image_issues)


if __name__ == "__main__":
    unittest.main()
