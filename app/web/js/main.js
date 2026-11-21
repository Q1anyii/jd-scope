/* 根组件：顶栏、侧栏、页面切换、提示堆叠。 */

import {
  state, toast, loadHealth, loadBoot, loadStats, loadDataDir, loadJobs, loadGaps, loadBases, loadCompanies, refreshCurrent,
} from "./store.js";
import { Dashboard } from "./pages/dashboard.js";
import { Intake } from "./pages/intake.js";
import { Jobs } from "./pages/jobs.js";
import { Gaps } from "./pages/gaps.js";
import { Bases } from "./pages/bases.js";
import { Companies } from "./pages/companies.js";
import { Profile } from "./pages/profile.js";
import { Settings } from "./pages/settings.js";

const { createApp, computed, onMounted } = window.Vue;

const NAV = [
  { key: "dash", label: "概览" },
  { key: "intake", label: "JD 入库" },
  { key: "jobs", label: "岗位", counter: "jobs" },
  { key: "gaps", label: "缺口库", counter: "gaps" },
  { key: "bases", label: "基底库", counter: "bases" },
  { key: "companies", label: "公司档案" },
  { key: "profile", label: "档案" },
  { key: "settings", label: "设置" },
];

const App = {
  setup() {
    const s = state;

    const counts = computed(() => ({
      jobs: s.summary.jobs || 0,
      gaps: s.summary.gaps_open || 0,
      bases: s.summary.bases || 0,
    }));

    const chips = computed(() => [
      { html: s.summary.jobs || 0, text: "岗位" },
      { html: s.summary.bases || 0, text: "基底" },
      { html: s.summary.gaps_open || 0, text: "待补缺口" },
      { html: s.summary.avg_score || 0, text: "平均分" },
      {
        html: s.summary.reply_rate === null || s.summary.reply_rate === undefined ? "—" : s.summary.reply_rate + "%",
        text: "回复率",
      },
    ]);

    // 侧栏只显示路径末两段：完整路径在小字里没有信息量，反而挤成一团
    const homeTail = computed(() => {
      const home = (s.dataDir && s.dataDir.home) || "";
      if (!home) return "数据目录读取中…";
      const parts = home.split(/[\\\\/]/).filter(Boolean);
      return parts.slice(-2).join("/");
    });

    const go = (key) => {
      if (key === s.view && key !== "dash") return;
      s.view = key;
      if (key !== "jobs") s.detail = null;
      if (key === "dash") loadStats().catch((e) => toast(e.message, "err"));
      if (key === "jobs") loadJobs().catch((e) => toast(e.message, "err"));
      if (key === "gaps") loadGaps().catch((e) => toast(e.message, "err"));
      if (key === "bases") loadBases().catch((e) => toast(e.message, "err"));
      if (key === "companies") loadCompanies().catch((e) => toast(e.message, "err"));
      if (key === "settings") {
        loadDataDir().catch((e) => toast(e.message, "err"));
        loadBoot().catch((e) => toast(e.message, "err"));
      }
    };

    const dismissSplash = () => {
      const splash = document.getElementById("boot-splash");
      if (!splash) return;
      splash.classList.add("hide");
      setTimeout(() => splash.remove(), 320);
    };

    const refresh = async () => {
      await refreshCurrent();
      toast("已刷新", "ok");
    };

    onMounted(async () => {
      const wanted = new URLSearchParams(location.search).get("view");
      try {
        await loadHealth();
        await loadBoot();
        await loadStats();
        await loadDataDir();
        s.ready = true;
        if (wanted && NAV.some((n) => n.key === wanted) && wanted !== "dash") go(wanted);
      } catch (err) {
        toast("启动失败：" + err.message, "err");
      } finally {
        dismissSplash();
      }
    });

    return { s, NAV, counts, chips, homeTail, go, refresh };
  },
  template: `
  <div>
    <header class="topbar">
      <div class="brand">
        <svg width="21" height="21" viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="10.5" cy="10.5" r="6.3" fill="none" stroke="currentColor" stroke-width="2.1"/>
          <path d="M15.3 15.3 L20.2 20.2" stroke="currentColor" stroke-width="2.1" stroke-linecap="round"/>
          <path d="M7.6 9.2h5.7M7.6 11.7h3.9" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" opacity=".7"/>
        </svg>
        <span class="brand-name">JDScope</span>
        <span class="brand-sub">岗位 JD 透视 · 简历缺口台账</span>
      </div>
      <div class="chips">
        <span class="chip" v-for="c in chips" :key="c.text"><b>{{ c.html }}</b> {{ c.text }}</span>
      </div>
      <div class="top-actions">
        <button class="ghost" @click="refresh" title="重新拉取数据">刷新</button>
      </div>
    </header>

    <aside class="rail">
      <div class="rail-group">工作台</div>
      <button class="nav" v-for="item in NAV" :key="item.key"
              :class="{active: s.view === item.key}" @click="go(item.key)">
        <span class="dot"></span>
        <span>{{ item.label }}</span>
        <span class="nav-count" v-if="item.counter && counts[item.counter]">{{ counts[item.counter] }}</span>
      </button>
      <div class="rail-foot">
        <div class="path" :title="s.dataDir ? s.dataDir.home : ''">{{ homeTail }}</div>
      </div>
    </aside>

    <main class="main">
      <dashboard v-if="s.view === 'dash'"></dashboard>
      <intake v-else-if="s.view === 'intake'"></intake>
      <jobs-page v-else-if="s.view === 'jobs'"></jobs-page>
      <gaps-page v-else-if="s.view === 'gaps'"></gaps-page>
      <bases-page v-else-if="s.view === 'bases'"></bases-page>
      <companies-page v-else-if="s.view === 'companies'"></companies-page>
      <profile-page v-else-if="s.view === 'profile'"></profile-page>
      <settings-page v-else-if="s.view === 'settings'"></settings-page>
    </main>

    <div class="toasts">
      <div class="toast" v-for="t in s.toasts" :key="t.id" :class="t.kind">{{ t.message }}</div>
    </div>
  </div>`,
};

const app = createApp(App);
app.component("dashboard", Dashboard);
app.component("intake", Intake);
app.component("jobs-page", Jobs);
app.component("gaps-page", Gaps);
app.component("bases-page", Bases);
app.component("companies-page", Companies);
app.component("profile-page", Profile);
app.component("settings-page", Settings);
app.mount("#app");
