"""Regression tests for bugs found while testing the 0.3.0 desktop build."""

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from bs4 import BeautifulSoup

from ai.manager import AIManager
from ai.models import AIServiceUnavailable, GenerationRequest, ProviderResponse, TransientAIError
from config import AIConfig
from epub_parser import _extract_title
from task_manager import PersistentTaskManager


class _BusyProvider:
    """A provider that is always overloaded, like Gemini returning 503."""

    def __init__(self):
        self.calls = 0

    def is_available(self, _capability):
        return True

    def generate(self, request, model):
        self.calls += 1
        raise TransientAIError("busy", code="network_unavailable")


class InteractiveRetryBudgetTests(unittest.TestCase):
    def setUp(self):
        self.config = replace(AIConfig(), pacing_seconds=0.0, max_retries=5)

    def test_interactive_requests_stop_after_their_own_attempt_budget(self):
        provider = _BusyProvider()
        manager = AIManager(self.config, provider)
        with self.assertRaises(TransientAIError):
            manager.generate(GenerationRequest(role="dictionary", prompt="hi", max_attempts=1))
        self.assertEqual(1, provider.calls)
        self.assertEqual("network_unavailable", manager.last_error["code"])

    def test_the_budget_never_exceeds_the_configured_maximum(self):
        provider = _BusyProvider()
        manager = AIManager(replace(self.config, max_retries=1), provider)
        with self.assertRaises(TransientAIError):
            manager.generate(GenerationRequest(role="dictionary", prompt="hi", max_attempts=9))
        self.assertEqual(1, provider.calls)

    def test_a_success_clears_the_last_error(self):
        class _Provider(_BusyProvider):
            def generate(self, request, model):
                return ProviderResponse(text="ok", provider="test", model=model)

        manager = AIManager(self.config, _Provider())
        manager.last_error = {"code": "network_unavailable", "model": "m", "attempt": 1, "at": 0.0}
        self.assertEqual("ok", manager.generate(GenerationRequest(role="dictionary", prompt="hi")).text)
        self.assertIsNone(manager.last_error)


class CancellableRetryTests(unittest.TestCase):
    def test_a_stop_request_ends_the_retry_loop(self):
        provider = _BusyProvider()
        manager = AIManager(replace(AIConfig(), pacing_seconds=0.0, max_retries=20), provider)
        stop = {"requested": False}

        class _StopsAfterFirstCall(_BusyProvider):
            def generate(self, request, model):
                stop["requested"] = True
                return super().generate(request, model)

        manager.provider = provider = _StopsAfterFirstCall()
        with manager.cancellable(lambda: stop["requested"]):
            with self.assertRaises(AIServiceUnavailable) as raised:
                manager.generate(GenerationRequest(role="chapter", prompt="hi"))
        self.assertEqual("cancelled", raised.exception.code)
        self.assertEqual(1, provider.calls)

    def test_the_check_only_applies_inside_its_scope(self):
        manager = AIManager(replace(AIConfig(), pacing_seconds=0.0, max_retries=1), _BusyProvider())
        with manager.cancellable(lambda: True):
            pass
        with self.assertRaises(TransientAIError):
            manager.generate(GenerationRequest(role="chapter", prompt="hi"))


class RestartRecoveryTests(unittest.TestCase):
    def test_tasks_left_queued_by_a_previous_run_are_closed_out(self):
        with tempfile.TemporaryDirectory() as root:
            path = str(Path(root, "tasks.db"))
            task = PersistentTaskManager(path).enqueue("search_index", "search::Book::Reading", session_key="Book::Reading")
            self.assertEqual("queued", task["state"])
            restarted = PersistentTaskManager(path)
            self.assertEqual("failed", restarted.list()[0]["state"])
            self.assertEqual([], restarted.list(state="queued"))


class ChapterTitleTests(unittest.TestCase):
    @staticmethod
    def title(html, index=9):
        return _extract_title(BeautifulSoup(html, "html.parser"), index)

    def test_a_bold_first_line_names_the_chapter(self):
        html = '<body><p><span><span class="bold">Chapter 9</span></span></p><p>After two years I remember the rest of that day.</p></body>'
        self.assertEqual("Chapter 9", self.title(html))

    def test_ordinary_first_sentences_are_not_mistaken_for_titles(self):
        for sentence in ("Part of me wanted to leave.", "Book in hand, she waited.", "Introduction was never his strength."):
            html = f"<body><p>{sentence}</p><p>More text follows here.</p></body>"
            self.assertEqual("Chapter 10", self.title(html), sentence)

    def test_numbered_and_named_headings_are_recognised(self):
        for heading in ("Chapter Two", "PART IV", "Prologue", "XII"):
            self.assertEqual(heading, self.title(f"<body><div>{heading}</div><p>Text.</p></body>"), heading)

    def test_real_headings_still_win(self):
        html = "<body><h1>The Monster in the Storm</h1><p>Chapter 3</p></body>"
        self.assertEqual("The Monster in the Storm", self.title(html))


if __name__ == "__main__":
    unittest.main()
