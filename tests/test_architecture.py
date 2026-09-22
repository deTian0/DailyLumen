"""架构守卫：分层依赖方向 + I/O 归属（v1.5.0 起强制）。

review_tool 按职责分四层，依赖只能自上而下：

    reports   ->  pipeline  ->  storage  ->  core
    (读库产出)    (md <-> 库)   (SQLite)   (纯规则)

- core     领域层：零 I/O —— 禁止 os / pathlib / sqlite3 / subprocess 等，
           只允许标准库纯计算模块、core 内部与包根 config。
- storage  持久化层：``import sqlite3`` **只允许出现在这里**，
           保证 SQLite 是唯一出入口。
- pipeline 数据流转层：md <-> 库，可用 core + storage。
- reports  产出层：可用全部下层。
- 包根（config / __init__ / __main__）不做限制（config 是可配置层，
  __main__ 是纯路由，本来就要 import 各层）。

背景：分层最初只写在 review_tool/README.md 的模块地图里，靠文档自觉维护；
本文件把规则变成可执行断言，谁破坏分层，CI 直接红。
"""

import ast
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "review_tool")
LAYERS = ["core", "storage", "pipeline", "reports"]

# 每层允许依赖的层（"root" = 包根 config / __init__ / __main__）
ALLOWED = {
    "core": {"core"},
    "storage": {"core", "storage"},
    "pipeline": {"core", "storage", "pipeline"},
    "reports": {"core", "storage", "pipeline", "reports"},
}
ROOT_LIKE = {"config", "__init__", "__main__"}

# core 层禁止出现的 I/O 模块（"零 I/O"的机器可查版本）
CORE_IO_FORBIDDEN = {"os", "os.path", "pathlib", "sqlite3", "shutil", "subprocess", "glob"}
# sqlite3 只允许出现在 storage 层
SQLITE3_LAYERS = {"storage", "root"}


def _iter_py():
    for dirpath, dirs, files in os.walk(PKG):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for fn in sorted(files):
            if fn.endswith(".py"):
                yield os.path.join(dirpath, fn)


def _layer_of_file(path):
    rel = os.path.relpath(path, PKG).replace("\\", "/").split("/")
    if len(rel) == 2 and rel[0] in LAYERS:
        return rel[0], rel[1]
    return "root", rel[-1]


def _layer_of_module(modpath):
    """review_tool.<layer>.<mod> -> layer；review_tool.config / review_tool 本身 -> root。"""
    parts = modpath.split(".")
    if not parts or parts[0] != "review_tool":
        return None                      # 标准库 / 第三方，不在约束范围
    if len(parts) == 1:
        return "root"                    # from . import ...（包自身）
    if len(parts) == 2:
        return "root" if parts[1] in ROOT_LIKE or parts[1] not in LAYERS else parts[1]
    if parts[1] in LAYERS:
        return parts[1]
    return "root"


def _imports_of(path):
    """解析一个文件的包内 import（绝对 + 相对），返回 {(目标模块, 顶层模块名)}。"""
    pkg = os.path.relpath(path, ROOT).replace("\\", "/").split("/")[:-1]
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    found = set()
    top_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                top_names.add(a.name.split(".")[0])
                if a.name == "review_tool" or a.name.startswith("review_tool."):
                    found.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                top_names.add(node.module.split(".")[0])
            if node.level:               # 相对导入
                base = pkg[: len(pkg) - (node.level - 1)]
                if node.module:
                    base = base + node.module.split(".")
                found.add(".".join(base))
            elif node.module and node.module.startswith("review_tool"):
                found.add(node.module)
    return found, top_names


class TestDependencyDirection(unittest.TestCase):
    def test_layers_only_depend_downward(self):
        """每个文件只准 import 本层及下层 + 包根。"""
        offenders = []
        for path in _iter_py():
            layer, fname = _layer_of_file(path)
            if layer == "root":
                continue                 # 包根不设限（纯路由 / 可配置层）
            found, _tops = _imports_of(path)
            for mod in found:
                target = _layer_of_module(mod)
                if target is None or target == "root":
                    continue
                if target not in ALLOWED[layer]:
                    offenders.append(f"{layer}/{fname} -> {mod}（{layer} 层禁止依赖 {target} 层）")
        self.assertEqual(offenders, [], "依赖方向被破坏：\n" + "\n".join(offenders))


class TestIoConfined(unittest.TestCase):
    def test_sqlite3_only_in_storage(self):
        offenders = []
        for path in _iter_py():
            layer, fn = _layer_of_file(path)
            _found, tops = _imports_of(path)
            if "sqlite3" in tops and layer not in SQLITE3_LAYERS:
                offenders.append(f"{layer}/{fn}")
        self.assertEqual(offenders, [], "sqlite3 只允许出现在 storage 层，越界：\n" + "\n".join(offenders))

    def test_core_is_io_free(self):
        """领域层零 I/O：禁止文件系统 / 数据库模块。"""
        offenders = []
        for path in _iter_py():
            layer, fn = _layer_of_file(path)
            if layer != "core":
                continue
            _found, tops = _imports_of(path)
            bad = tops & CORE_IO_FORBIDDEN
            if bad:
                offenders.append(f"core/{fn}: {sorted(bad)}")
        self.assertEqual(offenders, [], "core 层出现 I/O 依赖：\n" + "\n".join(offenders))


class TestSubpackageDocs(unittest.TestCase):
    def test_layer_inits_exist_and_document_rules(self):
        """每个子包的 __init__ 必须存在且用 docstring 写明职责与依赖方向。"""
        for layer in LAYERS:
            path = os.path.join(PKG, layer, "__init__.py")
            self.assertTrue(os.path.isfile(path), f"{layer}/__init__.py 缺失")
            with open(path, encoding="utf-8") as f:
                doc = ast.get_docstring(ast.parse(f.read()))
            self.assertTrue(doc, f"{layer}/__init__.py 缺 docstring")
            self.assertIn("依赖方向", doc, f"{layer}/__init__.py 的 docstring 未写依赖方向")


class TestPublicApiIntact(unittest.TestCase):
    def test_all_names_importable_from_package_root(self):
        """分层重构不得改变对外契约：__all__ 里的名字必须仍可从包根导入。"""
        import review_tool

        missing = [n for n in review_tool.__all__ if not hasattr(review_tool, n)]
        self.assertEqual(missing, [], f"公共 API 缺失: {missing}")


def _fn(path):
    return os.path.basename(path)


if __name__ == "__main__":
    unittest.main()
