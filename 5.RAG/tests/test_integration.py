"""Integration tests for the cloud LLM provider.

These tests make real API calls and require valid API keys in the
environment.  They are skipped automatically when the corresponding
key is not set.

Run with:
    MINIMAX_API_KEY=... python -m pytest tests/test_integration.py -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from llm_provider import get_llm_config, chat_completion

_MINIMAX_KEY = os.environ.get("MINIMAX_API_KEY")
_OPENAI_KEY = os.environ.get("OPENAI_API_KEY")


@unittest.skipUnless(_MINIMAX_KEY, "MINIMAX_API_KEY not set")
class TestMiniMaxIntegration(unittest.TestCase):
    """Live integration tests against the MiniMax API."""

    def test_simple_completion(self):
        cfg = get_llm_config(provider="minimax", max_tokens=256)
        result = chat_completion(
            cfg,
            [
                {"role": "system", "content": "Reply directly without thinking."},
                {"role": "user", "content": "Say hello in one sentence."},
            ],
        )
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_qa_with_context(self):
        from generate_answer import cloud_answer_with_context

        cfg = get_llm_config(provider="minimax", max_tokens=128)
        answer = cloud_answer_with_context(
            "CVE-2024-0001 affects OpenSSL 3.x with CVSS 9.8.",
            "What is the CVSS score?",
            cfg,
        )
        self.assertIn("9.8", answer)

    def test_summarize_document(self):
        from generate_answer import cloud_summarize_document

        cfg = get_llm_config(provider="minimax", max_tokens=512)
        summary = cloud_summarize_document(
            ["Firewall logs show 500 blocked requests from IP 10.0.0.5."],
            max_summary_length=50,
            llm_config=cfg,
        )
        self.assertIsInstance(summary, str)
        self.assertGreater(len(summary), 0)


@unittest.skipUnless(_OPENAI_KEY, "OPENAI_API_KEY not set")
class TestOpenAIIntegration(unittest.TestCase):
    """Live integration tests against the OpenAI API."""

    def test_simple_completion(self):
        cfg = get_llm_config(provider="openai", max_tokens=64)
        result = chat_completion(
            cfg, [{"role": "user", "content": "Say hello in one sentence."}]
        )
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)


if __name__ == "__main__":
    unittest.main()
