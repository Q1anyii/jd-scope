/* 与本地服务通信。所有请求同源打到 127.0.0.1，数据不出本机。 */

async function request(path, { method = "GET", body = null } = {}) {
  const init = { method, headers: { "Content-Type": "application/json" } };
  if (body !== null) init.body = JSON.stringify(body);
  let res;
  try {
    res = await fetch(path, init);
  } catch (err) {
    throw new Error("连不上本地服务，窗口可能已关闭");
  }
  let data = null;
  try { data = await res.json(); } catch (err) { data = { error: "响应不是 JSON" }; }
  if (!res.ok || (data && data.error)) {
    throw new Error((data && data.error) || `请求失败 ${res.status}`);
  }
  return data;
}

const qs = (obj) => {
  const p = new URLSearchParams();
  Object.entries(obj).forEach(([k, v]) => { if (v !== "" && v !== null && v !== undefined) p.set(k, v); });
  const text = p.toString();
  return text ? "?" + text : "";
};

export const api = {
  health: () => request("/api/health"),
  bootstrap: () => request("/api/bootstrap"),

  getProfile: () => request("/api/profile"),
  saveProfile: (profile) => request("/api/profile", { method: "POST", body: profile }),

  listBases: () => request("/api/bases"),
  createBase: (payload) => request("/api/bases", { method: "POST", body: payload }),
  deleteBase: (id) => request(`/api/bases/${id}`, { method: "DELETE" }),

  parseJd: (payload) => request("/api/jobs/parse", { method: "POST", body: payload }),
  parseJdAi: (payload) => request("/api/jobs/parse-ai", { method: "POST", body: payload }),
  createJob: (payload) => request("/api/jobs", { method: "POST", body: payload }),
  listJobs: (filters) => request("/api/jobs" + qs(filters)),
  getJob: (id) => request(`/api/jobs/${id}`),
  updateJob: (id, payload) => request(`/api/jobs/${id}`, { method: "PATCH", body: payload }),
  deleteJob: (id) => request(`/api/jobs/${id}`, { method: "DELETE" }),
  analyzeJob: (id) => request(`/api/jobs/${id}/analyze`, { method: "POST", body: {} }),
  exportJob: (id) => request(`/api/jobs/${id}/export`, { method: "POST", body: {} }),
  suggest: (id) => request(`/api/jobs/${id}/suggest`, { method: "POST", body: { module: "整体" } }),

  listGaps: (filters) => request("/api/gaps" + qs(filters)),
  updateGap: (id, payload) => request(`/api/gaps/${id}`, { method: "PATCH", body: payload }),
  answerGap: (id) => request(`/api/gaps/${id}/answer`, { method: "POST", body: {} }),

  saveSettings: (payload) => request("/api/settings", { method: "POST", body: payload }),
  testLlm: (payload) => request("/api/llm/test", { method: "POST", body: payload }),
  adoptSuggestion: (id, adopted) => request(`/api/suggestions/${id}/adopt`, { method: "POST", body: { adopted } }),

  stats: (minJobs = 2) => request(`/api/stats?min_jobs=${minJobs}`),

  dataDir: () => request("/api/data-dir"),
  setDataDir: (path, migrate) => request("/api/data-dir", { method: "POST", body: { path, migrate } }),
  resetDataDir: (migrate) => request("/api/data-dir/reset", { method: "POST", body: { migrate } }),
  openDataDir: () => request("/api/data-dir/open", { method: "POST", body: {} }),

  listCompanies: () => request("/api/companies"),
  generalResume: () => request("/api/resume/general", { method: "POST", body: {} }),
  createCompany: (payload) => request("/api/companies", { method: "POST", body: payload }),
  getCompany: (id) => request(`/api/companies/${id}`),
  deleteCompany: (id) => request(`/api/companies/${id}`, { method: "DELETE" }),
  saveCompanyStrategy: (id, text) => request(`/api/companies/${id}/strategy`, { method: "POST", body: { text } }),
  openCompanyFolder: (id) => request(`/api/companies/${id}/open`, { method: "POST", body: {} }),
  companyResume: (id) => request(`/api/companies/${id}/resume`),
};
