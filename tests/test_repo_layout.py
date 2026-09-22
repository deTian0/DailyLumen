"""仓库布局守卫：`.gitignore` 白名单规则 + 项目级 skill 完整性。

背景（v1.4.3）：项目级 skill 是可复用的**方法资产**，必须跟代码一起入库。
`.gitignore` 曾用整目录规则 `.workbuddy/` —— 它把目录本身也排除了，
git 因此不再向下遍历，后续的 `!.workbuddy/skills/` 白名单会**静默失效**
（不报错、不警告，只是文件不入库）。本测试把这条规则钉死，
防止有人日后「顺手清理」.gitignore 时改回去。
"""

import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GITIGNORE = os.path.join(ROOT, ".gitignore")
SKILLS_DIR = os.path.join(ROOT, ".workbuddy", "skills")


def _patterns() -> list[str]:
    """读出 `.gitignore` 里的有效规则（去空行、去注释）。"""
    with open(GITIGNORE, encoding="utf-8") as f:
        lines = f.read().splitlines()
    return [ln.strip() for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]


class TestGitignoreWhitelist(unittest.TestCase):
    def test_no_bare_workbuddy_dir_rule(self):
        """不许出现裸的 `.workbuddy/` —— 它会让 skills 白名单静默失效。"""
        self.assertNotIn(".workbuddy/", _patterns(),
                         "`.workbuddy/` 会排除目录本身，导致白名单失效；应为 `.workbuddy/*`")

    def test_contents_excluded_but_skills_whitelisted(self):
        pats = _patterns()
        self.assertIn(".workbuddy/*", pats)
        self.assertIn("!.workbuddy/skills/", pats)

    def test_private_dirs_stay_ignored(self):
        """隐私兜底：memory / backup / automations 不得被白名单放进来。"""
        negated = [p for p in _patterns() if p.startswith("!")]
        for private in ("memory", "backup", "automations"):
            self.assertFalse(
                any(p.startswith(f"!.workbuddy/{private}") for p in negated),
                f".workbuddy/{private}/ 不应被白名单放行",
            )
        self.assertEqual(negated, ["!.workbuddy/skills/", "!.workbuddy/skills/**"],
                         "白名单只应放行 skills/")


class TestProjectSkills(unittest.TestCase):
    def _skill_dirs(self) -> list[str]:
        if not os.path.isdir(SKILLS_DIR):
            return []
        return sorted(
            d for d in os.listdir(SKILLS_DIR)
            if os.path.isdir(os.path.join(SKILLS_DIR, d))
        )

    def test_skills_dir_is_tracked_and_nonempty(self):
        """项目级 skills 目录必须存在且至少有一个 skill。"""
        self.assertTrue(os.path.isdir(SKILLS_DIR), "缺少 .workbuddy/skills/")
        self.assertTrue(self._skill_dirs(), ".workbuddy/skills/ 下没有任何 skill")

    def test_every_skill_has_valid_frontmatter(self):
        """每个项目级 skill 都要有可被加载器识别的 frontmatter。"""
        for name in self._skill_dirs():
            path = os.path.join(SKILLS_DIR, name, "SKILL.md")
            self.assertTrue(os.path.isfile(path), f"{name}: 缺 SKILL.md")
            with open(path, encoding="utf-8") as f:
                text = f.read()
            self.assertTrue(text.startswith("---"), f"{name}: 缺 frontmatter 起始 ---")
            block = text.split("---", 2)[1]
            for field in ("name", "description"):
                self.assertRegex(block, rf"(?m)^{field}:\s*\S+", f"{name}: 缺 {field}")
            self.assertRegex(block, r"(?m)^agent_created:\s*true",
                             f"{name}: 缺 agent_created: true（否则无法被 skill 管理器改）")
            # name 字段应与目录名一致，避免加载器按目录找不到
            m = re.search(r"(?m)^name:\s*(\S+)", block)
            self.assertEqual(m.group(1), name, f"{name}: frontmatter 的 name 与目录名不一致")


if __name__ == "__main__":
    unittest.main()
