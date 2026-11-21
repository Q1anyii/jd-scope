"""AI 候选条目：结构化收敛、去重合并、勾选入库与重算保留。"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import config, db, jdparse  # noqa: E402

JD = """公司名称：示例数据科技有限公司
岗位名称：前端工程师
工作地点：杭州

岗位职责：
1、负责公司前端页面开发与组件库维护；
2、负责性能优化与构建链路改造。

任职要求：
1、熟练掌握 Vue 3 与 TypeScript；
2、至少 2 年前端经验；
3、熟悉 Node 构建工具。

加分项：
1、有组件库从 0 到 1 经验优先。"""


class FakeMatch:
    def group(self, _n=0):
        return "/api/jobs/1/analyze"


class TestNormalize(unittest.TestCase):
    def test_bad_category_falls_back_by_hard_words(self):
        items = jdparse.normalize_ai_items([
            {"text": "必须精通 TypeScript", "category": "unknown"},
            {"text": "负责组件库建设", "category": ""},
        ])
        self.assertEqual(items[0]["category"], "must")
        self.assertEqual(items[0]["priority"], "high")
        self.assertEqual(items[1]["category"], "duty")

    def test_short_and_invalid_items_dropped(self):
        # 裸字符串按「只有正文」处理，模型偶尔这么返回；None 与过短条目直接丢
        items = jdparse.normalize_ai_items([{"text": "会"}, "熟悉 Docker 部署", None])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["text"], "熟悉 Docker 部署")

    def test_terms_backfilled_from_lexicon(self):
        items = jdparse.normalize_ai_items([{"text": "熟悉 Vue 与 TypeScript 组件开发"}])
        self.assertIn("Vue", items[0]["terms"])

    def test_merge_keeps_rule_first_and_marks_ai(self):
        parsed = jdparse.parse_jd(JD)
        rule_count = len(parsed["requirements"])
        merged = jdparse.merge_ai_items(
            parsed,
            jdparse.normalize_ai_items([
                {"text": "熟练掌握 Vue 3 与 TypeScript", "category": "must"},
                {"text": "有微前端 qiankun 落地经验", "category": "nice", "terms": ["qiankun"]},
            ]),
        )
        self.assertEqual(len(merged["requirements"]), rule_count + 1)
        new_item = merged["requirements"][-1]
        self.assertEqual(new_item["source"], "ai")
        self.assertIn("qiankun", merged["terms"])


class TestAiIntoJob(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in ("JDSCOPE_CONFIG", "JDSCOPE_HOME")}
        self._tmp = tempfile.mkdtemp(prefix="jdscope-ai-")
        os.environ["JDSCOPE_CONFIG"] = self._tmp
        os.environ.pop("JDSCOPE_HOME", None)
        from app.api import Api

        config.ensure_dirs(config.data_home())
        self.api = Api()
        conn = db.connect()
        try:
            conn.execute(
                "INSERT INTO bases(code,intent,content,keywords,tags,kind,coverage,created_at)"
                " VALUES('js','前端','熟悉 Vue 3、TypeScript、Node 构建','[\"Vue\",\"TypeScript\"]','[]','html',2,'')"
            )
            conn.commit()
        finally:
            conn.close()

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _requirements(self, job_id):
        conn = db.connect()
        try:
            return [dict(r) for r in conn.execute(
                "SELECT text,source FROM requirements WHERE job_id=? ORDER BY ord", (job_id,))]
        finally:
            conn.close()

    def test_picked_ai_items_persist_and_survive_reanalyze(self):
        body = {
            "jd_raw": JD,
            "company": "示例科技",
            "title": "前端工程师",
            "city": "杭州",
            "base_id": 1,
            "ai_items": [
                {"text": "有微前端 qiankun 落地经验", "category": "nice", "priority": "low",
                 "terms": ["qiankun"]},
            ],
        }
        out = self.api.create_job(None, body, {})
        self.assertTrue(out["ok"])
        reqs = self._requirements(out["job_id"])
        self.assertTrue(any(r["source"] == "ai" and "qiankun" in r["text"] for r in reqs))

        self.api.reanalyze(FakeMatch(), {}, {})
        reqs = self._requirements(1)
        self.assertTrue(any(r["source"] == "ai" and "qiankun" in r["text"] for r in reqs))

    def test_without_ai_items_all_rule(self):
        out = self.api.create_job(None, {"jd_raw": JD, "company": "示例科技", "title": "前端工程师"}, {})
        reqs = self._requirements(out["job_id"])
        self.assertTrue(all(r["source"] == "rule" for r in reqs))


if __name__ == "__main__":
    unittest.main(verbosity=2)
