"""JD 结构化抽取（纯规则，不依赖任何在线服务）。

输入一段岗位描述原文，输出：
- 公司 / 岗位 / 城市 候选
- 硬性条件（学历、年限、英语、城市）
- 需求条目（必备 / 职责 / 加分），每条带术语与权重、优先级
- 全量术语集合

规则来源是一个通用的招聘文案结构：中文 JD 基本都由「岗位职责 / 任职要求 /
加分项」三段构成，因此按段落定位比逐句猜要稳。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .lexicon import CITIES, DEGREES, find_terms, normalize

DUTY_HEADS = [
    "岗位职责", "工作职责", "职位描述", "工作内容", "职责描述",
    "你将负责", "你将参与", "主要职责", "负责内容", "工作范围",
]
MUST_HEADS = [
    "任职要求", "岗位要求", "任职资格", "职位要求", "我们希望你",
    "你需要", "任职条件", "能力要求", "基本要求", "要求如下", "岗位需求",
]
NICE_HEADS = ["加分项", "加分", "优先条件", "有以下经验者优先", "其他要求", "福利"]

BULLET_RE = re.compile(r"^[\s\u3000]*[\-\u2022\u25cf\u25aa\*\u00b7]?\s*(?:\d{1,2}[\.\、\)）]\s*)?")
COMPANY_RE = re.compile(r"[（(]?([\u4e00-\u9fa5A-Za-z0-9]{2,20}(?:有限公司|股份有限公司|集团|研究院|银行|分行|软件|科技|信息|网络))[）)]?")
TITLE_RE = re.compile(r"([\u4e00-\u9fa5A-Za-z0-9（）()/\-\s]{2,26}(?:工程师|开发|经理|专员|实习生|架构师|主管|顾问|分析师|交付|实施|运维|测试))")
YEARS_RE = re.compile(r"(\d{1,2})\s*年(?:及)?以上[^\n，。；]{0,8}?经验")
YEARS_RE2 = re.compile(r"(\d{1,2})\s*年(?:以上|及以上)?[^\n，。；]{0,4}?经验")
EN_RE = re.compile(r"(CET-?\s?[46]|四级|六级|雅思|托福|英语[^\n，。]{0,8})")

META_TITLE_KEYS = ("岗位名称", "职位名称", "招聘岗位", "岗位")
META_CITY_KEYS = ("工作地点", "办公地点", "工作城市", "城市", "地点")

WEIGHT = {"must": 1.0, "duty": 0.8, "nice": 0.5}
PRIORITY = {"must": "high", "duty": "medium", "nice": "low"}
HARD_WORDS = ("必须", "精通", "熟练掌握", "扎实", "深入理解", "至少", "不接受", "不考虑")


@dataclass
class Requirement:
    text: str
    category: str
    weight: float
    priority: str
    terms: list[str] = field(default_factory=list)
    ord: int = 0


def _clean(line: str) -> str:
    line = line.replace("\u3000", " ").strip()
    line = BULLET_RE.sub("", line)
    return line.strip(" ：:;；,，")


def _is_heading(line: str, heads: list[str]) -> bool:
    if len(line) > 30:
        return False
    for h in heads:
        if h in line:
            return True
    return False


def split_sections(raw: str) -> dict[str, list[str]]:
    """按标题把 JD 切成 职责 / 要求 / 加分 三段。无标题时整段归入要求。"""
    sections: dict[str, list[str]] = {"duty": [], "must": [], "nice": [], "preamble": []}
    current = "preamble"
    for raw_line in raw.splitlines():
        line = _clean(raw_line)
        if not line:
            continue
        if _is_heading(line, DUTY_HEADS):
            current = "duty"
            continue
        if _is_heading(line, MUST_HEADS):
            current = "must"
            continue
        if _is_heading(line, NICE_HEADS):
            current = "nice"
            continue
        # 段落内的「优先」句即使挂在要求段，也归入加分
        if current == "must" and ("优先" in line or "加分" in line):
            sections["nice"].append(line)
            continue
        sections[current].append(line)

    if not sections["must"] and not sections["duty"]:
        sections["must"] = [x for x in sections["preamble"] if x]
        sections["preamble"] = []
    return sections


def _detect_company(raw: str) -> str:
    for line in raw.splitlines():
        line = _clean(line)
        if not line:
            continue
        for key in ("公司名称", "公司", "企业名称", "用人单位"):
            if line.startswith(key) and len(line) < 40:
                val = re.split(r"[：:]\s*", line, maxsplit=1)
                if len(val) == 2 and val[1]:
                    return val[1].strip()
        m = COMPANY_RE.search(line)
        if m and len(line) < 45:
            return m.group(1)
    return ""


def _meta_value(raw: str, keys: tuple[str, ...]) -> str:
    """从「键：值」形态的元信息行里取值。"""
    for line in raw.splitlines()[:15]:
        line = _clean(line)
        if not line or len(line) > 60:
            continue
        for key in keys:
            if not line.startswith(key):
                continue
            parts = re.split(r"[：:]\s*", line, maxsplit=1)
            if len(parts) == 2 and parts[1].strip():
                rest = parts[1].strip()
                # 「岗位：xx」也可能是段落标题，要求值不带常见小标题后缀
                if rest.endswith(("要求", "职责", "描述", "内容")):
                    continue
                return rest
    return ""


def _detect_title(raw: str) -> str:
    meta = _meta_value(raw, META_TITLE_KEYS)
    if meta:
        return meta
    for line in raw.splitlines()[:12]:
        line = _clean(line)
        if not line or len(line) > 40:
            continue
        m = TITLE_RE.search(line)
        if m:
            return m.group(1).strip()
    return ""


def _detect_city(raw: str) -> str:
    meta = _meta_value(raw, META_CITY_KEYS)
    if meta:
        for city in CITIES:
            if city in meta:
                return city
    head = "\n".join(raw.splitlines()[:25])
    for city in CITIES:
        if city in head:
            return city
    return ""


def extract_constraints(raw: str) -> list[dict]:
    out: list[dict] = []
    # 学历
    if "不限学历" in raw or "学历不限" in raw:
        out.append({"kind": "degree", "level": 0, "text": "学历不限"})
    else:
        best = None
        for word, level in DEGREES:
            if word in raw:
                if best is None or level > best[1]:
                    best = (word, level)
        if best:
            out.append({"kind": "degree", "level": best[1], "text": f"{best[0]}及以上"})
    # 年限
    for pattern in (YEARS_RE, YEARS_RE2):
        m = pattern.search(raw)
        if m:
            out.append({"kind": "years", "level": int(m.group(1)), "text": m.group(0)})
            break
    # 英语
    m = EN_RE.search(raw)
    if m:
        out.append({"kind": "english", "text": m.group(0).strip()})
    return out


def _dedupe_requirements(items: list[Requirement]) -> list[Requirement]:
    seen: set[str] = set()
    keep: list[Requirement] = []
    for it in items:
        key = normalize(it.text)
        if len(key) < 2 or key in seen:
            continue
        seen.add(key)
        keep.append(it)
    for i, it in enumerate(keep):
        it.ord = i
    return keep


def normalize_ai_items(items: list) -> list[dict]:
    """把模型给的候选条目收敛成与规则条目同构的结构。

    模型只负责「读懂了什么」，不负责打分：权重一律按分类取默认值，
    优先级非法就回落到分类默认值，术语缺失时补一次本地词表匹配。
    """
    clean: list[dict] = []
    for raw in items if isinstance(items, list) else []:
        if isinstance(raw, str):
            raw = {"text": raw}
        if not isinstance(raw, dict):
            continue
        text = str(raw.get("text") or "").strip()
        if len(text) < 3:
            continue
        category = str(raw.get("category") or "").strip()
        if category not in WEIGHT:
            category = "must" if any(w in text for w in HARD_WORDS) else "duty"
        priority = str(raw.get("priority") or "").strip()
        if priority not in ("high", "medium", "low"):
            priority = PRIORITY[category]
        terms = raw.get("terms")
        if not isinstance(terms, list) or not terms:
            terms = find_terms(text)
        clean.append(
            {
                "text": text[:60],
                "category": category,
                "weight": WEIGHT[category],
                "priority": priority,
                "terms": [str(t)[:24] for t in terms][:5],
                "rel": str(raw.get("reason") or raw.get("rel") or "")[:80],
            }
        )
    return clean


def merge_ai_items(parsed: dict, ai_items: list[dict]) -> dict:
    """把用户勾选的 AI 条目并入规则结果：同文去重，规则条目优先保留。"""
    existing = {normalize(r["text"]): r for r in parsed.get("requirements", [])}
    merged = list(parsed.get("requirements", []))
    for item in ai_items:
        key = normalize(item["text"])
        if len(key) < 2 or key in existing:
            continue
        existing[key] = item
        merged.append({**item, "ord": len(merged), "source": "ai"})
    parsed["requirements"] = merged

    all_terms = list(parsed.get("terms", []))
    for item in merged:
        for term in item.get("terms", []):
            if term not in all_terms:
                all_terms.append(term)
    parsed["terms"] = all_terms
    return parsed


def parse_jd(raw: str, company: str = "", title: str = "", city: str = "") -> dict:
    sections = split_sections(raw)
    items: list[Requirement] = []

    for category in ("must", "duty", "nice"):
        for text in sections[category]:
            if len(text) < 3:
                continue
            priority = PRIORITY[category]
            if category == "must" and any(w in text for w in HARD_WORDS):
                priority = "high"
            items.append(
                Requirement(
                    text=text,
                    category=category,
                    weight=WEIGHT[category],
                    priority=priority,
                    terms=find_terms(text),
                )
            )

    items = _dedupe_requirements(items)
    all_terms: list[str] = []
    for it in items:
        for t in it.terms:
            if t not in all_terms:
                all_terms.append(t)

    return {
        "company": company.strip() or _detect_company(raw),
        "title": title.strip() or _detect_title(raw),
        "city": city.strip() or _detect_city(raw),
        "constraints": extract_constraints(raw),
        "requirements": [
            {
                "text": it.text,
                "category": it.category,
                "weight": it.weight,
                "priority": it.priority,
                "terms": it.terms,
                "ord": it.ord,
            }
            for it in items
        ],
        "terms": all_terms,
        "sections": {k: len(v) for k, v in sections.items()},
    }
