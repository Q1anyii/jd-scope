"""HTTP 接口层：纯标准库实现，不引入任何 Web 框架。

所有接口只监听 127.0.0.1，数据不出本机。
"""

from __future__ import annotations

import json
import re
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import aggregate, analyze, config, db, jdparse, llm, location, reportmd
from .config import APP_NAME, APP_VERSION, DEFAULT_LLM_BASE_URL, DEFAULT_LLM_MODEL, WEB_DIR, ensure_dirs
from .lexicon import find_terms

ROUTES: list[tuple[str, str, str]] = []  # (method, pattern, handler_name)


def route(method: str, pattern: str):
    def deco(fn):
        ROUTES.append((method, pattern, fn.__name__))
        return fn

    return deco


class Api:
    """把处理函数挂成方法，便于 BaseHTTPRequestHandler 反射调用。"""

    def __init__(self) -> None:
        ensure_dirs()
        with db.connect() as conn:
            db.init_db(conn)

    # ---------- 工具 ----------
    @staticmethod
    def _conn():
        conn = db.connect()
        db.init_db(conn)
        return conn

    def settings_dict(self, conn) -> dict:
        return {
            "base_url": db.get_setting(conn, "llm_base_url", DEFAULT_LLM_BASE_URL),
            "model": db.get_setting(conn, "llm_model", DEFAULT_LLM_MODEL),
            "api_key": db.get_setting(conn, "llm_api_key", ""),
            "weights": json.loads(db.get_setting(conn, "weights", "{}") or "{}"),
        }

    # ---------- 基础 ----------
    @route("GET", r"/api/health")
    def health(self, m, body, q):
        return {
            "ok": True,
            "app": APP_NAME,
            "version": APP_VERSION,
            "data_home": str(config.data_home()),
            "data_home_source": config.data_home_source(),
        }

    @route("GET", r"/api/bootstrap")
    def bootstrap(self, m, body, q):
        conn = self._conn()
        try:
            bases = [dict(r) for r in conn.execute("SELECT * FROM bases ORDER BY id")]
            for b in bases:
                b.pop("content", None)
                b["keywords"] = json.loads(b.get("keywords") or "[]")
                b["tags"] = json.loads(b.get("tags") or "[]")
                b["terms"] = analyze.base_terms(
                    {"keywords": json.dumps(b["keywords"]), "content": ""}
                )
            cfg = self.settings_dict(conn)
            cfg["api_key_set"] = bool(cfg.pop("api_key", ""))
            return {
                "app": APP_NAME,
                "version": APP_VERSION,
                "profile": db.get_profile(conn),
                "bases": bases,
                "settings": cfg,
                "summary": aggregate.summary(conn),
            }
        finally:
            conn.close()

    @route("GET", r"/api/profile")
    def get_profile(self, m, body, q):
        conn = self._conn()
        try:
            return db.get_profile(conn)
        finally:
            conn.close()

    @route("POST", r"/api/profile")
    def save_profile(self, m, body, q):
        conn = self._conn()
        try:
            db.save_profile(conn, body or {})
            return {"ok": True}
        finally:
            conn.close()

    # ---------- 基底库 ----------
    @route("GET", r"/api/bases")
    def list_bases(self, m, body, q):
        conn = self._conn()
        try:
            rows = [dict(r) for r in conn.execute("SELECT * FROM bases ORDER BY id")]
            for r in rows:
                r.pop("content", None)
                r["keywords"] = json.loads(r.get("keywords") or "[]")
                r["tags"] = json.loads(r.get("tags") or "[]")
            return {"items": rows}
        finally:
            conn.close()

    @route("POST", r"/api/bases")
    def create_base(self, m, body, q):
        code = (body.get("code") or "").strip()
        intent = (body.get("intent") or "").strip()
        content = body.get("content") or ""
        if not code or not intent:
            return {"error": "基底代号与求职意向必填"}
        terms = sorted(set(find_terms(content)))
        tags = body.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in re.split(r"[,，、\s]+", tags) if t.strip()]
        conn = self._conn()
        try:
            try:
                conn.execute(
                    "INSERT INTO bases(code,intent,label,content,keywords,tags,coverage,created_at)"
                    " VALUES(?,?,?,?,?,?,?,?)",
                    (
                        code,
                        intent,
                        body.get("label") or "",
                        content,
                        json.dumps(terms, ensure_ascii=False),
                        json.dumps(tags, ensure_ascii=False),
                        len(terms),
                        db.now(),
                    ),
                )
                conn.commit()
            except Exception as e:  # noqa: BLE001
                return {"error": f"代号已存在或写入失败：{e}"}
            return {"ok": True, "terms": terms, "coverage": len(terms)}
        finally:
            conn.close()

    @route("PATCH", r"/api/bases/\d+")
    def patch_base(self, m, body, q):
        bid = int(m.group(0).split("/")[-1])
        conn = self._conn()
        try:
            if "intent" in body:
                conn.execute("UPDATE bases SET intent=? WHERE id=?", (body["intent"], bid))
            if "active" in body:
                conn.execute("UPDATE bases SET active=? WHERE id=?", (1 if body["active"] else 0, bid))
            conn.commit()
            return {"ok": True}
        finally:
            conn.close()

    @route("DELETE", r"/api/bases/\d+")
    def delete_base(self, m, body, q):
        bid = int(m.group(0).split("/")[-1])
        conn = self._conn()
        try:
            conn.execute("DELETE FROM bases WHERE id=?", (bid,))
            conn.commit()
            return {"ok": True}
        finally:
            conn.close()

    # ---------- 岗位 ----------
    @route("POST", r"/api/jobs/parse")
    def parse_preview(self, m, body, q):
        raw = (body.get("jd_raw") or "").strip()
        if len(raw) < 20:
            return {"error": "JD 原文太短，至少 20 字"}
        parsed = jdparse.parse_jd(
            raw,
            company=body.get("company") or "",
            title=body.get("title") or "",
            city=body.get("city") or "",
        )
        return parsed

    @route("POST", r"/api/jobs")
    def create_job(self, m, body, q):
        raw = (body.get("jd_raw") or "").strip()
        if len(raw) < 20:
            return {"error": "JD 原文太短，至少 20 字"}
        conn = self._conn()
        try:
            parsed = jdparse.parse_jd(
                raw,
                company=body.get("company") or "",
                title=body.get("title") or "",
                city=body.get("city") or "",
            )
            if not parsed["company"] or not parsed["title"]:
                return {"error": "公司名与岗位名至少要有一个能从 JD 里识别出来，请在表单里补上"}
            bases = [dict(r) for r in conn.execute("SELECT * FROM bases WHERE active=1")]
            profile = db.get_profile(conn)
            base_id = body.get("base_id")
            base = None
            selection = None
            if base_id:
                base = next((b for b in bases if b["id"] == int(base_id)), None)
            if base is None:
                selection = analyze.pick_base(parsed["terms"], bases, parsed["title"])
                base = selection["base"]
            else:
                selection = analyze.pick_base(parsed["terms"], [base], parsed["title"])

            weights = json.loads(db.get_setting(conn, "weights", "{}") or "{}")
            result = analyze.evaluate(parsed, base, profile, weights)
            cur = conn.execute(
                "INSERT INTO jobs(company,title,city,url,source,jd_raw,jd_hash,status,decision,"
                "base_id,score,score_json,constraint_state,verdict,created_at,updated_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    parsed["company"],
                    parsed["title"],
                    parsed["city"],
                    body.get("url") or "",
                    body.get("source") or "",
                    raw,
                    str(abs(hash(raw))),
                    "new",
                    result["decision_hint"],
                    base["id"] if base else None,
                    result["score"],
                    json.dumps(
                        {
                            "dims": result["dims"],
                            "coverage": result["coverage"],
                            "verdict_reason": result["verdict_reason"],
                            "criteria": (selection or {}).get("criteria", []),
                        },
                        ensure_ascii=False,
                    ),
                    json.dumps(result["constraints"], ensure_ascii=False),
                    result["verdict"],
                    db.now(),
                    db.now(),
                ),
            )
            job_id = cur.lastrowid
            self._persist_analysis(conn, job_id, parsed, result)
            conn.commit()
            return {"ok": True, "job_id": job_id, "score": result["score"], "verdict": result["verdict"]}
        finally:
            conn.close()

    def _persist_analysis(self, conn, job_id: int, parsed: dict, result: dict) -> None:
        # 重算时保留人工维护的缺口进度（状态 / 应答口径 / 补课方向）
        prev: dict[str, tuple[str, str, str]] = {}
        for g in conn.execute(
            "SELECT requirement, status, answer, action FROM gaps WHERE job_id=?", (job_id,)
        ):
            prev[g["requirement"]] = (g["status"], g["answer"], g["action"])

        conn.execute("DELETE FROM requirements WHERE job_id=?", (job_id,))
        conn.execute("DELETE FROM gaps WHERE job_id=?", (job_id,))
        req_ids: dict[str, int] = {}
        for r in result["requirements"]:
            cur = conn.execute(
                "INSERT INTO requirements(job_id,text,category,weight,terms,hit,evidence,priority,ord)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    job_id,
                    r["text"],
                    r["category"],
                    r.get("weight", 1),
                    json.dumps(r.get("terms", []), ensure_ascii=False),
                    r.get("hit", 0),
                    r.get("evidence", ""),
                    r.get("priority", "medium"),
                    r.get("ord", 0),
                ),
            )
            req_ids[r["text"]] = cur.lastrowid
        for g in result["gaps"]:
            status, answer, action = prev.get(g["requirement"], ("open", "", ""))
            gap_id = conn.execute(
                "INSERT INTO gaps(job_id,req_id,requirement,resume_state,gap,priority,action,answer,status,created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    job_id,
                    req_ids.get(g["requirement"]),
                    g["requirement"],
                    g["resume_state"],
                    g["gap"],
                    g["priority"],
                    action or g["action"],
                    answer,
                    status or "open",
                    db.now(),
                ),
            ).lastrowid
            del gap_id

    @route("GET", r"/api/jobs")
    def list_jobs(self, m, body, q):
        conn = self._conn()
        try:
            status = (q.get("status") or [""])[0]
            kw = (q.get("q") or [""])[0].strip()
            sort = (q.get("sort") or [""])[0]
            sql = ("SELECT id,company,title,city,status,decision,base_id,score,verdict,"
                   "score_json,created_at FROM jobs")
            cond, args = [], []
            if status:
                cond.append("status=?")
                args.append(status)
            if kw:
                cond.append("(company LIKE ? OR title LIKE ?)")
                args.append(f"%{kw}%")
                args.append(f"%{kw}%")
            if cond:
                sql += " WHERE " + " AND ".join(cond)
            # 排序白名单，避免把参数拼进 SQL
            order = {
                "score": "score DESC, id DESC",
                "score_asc": "score ASC, id DESC",
                "oldest": "id ASC",
            }.get(sort, "id DESC")
            sql += " ORDER BY " + order
            rows = [dict(r) for r in conn.execute(sql, args)]
            for r in rows:
                r["score_json"] = json.loads(r.get("score_json") or "{}")
            return {"items": rows}
        finally:
            conn.close()

    @route("GET", r"/api/jobs/\d+")
    def job_detail(self, m, body, q):
        job_id = int(m.group(0).split("/")[-1])
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                return {"error": "岗位不存在"}
            job = dict(row)
            base = conn.execute("SELECT * FROM bases WHERE id=?", (job.get("base_id"),)).fetchone()
            reqs = [dict(r) for r in conn.execute(
                "SELECT * FROM requirements WHERE job_id=? ORDER BY category DESC, ord", (job_id,))]
            for r in reqs:
                r["terms"] = json.loads(r.get("terms") or "[]")
            gaps = [dict(r) for r in conn.execute("SELECT * FROM gaps WHERE job_id=? ORDER BY id", (job_id,))]
            sugs = [dict(r) for r in conn.execute("SELECT * FROM suggestions WHERE job_id=? ORDER BY id", (job_id,))]
            score = json.loads(job.get("score_json") or "{}")
            return {
                "job": job,
                "base": dict(base) if base else None,
                "requirements": reqs,
                "gaps": gaps,
                "suggestions": sugs,
                "score": score,
                "constraints": json.loads(job.get("constraint_state") or "[]"),
            }
        finally:
            conn.close()

    @route("PATCH", r"/api/jobs/\d+")
    def patch_job(self, m, body, q):
        job_id = int(m.group(0).split("/")[-1])
        conn = self._conn()
        try:
            allowed = {"status", "decision", "decision_note", "city", "url", "source"}
            for k in list(body):
                if k in allowed:
                    conn.execute(f"UPDATE jobs SET {k}=?, updated_at=? WHERE id=?", (body[k], db.now(), job_id))
            conn.commit()
            return {"ok": True}
        finally:
            conn.close()

    @route("DELETE", r"/api/jobs/\d+")
    def delete_job(self, m, body, q):
        job_id = int(m.group(0).split("/")[-1])
        conn = self._conn()
        try:
            for t in ("requirements", "gaps", "suggestions", "jobs"):
                conn.execute(f"DELETE FROM {t} WHERE {'id' if t=='jobs' else 'job_id'}=?", (job_id,))
            conn.commit()
            return {"ok": True}
        finally:
            conn.close()

    @route("POST", r"/api/jobs/\d+/analyze")
    def reanalyze(self, m, body, q):
        job_id = int(m.group(0).split("/")[-2])
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                return {"error": "岗位不存在"}
            job = dict(row)
            bases = [dict(r) for r in conn.execute("SELECT * FROM bases WHERE active=1")]
            profile = db.get_profile(conn)
            parsed = jdparse.parse_jd(job["jd_raw"], job["company"], job["title"], job["city"])
            selection = analyze.pick_base(parsed["terms"], bases, parsed["title"])
            base = next((b for b in bases if b["id"] == job["base_id"]), None) or selection["base"]
            weights = json.loads(db.get_setting(conn, "weights", "{}") or "{}")
            result = analyze.evaluate(parsed, base, profile, weights)
            conn.execute(
                "UPDATE jobs SET score=?, score_json=?, constraint_state=?, verdict=?, base_id=?, updated_at=?"
                " WHERE id=?",
                (
                    result["score"],
                    json.dumps(
                        {"dims": result["dims"], "coverage": result["coverage"],
                         "verdict_reason": result["verdict_reason"],
                         "criteria": selection.get("criteria", [])},
                        ensure_ascii=False,
                    ),
                    json.dumps(result["constraints"], ensure_ascii=False),
                    result["verdict"],
                    base["id"] if base else None,
                    db.now(),
                    job_id,
                ),
            )
            self._persist_analysis(conn, job_id, parsed, result)
            conn.commit()
            return {"ok": True, "score": result["score"], "verdict": result["verdict"]}
        finally:
            conn.close()

    @route("POST", r"/api/jobs/\d+/export")
    def export_report(self, m, body, q):
        job_id = int(m.group(0).split("/")[-2])
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row is None:
                return {"error": "岗位不存在"}
            job = dict(row)
            base_row = conn.execute("SELECT * FROM bases WHERE id=?", (job.get("base_id"),)).fetchone()
            base = dict(base_row) if base_row else None
            reqs = [dict(r) for r in conn.execute(
                "SELECT * FROM requirements WHERE job_id=? ORDER BY category DESC, ord", (job_id,))]
            for r in reqs:
                r["terms"] = json.loads(r.get("terms") or "[]")
            gaps = [dict(r) for r in conn.execute("SELECT * FROM gaps WHERE job_id=?", (job_id,))]
            sugs = [dict(r) for r in conn.execute("SELECT * FROM suggestions WHERE job_id=?", (job_id,))]
            score = json.loads(job.get("score_json") or "{}")
            analysis = {
                "score": job["score"],
                "verdict": job["verdict"],
                "verdict_reason": score.get("verdict_reason", ""),
                "dims": score.get("dims", {}),
                "coverage": score.get("coverage", {}),
                "weights": json.loads(db.get_setting(conn, "weights", "{}") or "{}"),
                "constraints": json.loads(job.get("constraint_state") or "[]"),
                "gaps": gaps,
                "requirements": reqs,
                "decision_hint": job["decision"],
            }
            text = reportmd.build_report(
                job,
                analysis,
                base,
                {"criteria": score.get("criteria", []), "base": base},
                sugs,
                uncovered=aggregate.uncovered_skills(conn, 2)[:6],
            )
            safe = re.sub(r"[\\/:*?\"<>|]", "-", f"{job['company']}-{job['title']}")[:60]
            path = config.ensure_dirs() / "reports" / f"{job_id:03d}-{safe}.md"
            path.write_text(text, encoding="utf-8")
            return {"ok": True, "markdown": text, "path": str(path)}
        finally:
            conn.close()

    # ---------- 缺口库 ----------
    @route("GET", r"/api/gaps")
    def list_gaps(self, m, body, q):
        conn = self._conn()
        try:
            priority = (q.get("priority") or [""])[0]
            status = (q.get("status") or ["open"])[0]
            sql = ("SELECT g.*, j.company, j.title FROM gaps g"
                   " LEFT JOIN jobs j ON j.id=g.job_id")
            cond, args = [], []
            if priority:
                cond.append("g.priority=?")
                args.append(priority)
            if status:
                cond.append("g.status=?")
                args.append(status)
            if cond:
                sql += " WHERE " + " AND ".join(cond)
            sql += " ORDER BY CASE g.priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, g.id DESC"
            return {"items": [dict(r) for r in conn.execute(sql, args)]}
        finally:
            conn.close()

    @route("PATCH", r"/api/gaps/\d+")
    def patch_gap(self, m, body, q):
        gid = int(m.group(0).split("/")[-1])
        conn = self._conn()
        try:
            for k in ("status", "action", "answer", "priority"):
                if k in body:
                    conn.execute(f"UPDATE gaps SET {k}=? WHERE id=?", (body[k], gid))
            conn.commit()
            return {"ok": True}
        finally:
            conn.close()

    # ---------- 模型 ----------
    @route("POST", r"/api/jobs/\d+/suggest")
    def suggest(self, m, body, q):
        job_id = int(m.group(0).split("/")[-2])
        conn = self._conn()
        try:
            job = dict(conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone() or {})
            base_row = conn.execute("SELECT * FROM bases WHERE id=?", (job.get("base_id"),)).fetchone()
            if not job or base_row is None:
                return {"error": "缺少岗位或基底"}
            cfg = self.settings_dict(conn)
            result = llm.suggest_rewrite(cfg, job["jd_raw"], base_row["content"] or "", body.get("module") or "整体")
            if "items" in result:
                for it in result["items"]:
                    conn.execute(
                        "INSERT INTO suggestions(job_id,module,original,suggestion,reason,adopted,created_at)"
                        " VALUES(?,?,?,?,?,0,?)",
                        (job_id, it["module"], it["original"], it["suggestion"], it["reason"], db.now()),
                    )
                conn.commit()
            return result
        finally:
            conn.close()

    @route("POST", r"/api/gaps/\d+/answer")
    def gap_answer(self, m, body, q):
        gid = int(m.group(0).split("/")[-2])
        conn = self._conn()
        try:
            g = conn.execute("SELECT * FROM gaps WHERE id=?", (gid,)).fetchone()
            if g is None:
                return {"error": "缺口不存在"}
            cfg = self.settings_dict(conn)
            result = llm.answer_gap(cfg, g["requirement"], g["resume_state"], g["gap"])
            if "answer" in result and result["answer"]:
                conn.execute("UPDATE gaps SET answer=? WHERE id=?", (result["answer"], gid))
                conn.commit()
            return result
        finally:
            conn.close()

    @route("POST", r"/api/suggestions/\d+/adopt")
    def adopt(self, m, body, q):
        sid = int(m.group(0).split("/")[-2])
        conn = self._conn()
        try:
            conn.execute("UPDATE suggestions SET adopted=? WHERE id=?",
                         (1 if body.get("adopted", True) else 0, sid))
            conn.commit()
            return {"ok": True}
        finally:
            conn.close()

    @route("POST", r"/api/llm/test")
    def llm_test(self, m, body, q):
        conn = self._conn()
        try:
            cfg = self.settings_dict(conn)
            if body:
                cfg.update({k: body[k] for k in ("base_url", "model", "api_key") if body.get(k)})
            return llm.test_connection(cfg)
        finally:
            conn.close()

    # ---------- 统计 ----------
    @route("GET", r"/api/stats")
    def stats(self, m, body, q):
        conn = self._conn()
        try:
            min_jobs = int((q.get("min_jobs") or ["2"])[0])
            return aggregate.stats_bundle(conn, min_jobs)
        finally:
            conn.close()

    # ---------- 设置 ----------
    @route("GET", r"/api/settings")
    def get_settings(self, m, body, q):
        conn = self._conn()
        try:
            cfg = self.settings_dict(conn)
            cfg["api_key_set"] = bool(cfg.pop("api_key", ""))
            return cfg
        finally:
            conn.close()

    @route("POST", r"/api/settings")
    def save_settings(self, m, body, q):
        conn = self._conn()
        try:
            mapping = {"base_url": "llm_base_url", "model": "llm_model", "api_key": "llm_api_key"}
            for k, col in mapping.items():
                if k in body and body[k] is not None:
                    # 前端传空字符串表示「保持不变」，避免误清空已保存的 key
                    if k == "api_key" and body[k] == "":
                        continue
                    db.set_setting(conn, col, str(body[k]))
            if isinstance(body.get("weights"), dict):
                db.set_setting(conn, "weights", json.dumps(body["weights"], ensure_ascii=False))
            return {"ok": True}
        finally:
            conn.close()

    # ---------- 数据位置 ----------
    @route("GET", r"/api/data-dir")
    def get_data_dir(self, m, body, q):
        return location.describe()

    @route("POST", r"/api/data-dir")
    def set_data_dir(self, m, body, q):
        try:
            return location.switch_to(body.get("path") or "", bool(body.get("migrate", True)))
        except location.SwitchError as exc:
            return {"error": str(exc)}
        except OSError as exc:
            return {"error": f"文件系统拒绝：{exc}"}

    @route("POST", r"/api/data-dir/reset")
    def reset_data_dir(self, m, body, q):
        try:
            return location.reset(bool(body.get("migrate", True)))
        except location.SwitchError as exc:
            return {"error": str(exc)}
        except OSError as exc:
            return {"error": f"文件系统拒绝：{exc}"}

    @route("POST", r"/api/data-dir/open")
    def open_data_dir(self, m, body, q):
        try:
            return location.open_folder()
        except location.SwitchError as exc:
            return {"error": str(exc)}


# ---------------- HTTP 外壳 ----------------

_CT = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".json": "application/json; charset=utf-8",
}


def make_handler(api: Api):
    class Handler(BaseHTTPRequestHandler):
        server_version = f"{APP_NAME}/{APP_VERSION}"
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # 静默，避免污染控制台
            return

        # ---- 响应工具 ----
        def _send_json(self, obj, code=200):
            payload = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(payload)

        def _send_file(self, path: Path):
            if not path.exists() or not path.is_file():
                self._send_json({"error": "not found"}, 404)
                return
            data = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", _CT.get(path.suffix, "application/octet-stream"))
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _static(self):
            rel = urlparse(self.path).path.lstrip("/") or "index.html"
            if rel in ("", "/"):
                rel = "index.html"
            target = (WEB_DIR / rel).resolve()
            try:
                target.relative_to(WEB_DIR.resolve())
            except ValueError:
                self._send_json({"error": "forbidden"}, 403)
                return
            self._send_file(target)

        # ---- 分发 ----
        def _dispatch(self, method: str):
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)
            body = {}
            if method in ("POST", "PATCH", "DELETE"):
                length = int(self.headers.get("Content-Length") or 0)
                if length:
                    raw = self.rfile.read(length)
                    try:
                        body = json.loads(raw.decode("utf-8") or "{}")
                    except Exception:
                        body = {}
            if not path.startswith("/api/"):
                self._static()
                return
            for r_method, pattern, name in ROUTES:
                if r_method != method:
                    continue
                m = re.fullmatch(pattern, path)
                if m:
                    try:
                        result = getattr(api, name)(m, body, query)
                    except Exception:  # noqa: BLE001
                        traceback.print_exc()
                        self._send_json({"error": "内部错误，详见控制台日志"}, 500)
                        return
                    if isinstance(result, dict) and result.get("error") and len(result) == 1:
                        self._send_json(result, 400)
                    else:
                        self._send_json(result)
                    return
            self._send_json({"error": f"未知接口 {method} {path}"}, 404)

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

        def do_PATCH(self):
            self._dispatch("PATCH")

        def do_DELETE(self):
            self._dispatch("DELETE")

        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()

    return Handler


def make_server(port: int = 0) -> ThreadingHTTPServer:
    api = Api()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(api))
    httpd.daemon_threads = True
    return httpd
