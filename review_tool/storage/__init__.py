"""持久化层：SQLite 的唯一出入口（连接、迁移、读写、打卡对账）。

依赖方向：允许依赖 core 与包根 ``config``，禁止依赖 pipeline / reports。
``schema.sql`` 与 ``reviews*.db`` 按约定留在包根（数据三件套，
``reviews.db`` 含个人数据不入 git）。
"""
