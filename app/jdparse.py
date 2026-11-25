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
AGE_RE = re.compile(r"(\d{2})\s*(?:周岁|岁)")
AGE_RANGE_RE = re.compile(r"(\d{2})\s*[-~至]\s*(\d{2})\s*(?:周岁|岁)")
YEAR_TEXT_RE = re.compile(r"\d{1,2}\s*年(?:及)?以上[^\n，。；]{0,8}?经验")

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


def _clauses(line: str) -> list[str]:
    """按中文标点切小句；顿号不切，避免把「计算机类、电子信息类」拆散。"""
    return [x.strip() for x in re.split(r"[，,；;。]", line) if x.strip()]


def _degree_words(text: str) -> list[tuple[str, int]]:
    """取一句里的学历词。先把「博士研究生 / 硕士研究生」收敛成学位名，避免重复计级。"""
    text = text.replace("博士研究生", "博士").replace("硕士研究生", "硕士")
    return [(word, level) for word, level in DEGREES if word in text]


def _is_qualification(text: str) -> bool:
    """学历 / 专业 / 年龄 / 证书这类资格行，不该当成技术能力条目参与术语覆盖。"""
    if find_terms(text):
        return False
    s = (text or "").strip()
    if not s:
        return False
    if "不限学历" in s or "学历不限" in s:
        return True
    if s.startswith(("学历", "学位", "专业", "年龄", "毕业", "院校", "证书", "资格", "户籍", "性别", "身高")):
        return True
    if "学历" in s and _degree_words(s):
        return True
    if "专业" in s and ("相关专业" in s or "专业要求" in s or s.endswith("专业")):
        return True
    if AGE_RE.search(s) and any(k in s for k in ("年龄", "周岁", "以下", "以内")):
        return True
    if any(k in s for k in ("CET-4", "CET-6", "CET4", "CET6", "四级", "六级")) and (
        "以上" in s or "及以上" in s
    ):
        return True
    if YEAR_TEXT_RE.search(s) and len(s) < 60:
        return True
    return False


def _extract_degree(raw: str) -> dict | None:
    if "不限学历" in raw or "学历不限" in raw:
        return {"kind": "degree", "level": 0, "text": "学历不限"}

    candidates: list[tuple[str, int]] = []
    for line in raw.splitlines():
        for clause in _clauses(_clean(line)):
            # 「硕士优先」「博士加分」是偏好，不是硬门槛；年龄行里的学历词也不是学历要求
            if "优先" in clause or "加分" in clause:
                continue
            if AGE_RE.search(clause) and "学历" not in clause:
                continue
            words = _degree_words(clause)
            if not words:
                continue
            context = (
                "学历" in clause
                or "学位" in clause
                or "毕业" in clause
                or "统招" in clause
                or "全日制" in clause
                or any(f"{word}及以上" in clause or f"{word}以上" in clause for word, _ in words)
                or clause.startswith(tuple(word for word, _ in words))
            )
            if not context:
                continue
            candidates.append(min(words, key=lambda item: item[1]))

    if not candidates:
        return None
    # 「本科及以上」按最低可接受学历算，不能因为同一段还写了「硕士优先」就抬成硕士
    word, level = min(candidates, key=lambda item: item[1])
    return {"kind": "degree", "level": level, "text": f"{word}及以上"}


def _extract_years(raw: str) -> dict | None:
    values = []
    for line in raw.splitlines():
        for clause in _clauses(_clean(line)):
            if "优先" in clause or "加分" in clause:
                continue
            for pattern in (YEARS_RE, YEARS_RE2):
                m = pattern.search(clause)
                if m:
                    values.append(int(m.group(1)))
                    break
    if not values:
        return None
    level = min(values)
    return {"kind": "years", "level": level, "text": f"{level} 年以上经验"}


def _extract_major(raw: str) -> dict | None:
    for line in raw.splitlines():
        for clause in _clauses(_clean(line)):
            if "专业" not in clause or find_terms(clause):
                continue
            if "不限" in clause:
                return {"kind": "major", "text": "专业不限", "unlimited": True}
            if (
                clause.startswith("专业")
                or clause.endswith("专业")
                or "专业要求" in clause
                or "相关专业" in clause
            ):
                return {"kind": "major", "text": clause[:100]}
    return None


def _extract_age(raw: str) -> dict | None:
    rules: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for line in raw.splitlines():
        if not any(k in line for k in ("年龄", "周岁", "岁")):
            continue
        for clause in _clauses(_clean(line)):
            if "优先" in clause:
                continue
            m = AGE_RANGE_RE.search(clause)
            if m:
                max_age = int(m.group(2))
            else:
                m = AGE_RE.search(clause)
                if not m:
                    continue
                max_age = int(m.group(1))
            degree = ""
            for word, _ in DEGREES:
                if word in clause:
                    degree = word
                    break
            key = (degree, max_age)
            if key in seen:
                continue
            seen.add(key)
            rules.append({"degree": degree, "max": max_age, "text": clause[:50]})
    if not rules:
        return None
    text = "年龄要求：" + "；".join(r["text"] for r in rules)
    return {"kind": "age", "rules": rules, "text": text[:120]}


def extract_constraints(raw: str) -> list[dict]:
    out: list[dict] = []
    degree = _extract_degree(raw)
    if degree:
        out.append(degree)
    years = _extract_years(raw)
    if years:
        out.append(years)
    major = _extract_major(raw)
    if major:
        out.append(major)
    age = _extract_age(raw)
    if age:
        out.append(age)
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
        if _is_qualification(text):
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
            if _is_qualification(text):
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
