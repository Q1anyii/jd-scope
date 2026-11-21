/* 设置：数据位置（可自定义）、模型端点、评分权重。 */

import { api } from "../api.js";
import { state, toast, loadBoot, loadDataDir, loadStats, SOURCE_LABEL } from "../store.js";

const { reactive, ref, computed, watch } = window.Vue;

const fmtBytes = (n) => {
  if (!n) return "0 B";
  if (n < 1024) return n + " B";
  if (n < 1024 * 1024) return (n / 1024).toFixed(1) + " KB";
  return (n / 1024 / 1024).toFixed(1) + " MB";
};

export const Settings = {
  name: "settings",
  setup() {
    const s = state;

    const llm = reactive({ base_url: "", model: "", api_key: "" });
    const weights = reactive({ must: 30, duty: 30, nice: 15, constraint: 25 });
    const prompts = reactive({ jd_analysis: "", resume_rewrite: "" });
    const promptDefaults = reactive({ jd_analysis: "", resume_rewrite: "" });
    const promptSaved = reactive({ jd_analysis: "", resume_rewrite: "" });
    const promptTab = ref("jd_analysis");
    const promptTabs = [
      { key: "jd_analysis", label: "JD 分析提示词" },
      { key: "resume_rewrite", label: "简历改写提示词" },
    ];
    const busy = ref({ save: false, test: false, weights: false, prompts: false, dir: false, reset: false });
    const testHint = ref("");
    const modal = reactive({ open: false, path: "", migrate: true, error: "", note: "" });
    const canBrowse = ref(false);

    const sync = () => {
      const cfg = s.settings || {};
      llm.base_url = cfg.base_url || "";
      llm.model = cfg.model || "";
      llm.api_key = "";
      const w = cfg.weights || {};
      weights.must = w.must ?? 30;
      weights.duty = w.duty ?? 30;
      weights.nice = w.nice ?? 15;
      weights.constraint = w.constraint ?? 25;
      const p = cfg.prompts || {};
      const d = cfg.prompt_defaults || {};
      for (const key of ["jd_analysis", "resume_rewrite"]) {
        promptDefaults[key] = d[key] || "";
        promptSaved[key] = (p[key] || "").trim();
        prompts[key] = promptSaved[key] || promptDefaults[key];
      }
    };
    sync();
    watch(() => s.settings, sync);

    const weightTotal = computed(() => {
      const n = ["must", "duty", "nice", "constraint"].reduce((acc, k) => acc + Number(weights[k] || 0), 0);
      return Math.round(n * 10) / 10;
    });

    const promptDirty = computed(() => promptTabs.some(({ key }) =>
      (prompts[key] || "").trim() !== (promptSaved[key] || promptDefaults[key] || "").trim()
    ));

    const promptStatus = (key) => {
      const cur = (prompts[key] || "").trim();
      const def = (promptDefaults[key] || "").trim();
      return cur && cur !== def
        ? { text: "自定义", cls: "ok" }
        : { text: "默认", cls: "plain" };
    };

    const saveLlm = async () => {
      busy.value.save = true;
      try {
        await api.saveSettings({ base_url: llm.base_url.trim(), model: llm.model.trim(), api_key: llm.api_key.trim() });
        await loadBoot();
        toast("模型设置已保存", "ok");
      } catch (err) { toast(err.message, "err"); }
      finally { busy.value.save = false; }
    };

    const testLlm = async () => {
      busy.value.test = true;
      testHint.value = "测试中…";
      try {
        const out = await api.testLlm({ base_url: llm.base_url.trim(), model: llm.model.trim(), api_key: llm.api_key.trim() });
        testHint.value = out.ok ? "连通：" + out.reply : "失败：" + (out.error || "未知原因");
      } catch (err) { testHint.value = "失败：" + err.message; }
      finally { busy.value.test = false; }
    };

    const saveWeights = async () => {
      busy.value.weights = true;
      try {
        await api.saveSettings({
          weights: {
            must: Number(weights.must || 0), duty: Number(weights.duty || 0),
            nice: Number(weights.nice || 0), constraint: Number(weights.constraint || 0),
          },
        });
        await loadBoot();
        toast("权重已保存，记得对岗位点「重算」", "ok");
      } catch (err) { toast(err.message, "err"); }
      finally { busy.value.weights = false; }
    };

    /* ---- 模型提示词 ---- */
    const fillPromptDefault = (key) => {
      prompts[key] = promptDefaults[key] || "";
    };

    const savePrompts = async () => {
      busy.value.prompts = true;
      try {
        const payload = {};
        for (const key of ["jd_analysis", "resume_rewrite"]) {
          const cur = (prompts[key] || "").trim();
          const def = (promptDefaults[key] || "").trim();
          // 与默认一致就传空值，让后端清掉自定义覆盖
          payload[key] = cur === def ? "" : cur;
        }
        await api.saveSettings({ prompts: payload });
        await loadBoot();
        toast("提示词已保存", "ok");
      } catch (err) { toast(err.message, "err"); }
      finally { busy.value.prompts = false; }
    };

    /* ---- 数据位置 ---- */
    const dataInfo = computed(() => s.dataDir || {});
    const sourceLabel = computed(() => SOURCE_LABEL[dataInfo.value.source] || "—");
    const locked = computed(() => !!dataInfo.value.env_locked);

    const openModal = () => {
      modal.path = dataInfo.value.home || "";
      modal.migrate = true;
      modal.error = "";
      modal.note = "";
      modal.open = true;
      canBrowse.value = !!(window.pywebview && window.pywebview.api && window.pywebview.api.choose_folder);
    };

    const browse = async () => {
      try {
        const picked = await window.pywebview.api.choose_folder(modal.path || "");
        if (picked) modal.path = picked;
      } catch (err) {
        modal.note = "系统选择器不可用，请直接粘贴路径";
      }
    };

    const switchDir = async () => {
      modal.error = "";
      const target = (modal.path || "").trim();
      if (!target) { modal.error = "请填写目录路径"; return; }
      busy.value.dir = true;
      try {
        const out = await api.setDataDir(target, modal.migrate);
        modal.open = false;
        await loadDataDir();
        await loadBoot();
        await loadStats();
        const extra = out.adopted
          ? "，已接管该目录里已有的数据"
          : out.copied_files ? `，迁移 ${out.copied_files} 个文件` : "";
        toast("数据位置已切换" + extra, "ok");
      } catch (err) { modal.error = err.message; }
      finally { busy.value.dir = false; }
    };

    const resetDir = async () => {
      if (!confirm("切回默认数据目录？当前目录里的数据不会被删除。")) return;
      busy.value.reset = true;
      try {
        const out = await api.resetDataDir(true);
        await loadDataDir();
        await loadBoot();
        await loadStats();
        const extra = out.adopted ? "，已接管默认目录里的旧数据" : out.copied_files ? `，复制 ${out.copied_files} 个文件` : "";
        toast("已切回默认位置" + extra, "ok");
      } catch (err) { toast(err.message, "err"); }
      finally { busy.value.reset = false; }
    };

    const openFolder = async () => {
      try { await api.openDataDir(); }
      catch (err) { toast(err.message, "err"); }
    };

    return {
      s, llm, weights, busy, testHint, modal, canBrowse, weightTotal,
      dataInfo, sourceLabel, locked, fmtBytes,
      prompts, promptDefaults, promptTab, promptTabs, promptDirty, promptStatus,
      saveLlm, testLlm, saveWeights, savePrompts, fillPromptDefault,
      openModal, browse, switchDir, resetDir, openFolder,
    };
  },
  template: `
  <div>
    <div class="view-head">
      <h1>设置</h1>
      <p>模型是可选的：不配置也能用，解析、评分、缺口、聚合全部在本地完成。数据位置可以改到任意盘。</p>
    </div>

    <!-- 数据位置 -->
    <div class="panel">
      <div class="panel-head">
        <h2>数据位置</h2>
        <span class="badge" :class="locked ? 'warn' : (dataInfo.source === 'custom' ? 'ok' : 'plain')">{{ sourceLabel }}</span>
        <span class="hint">数据库、报告、备份都在这里；换机器或备份都是整目录搬运</span>
      </div>
      <div class="pad-18">
        <div class="row-gap">
          <input class="grow mono" :value="dataInfo.home || ''" readonly>
          <button class="ghost" @click="openFolder">打开文件夹</button>
        </div>
        <div class="row-gap mt8">
          <span class="hint">当前库 {{ dataInfo.has_db ? fmtBytes(dataInfo.db_bytes) : '尚未建立' }}</span>
          <span class="hint" v-if="locked">已由环境变量 JDSCOPE_HOME 指定，界面内不可更改</span>
        </div>
        <div class="row-gap mt12">
          <button class="primary" @click="openModal" :disabled="locked">更改位置</button>
          <button class="ghost" @click="resetDir" :disabled="locked || dataInfo.source === 'default'"
                  :title="dataInfo.source === 'default' ? '已经在默认位置' : ''">恢复默认</button>
        </div>
        <p class="hint mt8">切换只会改指针：选空目录时默认把现有数据库与报告迁过去；选已有库的目录会直接接管，不会覆盖。</p>
      </div>
    </div>

    <!-- 模型 -->
    <div class="panel">
      <div class="panel-head">
        <h2>模型端点</h2>
        <span class="hint">OpenAI 兼容协议，Key 只存本机</span>
      </div>
      <div class="pad-18">
        <div class="form-grid">
          <label class="field">BASE_URL<input v-model="llm.base_url" placeholder="https://api.deepseek.com/v1"></label>
          <label class="field">模型<input v-model="llm.model" placeholder="deepseek-chat"></label>
          <label class="field span2">API Key<input v-model="llm.api_key" type="password" placeholder="留空表示不修改已保存的 Key"></label>
        </div>
        <div class="row-gap mt12">
          <button class="primary" @click="saveLlm" :disabled="busy.save">{{ busy.save ? '保存中…' : '保存' }}</button>
          <button class="ghost" @click="testLlm" :disabled="busy.test">{{ busy.test ? '测试中…' : '测试连通' }}</button>
          <span class="hint">{{ testHint }}</span>
        </div>
        <p class="hint">模型只负责「出候选」：JD 解析的条目要你勾选才入库，改写建议与面试口径要你点「采用」才写台账；不配置也能用规则解析。</p>

        <!-- 提示词：两类任务分开编辑，各自在固定高度内滚动 -->
        <div class="prompt-block">
          <div class="row-between">
            <div class="prompt-tabs" role="tablist">
              <button v-for="tab in promptTabs" :key="tab.key" type="button"
                      class="prompt-tab" :class="{ on: promptTab === tab.key }"
                      @click="promptTab = tab.key">{{ tab.label }}</button>
            </div>
            <span class="badge" :class="promptStatus(promptTab).cls">{{ promptStatus(promptTab).text }}</span>
          </div>
          <p class="hint mt8">可改提示词但不改输出协议：必须保留「只输出 JSON」和对应字段名，否则解析会失败。留空即用内置默认。</p>

          <div v-show="promptTab === 'jd_analysis'" class="prompt-pane">
            <textarea v-model="prompts.jd_analysis" class="prompt-editor mono" spellcheck="false"
                      maxlength="20000" placeholder="JD 分析提示词"></textarea>
            <div class="prompt-foot">
              <span class="hint">用于「JD 入库」页的 AI 解析；条目只是候选，勾选才入库。{{ (prompts.jd_analysis || '').length }} / 20000</span>
              <button class="ghost" type="button" @click="fillPromptDefault('jd_analysis')">填入默认</button>
            </div>
          </div>

          <div v-show="promptTab === 'resume_rewrite'" class="prompt-pane">
            <textarea v-model="prompts.resume_rewrite" class="prompt-editor mono" spellcheck="false"
                      maxlength="20000" placeholder="简历改写提示词"></textarea>
            <div class="prompt-foot">
              <span class="hint">用于岗位详情「生成改写建议」；只改表达、不动事实。{{ (prompts.resume_rewrite || '').length }} / 20000</span>
              <button class="ghost" type="button" @click="fillPromptDefault('resume_rewrite')">填入默认</button>
            </div>
          </div>

          <div class="row-gap mt12">
            <button class="primary" type="button" @click="savePrompts" :disabled="busy.prompts">
              {{ busy.prompts ? '保存中…' : '保存提示词' }}
            </button>
            <span class="badge warn" v-if="promptDirty">有未保存修改</span>
            <span class="hint">编辑器里的 AI 对齐提示词仍在编辑器自己的 System Prompt 中修改。</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 权重 -->
    <div class="panel">
      <div class="panel-head">
        <h2>评分权重</h2>
        <span class="hint">四维加权，建议总和 100；改完需对岗位点一次「重算」</span>
      </div>
      <div class="pad-18">
        <div class="form-grid">
          <label class="field">必备要求<input v-model.number="weights.must" type="number" min="0"></label>
          <label class="field">职责同构<input v-model.number="weights.duty" type="number" min="0"></label>
          <label class="field">加分项<input v-model.number="weights.nice" type="number" min="0"></label>
          <label class="field">硬性条件<input v-model.number="weights.constraint" type="number" min="0"></label>
        </div>
        <div class="row-gap mt12">
          <button class="ghost" @click="saveWeights" :disabled="busy.weights">{{ busy.weights ? '保存中…' : '保存权重' }}</button>
          <span class="badge" :class="weightTotal === 100 ? 'ok' : 'warn'">合计 {{ weightTotal }} / 100</span>
        </div>
      </div>
    </div>

    <Teleport to="body">
      <div class="backdrop" v-if="modal.open" @click.self="modal.open = false"></div>
      <div class="modal-wrap" v-if="modal.open">
        <div class="modal">
          <div class="modal-head">
            <h3>更改数据位置</h3>
            <p>数据库与报告会写到新目录。选已有数据库的目录会直接接管它，不会覆盖任何文件。</p>
          </div>
          <div class="modal-body">
            <label class="field">目标目录
              <input v-model="modal.path" class="mono" placeholder="D:\\JDScopeData">
            </label>
            <div class="row-gap mt8">
              <button class="ghost" v-if="canBrowse" @click="browse">浏览…</button>
              <span class="hint">{{ canBrowse ? '在系统对话框里选一个文件夹' : '当前模式没有系统选择器，请直接粘贴绝对路径' }}</span>
            </div>
            <label class="check">
              <input type="checkbox" v-model="modal.migrate">
              <span>迁移现有数据（数据库 + 报告 + 备份）。目标目录已有数据库时会拒绝，避免误覆盖。</span>
            </label>
            <p class="hint" v-if="modal.note">{{ modal.note }}</p>
            <p class="hint" v-if="modal.error" style="color:var(--bad)">{{ modal.error }}</p>
          </div>
          <div class="modal-foot">
            <button class="ghost" @click="modal.open = false">取消</button>
            <button class="primary" @click="switchDir" :disabled="busy.dir">{{ busy.dir ? '切换中…' : '切换' }}</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>`,
};
