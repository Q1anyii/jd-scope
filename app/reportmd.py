"""单岗位交付物：一份能直接读、能贴进笔记的 Markdown 报告。

结构对齐投递前的固定交付标准：结论 → 四维得分 → 基底选型 → 硬性条件 →
关键词覆盖 → 缺口清单 → 改动摘要 → 面试提示 → 原始 JD。
"""

from __future__ import annotations

from datetime import datetime

from .config import APP_NAME, APP_VERSION

PRIORITY_LABELS = {"high": "高", "medium": "中", "low": "低"}
CATEGORY_LABELS = {"must": "必备", "duty": "职责", "nice": "加分"}
DIM_LABELS = {
    "must": "必备要求覆盖",
    "duty": "职责同构度",
    "nice": "加分项覆盖",
    "constraint": "硬性条件符合",
}
STATE_LABELS = {"pass": "满足", "partial": "勉强", "unknown": "未知", "fail": "不满足"}


def _cell(text: str) -> str:
    return (text or "").replace("|", "／").replace("\n", " ").strip()


def _pct(v) -> str:
    return "—" if v is None else f"{round(v * 100)}%"


def build_report(
    job: dict,
    analysis: dict,
    base: dict | None,
    selection: dict | None,
    suggestions: list[dict] | None = None,
    min_jobs_hint: int = 2,
    uncovered: list[dict] | None = None,
) -> str:
    suggestions = suggestions or []
    lines: list[str] = []
    push = lines.append

    push(f"# 岗位匹配报告 · {job.get('company','')} · {job.get('title','')}")
    push("")
    push(
        f"> {APP_NAME} v{APP_VERSION} · 生成于 "
        f"{datetime.now().strftime('%Y-%m-%d %H:%M')} · "
        f"城市：{job.get('city') or '未填'} · 来源：{job.get('source') or '未填'}"
    )
    push("")

    # 一、结论
    push("## 一、结论")
    push("")
    push("| 项 | 值 |")
    push("|---|---|")
    push(f"| 综合匹配度 | **{analysis.get('score', 0)} / 100** |")
    push(f"| 判定 | **{analysis.get('verdict','')}** |")
    push(f"| 判定依据 | {_cell(analysis.get('verdict_reason',''))} |")
    push(f"| 建议动作 | {_cell({'skip':'建议放弃或先补缺口','go':'进入定制改写','watch':'观望，等缺口补上再投'}.get(analysis.get('decision_hint'),''))} |")
    push("")

    # 二、四维得分
    push("## 二、四维得分")
    push("")
    push("| 维度 | 得分 | 权重 |")
    push("|---|---|---|")
    weights = analysis.get("weights", {})
    for key, label in DIM_LABELS.items():
        push(f"| {label} | {_pct(analysis.get('dims', {}).get(key))} | {weights.get(key, '')} |")
    push("")
    push("> 四个维度都是可回溯的：每个百分比都能在对应用求条目里找到命中证据，不存在黑盒总分。")
    push("")

    # 三、基底选型
    push("## 三、基底选型")
    push("")
    if base:
        push(f"选用：`{base.get('code','')}`（求职意向：{base.get('intent','')}），覆盖面 {base.get('coverage', 0)} 项。")
        push("")
        for crit in (selection or {}).get("criteria", []):
            push(f"- {crit}")
    else:
        push("_尚未登记基底简历，先到「基底库」导入一份。_")
    push("")

    # 四、硬性条件
    cons = analysis.get("constraints") or []
    if cons:
        push("## 四、硬性条件")
        push("")
        push("| 条件 | 状态 | 说明 |")
        push("|---|---|---|")
        for c in cons:
            label = c.get("text") or f"{c.get('kind')} {c.get('value', '')}"
            push(f"| {_cell(str(label))} | {STATE_LABELS.get(c.get('state'), '')} | {_cell(c.get('note',''))} |")
        push("")

    # 五、关键词覆盖
    cov = analysis.get("coverage", {})
    covered, partial, missing = cov.get("covered", []), cov.get("partial", []), cov.get("missing", [])
    push("## 五、关键词覆盖")
    push("")
    push(f"命中 **{len(covered)}** 项 · 部分 **{len(partial)}** 项 · 缺失 **{len(missing)}** 项")
    push("")
    if covered:
        push(f"- 已覆盖：{'、'.join(covered)}")
    if partial:
        push(f"- 仅部分覆盖：{'、'.join(partial)}")
    if missing:
        push(f"- 缺失：{'、'.join(missing)}")
    push("")

    # 六、缺口清单
    gaps = analysis.get("gaps") or []
    push("## 六、缺口清单")
    push("")
    if gaps:
        push("| 优先级 | JD 要求 | 简历现状 | 差在哪 | 补课方向 |")
        push("|---|---|---|---|---|")
        for g in gaps:
            push(
                f"| {PRIORITY_LABELS.get(g.get('priority'), '')} "
                f"| {_cell(g.get('requirement',''))[:60]} "
                f"| {_cell(g.get('resume_state',''))} "
                f"| {_cell(g.get('gap',''))} "
                f"| {_cell(g.get('action',''))} |"
            )
    else:
        push("_没有发现明确缺口，这份 JD 的显性要求基本都被覆盖。_")
    push("")

    # 七、改动摘要
    push("## 七、改动摘要（Before → After）")
    push("")
    adopted = [s for s in suggestions if s.get("adopted")]
    if adopted:
        for s in adopted:
            push(f"- **{s.get('module','')}**：{_cell(s.get('original',''))} → {_cell(s.get('suggestion',''))}")
            if s.get("reason"):
                push(f"  - 理由：{_cell(s['reason'])}")
    elif suggestions:
        push(f"_已有 {len(suggestions)} 条改写建议，但都还没标记为采用。_")
    else:
        push("_尚未生成改写建议。_")
    push("")
    push("> 红线：只改表达、不动事实。不得新增项目、技术、数字或时间；参与类经历不得写成主导。")
    push("")

    # 八、面试提示
    push("## 八、面试准备提示")
    push("")
    high_gaps = [g for g in gaps if g.get("priority") == "high"]
    if high_gaps:
        push("优先准备这三类追问：")
        push("")
        for g in high_gaps[:5]:
            push(f"- 「{_cell(g.get('requirement',''))[:50]}」—— 简历里没有直接事实，准备一句诚实的边界说明 + 最近补的进展。")
        push("")
    if missing:
        push(f"- 缺失技能集中在：{'、'.join(missing[:6])}，面试前至少能讲清它解决什么问题、和已会的东西什么关系。")
    if (selection or {}).get("base"):
        push(f"- 如果被问「为什么投这个岗」，用基底 `{selection['base'].get('code','')}` 的选型理由回答，别现编。")
    if uncovered:
        parts = []
        for x in uncovered[:6]:
            parts.append("{0}（{1}家）".format(x["term"], x["jobs"]))
        push("")
        push("> 台账提醒：以下技能已被多家要求而你零覆盖，优先级高于本岗位的临时补课 —— "
             + "、".join(parts))
    push("")

    # 附
    push("## 附：原始 JD")
    push("")
    push("```text")
    push((job.get("jd_raw") or "").strip())
    push("```")
    push("")
    return "\n".join(lines)
