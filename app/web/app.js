/* JDScope 前端。纯原生 JS，无构建、无框架。
   所有请求都打到同源的 /api/*，数据不出本机。 */

"use strict";

const S = {
  boot: null,
  view: "dash",
  parse: null,
  jobs: [],
  detail: null,
  stats: null,
  gaps: [],
  baseFile: null,
};

/* ---------------- 基础工具 ---------------- */

async function api(path, { method = "GET", body = null } = {}) {
  const init = { method, headers: { "Content-Type": "application/json" } };
  if (body !== null) init.body = JSON.stringify(body);
  const res = await fetch(path, init);
  let data = null;
  try { data = await res.json(); } catch (e) { data = { error: "响应不是 JSON" }; }
  if (!res.ok) {
    const msg = (data && data.error) || `请求失败 ${res.status}`;
    throw new Error(msg);
  }
  return data;
}

function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

let toastTimer = null;
function toast(msg, kind = "") {
  const box = document.getElementById("toast");
  box.textContent = msg;
  box.className = "toast show " + kind;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { box.className = "toast " + kind; }, 3200);
}

const STATUS_LABEL = {
  new: "待处理", applied: "已投递", replied: "已回复", interview: "面试中",
  offer: "已录用", rejected: "已拒绝", dropped: "已放弃",
};
const DECISION_LABEL = { undecided: "未决", go: "投", skip: "不投", watch: "观望" };
const CAT_LABEL = { must: "必备", duty: "职责", nice: "加分" };
const PRIO_LABEL = { high: "高", medium: "中", low: "低" };
const DIM_LABEL = { must: "必备要求覆盖", duty: "职责同构度", nice: "加分项覆盖", constraint: "硬性条件符合" };
const STATE_LABEL = { pass: "满足", partial: "勉强", unknown: "未知", fail: "不满足" };

function chipOf(score) {
  const v = Number(score || 0);
  if (v >= 72) return "hi";
  if (v >= 55) return "mid";
  return "lo";
}
function pct(v) { return v === null || v === undefined ? "—" : Math.round(v * 100) + "%"; }
function emptyRow(cols, text = "还没有数据") {
  return `<tr><td colspan="${cols}"><div class="empty">${esc(text)}</div></td></tr>`;
}
function badgePriority(p) {
  return `<span class="badge ${esc(p || "low")}">${esc(PRIO_LABEL[p] || p || "")}</span>`;
}

/* ---------------- 启动 ---------------- */

async function boot() {
  const health = await api("/api/health");
  document.getElementById("dataHome").textContent = health.data_home || "—";
  await loadBootstrap();
  await refreshAll();
}

async function loadBootstrap() {
  S.boot = await api("/api/bootstrap");
  renderChips(S.boot.summary);
  renderProfileForm(S.boot.profile);
  renderSettingsForm(S.boot.settings);
}

function renderChips(sum) {
  if (!sum) return;
  const chips = [
    [`<b>${sum.jobs}</b> 岗位`, "岗位总数"],
    [`<b>${sum.bases}</b> 基底`, "已登记母版"],
    [`<b>${sum.gaps_open}</b> 待补缺口`, "未处理"],
    [`<b>${sum.avg_score}</b> 平均分`, "全部岗位"],
    [sum.reply_rate === null ? "<b>—</b> 回复率" : `<b>${sum.reply_rate}%</b> 回复率`, "已投递 " + sum.applied + " / 回 " + sum.replied],
  ];
  document.getElementById("topChips").innerHTML = chips
    .map(([html]) => `<span class="chip">${html}</span>`).join("");
}

async function refreshAll() {
  if (S.view === "dash") await renderDash();
  if (S.view === "jobs") await renderJobs();
  if (S.view === "gaps") await renderGaps();
  if (S.view === "bases") await renderBases();
}

/* ---------------- 视图切换 ---------------- */

function switchView(name) {
  S.view = name;
  document.querySelectorAll(".nav").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("active", v.id === "view-" + name));
  if (name === "dash") renderDash();
  if (name === "jobs") renderJobs();
  if (name === "gaps") renderGaps();
  if (name === "bases") renderBases();
}

/* ---------------- 概览 ---------------- */

async function renderDash() {
  try {
    S.stats = await api("/api/stats?min_jobs=2");
  } catch (e) { toast(e.message, "err"); return; }
  const s = S.stats.summary;

  document.getElementById("statCards").innerHTML = `
    <div class="stat"><div class="k">岗位总数</div><div class="v">${s.jobs}</div></div>
    <div class="stat"><div class="k">平均匹配度</div><div class="v">${s.avg_score}<small>/100</small></div></div>
    <div class="stat"><div class="k">待补缺口</div><div class="v">${s.gaps_open}</div></div>
    <div class="stat"><div class="k">已投递</div><div class="v">${s.applied}</div></div>
    <div class="stat"><div class="k">回复率</div><div class="v">${s.reply_rate === null ? "—" : s.reply_rate + "<small>%</small>"}</div></div>
  `;

  // 技能需求榜
  const terms = S.stats.term_demand || [];
  document.getElementById("termTable").innerHTML = terms.length
    ? `<table><thead><tr><th>技能</th><th>领域</th><th>要求家数</th><th>我的覆盖</th></tr></thead><tbody>
        ${terms.map((t) => `<tr>
          <td><strong>${esc(t.term)}</strong></td>
          <td class="muted">${esc(t.domain || "—")}</td>
          <td>${t.jobs}</td>
          <td>${t.covered ? '<span class="badge ok">已覆盖</span>' : '<span class="badge bad">零覆盖</span>'}</td>
        </tr>`).join("")}
      </tbody></table>`
    : `<div class="empty">还没有岗位，先去「JD 入库」录一条</div>`;

  // 缺口热点
  const hot = S.stats.gap_hotspots || [];
  document.getElementById("gapHot").innerHTML = hot.length
    ? `<table><thead><tr><th>缺口（截断）</th><th>涉及岗位</th></tr></thead><tbody>
        ${hot.map((g) => `<tr><td>${esc(g.requirement)}…</td><td>${g.jobs}</td></tr>`).join("")}
      </tbody></table>`
    : `<div class="empty">暂无缺口记录</div>`;

  // 基底表现
  const perf = S.stats.base_performance || [];
  document.getElementById("basePerf").innerHTML = perf.length
    ? `<table><thead><tr><th>基底</th><th>用了几次</th><th>已投</th><th>回复率</th><th>均分</th></tr></thead><tbody>
        ${perf.map((b) => `<tr>
          <td><strong>${esc(b.code)}</strong><div class="hint">${esc(b.intent)}</div></td>
          <td>${b.used}</td><td>${b.applied}</td>
          <td>${b.reply_rate === null ? "—" : b.reply_rate + "%"}</td>
          <td>${b.avg_score}</td>
        </tr>`).join("")}
      </tbody></table>`
    : `<div class="empty">还没有登记基底</div>`;

  // 城市
  const cities = S.stats.city_demand || [];
  document.getElementById("cityStats").innerHTML = cities.length
    ? `<table><thead><tr><th>城市</th><th>岗位数</th></tr></thead><tbody>
        ${cities.map((c) => `<tr><td>${esc(c.city)}</td><td>${c.count}</td></tr>`).join("")}
      </tbody></table>`
    : `<div class="empty">暂无城市数据</div>`;

  // 未覆盖技能提醒
  const un = S.stats.uncovered || [];
  if (un.length) {
    const names = un.slice(0, 8).map((u) => `${u.term}（${u.jobs}家）`).join("、");
    toast("高频未覆盖技能：" + names, "");
  }
}

/* ---------------- JD 入库 ---------------- */

const SAMPLE_JD = `公司名称：示例数据科技有限公司
岗位名称：AI 应用开发工程师（Agent 方向）
工作地点：深圳

岗位职责：
1、负责基于大模型的智能体应用设计与开发，完成需求到上线的闭环；
2、负责 RAG 检索链路搭建，包含文档切分、Embedding、召回与重排；
3、参与工具调用（Function Calling）能力建设，沉淀可复用的 MCP 工具；
4、负责服务端接口开发与容器化部署，保障线上稳定性。

任职要求：
1、本科及以上学历，计算机相关专业，2 年以上开发经验；
2、熟练掌握 Python，熟悉 FastAPI 或同类 Web 框架；
3、熟悉 LangGraph 或 LangChain 等编排框架，理解 Agent 的多轮与记忆机制；
4、熟悉 MySQL、Redis，具备高并发场景下的性能优化经验；
5、熟悉 Docker、Linux，能独立完成服务部署与日志排查。

加分项：
1、有向量数据库（Milvus / pgvector）使用经验者优先；
2、有模型评测体系搭建经验者优先；
3、有开源项目或技术博客者优先。`;

function initIntake() {
  const ta = document.getElementById("fJd");
  const count = document.getElementById("jdCount");
  const update = () => { count.textContent = ta.value.trim().length + " 字"; };
  ta.addEventListener("input", update);
  document.getElementById("btnLoadSample").addEventListener("click", () => {
    ta.value = SAMPLE_JD; update(); S.parse = null;
    document.getElementById("parseResult").hidden = true;
    document.getElementById("btnSaveJob").disabled = true;
  });
  document.getElementById("fileJd").addEventListener("change", async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    ta.value = await f.text();
    update();
  });
  document.getElementById("btnParse").addEventListener("click", doParse);
  document.getElementById("btnSaveJob").addEventListener("click", doSaveJob);
}

async function doParse() {
  const jd = document.getElementById("fJd").value.trim();
  if (jd.length < 20) { toast("JD 原文太短", "err"); return; }
  try {
    S.parse = await api("/api/jobs/parse", {
      method: "POST",
      body: {
        jd_raw: jd,
        company: document.getElementById("fCompany").value.trim(),
        title: document.getElementById("fTitle").value.trim(),
        city: document.getElementById("fCity").value.trim(),
      },
    });
    renderParse(S.parse);
    document.getElementById("parseResult").hidden = false;
    document.getElementById("btnSaveJob").disabled = false;
    // 回填识别到的元信息，方便确认
    if (!document.getElementById("fCompany").value && S.parse.company) document.getElementById("fCompany").value = S.parse.company;
    if (!document.getElementById("fTitle").value && S.parse.title) document.getElementById("fTitle").value = S.parse.title;
    if (!document.getElementById("fCity").value && S.parse.city) document.getElementById("fCity").value = S.parse.city;
  } catch (e) { toast(e.message, "err"); }
}

function renderParse(p) {
  const groups = ["must", "duty", "nice"];
  const reqHtml = groups.map((cat) => {
    const rows = (p.requirements || []).filter((r) => r.category === cat);
    if (!rows.length) return "";
    return `<div class="section-title">${CAT_LABEL[cat]}（${rows.length} 条）</div>
      ${rows.map((r) => `<div class="req-row">
        <div>${badgePriority(r.priority)}</div>
        <div><div class="txt">${esc(r.text)}</div>
        <div class="ev">${r.terms && r.terms.length ? "识别术语：" + esc(r.terms.join("、")) : "未识别到技术术语"}</div></div>
      </div>`).join("")}`;
  }).join("");

  const cons = (p.constraints || []).map((c) => `<span class="badge plain">${esc(c.text || c.kind)}</span>`).join(" ");

  document.getElementById("parseBody").innerHTML = `
    <div class="pad-16">
      <div class="row-between">
        <div>
          <div class="detail-title">${esc(p.company || "（未识别公司）")} · ${esc(p.title || "（未识别岗位）")}</div>
          <div class="detail-sub">城市：${esc(p.city || "未识别")}　识别术语 ${p.terms.length} 个　需求 ${p.requirements.length} 条</div>
        </div>
        <div>${cons || '<span class="hint">未识别到硬性条件</span>'}</div>
      </div>
      <div class="row-gap mt8">${(p.terms || []).map((t) => `<span class="badge plain">${esc(t)}</span>`).join("")}</div>
      ${reqHtml}
    </div>`;
}

async function doSaveJob() {
  const jd = document.getElementById("fJd").value.trim();
  try {
    const r = await api("/api/jobs", {
      method: "POST",
      body: {
        jd_raw: jd,
        company: document.getElementById("fCompany").value.trim(),
        title: document.getElementById("fTitle").value.trim(),
        city: document.getElementById("fCity").value.trim(),
        url: document.getElementById("fUrl").value.trim(),
        source: document.getElementById("fSource").value.trim(),
      },
    });
    toast(`已保存：匹配度 ${r.score}，${r.verdict}`, "ok");
    document.getElementById("fJd").value = "";
    document.getElementById("jdCount").textContent = "0 字";
    document.getElementById("parseResult").hidden = true;
    document.getElementById("btnSaveJob").disabled = true;
    await loadBootstrap();
    switchView("jobs");
    openJob(r.job_id);
  } catch (e) { toast(e.message, "err"); }
}

/* ---------------- 岗位列表 ---------------- */

async function renderJobs() {
  const q = encodeURIComponent(document.getElementById("jobSearch").value.trim());
  const st = document.getElementById("jobStatus").value;
  try {
    S.jobs = (await api(`/api/jobs?q=${q}&status=${encodeURIComponent(st)}`)).items;
  } catch (e) { toast(e.message, "err"); return; }

  const rows = S.jobs.map((j) => {
    const cov = (j.score_json && j.score_json.coverage) || {};
    const miss = (cov.missing || []).length;
    return `<tr class="clickable" data-id="${j.id}">
      <td><strong>${esc(j.company)}</strong><div class="hint">${esc(j.title)}</div></td>
      <td>${esc(j.city || "—")}</td>
      <td><span class="score ${chipOf(j.score)}">${j.score}</span></td>
      <td><span class="badge ${j.verdict === "建议投" ? "ok" : j.verdict === "不建议投" ? "bad" : "warn"}">${esc(j.verdict || "")}</span></td>
      <td>${miss ? `<span class="badge bad">${miss}</span>` : '<span class="badge ok">0</span>'}</td>
      <td>${esc(STATUS_LABEL[j.status] || j.status)}</td>
      <td class="muted">${esc((j.created_at || "").slice(5, 10))}</td>
    </tr>`;
  }).join("");

  document.getElementById("jobTable").innerHTML = `
    <thead><tr><th>公司 / 岗位</th><th>城市</th><th>匹配度</th><th>判定</th><th>缺失项</th><th>状态</th><th>录入</th></tr></thead>
    <tbody>${rows || emptyRow(7, "还没有岗位")}</tbody>`;

  document.querySelectorAll("#jobTable tbody tr.clickable").forEach((tr) => {
    tr.addEventListener("click", () => openJob(Number(tr.dataset.id)));
  });
}

async function openJob(id) {
  try {
    const d = await api(`/api/jobs/${id}`);
    S.detail = d;
    renderJobDetail(d);
    document.getElementById("jobDetail").hidden = false;
    document.getElementById("jobDetail").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (e) { toast(e.message, "err"); }
}

function renderJobDetail(d) {
  const job = d.job;
  const dims = d.score.dims || {};
  const cov = d.score.coverage || {};
  const cons = d.constraints || [];

  const dimHtml = Object.keys(DIM_LABEL).map((k) => {
    const v = dims[k];
    return `<div class="dim">
      <div class="k">${DIM_LABEL[k]}</div>
      <div class="bar"><span>${pct(v)}</span></div>
      <div class="track"><div class="fill" style="width:${v === null || v === undefined ? 0 : Math.round(v * 100)}%"></div></div>
    </div>`;
  }).join("");

  const reqHtml = ["must", "duty", "nice"].map((cat) => {
    const rows = (d.requirements || []).filter((r) => r.category === cat);
    if (!rows.length) return "";
    return `<div class="section-title">${CAT_LABEL[cat]}（${rows.length}）</div>
      ${rows.map((r) => `<div class="req-row">
        <div>${r.hit === 2 ? '<span class="badge ok">命中</span>' : r.hit === 1 ? '<span class="badge warn">部分</span>' : '<span class="badge bad">缺失</span>'}</div>
        <div><div class="txt">${esc(r.text)}</div><div class="ev">${esc(r.evidence || "")}</div></div>
      </div>`).join("")}`;
  }).join("");

  const consHtml = cons.length ? `<div class="section-title">硬性条件</div>
    <table><thead><tr><th>条件</th><th>状态</th><th>说明</th></tr></thead><tbody>
    ${cons.map((c) => `<tr><td>${esc(c.text || c.value || c.kind)}</td>
      <td><span class="badge ${c.state === "pass" ? "ok" : c.state === "fail" ? "bad" : "warn"}">${STATE_LABEL[c.state] || c.state}</span></td>
      <td class="muted">${esc(c.note || "")}</td></tr>`).join("")}
    </tbody></table>` : "";

  const gapHtml = (d.gaps || []).length ? `<div class="section-title">缺口（${d.gaps.length}）</div>
    <table><thead><tr><th>优先级</th><th>JD 要求</th><th>差在哪</th><th>补课方向</th></tr></thead><tbody>
    ${d.gaps.map((g) => `<tr>
      <td>${badgePriority(g.priority)}</td>
      <td>${esc((g.requirement || "").slice(0, 46))}</td>
      <td class="muted">${esc(g.gap || "")}</td>
      <td class="muted">${esc(g.action || "")}</td>
    </tr>`).join("")}</tbody></table>` : '<div class="section-title">缺口</div><p class="hint">没有发现明确缺口。</div>';

  const sugHtml = (d.suggestions || []).length
    ? `<div class="section-title">改写建议（${d.suggestions.length}）</div>
      ${d.suggestions.map((s) => `<div class="sug">
        <div class="ori">${esc(s.original)}</div>
        <div class="new">${esc(s.suggestion)}</div>
        <div class="why">${esc(s.reason || "")}</div>
        <div class="ops">
          <span class="badge ${s.adopted ? "ok" : "low"}">${s.adopted ? "已采用" : "未采用"}</span>
          <button class="mini ${s.adopted ? "on" : ""}" data-adopt="${s.id}" data-cur="${s.adopted}">${s.adopted ? "取消采用" : "标记采用"}</button>
        </div>
      </div>`).join("")}`
    : '<div class="section-title">改写建议</div><p class="hint">尚未生成。首次使用请在「设置」里配置模型端点，再点上方「生成改写建议」。</p>';

  const coverageHtml = `<div class="section-title">关键词覆盖</div>
    <div class="row-gap">
      <span class="badge ok">命中 ${(cov.covered || []).length}</span>
      <span class="badge warn">部分 ${(cov.partial || []).length}</span>
      <span class="badge bad">缺失 ${(cov.missing || []).length}</span>
    </div>
    <div class="row-gap mt8">
      ${(cov.covered || []).map((t) => `<span class="badge ok">${esc(t)}</span>`).join("")}
      ${(cov.partial || []).map((t) => `<span class="badge warn">${esc(t)}</span>`).join("")}
      ${(cov.missing || []).map((t) => `<span class="badge bad">${esc(t)}</span>`).join("")}
    </div>`;

  document.getElementById("jobDetail").innerHTML = `
    <div class="detail-head">
      <div>
        <div class="detail-title">${esc(job.company)} · ${esc(job.title)}</div>
        <div class="detail-sub">
          城市 ${esc(job.city || "—")}　来源 ${esc(job.source || "—")}　
          基底 ${esc(d.base ? d.base.code : "未选")}　录入 ${esc((job.created_at || "").slice(0, 10))}
        </div>
      </div>
      <div class="detail-actions">
        <select id="detailStatus">
          ${Object.keys(STATUS_LABEL).map((k) => `<option value="${k}" ${job.status === k ? "selected" : ""}>${STATUS_LABEL[k]}</option>`).join("")}
        </select>
        <button class="ghost" id="btnReanalyze">重算</button>
        <button class="ghost" id="btnSuggest">生成改写建议</button>
        <button class="primary" id="btnExport">导出报告</button>
        <button class="danger-btn" id="btnDeleteJob">删除</button>
      </div>
    </div>
    <div class="dims">${dimHtml}</div>
    <div class="detail-body">
      <div class="section-title">结论</div>
      <div class="row-gap">
        <span class="score ${chipOf(job.score)}">${job.score}</span>
        <span class="badge ${job.verdict === "建议投" ? "ok" : job.verdict === "不建议投" ? "bad" : "warn"}">${esc(job.verdict)}</span>
        <span class="hint">${esc(d.score.verdict_reason || (d.score.criteria || [])[0] || "")}</span>
      </div>
      ${consHtml}
      ${coverageHtml}
      ${reqHtml}
      ${gapHtml}
      ${sugHtml}
      <div class="section-title">原始 JD</div>
      <pre style="white-space:pre-wrap;font-size:12.5px;color:var(--sub);background:var(--surface-2);padding:12px;border-radius:8px;max-height:260px;overflow:auto;">${esc(job.jd_raw)}</pre>
      <div id="reportBox"></div>
    </div>`;

  document.getElementById("detailStatus").addEventListener("change", async (e) => {
    try {
      await api(`/api/jobs/${job.id}`, { method: "PATCH", body: { status: e.target.value } });
      toast("状态已更新", "ok");
      await loadBootstrap(); await renderJobs();
    } catch (err) { toast(err.message, "err"); }
  });
  document.getElementById("btnReanalyze").addEventListener("click", async () => {
    try {
      await api(`/api/jobs/${job.id}/analyze`, { method: "POST" });
      toast("已重算", "ok"); await openJob(job.id);
    } catch (err) { toast(err.message, "err"); }
  });
  document.getElementById("btnSuggest").addEventListener("click", async () => {
    toast("正在请求模型，可能十几秒…");
    try {
      const r = await api(`/api/jobs/${job.id}/suggest`, { method: "POST", body: { module: "整体" } });
      if (r.error) throw new Error(r.error);
      toast(`生成 ${r.items.length} 条建议`, "ok"); await openJob(job.id);
    } catch (err) { toast(err.message, "err"); }
  });
  document.getElementById("btnExport").addEventListener("click", async () => {
    try {
      const r = await api(`/api/jobs/${job.id}/export`, { method: "POST" });
      const box = document.getElementById("reportBox");
      box.innerHTML = `<div class="section-title">报告已生成</div>
        <p class="hint">已写入：${esc(r.path)}</p>
        <pre style="white-space:pre-wrap;font-size:12.5px;background:var(--surface-2);padding:14px;border-radius:8px;max-height:420px;overflow:auto;">${esc(r.markdown)}</pre>`;
      toast("报告已生成并写入数据目录", "ok");
    } catch (err) { toast(err.message, "err"); }
  });
  document.getElementById("btnDeleteJob").addEventListener("click", async () => {
    if (!confirm("确认删除这条岗位及其缺口、建议？")) return;
    try {
      await api(`/api/jobs/${job.id}`, { method: "DELETE" });
      toast("已删除", "ok");
      document.getElementById("jobDetail").hidden = true;
      await loadBootstrap(); await renderJobs();
    } catch (err) { toast(err.message, "err"); }
  });
  document.querySelectorAll("[data-adopt]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const sid = Number(btn.dataset.adopt);
      const cur = btn.dataset.cur === "1";
      try {
        await api(`/api/suggestions/${sid}/adopt`, { method: "POST", body: { adopted: !cur } });
        await openJob(job.id);
      } catch (err) { toast(err.message, "err"); }
    });
  });
}

/* ---------------- 缺口库 ---------------- */

async function renderGaps() {
  const pr = document.getElementById("gapPriority").value;
  const st = document.getElementById("gapStatus").value;
  try {
    S.gaps = (await api(`/api/gaps?priority=${pr}&status=${encodeURIComponent(st)}`)).items;
  } catch (e) { toast(e.message, "err"); return; }
  document.getElementById("gapCount").textContent = `共 ${S.gaps.length} 条`;

  const rows = S.gaps.map((g) => `<tr>
    <td>${badgePriority(g.priority)}</td>
    <td>${esc(g.company || "—")}<div class="hint">${esc(g.title || "")}</div></td>
    <td>${esc((g.requirement || "").slice(0, 50))}</td>
    <td class="muted">${esc(g.resume_state || "")}</td>
    <td>
      <select data-gap-status="${g.id}">
        ${[["open", "未处理"], ["learning", "补课中"], ["closed", "已补上"]].map(([k, v]) =>
          `<option value="${k}" ${g.status === k ? "selected" : ""}>${v}</option>`).join("")}
      </select>
    </td>
    <td>
      <button class="mini" data-answer="${g.id}">生成应答</button>
      ${g.answer ? `<div class="hint mt8">${esc(g.answer)}</div>` : ""}
    </td>
  </tr>`).join("");

  document.getElementById("gapTable").innerHTML = `
    <thead><tr><th>优先级</th><th>来自</th><th>JD 要求</th><th>简历现状</th><th>状态</th><th>面试应答</th></tr></thead>
    <tbody>${rows || emptyRow(6, "这个筛选条件下没有缺口")}</tbody>`;

  document.querySelectorAll("[data-gap-status]").forEach((sel) => {
    sel.addEventListener("change", async () => {
      try {
        await api(`/api/gaps/${sel.dataset.gapStatus}`, { method: "PATCH", body: { status: sel.value } });
        toast("已更新", "ok"); renderGaps();
      } catch (e) { toast(e.message, "err"); }
    });
  });
  document.querySelectorAll("[data-answer]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      toast("正在请求模型…");
      try {
        const r = await api(`/api/gaps/${btn.dataset.answer}/answer`, { method: "POST" });
        if (r.error) throw new Error(r.error);
        toast("已生成应答口径", "ok"); renderGaps();
      } catch (e) { toast(e.message, "err"); }
    });
  });
}

/* ---------------- 基底库 ---------------- */

async function renderBases() {
  try {
    const d = await api("/api/bases");
    S.bases = d.items;
  } catch (e) { toast(e.message, "err"); return; }

  const rows = S.bases.map((b) => `<tr>
    <td><strong>${esc(b.code)}</strong><div class="hint">${esc(b.label || "")}</div></td>
    <td>${esc(b.intent)}</td>
    <td>${b.coverage}</td>
    <td>${(b.tags || []).map((t) => `<span class="badge low">${esc(t)}</span>`).join(" ") || '<span class="hint">—</span>'}</td>
    <td class="hint">${esc((b.keywords || []).slice(0, 10).join("、"))}${(b.keywords || []).length > 10 ? " …" : ""}</td>
    <td><button class="danger-btn" data-del-base="${b.id}">删除</button></td>
  </tr>`).join("");

  document.getElementById("baseTable").innerHTML = `
    <thead><tr><th>代号</th><th>求职意向</th><th>覆盖术语</th><th>标签</th><th>识别到</th><th></th></tr></thead>
    <tbody>${rows || emptyRow(6, "还没有登记基底")}</tbody>`;

  document.querySelectorAll("[data-del-base]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm("删除这个基底？已保存岗位的匹配结果不会自动重算。")) return;
      try {
        await api(`/api/bases/${btn.dataset.delBase}`, { method: "DELETE" });
        toast("已删除", "ok"); await loadBootstrap(); renderBases();
      } catch (e) { toast(e.message, "err"); }
    });
  });
}

function initBases() {
  const file = document.getElementById("fileBase");
  file.addEventListener("change", async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    S.baseFile = { name: f.name, text: await f.text() };
    document.getElementById("bFileHint").textContent = `已读取 ${f.name}（${S.baseFile.text.length} 字符）`;
    document.getElementById("btnAddBase").disabled = false;
  });
  document.getElementById("btnAddBase").addEventListener("click", async () => {
    if (!S.baseFile) return;
    const code = document.getElementById("bCode").value.trim();
    const intent = document.getElementById("bIntent").value.trim();
    if (!code || !intent) { toast("代号和求职意向必填", "err"); return; }
    try {
      const r = await api("/api/bases", {
        method: "POST",
        body: {
          code, intent,
          label: document.getElementById("bLabel").value.trim(),
          tags: document.getElementById("bTags").value,
          content: S.baseFile.text,
        },
      });
      toast(`已登记，识别 ${r.coverage} 个术语`, "ok");
      S.baseFile = null;
      document.getElementById("bFileHint").textContent = "未选择文件";
      document.getElementById("fileBase").value = "";
      document.getElementById("btnAddBase").disabled = true;
      ["bCode", "bIntent", "bLabel", "bTags"].forEach((id) => { document.getElementById(id).value = ""; });
      await loadBootstrap(); renderBases();
    } catch (e) { toast(e.message, "err"); }
  });
}

/* ---------------- 档案 ---------------- */

function renderProfileForm(p) {
  document.getElementById("pEdu").value = p.education || "";
  document.getElementById("pMajor").value = p.major || "";
  document.getElementById("pYears").value = p.years ?? 0;
  document.getElementById("pCities").value = p.cities || "";
  document.getElementById("pCerts").value = p.certs || "";
  document.getElementById("pNotes").value = p.notes || "";
  document.getElementById("pSavedAt").textContent = p.updated_at ? "上次保存 " + p.updated_at.slice(0, 16).replace("T", " ") : "";
}

function initProfile() {
  document.getElementById("btnSaveProfile").addEventListener("click", async () => {
    try {
      await api("/api/profile", {
        method: "POST",
        body: {
          education: document.getElementById("pEdu").value,
          major: document.getElementById("pMajor").value.trim(),
          years: Number(document.getElementById("pYears").value || 0),
          cities: document.getElementById("pCities").value.trim(),
          certs: document.getElementById("pCerts").value.trim(),
          notes: document.getElementById("pNotes").value.trim(),
        },
      });
      toast("档案已保存", "ok");
      await loadBootstrap();
    } catch (e) { toast(e.message, "err"); }
  });
}

/* ---------------- 设置 ---------------- */

function renderSettingsForm(s) {
  document.getElementById("sBaseUrl").value = s.base_url || "";
  document.getElementById("sModel").value = s.model || "";
  document.getElementById("sApiKey").value = "";
  const w = s.weights || {};
  document.getElementById("wMust").value = w.must ?? 30;
  document.getElementById("wDuty").value = w.duty ?? 30;
  document.getElementById("wNice").value = w.nice ?? 15;
  document.getElementById("wConstraint").value = w.constraint ?? 25;
}

function initSettings() {
  document.getElementById("btnSaveSettings").addEventListener("click", async () => {
    try {
      await api("/api/settings", {
        method: "POST",
        body: {
          base_url: document.getElementById("sBaseUrl").value.trim(),
          model: document.getElementById("sModel").value.trim(),
          api_key: document.getElementById("sApiKey").value.trim(),
        },
      });
      toast("设置已保存", "ok");
      document.getElementById("sApiKey").value = "";
      await loadBootstrap();
    } catch (e) { toast(e.message, "err"); }
  });
  document.getElementById("btnTestLlm").addEventListener("click", async () => {
    const hint = document.getElementById("llmTestHint");
    hint.textContent = "测试中…";
    try {
      const r = await api("/api/llm/test", {
        method: "POST",
        body: {
          base_url: document.getElementById("sBaseUrl").value.trim(),
          model: document.getElementById("sModel").value.trim(),
          api_key: document.getElementById("sApiKey").value.trim(),
        },
      });
      hint.textContent = r.ok ? "连通：" + r.reply : "失败：" + r.error;
    } catch (e) { hint.textContent = "失败：" + e.message; }
  });
  document.getElementById("btnSaveWeights").addEventListener("click", async () => {
    try {
      await api("/api/settings", {
        method: "POST",
        body: {
          weights: {
            must: Number(document.getElementById("wMust").value || 0),
            duty: Number(document.getElementById("wDuty").value || 0),
            nice: Number(document.getElementById("wNice").value || 0),
            constraint: Number(document.getElementById("wConstraint").value || 0),
          },
        },
      });
      toast("权重已保存，记得对岗位点「重算」", "ok");
      await loadBootstrap();
    } catch (e) { toast(e.message, "err"); }
  });
}

/* ---------------- 装配 ---------------- */

function initNav() {
  document.querySelectorAll(".nav").forEach((b) => {
    b.addEventListener("click", () => switchView(b.dataset.view));
  });
  document.getElementById("btnRefresh").addEventListener("click", async () => {
    await loadBootstrap(); await refreshAll(); toast("已刷新", "ok");
  });
  document.getElementById("jobSearch").addEventListener("input", debounce(renderJobs, 260));
  document.getElementById("jobStatus").addEventListener("change", renderJobs);
  document.getElementById("gapPriority").addEventListener("change", renderGaps);
  document.getElementById("gapStatus").addEventListener("change", renderGaps);
}

function debounce(fn, ms) {
  let t = null;
  return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

document.addEventListener("DOMContentLoaded", async () => {
  initNav(); initIntake(); initBases(); initProfile(); initSettings();
  try {
    await boot();
  } catch (e) {
    toast("启动失败：" + e.message, "err");
  }
});
