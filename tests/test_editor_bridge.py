"""内嵌编辑器桥接：模型代理复用 App 设置，JD 原文回灌。"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import companies, config, db  # noqa: E402


class FakeMatch:
    def __init__(self, path: str):
        self.path = path

    def group(self, _n=0):
        return self.path


class TestEditorChat(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in ("JDSCOPE_CONFIG", "JDSCOPE_HOME")}
        self._tmp = tempfile.mkdtemp(prefix="jdscope-ed-")
        os.environ["JDSCOPE_CONFIG"] = self._tmp
        os.environ.pop("JDSCOPE_HOME", None)
        from app.api import Api

        config.ensure_dirs(config.data_home())
        self.api = Api()

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _save_llm(self, key: str = "sk-test"):
        conn = db.connect()
        try:
            db.set_setting(conn, "llm_base_url", "https://api.example.com/v1")
            db.set_setting(conn, "llm_model", "example-chat")
            db.set_setting(conn, "llm_api_key", key)
        finally:
            conn.close()

    def test_missing_key_is_reported_without_calling_model(self):
        conn = db.connect()
        try:
            db.set_setting(conn, "llm_api_key", "")
        finally:
            conn.close()
        with mock.patch("app.api.llm.chat") as fake:
            out = self.api.editor_chat(FakeMatch("/api/editor/chat"),
                                       {"messages": [{"role": "user", "content": "hi"}]}, None)
        self.assertIn("error", out)
        fake.assert_not_called()

    def test_proxy_uses_app_settings_and_returns_content(self):
        self._save_llm()
        seen = {}

        def fake_chat(cfg, messages, **kwargs):
            seen["cfg"] = cfg
            seen["messages"] = messages
            seen["extra"] = kwargs.get("extra")
            return '{"changes": []}'

        with mock.patch("app.api.llm.chat", side_effect=fake_chat):
            out = self.api.editor_chat(
                FakeMatch("/api/editor/chat"),
                {"messages": [{"role": "system", "content": "s"},
                              {"role": "user", "content": "u"}]},
                None,
            )
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("content"), '{"changes": []}')
        self.assertEqual(seen["cfg"]["api_key"], "sk-test")
        self.assertEqual(seen["cfg"]["model"], "example-chat")
        self.assertEqual(seen["extra"]["response_format"], {"type": "json_object"})

    def test_bad_messages_rejected(self):
        out = self.api.editor_chat(FakeMatch("/api/editor/chat"), {"messages": []}, None)
        self.assertIn("error", out)

    def test_company_jd_returns_file_text(self):
        conn = db.connect()
        try:
            general = companies.ensure_general(conn)
        finally:
            conn.close()
        root = config.data_home() / "resumes" / general["folder"]
        (root / "jd.txt").write_text("岗位职责：维护通用简历母版。", encoding="utf-8")
        out = self.api.company_jd(FakeMatch(f"/api/companies/{general['id']}/jd"), None, None)
        self.assertIn("通用简历", out.get("text", ""))


if __name__ == "__main__":
    unittest.main()
