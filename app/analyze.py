"""匹配分析：基底选型、四维评分、缺口差集。

评分刻意做成「可解释」的：总分由四个维度加权得出，每个维度都能回溯到
具体的需求条目与命中证据，不做黑盒打分。
"""

from __future__ import annotations

import json

from .config import DEFAULT_WEIGHTS, VERDICT_GO, VERDICT_MAYBE
from .lexicon import DOMAIN_TERMS, EDU_LEVEL, TERM_DOMAIN, find_terms, normalize

STATUS_LABELS = {
    "new": "待处理",
    "applied": "已投递",
    "replied": "已回复",
    "interview": "面试中",
    "offer": "已录用",
    "rejected": "已拒绝",
    "dropped": "已放弃",
}
DECISION_LABELS = {"undecided": "未决", "go": "投", "skip": "不投", "watch": "观望"}
REPLY_STATUSES = ("replied", "interview", "offer")
CATEGORY_LABELS = {"must": "必备", "duty": "职责", "nice": "加分"}


def base_terms(base: dict) -> list[str]:
    """基底覆盖的术语 = 登记的关键词 ∪ 正文实际出现的术语。"""
    terms = set()
    try:
        kws = json.loads(base.get("keywords") or "[]")
    except Exception:
        kws = []
    terms.update(kws)
    content = base.get("content") or ""
    if content:
        terms.update(find_terms(content))
    return sorted(terms)


def _req_hit(req: dict, corpus: set[str]) -> tuple[int, str]:
    """返回 (命中等级 0/1/2, 证据文本)。"""
    exact = [t for t in req.get("terms", []) if t in corpus]
    if exact:
        return 2, "命中：" + "、".join(exact)
    partial = []
    for t in req.get("terms", []):
        domain = TERM_DOMAIN.get(t)
        if not domain:
            continue
        siblings = sorted(set(DOMAIN_TERMS.get(domain, [])) & corpus)
        if siblings:
            partial.append(f"{t}（同领域已有：{'、'.join(siblings[:3])}）")
    if partial:
        return 1, "部分：" + "；".join(partial[:2])
    if req.get("terms"):
        return 0, "未命中：" + "、".join(req["terms"][:3])
    return 0, "无可比对术语"


def pick_base(jd_terms: list[str], bases: list[dict], jd_title: str = "") -> dict:
    """按「术语命中数 → 覆盖面 → 意向同名」的顺序选基底，并给出判据。"""
    if not bases:
        return {"base": None, "rationale": "尚未登记任何基底简历", "rank": []}

    jd_set = set(jd_terms)
    title_norm = normalize(jd_title)
    rank = []
    for b in bases:
        terms = set(base_terms(b))
        hits = sorted(jd_set & terms)
        same_intent = bool(b.get("intent")) and normalize(b["intent"])[:4] in title_norm
        rank.append(
            {
                "base": b,
                "hits": hits,
                "hit_count": len(hits),
                "coverage": int(b.get("coverage") or len(terms)),
                "same_intent": same_intent,
                "key": (len(hits), 1 if same_intent else 0, int(b.get("coverage") or 0)),
            }
        )

    rank.sort(key=lambda x: x["key"], reverse=True)
    top = rank[0]
    tie = [r for r in rank if r["key"][:2] == top["key"][:2] and r is not top]

    matched = "、".join(top["hits"][:8]) if top["hits"] else "无共同术语"
    criteria = [
        f"① 术语命中 {top['hit_count']} 个：{matched}",
        f"② 覆盖面 {top['coverage']} 项"
        + ("（并列时取覆盖面最广）" if tie else ""),
        "③ 岗位名与求职意向不一致时，定制时直接改意向即可，不必强求同名基底",
    ]
    return {
        "base": top["base"],
        "rationale": "；".join(criteria[:2]),
        "criteria": criteria,
        "rank": [
            {
                "base_id": r["base"]["id"],
                "code": r["base"]["code"],
                "intent": r["base"]["intent"],
                "hit_count": r["hit_count"],
                "coverage": r["coverage"],
                "hits": r["hits"],
            }
            for r in rank
        ],
    }


def _score_constraints(constraints: list[dict], profile: dict, jd_city: str) -> list[dict]:
    """硬性条件逐项判定：pass / partial / fail / unknown。"""
    results = []
    edu_level = EDU_LEVEL.get((profile.get("education") or "").strip(), 0)
    years = float(profile.get("years") or 0)
    certs = (profile.get("certs") or "")
    cities = [c.strip() for c in normalize_city_list(profile.get("cities") or "")]

    for c in constraints:
        kind = c.get("kind")
        if kind == "degree":
            need = int(c.get("level") or 0)
            if need == 0:
                state, note = "pass", "学历不限"
            elif edu_level == 0:
                state, note = "unknown", "未填写学历，无法判定"
            elif edu_level >= need:
                state, note = "pass", f"你的学历达到「{c.get('text')}」"
            else:
                state, note = "fail", f"JD 要求「{c.get('text')}」，你的学历低于要求"
        elif kind == "years":
            need = int(c.get("level") or 0)
            if years >= need:
                state, note = "pass", f"年限满足「{c.get('text')}」"
            elif years > 0:
                state, note = "partial", f"年限 {years} 年，低于「{c.get('text')}」"
            else:
                state, note = "unknown", "未填写工作年限，无法判定"
        elif kind == "english":
            text = c.get("text") or ""
            high = any(k in text for k in ("六级", "CET-6", "CET6", "雅思", "托福"))
            if high and any(k in certs for k in ("六级", "CET-6", "CET6")):
                state, note = "pass", "证书满足"
            elif any(k in certs for k in ("四级", "六级", "CET", "雅思", "托福")):
                state, note = ("partial" if high else "pass"), "已具备英语证书"
            else:
                state, note = "unknown", "未填写英语证书"
        elif kind == "city":
            if not cities:
                state, note = "unknown", "未填写意向城市"
            elif c.get("value") in cities:
                state, note = "pass", f"「{c.get('value')}」在意向城市内"
            else:
                state, note = "partial", f"「{c.get('value')}」不在意向城市内"
        else:
            state, note = "unknown", ""

        if kind == "city" and jd_city:
            if not cities:
                state, note = "unknown", "未填写意向城市"
            elif jd_city in cities:
                state, note = "pass", f"JD 城市「{jd_city}」在意向城市内"
            else:
                state, note = "partial", f"JD 城市「{jd_city}」不在意向城市内"

        results.append({**c, "state": state, "note": note})

    if jd_city and not any(r.get("kind") == "city" for r in results):
        label = f"城市：{jd_city}"
        if not cities:
            results.append({"kind": "city", "value": jd_city, "text": label, "state": "unknown", "note": "未填写意向城市"})
        elif jd_city in cities:
            results.append({"kind": "city", "value": jd_city, "text": label, "state": "pass", "note": f"JD 城市「{jd_city}」在意向城市内"})
        else:
            results.append({"kind": "city", "value": jd_city, "text": label, "state": "partial", "note": f"JD 城市「{jd_city}」不在意向城市内"})
    return results


def normalize_city_list(text: str) -> list[str]:
    for sep in ("，", ",", "、", "/", "|", " "):
        text = text.replace(sep, ",")
    return [x for x in text.split(",") if x.strip()]


CONSTRAINT_VALUE = {"pass": 1.0, "partial": 0.55, "unknown": 0.5, "fail": 0.0}


def evaluate(jd: dict, base: dict | None, profile: dict, weights: dict | None = None) -> dict:
    weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    corpus = set(base_terms(base)) if base else set()

    reqs = []
    for r in jd.get("requirements", []):
        hit, evidence = _req_hit(r, corpus)
        reqs.append({**r, "hit": hit, "evidence": evidence})

    dims = {}
    for cat in ("must", "duty", "nice"):
        pool = [r for r in reqs if r["category"] == cat]
        if not pool:
            dims[cat] = None
            continue
        total_w = sum(float(r.get("weight") or 1) for r in pool)
        got = sum(float(r.get("weight") or 1) * (r["hit"] / 2.0) for r in pool)
        dims[cat] = round(got / total_w, 4) if total_w else None

    cons = _score_constraints(jd.get("constraints", []), profile, jd.get("city", ""))
    if cons:
        dims["constraint"] = round(
            sum(CONSTRAINT_VALUE.get(c["state"], 0.5) for c in cons) / len(cons), 4
        )
    else:
        dims["constraint"] = 1.0
        cons = []

    hard_fail = [c for c in cons if c["state"] == "fail"]
    used = {k: v for k, v in dims.items() if v is not None}
    wsum = sum(weights.get(k, 0) for k in used)
    score = round(sum(weights.get(k, 0) * v for k, v in used.items()) / wsum * 100, 1) if wsum else 0.0

    if hard_fail:
        verdict = "不建议投"
        reason = "硬性条件不满足：" + "；".join(c.get("note", "") for c in hard_fail)
        decision_hint = "skip"
    elif score >= VERDICT_GO:
        verdict = "建议投"
        reason = "综合匹配度高，可直接进入定制改写"
        decision_hint = "go"
    elif score >= VERDICT_MAYBE:
        verdict = "可投，需针对性改写"
        reason = "基本盘够，但存在明确缺口，改写要先把缺口那条补上口径"
        decision_hint = "go"
    else:
        verdict = "谨慎，先补缺口"
        reason = "覆盖度偏低，除非岗位意愿很强，否则性价比不高"
        decision_hint = "watch"

    covered = sorted({t for r in reqs if r["hit"] == 2 for t in r.get("terms", [])})
    partial = sorted({t for r in reqs if r["hit"] == 1 for t in r.get("terms", [])})
    missing = sorted({t for r in reqs if r["hit"] == 0 for t in r.get("terms", [])})

    gaps = []
    for r in reqs:
        if r["hit"] == 2 or not r.get("terms"):
            continue
        state = "未覆盖" if r["hit"] == 0 else "部分覆盖"
        gap_text = (
            f"JD 要求「{r['text'][:40]}」，简历中无对应事实"
            if r["hit"] == 0
            else f"JD 要求「{r['text'][:40]}」，简历仅有同领域能力，缺直接对应事实"
        )
        learned = "、".join(r["terms"][:3])
        domain = TERM_DOMAIN.get(r["terms"][0], "相关") if r["terms"] else "相关"
        gaps.append(
            {
                "req_id": None,
                "requirement": r["text"],
                "resume_state": f"{state}（{'、'.join(r['terms'][:3])}）",
                "gap": gap_text,
                "priority": "high" if r["priority"] == "high" else r["priority"],
                "action": f"补课：{learned} 的{domain}基础，配一次可验证的小练习",
                "terms": r["terms"],
            }
        )

    return {
        "score": score,
        "dims": dims,
        "requirements": reqs,
        "constraints": cons,
        "verdict": verdict,
        "verdict_reason": reason,
        "decision_hint": decision_hint,
        "coverage": {"covered": covered, "partial": partial, "missing": missing},
        "gaps": gaps,
        "weights": weights,
    }
