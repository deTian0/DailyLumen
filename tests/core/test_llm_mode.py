"""L-1：LLM mode 互斥 / Settings DeepSeek 字段 / workbuddy 禁调。"""
from __future__ import annotations

import os
import tempfile
import unittest

from review_tool import config
from review_tool.core.llm_mode import (
    ALLOWED_LLM_MODES,
    DEFAULT_LLM_MODE,
    LLM_MODE_DEEPSEEK,
    LLM_MODE_WORKBUDDY,
    LlmModeError,
    is_deepseek_mode,
    is_workbuddy_mode,
    normalize_llm_mode,
)
from review_tool.pipeline import deepseek as ds
from review_tool.settings import (
    DEFAULT_DEEPSEEK_BASE_URL,
    DEFAULT_DEEPSEEK_MODEL,
    SettingsError,
    load_settings,
)


def _write_env(dirpath: str, text: str) -> str:
    path = os.path.join(dirpath, ".env")
    with open(path, "wb") as f:
        f.write(text.replace("\r\n", "\n").encode("utf-8"))
    return path


class TestNormalizeLlmMode(unittest.TestCase):
    def test_default_when_empty(self):
        self.assertEqual(normalize_llm_mode(None), DEFAULT_LLM_MODE)
        self.assertEqual(normalize_llm_mode(""), LLM_MODE_WORKBUDDY)
        self.assertEqual(normalize_llm_mode("  "), LLM_MODE_WORKBUDDY)

    def test_accepts_both_modes_case_insensitive(self):
        self.assertEqual(normalize_llm_mode("workbuddy"), LLM_MODE_WORKBUDDY)
        self.assertEqual(normalize_llm_mode("DeepSeek"), LLM_MODE_DEEPSEEK)
        self.assertEqual(ALLOWED_LLM_MODES, frozenset({"workbuddy", "deepseek"}))

    def test_rejects_unknown_and_openai(self):
        with self.assertRaises(LlmModeError) as ctx:
            normalize_llm_mode("openai")
        self.assertIn("DAILYLUMEN_LLM_MODE", str(ctx.exception))
        with self.assertRaises(LlmModeError):
            normalize_llm_mode("both")

    def test_predicates(self):
        self.assertTrue(is_workbuddy_mode("workbuddy"))
        self.assertTrue(is_deepseek_mode("deepseek"))
        self.assertFalse(is_deepseek_mode("workbuddy"))


class TestSettingsLlmFields(unittest.TestCase):
    def test_defaults_are_workbuddy_without_deepseek_key(self):
        s = load_settings(env_path="", environ={}, apply_to_environ=False)
        self.assertEqual(s.llm_mode, "workbuddy")
        self.assertEqual(s.deepseek_api_key, "")
        self.assertEqual(s.deepseek_base_url, DEFAULT_DEEPSEEK_BASE_URL)
        self.assertEqual(s.deepseek_model, DEFAULT_DEEPSEEK_MODEL)
        self.assertEqual(s.deepseek_timeout_s, 60.0)

    def test_reads_deepseek_env(self):
        env = {
            "DAILYLUMEN_LLM_MODE": "deepseek",
            "DEEPSEEK_API_KEY": "sk-test-fake-not-real",
            "DEEPSEEK_BASE_URL": "https://example.test/v1",
            "DEEPSEEK_MODEL": "deepseek-chat",
            "DEEPSEEK_TIMEOUT_S": "45",
        }
        s = load_settings(env_path="", environ=env, apply_to_environ=False)
        self.assertEqual(s.llm_mode, "deepseek")
        self.assertEqual(s.deepseek_api_key, "sk-test-fake-not-real")
        self.assertEqual(s.deepseek_base_url, "https://example.test/v1")
        self.assertEqual(s.deepseek_model, "deepseek-chat")
        self.assertEqual(s.deepseek_timeout_s, 45.0)

    def test_blank_base_and_model_fall_back_to_defaults(self):
        env = {
            "DAILYLUMEN_LLM_MODE": "deepseek",
            "DEEPSEEK_BASE_URL": "",
            "DEEPSEEK_MODEL": "  ",
        }
        s = load_settings(env_path="", environ=env, apply_to_environ=False)
        self.assertEqual(s.deepseek_base_url, DEFAULT_DEEPSEEK_BASE_URL)
        self.assertEqual(s.deepseek_model, DEFAULT_DEEPSEEK_MODEL)

    def test_invalid_mode_raises_named_error(self):
        with self.assertRaises(SettingsError) as ctx:
            load_settings(
                env_path="",
                environ={"DAILYLUMEN_LLM_MODE": "openai"},
                apply_to_environ=False,
            )
        msg = str(ctx.exception)
        self.assertIn("DAILYLUMEN_LLM_MODE", msg)

    def test_dotenv_file_mode(self):
        with tempfile.TemporaryDirectory() as td:
            path = _write_env(
                td,
                "DAILYLUMEN_LLM_MODE=deepseek\n"
                "DEEPSEEK_API_KEY=sk-from-file\n",
            )
            s = load_settings(env_path=path, environ={}, apply_to_environ=False)
        self.assertEqual(s.llm_mode, "deepseek")
        self.assertEqual(s.deepseek_api_key, "sk-from-file")

    def test_dotenv_production_loader_reads_dailylumen_llm_mode(self):
        """生产路径 Settings(_env_file) 必须认 DAILYLUMEN_LLM_MODE（非 LLM_MODE）。"""
        saved = {
            k: os.environ.pop(k)
            for k in list(os.environ)
            if k in {"DAILYLUMEN_LLM_MODE", "LLM_MODE", "DEEPSEEK_API_KEY"}
        }
        try:
            with tempfile.TemporaryDirectory() as td:
                path = _write_env(
                    td,
                    "DAILYLUMEN_LLM_MODE=deepseek\n"
                    "DEEPSEEK_API_KEY=sk-prod-path\n",
                )
                s = load_settings(env_path=path, apply_to_environ=False)
            self.assertEqual(s.llm_mode, "deepseek")
            self.assertEqual(s.deepseek_api_key, "sk-prod-path")
        finally:
            os.environ.update(saved)


class TestConfigFacade(unittest.TestCase):
    def test_facade_exposes_mode(self):
        self.assertTrue(hasattr(config, "LLM_MODE"))
        self.assertTrue(callable(config.get_llm_mode))
        self.assertIn(config.get_llm_mode(), ALLOWED_LLM_MODES)


class TestWorkbuddyBlocksExternalCall(unittest.TestCase):
    def test_require_deepseek_rejects_workbuddy(self):
        with self.assertRaises(ds.DeepSeekModeError) as ctx:
            ds.require_deepseek_mode("workbuddy")
        self.assertIn("workbuddy", str(ctx.exception))
        self.assertIn("禁止", str(ctx.exception))

    def test_client_chat_noop_reject_under_workbuddy(self):
        calls = {"n": 0}

        def urlopen(req, timeout=None):
            calls["n"] += 1
            raise AssertionError("workbuddy 不应发网")

        client = ds.Client(
            "sk-fake",
            mode="workbuddy",
            urlopen=urlopen,
        )
        with self.assertRaises(ds.DeepSeekModeError):
            client.chat_completions([{"role": "user", "content": "hi"}])
        self.assertEqual(calls["n"], 0)


if __name__ == "__main__":
    unittest.main()
