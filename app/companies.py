"""公司档案：一家公司一个本地文件夹。

目录形态（位于当前数据目录下，随数据目录迁移一起搬走）：

    resumes/
      示例科技/
        示例科技-前端工程师-jd.txt          JD 原文
        示例科技-前端工程师-strategy.md      这家公司的策略
        resume.json                          编辑器完整状态（事实源）
        张三-前端工程师-简历.html             导出的成品简历
        张三-前端工程师-简历.pdf              打印导出的 PDF
        示例科技-前端工程师-report.md        建档时自动生成的分析摘要
        base.html                            从 HTML 基底复制来的原文

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


FILE_PART_MAX = 60
SUPPORT_LEGACY = {"jd": "jd.txt", "strategy": "strategy.md", "report": "report.md"}


def _safe_part(name: str, fallback: str = "", limit: int = FILE_PART_MAX) -> str:
    stem = ILLEGAL.sub("-", (name or "").strip()).strip(" .-")
    stem = re.sub(r"-{2,}", "-", stem)
    return (stem[:limit].strip(" .-") or fallback)


def _prefix(company: str, title: str) -> str:
    """公司岗位名前缀：jd / report / strategy 等支撑文件共用。"""
    return "-".join(x for x in (_safe_part(company, "未命名公司", 48),
                                _safe_part(title, "", 40)) if x)


def _resume_stem(name: str, title: str) -> str:
    """成品简历名：姓名-岗位名-简历。没填姓名时退回岗位名-简历。"""
    clean_name = _safe_part(name, "", 30)
    if clean_name in ("", "你的姓名"):
        clean_name = ""
    clean_title = _safe_part(title, "", 40)
    if clean_name and clean_title:
        return f"{clean_name}-{clean_title}-简历"
    if clean_name:
        return f"{clean_name}-简历"
    if clean_title:
        return f"{clean_title}-简历"
    return "简历"


def _html_name(text: str) -> str:
    m = re.search(r"<h1[^>]*>(.*?)</h1>", text or "", re.I | re.S)
    if not m:
        return ""
    name = re.sub(r"<[^>]+>", "", m.group(1))
    return re.sub(r"\s+", " ", name).strip()


def _resume_name(root: Path) -> str:
    text = _read(root / "resume.json")
    if text.strip():
        try:
            state = json.loads(text)
            name = str(((state.get("meta") or {}).get("name")) or "").strip()
            if name:
                return name
        except (ValueError, TypeError):
            pass
    html = _find_resume(root, ".html")
    return _html_name(_read(html)) if html else _html_name(_read(root / "base.html"))


def _resume_stem_for(conn, row, root: Path, html: str = "") -> str:
    job = conn.execute("SELECT title FROM jobs WHERE id=?", (row["job_id"] or -1,)).fetchone()
    title = job["title"] if job else ""
    name = _html_name(html) if html else ""
    return _resume_stem(name or _resume_name(root), title)


def _support_path(root: Path, prefix: str, kind: str) -> Path:
    suffix = {"jd": "jd.txt", "strategy": "strategy.md", "report": "report.md"}[kind]
    return root / f"{prefix}-{suffix}"


def _find_support(root: Path, kind: str) -> Path | None:
    legacy = root / SUPPORT_LEGACY[kind]
    if legacy.exists():
        return legacy
    suffix = SUPPORT_LEGACY[kind]
    matches = sorted(root.glob(f"*-{suffix}"))
    return matches[0] if matches else None


def _find_resume(root: Path, ext: str) -> Path | None:
    legacy = root / f"resume{ext}"
    if legacy.exists():
        return legacy
    matches = sorted(root.glob(f"*-简历{ext}"))
    return matches[0] if matches else None


def _ensure_names(conn, row, root: Path) -> None:
    """把旧命名就地迁到新口径；只改名，不覆盖任何已有成品。"""
    if not root.exists() or (row["kind"] or "company") == "general":
        return
    job = conn.execute("SELECT title FROM jobs WHERE id=?", (row["job_id"] or -1,)).fetchone()
    title = job["title"] if job else ""
    prefix = _prefix(row["name"], title)
    stem = _resume_stem_for(conn, row, root)

    for kind in ("jd", "strategy", "report"):
        src = root / SUPPORT_LEGACY[kind]
        dst = _support_path(root, prefix, kind)
        if src.exists() and not dst.exists():
            src.rename(dst)

    for ext in (".html", ".pdf"):
        src = root / f"resume{ext}"
        dst = root / f"{stem}{ext}"
        if src.exists() and not dst.exists():
            src.rename(dst)

    if not _find_resume(root, ".pdf"):
        loose = sorted(root.glob("*.pdf"))
        title_key = re.sub(r"[\s\-_（）()]+", "", title)
        if len(loose) == 1 and re.sub(r"[\s\-_（）()]+", "", loose[0].stem) == title_key:
            dst = root / f"{stem}.pdf"
            if not dst.exists():
                loose[0].rename(dst)


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


def create(conn, name: str, job_id: int | None = None, base_id: int | None = None,
           kind: str = "company") -> dict:
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

    prefix = _prefix(name, job["title"] if job else "")
    if job:
        _write(root / f"{prefix}-jd.txt", job["jd_raw"] or "")
    _write(root / f"{prefix}-strategy.md", _strategy_skeleton(conn, name, job, base_label))
    _write(root / f"{prefix}-report.md", _report(conn, name, job, base_label))

    cur = conn.execute(
        "INSERT INTO companies(name, folder, job_id, base_id, status, kind, note, created_at, updated_at)"
        " VALUES(?,?,?,?,?,?,?,?,?)",
        (
            name,
            folder,
            job["id"] if job else None,
            base["id"] if base else None,
            "draft",
            kind,
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
    _ensure_names(conn, row, root)
    job = conn.execute("SELECT * FROM jobs WHERE id=?", (item["job_id"] or -1,)).fetchone()
    reviews = {
        "jd": _find_support(root, "jd") is not None,
        "resume": (root / "resume.json").exists(),
        "html": _find_resume(root, ".html") is not None,
        "pdf": _find_resume(root, ".pdf") is not None,
        "strategy": _find_support(root, "strategy") is not None,
        "report": _find_support(root, "report") is not None,
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


GENERAL_NAME = "通用简历"
GENERAL_FOLDER = "_通用简历"


def _general_strategy() -> str:
    return """# 通用简历（母版）

这份简历不属于任何一家公司，只做两件事：

1. 记录真实、可复用的经历与事实；
2. 作为各公司定制版的起点（进公司档案后再按 JD 改）。

## 维护原则

- 只写发生过的事实，不写期望；
- 一页为限，与目标岗位最相关的经历放前面；
- 量化结果用真实数字，没有数字就不编。

## 投递前检查

- [ ] 联系方式可用
- [ ] 时间线无空档，或有可解释的说法
- [ ] 导出 HTML 后逐页检查不溢出
"""


def ensure_general(conn) -> dict:
    """通用简历固定一份：没有就建，有就返回；文件夹优先复用已有的 _通用简历。"""
    row = conn.execute(
        "SELECT * FROM companies WHERE kind='general' ORDER BY id LIMIT 1"
    ).fetchone()
    if row is not None:
        root = folder_of(row)
        if not root.exists():
            root.mkdir(parents=True, exist_ok=True)
        if not (root / "strategy.md").exists():
            _write(root / "strategy.md", _general_strategy())
        return detail(conn, row["id"])

    preferred = resumes_root() / GENERAL_FOLDER
    folder = GENERAL_FOLDER if preferred.exists() else _unique_folder(resumes_root(), GENERAL_FOLDER)
    root = resumes_root() / folder
    root.mkdir(parents=True, exist_ok=True)
    if not (root / "strategy.md").exists():
        _write(root / "strategy.md", _general_strategy())
    cur = conn.execute(
        "INSERT INTO companies(name, folder, job_id, base_id, status, kind, note, created_at, updated_at)"
        " VALUES(?,?,?,?,?,?,?,?,?)",
        (GENERAL_NAME, folder, None, None, "draft", "general", "通用简历母版", db.now(), db.now()),
    )
    conn.commit()
    return detail(conn, cur.lastrowid)


def list_all(conn) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM companies ORDER BY CASE kind WHEN 'general' THEN 0 ELSE 1 END,"
        " updated_at DESC, id DESC"
    ).fetchall()
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
    row = conn.execute("SELECT * FROM companies WHERE id=?", (cid,)).fetchone()
    if not row:
        return ""
    path = _find_support(folder_of(row), "strategy")
    return _read(path) if path else ""


def save_strategy(conn, cid: int, text: str) -> dict:
    row = conn.execute("SELECT * FROM companies WHERE id=?", (cid,)).fetchone()
    if row is None:
        return {"error": "公司档案不存在"}
    root = folder_of(row)
    path = _find_support(root, "strategy")
    if path is None:
        job = conn.execute("SELECT title FROM jobs WHERE id=?", (row["job_id"] or -1,)).fetchone()
        path = _support_path(root, _prefix(row["name"], job["title"] if job else ""), "strategy")
    _write(path, text)
    conn.execute("UPDATE companies SET updated_at=? WHERE id=?", (db.now(), cid))
    conn.commit()
    return {"ok": True, "filename": path.name}


def _clean_filename(filename: str) -> str:
    return re.sub(r"\.(?:html|htm|pdf)$", "", (filename or "").strip(), flags=re.I)


def save_export(conn, cid: int, html: str, filename: str = "") -> dict:
    row = conn.execute("SELECT * FROM companies WHERE id=?", (cid,)).fetchone()
    if row is None:
        return {"error": "公司档案不存在"}
    root = folder_of(row)
    stem = _safe_part(_clean_filename(filename), "", 80) or _resume_stem_for(conn, row, root, html)
    target = root / f"{stem}.html"
    _write(target, html)
    conn.execute(
        "UPDATE companies SET status='exported', updated_at=? WHERE id=?", (db.now(), cid)
    )
    conn.commit()
    return {"ok": True, "filename": target.name, "bytes": len(html.encode("utf-8"))}


def save_pdf(conn, cid: int, data: bytes, filename: str = "") -> dict:
    """把编辑器导出的 PDF 归档到公司文件夹；已有同名 PDF 时按用户口径跳过，不覆盖。"""
    row = conn.execute("SELECT * FROM companies WHERE id=?", (cid,)).fetchone()
    if row is None:
        return {"error": "公司档案不存在"}
    root = folder_of(row)
    stem = _safe_part(_clean_filename(filename), "", 80) or _resume_stem_for(conn, row, root)
    target = root / f"{stem}.pdf"
    if target.exists():
        return {"ok": True, "skipped": True, "bytes": target.stat().st_size, "filename": target.name}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    conn.execute(
        "UPDATE companies SET status='exported', updated_at=? WHERE id=?", (db.now(), cid)
    )
    conn.commit()
    return {"ok": True, "skipped": False, "bytes": len(data), "filename": target.name}


def base_html(conn, cid: int) -> str:
    row = conn.execute("SELECT folder FROM companies WHERE id=?", (cid,)).fetchone()
    return _read(folder_of(row) / "base.html") if row else ""


def jd_text(conn, cid: int) -> str:
    row = conn.execute("SELECT * FROM companies WHERE id=?", (cid,)).fetchone()
    if not row:
        return ""
    path = _find_support(folder_of(row), "jd")
    return _read(path) if path else ""


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
    row = conn.execute("SELECT folder, kind FROM companies WHERE id=?", (cid,)).fetchone()
    if row is None:
        return {"error": "公司档案不存在"}
    if (row["kind"] or "company") == "general":
        return {"error": "通用简历是母版，不能删除"}
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
