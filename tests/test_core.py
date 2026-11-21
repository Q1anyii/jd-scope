"""核心逻辑单元测试（纯标准库 unittest）。

运行：python -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 先固定数据目录，避免测试写进真实用户数据
_TMP = tempfile.mkdtemp(prefix="jdscope-test-")
os.environ["JDSCOPE_HOME"] = _TMP

from app import aggregate, analyze, db, jdparse, reportmd  # noqa: E402
from app.lexicon import find_terms  # noqa: E402

DEMO_JD = (ROOT / "samples" / "demo_jd.txt").read_text(encoding="utf-8")
DEMO_RESUME = (ROOT / "samples" / "demo_resume.html").read_text(encoding="utf-8")


class TestLexicon(unittest.TestCase):
    def test_longest_match_wins(self):
        self.assertIn("MySQL", find_terms("熟悉 MySQL 数据库"))
        self.assertNotIn("SQL", find_terms("熟悉 MySQL 数据库"))

    def test_framework_not_double_counted(self):
        terms = find_terms("熟悉 Spring Boot 开发")
        self.assertIn("Spring Boot", terms)
        self.assertNotIn("Spring", terms)

    def test_no_false_positive_on_generic_word(self):
        self.assertNotIn("文档写作", find_terms("负责文档切分与入库"))

    def test_empty_input(self):
        self.assertEqual(find_terms(""), [])


class TestJdParse(unittest.TestCase):
    def setUp(self):
        self.p = jdparse.parse_jd(DEMO_JD)

    def test_meta_fields(self):
        self.assertEqual(self.p["company"], "示例数据科技有限公司")
        self.assertEqual(self.p["title"], "AI 应用开发工程师（Agent 方向）")
        self.assertEqual(self.p["city"], "深圳")

    def test_sections_split(self):
        cats = {r["category"] for r in self.p["requirements"]}
        self.assertEqual(cats, {"must", "duty", "nice"})
        counts = {r["category"]: 0 for r in self.p["requirements"]}
        for r in self.p["requirements"]:
            counts[r["category"]] += 1
        self.assertEqual(counts, {"must": 5, "duty": 4, "nice": 3})

    def test_constraints(self):
        kinds = {c["kind"] for c in self.p["constraints"]}
        self.assertIn("degree", kinds)
        self.assertIn("years", kinds)
        years = next(c for c in self.p["constraints"] if c["kind"] == "years")
        self.assertEqual(years["level"], 2)

    def test_terms_not_empty(self):
        for t in ("Python", "FastAPI", "LangGraph", "RAG"):
            self.assertIn(t, self.p["terms"])

    def test_short_text_does_not_crash(self):
        out = jdparse.parse_jd("招人")
        self.assertEqual(out["requirements"], [])


class TestAnalyze(unittest.TestCase):
    def _base(self, code="ai-app", content=DEMO_RESUME):
        terms = sorted(set(find_terms(content)))
        return {
            "id": 1,
            "code": code,
            "intent": "AI 应用开发工程师",
            "content": content,
            "keywords": json.dumps(terms, ensure_ascii=False),
            "coverage": len(terms),
        }

    def _parsed(self):
        return jdparse.parse_jd(DEMO_JD)

    def test_score_range_and_dims(self):
        res = analyze.evaluate(self._parsed(), self._base(), {"education": "本科", "years": 2, "cities": "深圳"})
        self.assertGreaterEqual(res["score"], 0)
        self.assertLessEqual(res["score"], 100)
        self.assertEqual(set(res["dims"]), {"must", "duty", "nice", "constraint"})
        self.assertIn(res["verdict"], {"建议投", "可投，需针对性改写", "谨慎，先补缺口", "不建议投"})

    def test_degree_fail_forces_skip(self):
        profile = {"education": "大专", "years": 2, "cities": "深圳"}
        res = analyze.evaluate(self._parsed(), self._base(), profile)
        self.assertEqual(res["verdict"], "不建议投")
        self.assertEqual(res["decision_hint"], "skip")
        fail = [c for c in res["constraints"] if c["state"] == "fail"]
        self.assertTrue(fail)

    def test_unknown_profile_is_not_fail(self):
        res = analyze.evaluate(self._parsed(), self._base(), {})
        self.assertNotEqual(res["verdict"], "不建议投")
        states = {c["state"] for c in res["constraints"]}
        self.assertIn("unknown", states)

    def test_no_base_still_scores(self):
        res = analyze.evaluate(self._parsed(), None, {"education": "本科"})
        self.assertEqual(res["dims"]["must"], 0.0)
        self.assertGreater(res["score"], 0)  # 硬性条件维度仍计分

    def test_gaps_have_action_and_priority(self):
        res = analyze.evaluate(self._parsed(), self._base(), {"education": "本科", "years": 2, "cities": "深圳"})
        for g in res["gaps"]:
            self.assertTrue(g["action"])
            self.assertIn(g["priority"], {"high", "medium", "low"})

    def test_pick_base_prefers_most_hits(self):
        base_ai = self._base("ai-app")
        base_java = {
            "id": 2,
            "code": "backend",
            "intent": "Java 后端开发工程师",
            "content": "<p>Spring Boot MySQL Redis 微服务 高并发</p>",
            "keywords": json.dumps(["Spring Boot", "MySQL", "Redis", "微服务", "高并发"], ensure_ascii=False),
            "coverage": 5,
        }
        sel = analyze.pick_base(self._parsed()["terms"], [base_java, base_ai], self._parsed()["title"])
        self.assertEqual(sel["base"]["code"], "ai-app")
        self.assertTrue(sel["criteria"])

    def test_pick_base_without_bases(self):
        sel = analyze.pick_base(["Python"], [], "")
        self.assertIsNone(sel["base"])


class TestPipelineAndAggregate(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect()
        db.init_db(self.conn)
        self.conn.execute("DELETE FROM jobs")
        self.conn.execute("DELETE FROM requirements")
        self.conn.execute("DELETE FROM gaps")
        self.conn.execute("DELETE FROM bases")
        self.conn.commit()
        db.save_profile(self.conn, {"education": "本科", "years": 2, "cities": "深圳", "certs": "CET-4"})
        terms = sorted(set(find_terms(DEMO_RESUME)))
        self.conn.execute(
            "INSERT INTO bases(code,intent,label,content,keywords,tags,coverage,created_at)"
            " VALUES('ai-app','AI 应用开发工程师','','',?, '[]', ?, ?)",
            (json.dumps(terms, ensure_ascii=False), len(terms), db.now()),
        )
        self.conn.commit()
        self.base = dict(self.conn.execute("SELECT * FROM bases").fetchone())

    def tearDown(self):
        self.conn.close()

    def _add_job(self, jd_text, city="深圳"):
        parsed = jdparse.parse_jd(jd_text)
        res = analyze.evaluate(parsed, self.base, db.get_profile(self.conn))
        cur = self.conn.execute(
            "INSERT INTO jobs(company,title,city,jd_raw,status,decision,base_id,score,score_json,"
            "constraint_state,verdict,created_at,updated_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                parsed["company"], parsed["title"], city, jd_text, "new", res["decision_hint"],
                self.base["id"], res["score"],
                json.dumps({"dims": res["dims"], "coverage": res["coverage"],
                            "verdict_reason": res["verdict_reason"]}, ensure_ascii=False),
                json.dumps(res["constraints"], ensure_ascii=False), res["verdict"], db.now(), db.now(),
            ),
        )
        job_id = cur.lastrowid
        for r in res["requirements"]:
            self.conn.execute(
                "INSERT INTO requirements(job_id,text,category,weight,terms,hit,evidence,priority,ord)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (job_id, r["text"], r["category"], r.get("weight", 1),
                 json.dumps(r.get("terms", []), ensure_ascii=False), r["hit"],
                 r["evidence"], r["priority"], r["ord"]),
            )
        for g in res["gaps"]:
            self.conn.execute(
                "INSERT INTO gaps(job_id,requirement,resume_state,gap,priority,action,answer,status,created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (job_id, g["requirement"], g["resume_state"], g["gap"], g["priority"],
                 g["action"], "", "open", db.now()),
            )
        self.conn.commit()
        return job_id

    def test_summary_and_term_demand(self):
        self._add_job(DEMO_JD)
        self._add_job(DEMO_JD.replace("深圳", "东莞"))
        s = aggregate.summary(self.conn)
        self.assertEqual(s["jobs"], 2)
        rows = aggregate.term_demand(self.conn)
        self.assertTrue(rows)
        self.assertTrue(any(r["term"] == "Python" and r["jobs"] == 2 for r in rows))

    def test_uncovered_skills_needs_threshold(self):
        self._add_job(DEMO_JD)
        self.assertEqual(aggregate.uncovered_skills(self.conn, 2), [])
        self._add_job(DEMO_JD)
        self.assertTrue(aggregate.uncovered_skills(self.conn, 2))

    def test_base_performance_counts(self):
        jid = self._add_job(DEMO_JD)
        self.conn.execute("UPDATE jobs SET status='applied' WHERE id=?", (jid,))
        self.conn.commit()
        rows = aggregate.base_performance(self.conn)
        self.assertEqual(rows[0]["applied"], 1)

    def test_report_contains_required_sections(self):
        jid = self._add_job(DEMO_JD)
        job = dict(self.conn.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone())
        score = json.loads(job["score_json"])
        reqs = [dict(r) for r in self.conn.execute("SELECT * FROM requirements WHERE job_id=?", (jid,))]
        for r in reqs:
            r["terms"] = json.loads(r["terms"])
        gaps = [dict(r) for r in self.conn.execute("SELECT * FROM gaps WHERE job_id=?", (jid,))]
        analysis = {
            "score": job["score"], "verdict": job["verdict"],
            "verdict_reason": score.get("verdict_reason", ""),
            "dims": score["dims"], "coverage": score["coverage"],
            "weights": {"must": 30, "duty": 30, "nice": 15, "constraint": 25},
            "constraints": json.loads(job["constraint_state"]),
            "gaps": gaps, "requirements": reqs,
            "decision_hint": job["decision"],
        }
        md = reportmd.build_report(job, analysis, self.base, {"criteria": ["① 术语命中"], "base": self.base}, [])
        for section in ("一、结论", "二、四维得分", "三、基底选型", "五、关键词覆盖", "六、缺口清单", "附：原始 JD"):
            self.assertIn(section, md)
        self.assertIn("只改表达、不动事实", md)


class HttpCase(unittest.TestCase):
    """起一个真实 HTTP 服务，走完整接口链路。"""

    @classmethod
    def setUpClass(cls):
        import threading

        from app.api import make_server

        cls.httpd = make_server(0)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def call(self, path, method="GET", body=None):
        import urllib.request

        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self.base + path, data=data, method=method,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def test_health_and_static(self):
        self.assertTrue(self.call("/api/health")["ok"])
        import urllib.request
        with urllib.request.urlopen(self.base + "/", timeout=15) as resp:
            html = resp.read().decode("utf-8")
        self.assertIn("JDScope", html)
        self.assertIn("/js/main.js", html)
        self.assertIn("/vendor/vue.global.prod.js", html)


class TestReanalyzeKeepsGapProgress(HttpCase):
    def test_gap_status_and_answer_survive_recalc(self):
        # 清空库，准备一份基底
        conn = db.connect()
        db.init_db(conn)
        for t in ("jobs", "requirements", "gaps", "suggestions", "bases"):
            conn.execute(f"DELETE FROM {t}")
        conn.commit()
        conn.close()

        self.call("/api/profile", "POST", {"education": "本科", "years": 2, "cities": "深圳"})
        self.call("/api/bases", "POST", {
            "code": "ai-app", "intent": "AI 应用开发工程师", "content": DEMO_RESUME,
        })
        job = self.call("/api/jobs", "POST", {"jd_raw": DEMO_JD})
        self.assertTrue(job.get("ok"), job)

        detail = self.call(f"/api/jobs/{job['job_id']}")
        self.assertGreater(len(detail["gaps"]), 0)
        gap_id = detail["gaps"][0]["id"]

        self.call(f"/api/gaps/{gap_id}", "PATCH", {"status": "learning", "answer": "已开始补课"})
        self.call(f"/api/jobs/{job['job_id']}/analyze", "POST", {})

        after = self.call(f"/api/jobs/{job['job_id']}")
        matched = [g for g in after["gaps"] if g["requirement"] == detail["gaps"][0]["requirement"]]
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["status"], "learning")
        self.assertEqual(matched[0]["answer"], "已开始补课")

    def test_export_returns_markdown(self):
        job = self.call("/api/jobs", "POST", {"jd_raw": DEMO_JD})
        md = self.call(f"/api/jobs/{job['job_id']}/export", "POST", {})
        self.assertIn("岗位匹配报告", md["markdown"])
        self.assertTrue(Path(md["path"]).exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
