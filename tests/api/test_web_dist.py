"""W5：入库的 web/dist 开箱可用 + 前端产物不含密钥（G1 / G4）。

不依赖 node：只校验仓库里已提交的构建产物。
"""
from __future__ import annotations

import os
import re
import unittest

from review_tool.config import BASE_DIR

DIST = os.path.join(BASE_DIR, "web", "dist")
_ASSET_RE = re.compile(r'(?:src|href)="(/assets/[^"]+)"')
# ClickUp 个人 token（pk_）、DeepSeek/OpenAI 风格 key（sk-）、Bearer 头
_SECRET_RE = re.compile(r"pk_\d{3,}_[A-Za-z0-9]{8,}|sk-[A-Za-z0-9]{16,}|Bearer\s+[A-Za-z0-9._-]{16,}")


def _read(path: str) -> str:
    with open(path, "rb") as f:
        return f.read().decode("utf-8")


class TestWebDist(unittest.TestCase):
    def test_index_exists_and_assets_resolve(self):
        index = os.path.join(DIST, "index.html")
        self.assertTrue(os.path.isfile(index), "web/dist/index.html 未入库")
        html = _read(index)
        self.assertIn('<div id="root">', html)
        assets = _ASSET_RE.findall(html)
        self.assertTrue(any(a.endswith(".js") for a in assets))
        self.assertTrue(any(a.endswith(".css") for a in assets))
        for a in assets:
            self.assertTrue(os.path.isfile(os.path.join(DIST, a.lstrip("/"))), f"缺产物 {a}")

    def test_bundle_has_no_secrets(self):
        for root, _dirs, files in os.walk(DIST):
            for name in files:
                if not name.endswith((".js", ".css", ".html")):
                    continue
                text = _read(os.path.join(root, name))
                # 只报文件名，不回显命中内容
                self.assertIsNone(_SECRET_RE.search(text), f"疑似密钥出现在 {name}")
                for key in ("CLICKUP_API_KEY", "KEEPSTRONG_API_KEY", "DEEPSEEK_API_KEY"):
                    self.assertNotIn(key, text, f"{key} 不应出现在前端产物 {name}")

    def test_bundle_has_no_web_key_value(self):
        """W14：本机配置的访问密钥值绝不能被打进 bundle（登录页只认用户输入）。"""
        from review_tool.settings import SETTINGS

        web_key = (SETTINGS.web_key or "").strip()
        if not web_key:
            self.skipTest("本机未配置 DAILYLUMEN_WEB_KEY")
        for root, _dirs, files in os.walk(DIST):
            for name in files:
                text = _read(os.path.join(root, name)) if name.endswith((".js", ".css", ".html")) else ""
                self.assertFalse(web_key in text, f"访问密钥值出现在前端产物 {name}")


try:
    import fastapi  # noqa: F401
    from fastapi.testclient import TestClient

    _HAS_WEB = True
except ImportError:  # pragma: no cover
    _HAS_WEB = False


@unittest.skipUnless(_HAS_WEB, "未安装 web extra")
class TestServeRealDist(unittest.TestCase):
    def test_root_serves_committed_dist(self):
        from review_tool.api.app import create_app

        # Host 守卫只放行回环；TestClient 默认 Host=testserver 会被 403
        client = TestClient(create_app(dist_dir=DIST), base_url="http://127.0.0.1:8765")
        r = client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn('<div id="root">', r.text)
        # SPA hash 路由之外的深链也回 index
        self.assertEqual(client.get("/reports").status_code, 200)
        asset = _ASSET_RE.findall(r.text)[0]
        self.assertEqual(client.get(asset).status_code, 200)


if __name__ == "__main__":
    unittest.main()
