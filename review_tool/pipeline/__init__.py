"""数据流转层：复盘 md 文件 <-> 数据库的双向管道。

解析（md -> dict）、入库、分数回写 md、历史格式转换、当天文件生成、导出；
外部素材源编排（ClickUp / 练练健身；HTTP 在 ``integrations``）与受控回写。
依赖方向：允许依赖 core / storage / integrations / 包根 ``config``，禁止依赖 reports。
"""
