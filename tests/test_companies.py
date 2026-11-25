"""公司档案：文件夹隔离、文件落盘、v1 → v2 迁移。全部在临时目录里跑。"""

from __future__ import annotations

import json
import base64
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import companies, config, db  # noqa: E402


class CompanyBase(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in ("JDSCOPE_CONFIG", "JDSCOPE_HOME")}
        self._tmp = tempfile.mkdtemp(prefix="jdscope-co-")
        os.environ["JDSCOPE_CONFIG"] = str(Path(self._tmp) / "config")
        os.environ.pop("JDSCOPE_HOME", None)
        config.ensure_dirs(config.data_home())
        self.conn = db.connect()
        db.init_db(self.conn)
        self.conn.execute(
            "INSERT INTO jobs(company,title,city,url,jd_raw,status,decision,score,score_json,"
            "constraint_state,verdict,created_at,updated_at)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "示例科技", "前端工程师", "杭州", "https://example.com/j/1",
                "岗位职责：做前端。\n任职要求：熟练掌握 Vue。", "new", "go", 77.3,
                json.dumps({"dims": {"must": 1.0, "duty": 0.5}, "verdict_reason": "基本盘够"},
                           ensure_ascii=False),
                "[]", "建议投", db.now(), db.now(),
            ),
        )
        self.conn.execute(
            "INSERT INTO requirements(job_id,text,category,weight,terms,hit,evidence,priority,ord,source)"
            " VALUES(1,'熟练掌握 Vue','must',1,'[\"Vue\"]',2,'命中 Vue','high',0,'rule')"
        )
        self.conn.execute(
            "INSERT INTO bases(code,intent,label,content,keywords,tags,kind,coverage,created_at)"
            " VALUES('js','前端','前端通用','<h1>张三</h1><p>前端</p><h2>教育</h2>','[]','[]','html',0,?)",
            (db.now(),),
        )
        self.conn.commit()
        self.job_id = 1

    def tearDown(self):
        self.conn.close()
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)


class TestGeneralResume(CompanyBase):
    def test_ensure_general_is_idempotent(self):
        first = companies.ensure_general(self.conn)
        second = companies.ensure_general(self.conn)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(first["kind"], "general")
        self.assertEqual(first["name"], "通用简历")
        root = Path(self._tmp) / "config" / "resumes" / first["folder"]
        self.assertTrue((root / "strategy.md").exists())
        self.assertIn("母版", (root / "strategy.md").read_text(encoding="utf-8"))

    def test_general_listed_first_and_undeletable(self):
        companies.create(self.conn, "普通公司", self.job_id, None)
        general = companies.ensure_general(self.conn)
        items = companies.list_all(self.conn)
        self.assertEqual(items[0]["id"], general["id"])
        out = companies.delete_record(self.conn, general["id"])
        self.assertIn("error", out)
        self.assertIn("不能删除", out["error"])

    def test_general_adopts_existing_folder(self):
        root = Path(self._tmp) / "config" / "resumes" / companies.GENERAL_FOLDER
        root.mkdir(parents=True, exist_ok=True)
        (root / "resume.json").write_text('{"meta":{},"modules":{}}', encoding="utf-8")
        item = companies.ensure_general(self.conn)
        self.assertEqual(item["folder"], companies.GENERAL_FOLDER)
        self.assertTrue(item["files"]["resume"])


class TestCompanyFiles(CompanyBase):
    def test_detect_base_kind(self):
        self.assertEqual(companies.detect_kind("<h1>x</h1>"), "html")
        self.assertEqual(companies.detect_kind('{"meta":{},"modules":{}}'), "json")
        self.assertEqual(companies.detect_kind('{"hello":1}'), "html")
        self.assertEqual(companies.detect_kind("{ not json"), "html")

    def test_create_writes_folder_and_files(self):
        item = companies.create(self.conn, "示例科技", self.job_id, 1)
        root = Path(self._tmp) / "config" / "resumes" / item["folder"]
        self.assertTrue(root.is_dir())
        prefix = "示例科技-前端工程师"
        for name in (f"{prefix}-jd.txt", f"{prefix}-strategy.md", f"{prefix}-report.md", "base.html"):
            self.assertTrue((root / name).exists(), name)
        strategy = (root / f"{prefix}-strategy.md").read_text(encoding="utf-8")
        self.assertIn("示例科技", strategy)
        self.assertIn("建议投", strategy)
        self.assertIn("基本盘够", (root / f"{prefix}-report.md").read_text(encoding="utf-8"))
        self.assertFalse((root / "resume.json").exists())

    def test_same_name_never_overwrites(self):
        first = companies.create(self.conn, "同名公司", self.job_id, None)
        second = companies.create(self.conn, "同名公司", self.job_id, None)
        self.assertNotEqual(first["folder"], second["folder"])
        self.assertTrue((Path(self._tmp) / "config" / "resumes" / first["folder"]).exists())
        self.assertTrue((Path(self._tmp) / "config" / "resumes" / second["folder"]).exists())

    def test_resume_roundtrip(self):
        cid = companies.create(self.conn, "简历公司", self.job_id, None)["id"]
        self.assertIsNone(companies.resume_state(self.conn, cid))
        state = {"meta": {"name": "张三"}, "modules": {"edu": {}}, "order": ["edu"]}
        out = companies.save_resume(self.conn, cid, state)
        self.assertTrue(out["ok"])
        self.assertEqual(companies.resume_state(self.conn, cid)["meta"]["name"], "张三")

    def test_resume_rejects_bad_state(self):
        cid = companies.create(self.conn, "坏结构", self.job_id, None)["id"]
        out = companies.save_resume(self.conn, cid, {"meta": {}})
        self.assertIn("error", out)

    def test_strategy_and_export(self):
        cid = companies.create(self.conn, "导出公司", self.job_id, None)["id"]
        companies.save_strategy(self.conn, cid, "# 自定义策略\n")
        self.assertIn("自定义策略", companies.read_strategy(self.conn, cid))
        out = companies.save_export(self.conn, cid, "<!doctype html><html><body>hi</body></html>" * 20)
        self.assertTrue(out["ok"])
        detail = companies.detail(self.conn, cid)
        self.assertTrue(detail["files"]["html"])
        self.assertEqual(detail["status"], "exported")

    def test_pdf_archive_once_and_skip_existing(self):
        cid = companies.create(self.conn, "PDF 公司", self.job_id, None)["id"]
        first = companies.save_pdf(self.conn, cid, b"%PDF-1.4\n" + b"x" * 300)
        self.assertTrue(first["ok"])
        self.assertFalse(first["skipped"])
        root = Path(self._tmp) / "config" / "resumes" / companies.detail(self.conn, cid)["folder"]
        target = root / first["filename"]
        self.assertTrue(target.exists())
        self.assertIn("-简历.pdf", target.name)
        self.assertTrue(companies.detail(self.conn, cid)["files"]["pdf"])

        second = companies.save_pdf(self.conn, cid, b"%PDF-1.4\n" + b"y" * 300)
        self.assertTrue(second["skipped"])
        self.assertEqual(target.read_bytes(), b"%PDF-1.4\n" + b"x" * 300)

    def test_delete_record_keeps_folder(self):
        cid = companies.create(self.conn, "保留公司", self.job_id, None)["id"]
        folder = companies.detail(self.conn, cid)["folder"]
        out = companies.delete_record(self.conn, cid)
        self.assertTrue(out["kept"])
        self.assertTrue((Path(self._tmp) / "config" / "resumes" / folder).exists())
        self.assertEqual(companies.detail(self.conn, cid), {})

    def test_detail_migrates_legacy_filenames(self):
        cid = companies.create(self.conn, "迁移公司", self.job_id, None)["id"]
        folder = companies.detail(self.conn, cid)["folder"]
        root = Path(self._tmp) / "config" / "resumes" / folder
        # 模拟旧版公司文件夹：先删掉新版支撑文件，再放固定文件名 + 岗位名当 PDF 名
        for name in ("迁移公司-前端工程师-jd.txt", "迁移公司-前端工程师-strategy.md", "迁移公司-前端工程师-report.md"):
            (root / name).unlink(missing_ok=True)
        (root / "jd.txt").write_text("旧 JD", encoding="utf-8")
        (root / "strategy.md").write_text("旧策略", encoding="utf-8")
        (root / "report.md").write_text("旧报告", encoding="utf-8")
        (root / "resume.html").write_text("<html><body><h1>张三</h1></body></html>", encoding="utf-8")
        (root / "前端工程师.pdf").write_bytes(b"%PDF-1.4\n" + b"x" * 50)
        detail = companies.detail(self.conn, cid)
        self.assertTrue((root / "迁移公司-前端工程师-jd.txt").exists())
        self.assertTrue((root / "张三-前端工程师-简历.html").exists())
        self.assertTrue((root / "张三-前端工程师-简历.pdf").exists())
        self.assertTrue(detail["files"]["jd"])
        self.assertTrue(detail["files"]["html"])
        self.assertTrue(detail["files"]["pdf"])

        # 没有 resume.json 时，导出兜底也要能从已迁移的成品 HTML 读到姓名
        out = companies.save_export(self.conn, cid, "<html><body>hi</body></html>")
        self.assertEqual(out["filename"], "张三-前端工程师-简历.html")


class TestApiCompanies(CompanyBase):
    def setUp(self):
        super().setUp()
        import threading
        from app.api import make_server

        self.httpd = make_server(0)
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        super().tearDown()

    def call(self, path, method="GET", body=None):
        import urllib.error
        import urllib.request

        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self.base + path, data=data, method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return json.loads(exc.read().decode("utf-8"))

    def test_general_resume_endpoint(self):
        first = self.call("/api/resume/general", "POST", {})
        second = self.call("/api/resume/general", "POST", {})
        self.assertTrue(first["ok"])
        self.assertEqual(first["company"]["id"], second["company"]["id"])
        self.assertEqual(first["company"]["kind"], "general")
        self.assertEqual(self.call("/api/companies")["items"][0]["kind"], "general")

    def test_company_lifecycle(self):
        created = self.call("/api/companies", "POST", {"job_id": 1, "base_id": 1})
        cid = created["company"]["id"]
        self.assertIn("folder", created["company"])

        listed = self.call("/api/companies")
        self.assertEqual(len(listed["items"]), 1)

        detail = self.call(f"/api/companies/{cid}")
        self.assertIn("strategy", detail)
        self.assertTrue(detail["files"]["base"])

        self.assertIn("error", self.call(f"/api/companies/{cid}/resume"))

        state = {"meta": {"name": "张三"}, "modules": {"edu": {}}, "order": ["edu"]}
        self.assertTrue(self.call(f"/api/companies/{cid}/resume", "POST", {"state": state})["ok"])
        self.assertEqual(self.call(f"/api/companies/{cid}/resume")["meta"]["name"], "张三")

        self.assertTrue(self.call(f"/api/companies/{cid}/strategy", "POST", {"text": "# s"})["ok"])
        self.assertIn("# s", self.call(f"/api/companies/{cid}")["strategy"])

        html = "<!doctype html><html><body>" + "x" * 400 + "</body></html>"
        self.assertTrue(self.call(f"/api/companies/{cid}/export", "POST", {"html": html})["ok"])

        pdf_b64 = base64.b64encode(b"%PDF-1.4\n" + b"z" * 200).decode("ascii")
        pdf_out = self.call(f"/api/companies/{cid}/pdf", "POST", {"pdf": pdf_b64})
        self.assertTrue(pdf_out["ok"])
        self.assertFalse(pdf_out["skipped"])
        self.assertTrue(self.call(f"/api/companies/{cid}")["files"]["pdf"])

        self.assertTrue(self.call(f"/api/companies/{cid}/adopt-base", "POST", {})["ok"])
        self.assertIn("error", self.call(f"/api/companies/{cid}/base-html"))

        self.assertTrue(self.call(f"/api/companies/{cid}", "DELETE")["kept"])


class TestSchemaMigration(unittest.TestCase):
    def test_v1_database_gets_new_columns(self):
        tmp = tempfile.mkdtemp(prefix="jdscope-mig-")
        path = Path(tmp) / "old.db"
        raw = sqlite3.connect(path)
        raw.executescript(
            """
            CREATE TABLE meta(k TEXT PRIMARY KEY, v TEXT);
            CREATE TABLE bases(id INTEGER PRIMARY KEY, code TEXT, intent TEXT, content TEXT,
                               keywords TEXT, tags TEXT, coverage INTEGER, active INTEGER, created_at TEXT);
            CREATE TABLE requirements(id INTEGER PRIMARY KEY, job_id INTEGER, text TEXT, category TEXT,
                                      weight REAL, terms TEXT, hit INTEGER, evidence TEXT,
                                      priority TEXT, ord INTEGER);
            INSERT INTO meta(k,v) VALUES('schema_version','1');
            INSERT INTO bases(code,intent,content) VALUES('old','旧基底','熟悉 Python');
            INSERT INTO requirements(job_id,text,terms) VALUES(1,'熟悉 Python','["Python"]');
            """
        )
        raw.commit()
        raw.close()
        conn = db.connect(path)
        try:
            db.init_db(conn)
            self.assertNotEqual(db._columns(conn, "bases"), set())
            self.assertIn("kind", db._columns(conn, "bases"))
            self.assertIn("source", db._columns(conn, "requirements"))
            self.assertIn("companies", {r["name"] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")})
            version = conn.execute("SELECT v FROM meta WHERE k='schema_version'").fetchone()["v"]
            self.assertEqual(version, "4")
            self.assertIn("kind", db._columns(conn, "companies"))
            self.assertIn("age", db._columns(conn, "profile"))
            row = conn.execute("SELECT kind FROM bases WHERE code='old'").fetchone()
            self.assertEqual(row["kind"], "html")
            row = conn.execute("SELECT source FROM requirements WHERE job_id=1").fetchone()
            self.assertEqual(row["source"], "rule")
        finally:
            conn.close()
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
