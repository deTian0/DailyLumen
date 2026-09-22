"""领域层：与 I/O 无关的纯规则（评分 / 归一化 / 折算 / 类型转换）。

依赖方向（由 ``tests/test_architecture.py`` 用 ast 强制）：
只允许依赖标准库与包根的 ``config``，禁止依赖 storage / pipeline / reports。
这一层应可脱离 SQLite 与文件系统单独测试。
"""
