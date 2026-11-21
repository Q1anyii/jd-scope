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
    const busy = ref({ save: false, test: false, weights: false, dir: false, reset: false });
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
    };
    sync();
    watch(() => s.settings, sync);

    const weightTotal = computed(() => {
      const n = ["must", "duty", "nice", "constraint"].reduce((acc, k) => acc + Number(weights[k] || 0), 0);
      return Math.round(n * 10) / 10;
    });

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
      saveLlm, testLlm, saveWeights,
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
