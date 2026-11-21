"""跨岗位聚合：这是单点工具做不出来、只有台账才做得出来的部分。

三个核心视图：
- 技能需求榜：某个技能被多少家要求、我的基底覆盖了几家 —— 反向指导补课优先级
- 缺口热点：同一类缺口在多少岗位重复出现
- 基底表现：不同基底 × 投递结果的概率分布
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict

from .analyze import REPLY_STATUSES, STATUS_LABELS, base_terms
from .lexicon import TERM_DOMAIN


def _load(conn, table: str) -> list[dict]:
    return [dict(r) for r in conn.execute(f"SELECT * FROM {table}").fetchall()]


def summary(conn) -> dict:
    jobs = _load(conn, "jobs")
    gaps = _load(conn, "gaps")
    bases = _load(conn, "bases")
    status_counts = Counter(j["status"] for j in jobs)
    decision_counts = Counter(j["decision"] for j in jobs)
    applied = [j for j in jobs if j["status"] not in ("new",)]
    replied = [j for j in applied if j["status"] in REPLY_STATUSES]
    return {
        "jobs": len(jobs),
        "bases": len(bases),
        "gaps_open": len([g for g in gaps if g["status"] == "open"]),
        "avg_score": round(sum(float(j["score"] or 0) for j in jobs) / len(jobs), 1) if jobs else 0,
        "status_counts": [
            {"status": k, "label": STATUS_LABELS.get(k, k), "count": v}
            for k, v in status_counts.most_common()
        ],
        "decision_counts": dict(decision_counts),
        "reply_rate": round(len(replied) / len(applied) * 100, 1) if applied else None,
        "applied": len(applied),
        "replied": len(replied),
    }


def term_demand(conn, used_only: bool = True) -> list[dict]:
    """技能需求榜：需求家数 vs 我的覆盖。"""
    jobs = _load(conn, "jobs")
    bases = _load(conn, "bases")
    my_terms: set[str] = set()
    for b in bases:
        my_terms.update(base_terms(b))

    per_term_jobs: dict[str, set[int]] = defaultdict(set)
    for req in _load(conn, "requirements"):
        if used_only and req["category"] not in ("must", "duty"):
            continue
        try:
            terms = json.loads(req["terms"] or "[]")
        except Exception:
            terms = []
        for t in terms:
            per_term_jobs[t].add(req["job_id"])

    rows = []
    for term, ids in per_term_jobs.items():
        covered = term in my_terms
        rows.append(
            {
                "term": term,
                "domain": TERM_DOMAIN.get(term, ""),
                "jobs": len(ids),
                "covered": covered,
                "job_ids": sorted(ids),
            }
        )
    rows.sort(key=lambda r: (not r["covered"], -r["jobs"], r["term"]))
    return rows


def uncovered_skills(conn, min_jobs: int = 2) -> list[dict]:
    """被 N 家以上要求、但我的基底零覆盖的技能。"""
    return [r for r in term_demand(conn, used_only=True) if not r["covered"] and r["jobs"] >= min_jobs]


def gap_hotspots(conn) -> list[dict]:
    gaps = [g for g in _load(conn, "gaps") if g["status"] == "open"]
    counter: Counter = Counter()
    job_sets: dict[str, set] = defaultdict(set)
    for g in gaps:
        key = g["requirement"][:30]
        counter[key] += 1
        job_sets[key].add(g["job_id"])
    rows = []
    for key, cnt in counter.most_common(30):
        rows.append({"requirement": key, "jobs": len(job_sets[key]), "instances": cnt})
    return rows


def base_performance(conn) -> list[dict]:
    jobs = _load(conn, "jobs")
    bases = {b["id"]: b for b in _load(conn, "bases")}
    out = []
    for bid, b in bases.items():
        used = [j for j in jobs if j["base_id"] == bid]
        applied = [j for j in used if j["status"] != "new"]
        replied = [j for j in applied if j["status"] in REPLY_STATUSES]
        out.append(
            {
                "base_id": bid,
                "code": b["code"],
                "intent": b["intent"],
                "used": len(used),
                "applied": len(applied),
                "replied": len(replied),
                "reply_rate": round(len(replied) / len(applied) * 100, 1) if applied else None,
                "avg_score": round(sum(float(j["score"] or 0) for j in used) / len(used), 1) if used else 0,
            }
        )
    out.sort(key=lambda r: (-r["used"], r["code"]))
    return out


def city_demand(conn) -> list[dict]:
    jobs = _load(conn, "jobs")
    counter = Counter(j["city"] for j in jobs if j["city"])
    return [{"city": k, "count": v} for k, v in counter.most_common(15)]


def weekly_flow(conn) -> list[dict]:
    jobs = _load(conn, "jobs")
    counter: Counter = Counter()
    for j in jobs:
        created = (j.get("created_at") or "")[:10]
        counter[created] += 1
    return [{"date": k, "count": v} for k, v in sorted(counter.items())]


def stats_bundle(conn, min_jobs: int = 2) -> dict:
    return {
        "summary": summary(conn),
        "term_demand": term_demand(conn)[:40],
        "uncovered": uncovered_skills(conn, min_jobs)[:20],
        "gap_hotspots": gap_hotspots(conn),
        "base_performance": base_performance(conn),
        "city_demand": city_demand(conn),
        "weekly_flow": weekly_flow(conn),
    }
