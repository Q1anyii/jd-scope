/* 岗位：筛选、排序、批量重算，详情以右侧抽屉展开。 */

import { api } from "../api.js";
import {
  state, toast, chipOf, pct, shortDate, STATUS_LABEL, DIM_LABEL, STATE_LABEL, PRIO_LABEL,
  loadJobs, loadBoot, openJob, closeDetail, openEditor,
} from "../store.js";

const { computed, ref, watch, onMounted, onBeforeUnmount } = window.Vue;

export const Jobs = {
  name: "jobs",
  setup() {
    const s = state;
    const report = ref(null);
    const busy = ref({ analyze: false, suggest: false, export: false, batch: 0, company: false, edit: false });
    const editing = ref(false);
    const form = ref({ company: "", title: "", city: "", source: "", url: "" });

    let timer = null;
    watch(() => s.jobQuery, () => {
      clearTimeout(timer);
      timer = setTimeout(() => loadJobs().catch((e) => toast(e.message, "err")), 260);
    });
    watch(() => [s.jobStatus, s.jobSort], () => loadJobs().catch((e) => toast(e.message, "err")));

    const missingOf = (job) => {
      const cov = (job.score_json && job.score_json.coverage) || {};
      return (cov.missing || []).length;
    };

    const dimList = computed(() => {
      const d = (s.detail && s.detail.score && s.detail.score.dims) || {};
      return Object.keys(DIM_LABEL).map((k) => ({ key: k, label: DIM_LABEL[k], value: d[k] }));
    });

    const reqGroups = computed(() => {
      const reqs = (s.detail && s.detail.requirements) || [];
      return ["must", "duty", "nice"].map((cat) => ({
        cat,
        label: { must: "必备要求", duty: "岗位职责", nice: "加分项" }[cat],
        items: reqs.filter((r) => r.category === cat),
      })).filter((g) => g.items.length);
    });

    const coverage = computed(() => {
      const cov = (s.detail && s.detail.score && s.detail.score.coverage) || {};
      return {
        covered: cov.covered || [],
        partial: cov.partial || [],
        missing: cov.missing || [],
      };
    });

    const setStatus = async (value) => {
      try {
        await api.updateJob(s.detail.job.id, { status: value });
        s.detail.job.status = value;
        toast("状态已更新", "ok");
        await loadBoot();
        await loadJobs();
      } catch (err) { toast(err.message, "err"); }
    };

    const startEdit = () => {
      const job = s.detail.job;
      form.value = {
        company: job.company || "",
        title: job.title || "",
        city: job.city || "",
        source: job.source || "",
        url: job.url || "",
      };
      editing.value = true;
    };

    const cancelEdit = () => { editing.value = false; };

    const toggleEdit = () => { if (editing.value) editing.value = false; else startEdit(); };

    const saveEdit = async () => {
      const id = s.detail.job.id;
      const f = form.value;
      if (!f.company.trim() || !f.title.trim()) {
        toast("公司名和岗位名不能为空", "err");
        return;
      }
      busy.value.edit = true;
      try {
        await api.updateJob(id, {
          company: f.company.trim(),
          title: f.title.trim(),
          city: f.city.trim(),
          source: f.source.trim(),
          url: f.url.trim(),
        });
        editing.value = false;
        await openJob(id);
        await loadJobs();
        await loadBoot();
        toast("岗位信息已更新", "ok");
      } catch (err) { toast(err.message, "err"); }
      finally { busy.value.edit = false; }
    };

    const reanalyze = async () => {
      const id = s.detail.job.id;
      busy.value.analyze = true;
      try {
        await api.analyzeJob(id);
        await openJob(id);
        await loadJobs();
        toast("已重算", "ok");
      } catch (err) { toast(err.message, "err"); }
      finally { busy.value.analyze = false; }
    };

    const reanalyzeAll = async () => {
      if (!s.jobs.length) return;
      if (!confirm(`对当前列表的 ${s.jobs.length} 个岗位逐个重算？缺口的人工进度会保留。`)) return;
      busy.value.batch = s.jobs.length;
      let done = 0;
      for (const job of s.jobs) {
        try { await api.analyzeJob(job.id); } catch (err) { /* 单条失败不阻断 */ }
        done += 1;
        busy.value.batch = s.jobs.length - done;
      }
      busy.value.batch = 0;
      await loadJobs();
      await loadBoot();
      toast(`已重算 ${done} 个岗位`, "ok");
    };

    const suggest = async () => {
      const id = s.detail.job.id;
      busy.value.suggest = true;
      toast("正在请求模型，可能十几秒…");
      try {
        const out = await api.suggest(id);
        toast(`生成 ${out.items.length} 条建议`, "ok");
        await openJob(id);
      } catch (err) { toast(err.message, "err"); }
      finally { busy.value.suggest = false; }
    };

    const exportReport = async () => {
      busy.value.export = true;
      try {
        const out = await api.exportJob(s.detail.job.id);
        report.value = out;
        toast("报告已写入数据目录", "ok");
      } catch (err) { toast(err.message, "err"); }
      finally { busy.value.export = false; }
    };

    const remove = async () => {
      if (!confirm("删除这条岗位，连同它的需求、缺口与建议？")) return;
      try {
        await api.deleteJob(s.detail.job.id);
        closeDetail();
        await loadBoot();
        await loadJobs();
        toast("已删除", "ok");
      } catch (err) { toast(err.message, "err"); }
    };

    /* 一条龙入口：这份 JD 已经有公司档案就直接打开编辑器，没有就先建档（带 JD / 策略 / 报告） */
    const makeCompany = async () => {
      if (!s.detail) return;
      const job = s.detail.job;
      busy.value.company = true;
      try {
        const list = await api.listCompanies();
        const found = (list.items || []).find((c) => c.job_id === job.id);
        if (found) { openEditor(found.id); return; }
        const res = await api.createCompany({
          name: job.company,
          job_id: job.id,
          base_id: job.base_id || null,
        });
        toast(`已建档：${res.company.folder}`, "ok");
        openEditor(res.company.id);
      } catch (err) { toast(err.message, "err"); }
      finally { busy.value.company = false; }
    };

    const adopt = async (sug) => {
      try {
        await api.adoptSuggestion(sug.id, !sug.adopted);
        sug.adopted = sug.adopted ? 0 : 1;
      } catch (err) { toast(err.message, "err"); }
    };

    const open = async (id) => {
      report.value = null;
      editing.value = false;
      try { await openJob(id); } catch (err) { toast(err.message, "err"); }
    };

    const onKey = (e) => { if (e.key === "Escape" && s.detail) closeDetail(); };
    onMounted(() => {
      document.addEventListener("keydown", onKey);
      // 支持 ?job=<id> 直接打开某条岗位，便于从外部跳转与排查
      const wanted = new URLSearchParams(location.search).get("job");
      if (wanted && /^\d+$/.test(wanted)) open(Number(wanted));
    });
    onBeforeUnmount(() => document.removeEventListener("keydown", onKey));

    return {
      s, report, busy, editing, form, missingOf, dimList, reqGroups, coverage,
      STATUS_LABEL, PRIO_LABEL, STATE_LABEL, chipOf, pct, shortDate,
      setStatus, startEdit, cancelEdit, toggleEdit, saveEdit,
      reanalyze, reanalyzeAll, suggest, exportReport, remove, adopt, open, closeDetail,
      makeCompany,
    };
  },
  template: `
  <div>
    <div class="view-head">
      <h1>岗位</h1>
      <p>点一行打开详情：四维得分、逐条命中证据、缺口、改写建议。列表按匹配度排序，也可以改回录入顺序。</p>
    </div>

    <div class="panel">
      <div class="pad-18">
        <div class="row-gap">
          <input class="grow" v-model="s.jobQuery" placeholder="搜公司 / 岗位">
          <select v-model="s.jobStatus" style="width:140px">
            <option value="">全部状态</option>
            <option v-for="(label, key) in STATUS_LABEL" :key="key" :value="key">{{ label }}</option>
          </select>
          <select v-model="s.jobSort" style="width:150px">
            <option value="score">匹配度从高到低</option>
            <option value="score_asc">匹配度从低到高</option>
            <option value="newest">最近录入</option>
            <option value="oldest">最早录入</option>
          </select>
          <button class="ghost" @click="reanalyzeAll" :disabled="busy.batch > 0 || !s.jobs.length">
            {{ busy.batch > 0 ? '重算中 ' + busy.batch + ' 条' : '批量重算' }}
          </button>
        </div>
      </div>

      <div class="table-wrap">
        <table>
          <thead>
            <tr><th>公司 / 岗位</th><th>城市</th><th>匹配度</th><th>判定</th><th>缺失项</th><th>状态</th><th>录入</th></tr>
          </thead>
          <tbody>
            <tr v-for="job in s.jobs" :key="job.id" class="clickable"
                :class="{'active-row': s.detail && s.detail.job.id === job.id}" @click="open(job.id)">
              <td><strong>{{ job.company }}</strong><div class="hint">{{ job.title }}</div></td>
              <td>{{ job.city || '—' }}</td>
              <td><span class="score" :class="chipOf(job.score)">{{ job.score }}</span></td>
              <td>
                <span class="badge" :class="job.verdict === '建议投' ? 'ok' : job.verdict === '不建议投' ? 'bad' : 'warn'">
                  {{ job.verdict || '—' }}
                </span>
              </td>
              <td><span class="badge" :class="missingOf(job) ? 'bad' : 'ok'">{{ missingOf(job) }}</span></td>
              <td>{{ STATUS_LABEL[job.status] || job.status }}</td>
              <td class="muted">{{ shortDate(job.created_at) }}</td>
            </tr>
            <tr v-if="!s.jobs.length">
              <td colspan="7"><div class="empty">
                <svg width="46" height="46" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4">
                  <rect x="3" y="4" width="18" height="16" rx="3"/><path d="M7 9h10M7 13h6M7 17h4"/>
                </svg>
                {{ s.jobQuery || s.jobStatus ? '这个筛选条件下没有岗位' : '还没有岗位，先去「JD 入库」录一条' }}
              </div></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <Teleport to="body">
      <div class="backdrop" v-if="s.detail" @click.self="closeDetail"></div>
      <div class="drawer" v-if="s.detail">
        <div class="drawer-head">
          <div>
            <h2>{{ s.detail.job.company }} · {{ s.detail.job.title }}</h2>
            <div class="sub">
              城市 {{ s.detail.job.city || '—' }} ｜ 来源 {{ s.detail.job.source || '—' }} ｜
              基底 {{ s.detail.base ? s.detail.base.code : '未选' }} ｜ 录入 {{ shortDate(s.detail.job.created_at) }}
            </div>
          </div>
          <button class="drawer-close" @click="closeDetail" title="关闭（Esc）">×</button>
        </div>

        <div class="drawer-body">
          <div v-if="editing" class="edit-panel">
            <div class="section-title" style="margin-top:0">修改岗位信息</div>
            <div class="form-grid">
              <label class="field">公司名
                <input v-model="form.company" placeholder="公司名称">
              </label>
              <label class="field">岗位名
                <input v-model="form.title" placeholder="如 AI 应用开发工程师">
              </label>
              <label class="field">城市
                <input v-model="form.city" placeholder="如 杭州">
              </label>
              <label class="field">来源
                <input v-model="form.source" placeholder="官网 / BOSS / 内推">
              </label>
              <label class="field span2">链接
                <input v-model="form.url" placeholder="岗位链接（可选）">
              </label>
            </div>
            <div class="row-gap" style="margin-top:12px">
              <button class="primary" @click="saveEdit" :disabled="busy.edit">{{ busy.edit ? '保存中…' : '保存修改' }}</button>
              <button class="ghost" @click="cancelEdit" :disabled="busy.edit">取消</button>
              <span class="hint">只改元信息，不会重算 JD 需求；改岗位名不会重命名已建的公司文件夹。</span>
            </div>
          </div>

          <div class="dims">
            <div class="dim" v-for="d in dimList" :key="d.key">
              <div class="k">{{ d.label }}</div>
              <div class="v">{{ pct(d.value) }}</div>
              <div class="track"><div class="fill" :style="'width:' + Math.round((d.value || 0) * 100) + '%'"></div></div>
            </div>
          </div>

          <div class="row-gap" style="margin-top:14px">
            <span class="score" :class="chipOf(s.detail.job.score)">{{ s.detail.job.score }}</span>
            <span class="badge" :class="s.detail.job.verdict === '建议投' ? 'ok' : s.detail.job.verdict === '不建议投' ? 'bad' : 'warn'">
              {{ s.detail.job.verdict }}
            </span>
            <span class="hint">{{ s.detail.score.verdict_reason || (s.detail.score.criteria || [])[0] || '' }}</span>
          </div>

          <div class="row-gap mt12">
            <button class="ghost" @click="toggleEdit">{{ editing ? '收起编辑' : '编辑信息' }}</button>
            <select :value="s.detail.job.status" style="width:132px" @change="setStatus($event.target.value)">
              <option v-for="(label, key) in STATUS_LABEL" :key="key" :value="key">{{ label }}</option>
            </select>
            <button class="ghost" @click="reanalyze" :disabled="busy.analyze">{{ busy.analyze ? '重算中…' : '重算' }}</button>
            <button class="ghost" @click="suggest" :disabled="busy.suggest">{{ busy.suggest ? '生成中…' : '生成改写建议' }}</button>
            <button class="ghost" @click="makeCompany" :disabled="busy.company" title="建公司档案并打开简历编辑器">
              {{ busy.company ? '准备中…' : '建公司档案 / 改简历' }}
            </button>
            <button class="primary" @click="exportReport" :disabled="busy.export">{{ busy.export ? '导出中…' : '导出报告' }}</button>
            <button class="danger" @click="remove">删除</button>
          </div>

          <div class="section-title" v-if="(s.detail.constraints || []).length">硬性条件</div>
          <table v-if="(s.detail.constraints || []).length">
            <thead><tr><th>条件</th><th>状态</th><th>说明</th></tr></thead>
            <tbody>
              <tr v-for="(c, i) in s.detail.constraints" :key="i">
                <td>{{ c.text || c.value || c.kind }}</td>
                <td><span class="badge" :class="c.state === 'pass' ? 'ok' : c.state === 'fail' ? 'bad' : 'warn'">{{ STATE_LABEL[c.state] || c.state }}</span></td>
                <td class="muted">{{ c.note || '' }}</td>
              </tr>
            </tbody>
          </table>

          <div class="section-title">关键词覆盖</div>
          <div class="row-gap">
            <span class="badge ok">命中 {{ coverage.covered.length }}</span>
            <span class="badge warn">部分 {{ coverage.partial.length }}</span>
            <span class="badge bad">缺失 {{ coverage.missing.length }}</span>
          </div>
          <div class="row-gap mt8">
            <span class="badge ok" v-for="t in coverage.covered" :key="'c-' + t">{{ t }}</span>
            <span class="badge warn" v-for="t in coverage.partial" :key="'p-' + t">{{ t }}</span>
            <span class="badge bad" v-for="t in coverage.missing" :key="'m-' + t">{{ t }}</span>
          </div>

          <div v-for="g in reqGroups" :key="g.cat">
            <div class="section-title">{{ g.label }}（{{ g.items.length }}）</div>
            <div class="req-row" v-for="r in g.items" :key="r.id">
              <div>
                <span class="badge" :class="r.hit === 2 ? 'ok' : r.hit === 1 ? 'warn' : 'bad'">
                  {{ r.hit === 2 ? '命中' : r.hit === 1 ? '部分' : '缺失' }}
                </span>
              </div>
              <div>
                <div class="txt">{{ r.text }} <span class="badge plain" v-if="r.source === 'ai'">AI</span></div>
                <div class="ev">{{ r.evidence || '' }}</div>
              </div>
            </div>
          </div>

          <div class="section-title">缺口（{{ (s.detail.gaps || []).length }}）</div>
          <table v-if="(s.detail.gaps || []).length">
            <thead><tr><th>优先级</th><th>JD 要求</th><th>差在哪</th><th>补课方向</th></tr></thead>
            <tbody>
              <tr v-for="g in s.detail.gaps" :key="g.id">
                <td><span class="badge" :class="g.priority">{{ PRIO_LABEL[g.priority] || g.priority }}</span></td>
                <td>{{ g.requirement }}</td>
                <td class="muted">{{ g.gap }}</td>
                <td class="muted">{{ g.action }}</td>
              </tr>
            </tbody>
          </table>
          <p class="hint" v-else>没有发现明确缺口。</p>

          <div class="section-title">改写建议（{{ (s.detail.suggestions || []).length }}）</div>
          <div v-if="(s.detail.suggestions || []).length">
            <div class="sug" v-for="sug in s.detail.suggestions" :key="sug.id">
              <div class="ori">{{ sug.original }}</div>
              <div class="new">{{ sug.suggestion }}</div>
              <div class="why">{{ sug.reason }}</div>
              <div class="ops">
                <span class="badge" :class="sug.adopted ? 'ok' : 'low'">{{ sug.adopted ? '已采用' : '未采用' }}</span>
                <button class="mini" :class="{on: sug.adopted}" @click="adopt(sug)">{{ sug.adopted ? '取消采用' : '标记采用' }}</button>
              </div>
            </div>
          </div>
          <p class="hint" v-else>尚未生成。需要先在「设置」里配置模型端点；建议只改表达、不动事实。</p>

          <div v-if="report">
            <div class="section-title">已生成报告</div>
            <p class="hint mono">{{ report.path }}</p>
            <pre class="raw" style="max-height:420px">{{ report.markdown }}</pre>
          </div>

          <div class="section-title">原始 JD</div>
          <pre class="raw">{{ s.detail.job.jd_raw }}</pre>
        </div>
      </div>
    </Teleport>
  </div>`,
};
