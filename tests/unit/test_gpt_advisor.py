#!/usr/bin/env python3
import unittest
import tempfile
from pathlib import Path
from src.gpt_client import (
    ChatGPTClient,
    load_openai_api_key,
    save_openai_api_key,
    INSTITUTIONAL_SYSTEM_PROMPT,
)


class TestChatGPTAdvisor(unittest.TestCase):
    def test_client_initialization_without_key(self):
        client = ChatGPTClient(api_key=None)
        # Without key in environment, is_configured should be False or True if user set env
        if not client.api_key:
            self.assertFalse(client.is_configured())
        self.assertEqual(client.model, "gpt-4o")
        self.assertIn("Algo Lab", client.system_prompt)

    def test_save_and_load_api_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_env = Path(tmpdir) / ".env"
            test_env.write_text("SOME_VAR=123\n", encoding="utf-8")

            test_key = "sk-test1234567890abcdef"
            saved = save_openai_api_key(test_key, env_path=test_env)
            self.assertTrue(saved)

            loaded = load_openai_api_key(env_path=test_env)
            self.assertEqual(loaded, test_key)

            # Test updating existing key
            new_key = "sk-updated9876543210zyx"
            save_openai_api_key(new_key, env_path=test_env)
            reloaded = load_openai_api_key(env_path=test_env)
            self.assertEqual(reloaded, new_key)

    def test_build_messages_structure(self):
        client = ChatGPTClient(api_key="sk-dummy-key-for-test")
        messages = client._build_messages("What is Nifty?")
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1]["role"], "user")
        self.assertEqual(messages[1]["content"], "What is Nifty?")


if __name__ == "__main__":
    unittest.main()
