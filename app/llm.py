"""可选的大模型接入：OpenAI 兼容端点（默认 DeepSeek）。

两条硬约束写进提示词，也写进解析兜底：
1. 只改表达，不动事实——不得新增项目、技术、数字或时间；
2. 只输出 JSON，解析失败即视为失败，不回退成自由文本。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

SYSTEM_SUGGEST = """你是一名简历表达顾问。你的任务只有一个：在不改变任何事实的前提下，
把给定简历片段改写得更贴合目标岗位。严格遵守：
1. 不得新增项目、技术、工具、数字、时间、级别、职责范围；
2. 参与/协助类经历不得升级为主导/独立负责；
3. 没有量化事实的地方不要补造数字；
4. 只调整措辞、顺序与信息密度。
只输出 JSON，不要任何解释性文字，格式：
{"items":[{"module":"模块名","original":"原文","suggestion":"建议改写","reason":"一句话理由"}]}
若某处无可改之处，就少给几条，不要凑数。"""

SYSTEM_ANSWER = """你是面试教练。给定一条「JD 要求 / 简历现状 / 差距」，写一段求职者在面试中
可以诚实使用的应答口径。要求：
1. 不得编造经历，不得把没做过的事说成做过；
2. 结构为：诚实边界 → 已有相近能力 → 正在补充的具体动作；
3. 150 字以内，口语化，可直接背。
只输出 JSON：{"answer":"..."}"""


def _post(url: str, payload: dict, api_key: str, timeout: int = 60) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def chat(cfg: dict, messages: list[dict], temperature: float = 0.3, timeout: int = 60) -> str:
    base_url = (cfg.get("base_url") or "").rstrip("/")
    api_key = cfg.get("api_key") or ""
    model = cfg.get("model") or ""
    if not base_url or not api_key or not model:
        raise ValueError("尚未配置模型端点（BASE_URL / API_KEY / MODEL）")
    url = f"{base_url}/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": False,
    }
    resp = _post(url, payload, api_key, timeout)
    choices = resp.get("choices") or []
    if not choices:
        raise ValueError("模型无返回内容")
    return (choices[0].get("message") or {}).get("content") or ""


def _extract_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        lines = [ln for ln in text.splitlines() if not ln.strip().startswith("```")]
        text = "\n".join(lines).strip()
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    return json.loads(text)


def suggest_rewrite(cfg: dict, jd_text: str, base_text: str, module: str = "整体") -> dict:
    """返回 {"items":[{"module","original","suggestion","reason"}]} 或 {"error": ...}"""
    try:
        user = (
            f"目标岗位 JD：\n{jd_text[:3000]}\n\n"
            f"待改写的简历片段（模块：{module}）：\n{base_text[:4000]}\n\n"
            "请输出 JSON。"
        )
        raw = chat(
            cfg,
            [
                {"role": "system", "content": SYSTEM_SUGGEST},
                {"role": "user", "content": user},
            ],
        )
        data = _extract_json(raw)
        items = data.get("items")
        if not isinstance(items, list):
            return {"error": "返回结构不符合约定（缺少 items 数组）"}
        clean = []
        for it in items[:20]:
            if not isinstance(it, dict):
                continue
            clean.append(
                {
                    "module": str(it.get("module") or module),
                    "original": str(it.get("original") or ""),
                    "suggestion": str(it.get("suggestion") or ""),
                    "reason": str(it.get("reason") or ""),
                }
            )
        return {"items": clean}
    except urllib.error.HTTPError as e:
        return {"error": f"接口返回 {e.code}：{e.read()[:200].decode('utf-8', 'ignore')}"}
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}


def answer_gap(cfg: dict, requirement: str, resume_state: str, gap: str) -> dict:
    try:
        user = (
            f"JD 要求：{requirement}\n简历现状：{resume_state}\n差距：{gap}\n\n"
            "请输出 JSON。"
        )
        raw = chat(
            cfg,
            [
                {"role": "system", "content": SYSTEM_ANSWER},
                {"role": "user", "content": user},
            ],
            temperature=0.4,
        )
        data = _extract_json(raw)
        return {"answer": str(data.get("answer") or "")}
    except Exception as e:  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {e}"}


def test_connection(cfg: dict) -> dict:
    try:
        reply = chat(cfg, [{"role": "user", "content": "回复两个字：连通"}], temperature=0)
        return {"ok": True, "reply": reply[:60]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
