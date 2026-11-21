/* 全局状态与数据加载。页面组件共享同一个 reactive 对象，不引入额外状态库。 */

import { api } from "./api.js";

const { reactive } = window.Vue;

export const state = reactive({
  view: "dash",
  ready: false,
  summary: {},
  profile: {},
  settings: {},
  health: null,
  dataDir: null,

  stats: null,
  statsLoading: false,

  jobs: [],
  jobsLoading: false,
  jobQuery: "",
  jobStatus: "",
  jobSort: "score",

  detail: null,
  detailLoading: false,

  gaps: [],
  gapsLoading: false,
  gapPriority: "",
  gapStatus: "open",
  gapQuery: "",

  bases: [],
  companies: [],
  companiesLoading: false,
  companyDetail: null,
  toasts: [],
});

/* ---------------- 文案表 ---------------- */

export const STATUS_LABEL = {
  new: "待处理", applied: "已投递", replied: "已回复", interview: "面试中",
  offer: "已录用", rejected: "已拒绝", dropped: "已放弃",
};
export const CAT_LABEL = { must: "必备要求", duty: "岗位职责", nice: "加分项" };
export const PRIO_LABEL = { high: "高", medium: "中", low: "低" };
export const DIM_LABEL = {
  must: "必备要求覆盖", duty: "职责同构度", nice: "加分项覆盖", constraint: "硬性条件符合",
};
export const STATE_LABEL = { pass: "满足", partial: "勉强", unknown: "未知", fail: "不满足" };
export const SOURCE_LABEL = { default: "默认位置", custom: "自定义位置", env: "环境变量指定" };

/* ---------------- 工具 ---------------- */

export function toast(message, kind = "") {
  const id = Date.now() + Math.random();
  state.toasts.push({ id, message, kind });
  setTimeout(() => {
    const i = state.toasts.findIndex((t) => t.id === id);
    if (i >= 0) state.toasts.splice(i, 1);
  }, kind === "err" ? 4200 : 2800);
}

export function chipOf(score) {
  const v = Number(score || 0);
  if (v >= 72) return "hi";
  if (v >= 55) return "mid";
  return "lo";
}

export function pct(v) {
  if (v === null || v === undefined) return "—";
  return Math.round(v * 100) + "%";
}

export function shortDate(s) {
  return (s || "").slice(0, 10);
}

/* ---------------- 加载 ---------------- */

export async function loadBoot() {
  const boot = await api.bootstrap();
  state.summary = boot.summary || {};
  state.profile = boot.profile || {};
  state.settings = boot.settings || {};
  state.bases = boot.bases || [];
}

export async function loadHealth() {
  state.health = await api.health();
}

export async function loadStats() {
  state.statsLoading = true;
  try {
    state.stats = await api.stats(2);
  } finally {
    state.statsLoading = false;
  }
}

export async function loadJobs() {
  state.jobsLoading = true;
  try {
    const data = await api.listJobs({
      q: state.jobQuery.trim(),
      status: state.jobStatus,
      sort: state.jobSort,
    });
    state.jobs = data.items || [];
  } finally {
    state.jobsLoading = false;
  }
}

export async function loadGaps() {
  state.gapsLoading = true;
  try {
    const data = await api.listGaps({ priority: state.gapPriority, status: state.gapStatus });
    state.gaps = data.items || [];
  } finally {
    state.gapsLoading = false;
  }
}

export async function loadBases() {
  const data = await api.listBases();
  state.bases = data.items || [];
}

export async function loadDataDir() {
  state.dataDir = await api.dataDir();
}

export async function loadCompanies() {
  state.companiesLoading = true;
  try {
    const data = await api.listCompanies();
    state.companies = data.items || [];
  } finally {
    state.companiesLoading = false;
  }
}

export function openEditor(id) {
  // 同窗口切到编辑器：它和台帐同源，返回链接直接回首页，不需要另开浏览器
  location.href = `/editor/?company=${id}`;
}

/* 通用简历：固定一份母版，第一次点入口时自动建档 */
export async function openGeneral() {
  const res = await api.generalResume();
  openEditor(res.company.id);
}

export async function openJob(id) {
  state.detailLoading = true;
  try {
    state.detail = await api.getJob(id);
  } finally {
    state.detailLoading = false;
  }
}

export function closeDetail() {
  state.detail = null;
}

/* 视图切换时的最小加载策略：只拉当前页需要的数据。 */
export async function switchView(name) {
  state.view = name;
  try {
    if (name === "dash") await loadStats();
    if (name === "jobs") await loadJobs();
    if (name === "gaps") await loadGaps();
    if (name === "bases") await loadBases();
    if (name === "settings") {
      await loadDataDir();
      await loadBoot();
    }
  } catch (err) {
    toast(err.message, "err");
  }
}

export async function refreshCurrent() {
  await loadBoot();
  await switchView(state.view);
}
