"""v1.105.0 本地镜像配置：Settings 默认值 / env 覆盖 / config 门面 / ingest 切换。"""
import os
import unittest

from review_tool import config
from review_tool.pipeline.ingest import resolve_input_dir
from review_tool.settings import DEFAULT_LOCAL_MIRROR_DIR, load_settings


class TestMirrorSettings(unittest.TestCase):
    def test_default_matches_obsidian_vault(self):
        self.assertEqual(DEFAULT_LOCAL_MIRROR_DIR, r"D:\Obsidian_data\每日复盘记录")
        s = load_settings(env_path="", environ={}, apply_to_environ=False)
        self.assertEqual(s.local_mirror_dir, DEFAULT_LOCAL_MIRROR_DIR)

    def test_env_overrides(self):
        s = load_settings(
            env_path="", environ={"DAILYLUMEN_LOCAL_MIRROR_DIR": "D:/custom/vault"},
            apply_to_environ=False,
        )
        self.assertEqual(s.local_mirror_dir, "D:/custom/vault")

    def test_config_facade_exposes_mirror_dirs(self):
        self.assertEqual(config.MIRROR_DIR, config.SETTINGS.local_mirror_dir)
        self.assertEqual(config.MIRROR_INPUT_DIR,
                         os.path.join(config.MIRROR_DIR, "每日复盘"))

    def test_ingest_input_dir_switch(self):
        self.assertEqual(resolve_input_dir([]), config.INPUT_DIR)
        self.assertEqual(resolve_input_dir(["--overwrite"]), config.INPUT_DIR)
        self.assertEqual(resolve_input_dir(["--mirror"]), config.MIRROR_INPUT_DIR)
        self.assertEqual(resolve_input_dir(["--mirror", "--prune-tracks"]),
                         config.MIRROR_INPUT_DIR)


if __name__ == "__main__":
    unittest.main()
