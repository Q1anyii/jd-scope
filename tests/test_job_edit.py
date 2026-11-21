"""岗位详情编辑：公司名 / 岗位名等元信息可改，空值拒绝。"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import config, db  # noqa: E402


class FakeMatch:
    def __init__(self, path: str):
        self.path = path

    def group(self, _n=0):
        return self.path


class TestJobEdit(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in ("JDSCOPE_CONFIG", "JDSCOPE_HOME")}
        self._tmp = tempfile.mkdtemp(prefix="jdscope-jedit-")
        os.environ["JDSCOPE_CONFIG"] = self._tmp
        os.environ.pop("JDSCOPE_HOME", None)
        from app.api import Api

        config.ensure_dirs(config.data_home())
        self.api = Api()
        conn = db.connect()
        try:
            self.job_id = conn.execute(
                "INSERT INTO jobs(company,title,city,url,jd_raw,status,decision,score,score_json,"
                "constraint_state,verdict,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("旧公司", "旧岗位", "南昌", "https://example.com/old",
                 "岗位职责：负责 Agent 应用开发。\n任职要求：熟悉 Python。",
                 "new", "go", 70.0, "{}", "[]", "建议投", db.now(), db.now()),
            ).lastrowid
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_patch_company_title_and_meta(self):
        out = self.api.patch_job(
            FakeMatch(f"/api/jobs/{self.job_id}"),
            {"company": " 新公司 ", "title": " Agent 工程师 ", "city": "杭州",
             "source": "内推", "url": "https://example.com/new"},
            None,
        )
        self.assertTrue(out.get("ok"))
        detail = self.api.job_detail(FakeMatch(f"/api/jobs/{self.job_id}"), None, None)
        self.assertEqual(detail["job"]["company"], "新公司")
        self.assertEqual(detail["job"]["title"], "Agent 工程师")
        self.assertEqual(detail["job"]["city"], "杭州")
        self.assertEqual(detail["job"]["source"], "内推")
        self.assertEqual(detail["job"]["url"], "https://example.com/new")

    def test_blank_company_or_title_rejected(self):
        out = self.api.patch_job(FakeMatch(f"/api/jobs/{self.job_id}"),
                                 {"company": "   ", "title": "新岗位"}, None)
        self.assertIn("error", out)
        detail = self.api.job_detail(FakeMatch(f"/api/jobs/{self.job_id}"), None, None)
        self.assertEqual(detail["job"]["company"], "旧公司")
        self.assertEqual(detail["job"]["title"], "旧岗位")


if __name__ == "__main__":
    unittest.main()
