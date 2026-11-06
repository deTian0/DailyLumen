"""Web 看板 API 层（最上层 HTTP 薄壳，Web 看板 W1 起）。

依赖方向：允许依赖 core / storage / integrations / pipeline / reports 与包根
``config`` / ``settings``；⛔ 其余各层不得反向依赖本层。

职责：只做路由、参数校验、响应序列化（白名单），**不另写业务口径**——
评分 / 归日 / 拉数一律调用下层共享函数，与 CLI 同源。
第三方 Web 栈（fastapi / uvicorn）与 pydantic 只准出现在本层（optional extra ``web``），
``import review_tool.api`` 本身不加载它们，缺依赖时 ``serve`` 给出友好提示。
默认只读、绑定 127.0.0.1；W14 起 ``/api/*`` 需访问密钥 ``DAILYLUMEN_WEB_KEY``（见 ``auth.py``）。
"""
