"""公司档案：一家公司一个本地文件夹。

目录形态（位于当前数据目录下，随数据目录迁移一起搬走）：

    resumes/
      示例科技-1/
        jd.txt          JD 原文
        strategy.md     这家公司的策略（岗位判断 / 缺口 / 改写与投递动作）
        resume.json     编辑器完整状态（事实源，可再次打开继续改）
        resume.html     导出的成品简历快照
        report.md       入库时自动生成的分析摘要
        base.html       从 HTML 基底复制来的原文，供编辑器首次导入

数据库里只存文件夹名（不含绝对路径），所以换机器、换数据目录都能直接用。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from . import config, db

ILLEGAL = re.compile(r'[\\/:*?"<>|\r\n\t]+')
MAX_STEM = 40


def _safe_stem(name: str) -> str:
    stem = ILLEGAL.sub("-", (name or "").strip()).strip(" .-")
    stem = re.sub(r"-{2,}", "-", stem)
    return (stem[:MAX_STEM] or "company")


def _unique_folder(root: Path, stem: str) -> str:
    if not (root / stem).exists():
        return stem
    for i in range(2, 100):
        candidate = f"{stem}-{i}"
        if not (root / candidate).exists():
            return candidate
    return f"{stem}-{db.now().replace(':', '')}"


def resumes_root() -> Path:
    return config.data_home() / "resumes"


def folder_of(row) -> Path:
    return resumes_root() / (row["folder"] if not isinstance(row, dict) else row.get("folder", ""))


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _read(path: Path, limit: int = 0) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="ignore")
    return text[:limit] if limit else text


def _strategy_skeleton(conn, name: str, job, base_label: str) -> str:
    lines = [f"# {name} · 策略", ""]
    if job:
        score = job["score"] or 0
        lines += [
            f"- 岗位：{job['title']}" + (f"（{job['city']}）" if job["city"] else ""),
            f"- 结论：{job['verdict'] or '未判定'} · {score} / 100",
        ]
        if job["url"]:
            lines.append(f"- 链接：{job['url']}")
        score_json = {}
        try:
            score_json = json.loads(job["score_json"] or "{}")
        except ValueError:
            score_json = {}
        dims = score_json.get("dims") or {}
        labels = {"must": "硬性", "duty": "职责", "nice": "加分", "constraint": "约束"}
        dim_text = "、".join(
            f"{labels.get(k, k)} {round(v * 100)}%" for k, v in dims.items() if v is not None
        )
        if dim_text:
            lines.append(f"- 四维：{dim_text}")
    if base_label:
        lines.append(f"- 基底：{base_label}")
    lines.append(f"- 建档：{db.now()[:10]}")
    lines += ["", "## 一、这份 JD 真正要什么", ""]
    reqs = conn.execute(
        "SELECT text, category, source FROM requirements WHERE job_id=? AND category='must'"
        " ORDER BY ord LIMIT 6",
        (job["id"] if job else -1,),
    ).fetchall()
    if reqs:
        for r in reqs:
            tag = "（AI）" if r["source"] == "ai" else ""
            lines.append(f"- {r['text']}{tag}")
    else:
        lines.append("- （未关联岗位，手动补）")
    lines += ["", "## 二、我的缺口", ""]
    gaps = conn.execute(
        "SELECT requirement, gap FROM gaps WHERE job_id=? ORDER BY CASE priority"
        " WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END LIMIT 8",
        (job["id"] if job else -1,),
    ).fetchall()
    if gaps:
        for g in gaps:
            lines.append(f"- **{g['requirement'][:30]}**：{g['gap']}")
    else:
        lines.append("- （暂无缺口记录）")
    lines += [
        "",
        "## 三、改写动作",
        "",
        "- [ ] 按缺口逐条决定：补事实 / 换表述 / 不写",
        "- [ ] 在简历编辑器里改，导出前逐页检查不溢出",
        "",
        "## 四、投递记录",
        "",
        "- [ ] 投递",
        "- [ ] 笔试",
        "- [ ] 一面",
    ]
    return "\n".join(lines) + "\n"


def _report(conn, name: str, job, base_label: str) -> str:
    if not job:
        return f"# {name} · 建档摘要\n\n未关联岗位，仅建立公司文件夹。\n"
    try:
        reason = (json.loads(job["score_json"] or "{}") or {}).get("verdict_reason") or ""
    except (ValueError, TypeError):
        reason = ""
    lines = [
        f"# {name} · 建档摘要",
        "",
        f"- 岗位：{job['title']}",
        f"- 结论：{job['verdict']}（{job['score']} / 100）",
        f"- 基底：{base_label or '未选'}",
        "",
        "## 判定理由",
        "",
        reason or "（无）",
        "",
        "## 缺口清单",
        "",
    ]
    gaps = conn.execute(
        "SELECT requirement, gap, action FROM gaps WHERE job_id=? ORDER BY id", (job["id"],)
    ).fetchall()
    if gaps:
        for g in gaps:
            lines.append(f"- {g['requirement'][:40]}｜{g['gap']}")
    else:
        lines.append("- 无")
    return "\n".join(lines) + "\n"


def detect_kind(content: str) -> str:
    """基底内容判型：编辑器导出的配置（JSON，含 modules）算 json，其余按 HTML 文本。"""
    text = (content or "").lstrip()
    if not text.startswith("{"):
        return "html"
    try:
        data = json.loads(text)
    except ValueError:
        return "html"
    return "json" if isinstance(data, dict) and isinstance(data.get("modules"), dict) else "html"


def create(conn, name: str, job_id: int | None = None, base_id: int | None = None) -> dict:
    """建公司档案：写文件夹 + 落库；同名自动加序号，绝不覆盖已有目录。"""
    job = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id or -1,)).fetchone()
    if not name:
        name = (job["company"] if job else "") or "未命名公司"
    folder = _unique_folder(resumes_root(), _safe_stem(name))
    root = resumes_root() / folder
    root.mkdir(parents=True, exist_ok=True)

    base = conn.execute("SELECT * FROM bases WHERE id=?", (base_id or -1,)).fetchone()
    base_label = base["label"] if base else ""
    if base and (base["kind"] or "html") == "json":
        _write(root / "resume.json", base["content"] or "")
    elif base:
        # HTML 基底：原样放进来，编辑器首次打开时用 parseResumeHtml 导入
        _write(root / "base.html", base["content"] or "")

    if job:
        _write(root / "jd.txt", job["jd_raw"] or "")
    _write(root / "strategy.md", _strategy_skeleton(conn, name, job, base_label))
    _write(root / "report.md", _report(conn, name, job, base_label))

    cur = conn.execute(
        "INSERT INTO companies(name, folder, job_id, base_id, status, note, created_at, updated_at)"
        " VALUES(?,?,?,?,?,?,?,?)",
        (
            name,
            folder,
            job["id"] if job else None,
            base["id"] if base else None,
            "draft",
            "",
            db.now(),
            db.now(),
        ),
    )
    conn.commit()
    return detail(conn, cur.lastrowid)


def detail(conn, cid: int) -> dict:
    row = conn.execute("SELECT * FROM companies WHERE id=?", (cid,)).fetchone()
    if row is None:
        return {}
    item = dict(row)
    root = folder_of(item)
    job = conn.execute("SELECT * FROM jobs WHERE id=?", (item["job_id"] or -1,)).fetchone()
    reviews = {
        "jd": (root / "jd.txt").exists(),
        "resume": (root / "resume.json").exists(),
        "html": (root / "resume.html").exists(),
        "strategy": (root / "strategy.md").exists(),
        "report": (root / "report.md").exists(),
        "base": (root / "base.html").exists(),
    }
    item.update(
        {
            "job_title": job["title"] if job else "",
            "job_company": job["company"] if job else "",
            "verdict": job["verdict"] if job else "",
            "score": job["score"] if job else 0,
            "base_label": "",
            "files": reviews,
            "folder_exists": root.exists(),
            "updated_at": item["updated_at"] or item["created_at"],
        }
    )
    if item["base_id"]:
        base = conn.execute("SELECT label FROM bases WHERE id=?", (item["base_id"],)).fetchone()
        item["base_label"] = base["label"] if base else ""
    return item


def list_all(conn) -> list[dict]:
    rows = conn.execute("SELECT * FROM companies ORDER BY updated_at DESC, id DESC").fetchall()
    return [detail(conn, r["id"]) for r in rows]


def resume_state(conn, cid: int) -> dict | None:
    row = conn.execute("SELECT folder FROM companies WHERE id=?", (cid,)).fetchone()
    if row is None:
        return None
    text = _read(folder_of(row) / "resume.json")
    if not text.strip():
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def save_resume(conn, cid: int, state: dict) -> dict:
    row = conn.execute("SELECT * FROM companies WHERE id=?", (cid,)).fetchone()
    if row is None:
        return {"error": "公司档案不存在"}
    if not isinstance(state, dict) or not isinstance(state.get("modules"), dict):
        return {"error": "简历状态结构不对（缺 modules）"}
    _write(folder_of(row) / "resume.json", json.dumps(state, ensure_ascii=False, indent=1))
    conn.execute(
        "UPDATE companies SET status='edited', updated_at=? WHERE id=?", (db.now(), cid)
    )
    conn.commit()
    return {"ok": True, "bytes": (folder_of(row) / "resume.json").stat().st_size}


def read_strategy(conn, cid: int) -> str:
    row = conn.execute("SELECT folder FROM companies WHERE id=?", (cid,)).fetchone()
    return _read(folder_of(row) / "strategy.md") if row else ""


def save_strategy(conn, cid: int, text: str) -> dict:
    row = conn.execute("SELECT * FROM companies WHERE id=?", (cid,)).fetchone()
    if row is None:
        return {"error": "公司档案不存在"}
    _write(folder_of(row) / "strategy.md", text)
    conn.execute("UPDATE companies SET updated_at=? WHERE id=?", (db.now(), cid))
    conn.commit()
    return {"ok": True}


def save_export(conn, cid: int, html: str) -> dict:
    row = conn.execute("SELECT * FROM companies WHERE id=?", (cid,)).fetchone()
    if row is None:
        return {"error": "公司档案不存在"}
    _write(folder_of(row) / "resume.html", html)
    conn.execute(
        "UPDATE companies SET status='exported', updated_at=? WHERE id=?", (db.now(), cid)
    )
    conn.commit()
    return {"ok": True, "bytes": len(html.encode("utf-8"))}


def base_html(conn, cid: int) -> str:
    row = conn.execute("SELECT folder FROM companies WHERE id=?", (cid,)).fetchone()
    return _read(folder_of(row) / "base.html") if row else ""


def open_folder(conn, cid: int) -> dict:
    row = conn.execute("SELECT folder FROM companies WHERE id=?", (cid,)).fetchone()
    if row is None:
        return {"error": "公司档案不存在"}
    path = folder_of(row)
    if not path.exists():
        return {"error": "文件夹已不存在（可能被手动删掉）"}
    try:
        os.startfile(str(path))  # type: ignore[attr-defined]
    except AttributeError:
        subprocess.Popen(["xdg-open", str(path)])
    except OSError as exc:
        return {"error": f"打不开文件夹：{exc}"}
    return {"ok": True, "path": str(path)}


def delete_record(conn, cid: int) -> dict:
    """只删数据库记录，文件夹原样留在磁盘上（简历是资产，不跟着记录一起消失）。"""
    row = conn.execute("SELECT folder FROM companies WHERE id=?", (cid,)).fetchone()
    if row is None:
        return {"error": "公司档案不存在"}
    conn.execute("DELETE FROM companies WHERE id=?", (cid,))
    conn.commit()
    return {"ok": True, "folder": row["folder"], "kept": True}


def adopt_base(conn, cid: int) -> None:
    """编辑器首次导入基底后，删掉临时 base.html，避免下次重复导入。"""
    row = conn.execute("SELECT folder FROM companies WHERE id=?", (cid,)).fetchone()
    if row:
        path = folder_of(row) / "base.html"
        if path.exists():
            path.unlink()


def copy_tree(src: str, dst: Path) -> None:
    """保留给未来「把某公司档案复制成另一份」用。"""
    shutil.copytree(src, dst, dirs_exist_ok=True)
