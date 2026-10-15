"""M16：零依赖 Settings 层 —— .env 解析 / env 覆盖 / 类型校验 / 门面兼容。"""
from __future__ import annotations

import ast
import os
import tempfile
import unittest

from review_tool import config
from review_tool.settings import (
    DEFAULT_KEEPSTRONG_BASE_URL,
    DEFAULT_KEEPSTRONG_SKILL_VERSION,
    DEFAULT_KEEPSTRONG_TIMEOUT_S,
    SettingsError,
    load_settings,
    parse_env_file,
)

PKG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "review_tool")
SETTINGS_PATH = os.path.join(PKG, "settings.py")


def _write_env(dirpath: str, text: str) -> str:
    path = os.path.join(dirpath, ".env")
    with open(path, "wb") as f:
        f.write(text.replace("\r\n", "\n").encode("utf-8"))
    return path


class TestParseEnvFile(unittest.TestCase):
    def test_key_value_comment_blank_quotes(self):
        with tempfile.TemporaryDirectory() as td:
            path = _write_env(
                td,
                "# comment\n\n"
                "FOO=bar\n"
                "QUOTED=\"hello world\"\n"
                "SINGLE='x=y'\n"
                "SPACED =  spaced  \n",
            )
            got = parse_env_file(path)
        self.assertEqual(got["FOO"], "bar")
        self.assertEqual(got["QUOTED"], "hello world")
        self.assertEqual(got["SINGLE"], "x=y")
        self.assertEqual(got["SPACED"], "spaced")
        self.assertNotIn("# comment", got)

    def test_missing_file_is_empty(self):
        self.assertEqual(parse_env_file("/no/such/.env"), {})


class TestLoadSettingsThreeStates(unittest.TestCase):
    """三态：未设 → 默认；已设 → 覆盖；类型非法 → 含变量名的清晰错误。"""

    def test_defaults_when_env_unset(self):
        s = load_settings(env_path="", environ={}, apply_to_environ=False)
        self.assertEqual(s.keepstrong_api_key, "")
        self.assertEqual(s.keepstrong_base_url, DEFAULT_KEEPSTRONG_BASE_URL)
        self.assertEqual(s.keepstrong_skill_version, DEFAULT_KEEPSTRONG_SKILL_VERSION)
        self.assertEqual(s.keepstrong_timeout_s, DEFAULT_KEEPSTRONG_TIMEOUT_S)
        self.assertTrue(s.db_path.endswith("reviews.db"))
        self.assertIsNone(s.history_src_dir)

    def test_environ_overrides_defaults(self):
        env = {
            "KEEPSTRONG_API_KEY": "ks_test_key",
            "KEEPSTRONG_BASE_URL": "https://example.test",
            "KEEPSTRONG_TIMEOUT_S": "12.5",
            "DAILYLUMEN_HISTORY_SRC": "D:/hist",
            "CLICKUP_API_KEY": "pk_x",
            "CLICKUP_TEAM_ID": "9",
        }
        s = load_settings(env_path="", environ=env, apply_to_environ=False)
        self.assertEqual(s.keepstrong_api_key, "ks_test_key")
        self.assertEqual(s.keepstrong_base_url, "https://example.test")
        self.assertEqual(s.keepstrong_timeout_s, 12.5)
        self.assertEqual(s.history_src_dir, "D:/hist")
        self.assertEqual(s.clickup_api_key, "pk_x")
        self.assertEqual(s.clickup_team_id, "9")

    def test_dotenv_file_used_when_environ_empty(self):
        with tempfile.TemporaryDirectory() as td:
            path = _write_env(
                td,
                "KEEPSTRONG_API_KEY=from_file\n"
                "KEEPSTRONG_SKILL_VERSION=9.9.9\n",
            )
            s = load_settings(env_path=path, environ={}, apply_to_environ=False)
        self.assertEqual(s.keepstrong_api_key, "from_file")
        self.assertEqual(s.keepstrong_skill_version, "9.9.9")

    def test_environ_beats_dotenv_file(self):
        with tempfile.TemporaryDirectory() as td:
            path = _write_env(td, "KEEPSTRONG_API_KEY=from_file\n")
            s = load_settings(
                env_path=path,
                environ={"KEEPSTRONG_API_KEY": "from_env"},
                apply_to_environ=False,
            )
        self.assertEqual(s.keepstrong_api_key, "from_env")

    def test_invalid_float_raises_named_error(self):
        with self.assertRaises(SettingsError) as ctx:
            load_settings(
                env_path="",
                environ={"KEEPSTRONG_TIMEOUT_S": "not-a-number"},
                apply_to_environ=False,
            )
        msg = str(ctx.exception)
        self.assertIn("KEEPSTRONG_TIMEOUT_S", msg)
        self.assertIn("float", msg)


class TestZeroThirdParty(unittest.TestCase):
    def test_settings_module_has_no_pydantic_or_dotenv(self):
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    names.add(a.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module.split(".")[0])
        forbidden = {"pydantic", "dotenv", "python_dotenv"}
        self.assertEqual(names & forbidden, set())


class TestConfigFacade(unittest.TestCase):
    """门面：既有名字仍可从 config 取到；KS_DEFAULTS 与 SETTINGS 对齐。"""

    def test_public_names_still_present(self):
        for name in (
            "PROFILE", "FEATURES", "DB_PATH", "CLICKUP_LISTS", "FOOD_LIB",
            "SCORE_THRESHOLDS", "HISTORY_SRC_DIR", "KS_DEFAULTS", "SETTINGS",
        ):
            self.assertTrue(hasattr(config, name), name)

    def test_features_new_day_still_false(self):
        self.assertIs(config.FEATURES["new_day"], False)

    def test_ks_defaults_mirror_settings(self):
        self.assertEqual(config.KS_DEFAULTS["base_url"], config.SETTINGS.keepstrong_base_url)
        self.assertEqual(
            config.KS_DEFAULTS["skill_version"], config.SETTINGS.keepstrong_skill_version
        )
        self.assertEqual(config.KS_DEFAULTS["timeout_s"], config.SETTINGS.keepstrong_timeout_s)


if __name__ == "__main__":
    unittest.main()
