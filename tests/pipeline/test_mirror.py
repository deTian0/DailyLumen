"""mirror 模块测试：local → 目标目录镜像 + manifest/hash 守护的安全删除。"""
import os
import shutil
import tempfile
import unittest

from review_tool.pipeline.mirror import (
    MANIFEST_NAME,
    apply_mirror,
    plan_mirror,
    read_manifest,
    rel_of,
    sha256_file,
    untracked_files,
)


class _Fixture(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        # 造一个 project/local 结构，git 不可用 → untracked_files 走回退全量扫描
        self.project = os.path.join(self.dir, "project")
        self.local = os.path.join(self.project, "local")
        self.target = os.path.join(self.dir, "vault")  # project 之外，无包含关系
        os.makedirs(os.path.join(self.local, "每日复盘", "复盘", "2026-11"))
        os.makedirs(os.path.join(self.local, "exports"))
        os.makedirs(self.target)
        self._put(os.path.join(self.local, "每日复盘", "复盘", "2026-11", "2026-11-20.md"),
                  "# 复盘\n正文")
        self._put(os.path.join(self.local, "exports", "daily_reviews.csv"), "a,b\n1,2\n")
        self._put(os.path.join(self.local, ".gitkeep"), "")
        self._put(os.path.join(self.local, "README.md"), "local readme")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _put(self, path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(text.encode("utf-8"))

    def _get(self, path):
        with open(path, "rb") as f:
            return f.read().decode("utf-8")

    def _plan(self, **kw):
        return plan_mirror(self.local, self.target, **kw)


class TestUntrackedFiles(_Fixture):
    def test_excludes_tracked_placeholders_and_env(self):
        self._put(os.path.join(self.local, ".env"), "SECRET=1")
        self._put(os.path.join(self.local, "backups", ".env.bak-1"), "SECRET=2")
        files = untracked_files(self.local)
        names = [os.path.basename(f) for f in files]
        self.assertNotIn(".env", names)
        self.assertNotIn(".env.bak-1", names)
        self.assertNotIn(".gitkeep", names)
        self.assertNotIn("README.md", names)
        self.assertTrue(any(n == "2026-11-20.md" for n in names))

    def test_rel_of_posix_style(self):
        p = os.path.join(self.local, "每日复盘", "复盘", "x.md")
        self.assertEqual(rel_of(p, self.local), "每日复盘/复盘/x.md")

    def test_injected_source_cannot_smuggle_env(self):
        env = os.path.join(self.local, ".env")
        p = plan_mirror(self.local, self.target, source_files=[env])
        self.assertEqual(p["copies"], [])
        self.assertNotIn(".env", p["manifest"])


class TestPlanAndApply(_Fixture):
    def test_plan_copies_preserving_relative_path(self):
        p = self._plan()
        dsts = {dst for _src, dst in p["copies"]}
        expect = os.path.join(self.target, "每日复盘", "复盘", "2026-11", "2026-11-20.md")
        self.assertIn(expect, dsts)
        self.assertTrue(any(d.endswith("daily_reviews.csv") for d in dsts))

    def test_apply_writes_files_and_manifest(self):
        p = self._plan()
        stats = apply_mirror(p)
        self.assertEqual(stats["copied"], 2)
        md = os.path.join(self.target, "每日复盘", "复盘", "2026-11", "2026-11-20.md")
        self.assertTrue(os.path.isfile(md))
        self.assertEqual(self._get(md), "# 复盘\n正文")
        mf = read_manifest(self.target)
        self.assertIn("每日复盘/复盘/2026-11/2026-11-20.md", mf)
        self.assertEqual(mf["exports/daily_reviews.csv"],
                         sha256_file(os.path.join(self.local, "exports", "daily_reviews.csv")))

    def test_second_apply_is_noop(self):
        apply_mirror(self._plan())
        stats = apply_mirror(self._plan())
        self.assertEqual(stats["copied"], 0)
        self.assertEqual(stats["unchanged"], 2)

    def test_nested_target_path_rejected(self):
        with self.assertRaises(ValueError):
            plan_mirror(self.local, os.path.join(self.local, "nested"))
        with self.assertRaises(ValueError):
            plan_mirror(self.local, os.path.dirname(self.local))

    def test_no_prune_keeps_deletes_empty(self):
        apply_mirror(self._plan())
        os.remove(os.path.join(self.local, "exports", "daily_reviews.csv"))
        self.assertEqual(self._plan(prune=False)["deletes"], [])
        self.assertEqual(len(self._plan(prune=True)["deletes"]), 1)


class TestSafeDelete(_Fixture):
    def test_deletes_source_removed_and_target_untouched(self):
        apply_mirror(self._plan())
        csv = os.path.join(self.local, "exports", "daily_reviews.csv")
        dst = os.path.join(self.target, "exports", "daily_reviews.csv")
        os.remove(csv)
        p = self._plan()
        self.assertIn(dst, p["deletes"])
        apply_mirror(p)
        self.assertFalse(os.path.exists(dst))

    def test_keeps_target_file_modified_by_user(self):
        apply_mirror(self._plan())
        csv = os.path.join(self.local, "exports", "daily_reviews.csv")
        dst = os.path.join(self.target, "exports", "daily_reviews.csv")
        os.remove(csv)
        self._put(dst, "USER EDITED")
        p = self._plan()
        self.assertNotIn(dst, p["deletes"])
        self.assertTrue(any("手工改过" in reason for _rel, reason in p["conflicts"]))

    def test_never_deletes_native_vault_notes(self):
        apply_mirror(self._plan())
        self._put(os.path.join(self.target, "欢迎.md"), "欢迎使用 Obsidian")
        self._put(os.path.join(self.target, ".obsidian", "app.json"), "{}")
        # 源删一份 → 只删 manifest 里那份，绝不碰 vault 原生笔记
        os.remove(os.path.join(self.local, "exports", "daily_reviews.csv"))
        p = self._plan()
        apply_mirror(p)
        self.assertTrue(os.path.isfile(os.path.join(self.target, "欢迎.md")))
        self.assertTrue(os.path.isfile(os.path.join(self.target, ".obsidian", "app.json")))

    def test_force_overwrites_user_modified_target(self):
        apply_mirror(self._plan())
        dst = os.path.join(self.target, "每日复盘", "复盘", "2026-11", "2026-11-20.md")
        self._put(dst, "USER EDITED")
        # 默认：目标手改过 → 记 conflict、不覆盖；--force 才覆盖
        self.assertEqual(len(self._plan()["conflicts"]), 1)
        p = self._plan(force=True)
        self.assertIn(dst, [d for _s, d in p["copies"]])
        apply_mirror(p)
        self.assertEqual(self._get(dst), "# 复盘\n正文")


class TestCli(unittest.TestCase):
    def test_dry_run_does_not_write(self):
        from review_tool.pipeline.mirror import main
        with tempfile.TemporaryDirectory() as td:
            local = os.path.join(td, "local")
            target = os.path.join(td, "vault")
            os.makedirs(os.path.join(local, "每日复盘", "复盘"))
            self._put_static(os.path.join(local, "每日复盘", "复盘", "a.md"), "x")
            rc = main(["--src", local, "--target", target])
            self.assertEqual(rc, 0)
            self.assertFalse(os.path.exists(target))

    def test_apply_via_cli(self):
        from review_tool.pipeline.mirror import main
        with tempfile.TemporaryDirectory() as td:
            local = os.path.join(td, "local")
            target = os.path.join(td, "vault")
            os.makedirs(os.path.join(local, "每日复盘", "复盘"))
            self._put_static(os.path.join(local, "每日复盘", "复盘", "a.md"), "x")
            rc = main(["--apply", "--src", local, "--target", target])
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.isfile(os.path.join(
                target, "每日复盘", "复盘", "a.md")))
            self.assertTrue(os.path.isfile(os.path.join(target, MANIFEST_NAME)))

    def test_target_inside_local_rejected(self):
        from review_tool.pipeline.mirror import main
        with tempfile.TemporaryDirectory() as td:
            local = os.path.join(td, "local")
            target = os.path.join(local, "vault")
            os.makedirs(local)
            self._put_static(os.path.join(local, "复盘", "a.md"), "x")
            rc = main(["--apply", "--src", local, "--target", target])
            self.assertEqual(rc, 2)
            self.assertFalse(os.path.exists(target), "被拒时不得写任何文件")

    @staticmethod
    def _put_static(path, text):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(text.encode("utf-8"))


if __name__ == "__main__":
    unittest.main()
