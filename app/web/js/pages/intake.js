/* JD 入库：粘原文 → 本地规则解析 → 落库并分析。 */

import { api } from "../api.js";
import { state, toast, CAT_LABEL, PRIO_LABEL, loadBoot, openJob, switchView } from "../store.js";

const { reactive, ref } = window.Vue;

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

export const Intake = {
  name: "intake",
  setup() {
    const form = reactive({ company: "", title: "", city: "", source: "", url: "" });
    const jd = ref("");
    const parsed = ref(null);
    const parsing = ref(false);
    const saving = ref(false);
    const aiItems = ref([]);
    const aiLoading = ref(false);
    const aiNote = ref("");

    const fillSample = () => {
      jd.value = SAMPLE_JD;
      parsed.value = null;
      aiItems.value = [];
      aiNote.value = "";
    };

    const readFile = async (event) => {
      const file = event.target.files && event.target.files[0];
      if (!file) return;
      jd.value = await file.text();
      parsed.value = null;
      aiItems.value = [];
      aiNote.value = "";
      event.target.value = "";
    };

    const parse = async () => {
      const raw = jd.value.trim();
      if (raw.length < 20) { toast("JD 原文太短，至少 20 字", "err"); return; }
      parsing.value = true;
      try {
        const data = await api.parseJd({
          jd_raw: raw,
          company: form.company.trim(),
          title: form.title.trim(),
          city: form.city.trim(),
        });
        parsed.value = data;
        if (!form.company && data.company) form.company = data.company;
        if (!form.title && data.title) form.title = data.title;
        if (!form.city && data.city) form.city = data.city;
      } catch (err) {
        toast(err.message, "err");
      } finally {
        parsing.value = false;
      }
    };

    const save = async () => {
      if (!parsed.value) { toast("先解析一次，确认抽取结果", "err"); return; }
      saving.value = true;
      try {
        const picked = aiItems.value.filter((i) => i.picked).map((i) => ({
          text: i.text, category: i.category, priority: i.priority, terms: i.terms,
        }));
        const res = await api.createJob({
          jd_raw: jd.value.trim(),
          company: form.company.trim(),
          title: form.title.trim(),
          city: form.city.trim(),
          source: form.source.trim(),
          url: form.url.trim(),
          ai_items: picked,
        });
        toast(`已入库：匹配度 ${res.score}，${res.verdict}${picked.length ? `（含 ${picked.length} 条 AI 条目）` : ""}`, "ok");
        jd.value = "";
        parsed.value = null;
        aiItems.value = [];
        aiNote.value = "";
        Object.keys(form).forEach((k) => { form[k] = ""; });
        await loadBoot();
        await switchView("jobs");
        await openJob(res.job_id);
      } catch (err) {
        toast(err.message, "err");
      } finally {
        saving.value = false;
      }
    };

    /* AI 只出候选：这里不落库、不打分，等用户勾完再随表单一起提交 */
    const askAi = async () => {
      if (jd.value.trim().length < 20) { toast("JD 原文太短，至少 20 字", "err"); return; }
      if (!parsed.value) await parse();
      aiLoading.value = true;
      aiNote.value = "";
      try {
        const data = await api.parseJdAi({ jd_raw: jd.value.trim() });
        aiItems.value = (data.items || []).map((it) => ({ ...it, picked: !it.duplicate }));
        aiNote.value = `模型 ${data.model || ""} 给出 ${aiItems.value.length} 条；规则已识别 ${data.rule_count} 条，重复项默认不勾`;
        if (!aiItems.value.length) aiNote.value = "模型没有给出可用条目，换个模型或手工补";
      } catch (err) {
        aiItems.value = [];
        aiNote.value = err.message;
        toast(err.message, "err");
      } finally {
        aiLoading.value = false;
      }
    };

    const toggleAll = (on) => {
      aiItems.value.forEach((i) => { if (!i.duplicate) i.picked = on; });
    };

    const pickedCount = () => aiItems.value.filter((i) => i.picked).length;

    const grouped = (cat) => ((parsed.value && parsed.value.requirements) || []).filter((r) => r.category === cat);

    return {
      s: state, form, jd, parsed, parsing, saving, aiItems, aiLoading, aiNote,
      CAT_LABEL, PRIO_LABEL, grouped, askAi, toggleAll, pickedCount,
      fillSample, readFile, parse, save,
    };
  },
  template: `
  <div>
    <div class="view-head">
      <h1>JD 入库</h1>
      <p>粘原文 → 解析预览 → 保存并分析。规则解析不联网；AI 解析只产出候选条目，勾哪条由你定，未勾的不入库、不参与打分。</p>
    </div>

    <div class="panel">
      <div class="form-grid three">
        <label class="field">公司<input v-model="form.company" placeholder="可从 JD 自动识别，也可手填"></label>
        <label class="field">岗位<input v-model="form.title" placeholder="如 AI 应用开发工程师"></label>
        <label class="field">城市<input v-model="form.city" placeholder="如 深圳"></label>
        <label class="field">来源<input v-model="form.source" placeholder="官网 / BOSS / 内推"></label>
        <label class="field span2">链接<input v-model="form.url" placeholder="岗位链接（可选）"></label>
      </div>

      <div class="pad-18">
        <div class="row-between">
          <div class="row-gap">
            <button class="ghost" @click="fillSample">填入示例 JD</button>
            <label class="file-btn">从文件读取<input type="file" accept=".txt,.md" hidden @change="readFile"></label>
          </div>
          <span class="hint">{{ jd.trim().length }} 字</span>
        </div>
        <textarea v-model="jd" rows="13" class="mt8"
          placeholder="把岗位描述整段粘进来。含「岗位职责 / 任职要求 / 加分项」小标题时抽取效果最好。"></textarea>
        <div class="row-gap mt12">
          <button class="primary" @click="parse" :disabled="parsing || !jd.trim()">
            {{ parsing ? '解析中…' : '解析预览' }}
          </button>
          <button class="ghost" @click="askAi" :disabled="aiLoading || !jd.trim()">
            {{ aiLoading ? 'AI 解析中…' : 'AI 补解析（出候选）' }}
          </button>
          <button class="ghost" @click="save" :disabled="saving || !parsed">
            {{ saving ? '保存中…' : '保存并分析' }}
          </button>
          <span class="hint" v-if="!parsed">先解析，确认抽到的需求条目对不对</span>
        </div>
      </div>
    </div>

    <div class="panel" v-if="aiItems.length || aiLoading || aiNote">
      <div class="panel-head">
        <h2>AI 候选条目</h2>
        <span class="hint" v-if="aiItems.length">已勾 {{ pickedCount() }} / {{ aiItems.length }}</span>
        <div class="row-gap" v-if="aiItems.length">
          <button class="mini" @click="toggleAll(true)">全选</button>
          <button class="mini" @click="toggleAll(false)">清空</button>
        </div>
      </div>
      <div class="pad-18">
        <p class="hint">{{ aiLoading ? '正在请求模型…' : aiNote }}</p>
        <div class="req-row" v-for="(it, i) in aiItems" :key="i">
          <label class="check">
            <input type="checkbox" v-model="it.picked" :disabled="it.duplicate">
          </label>
          <div>
            <div class="txt">{{ it.text }}</div>
            <div class="ev row-gap">
              <span class="badge" :class="it.priority === 'high' ? 'high' : it.priority === 'medium' ? 'medium' : 'low'">{{ CAT_LABEL[it.category] || it.category }} · {{ PRIO_LABEL[it.priority] || it.priority }}</span>
              <span class="badge plain" v-if="it.duplicate">规则已识别</span>
              <span class="badge plain" v-for="t in (it.terms || [])" :key="t">{{ t }}</span>
              <span class="hint" v-if="it.reason">{{ it.reason }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="panel" v-if="parsed">
      <div class="panel-head">
        <h2>解析结果</h2>
        <span class="hint">
          {{ parsed.company || '未识别公司' }} · {{ parsed.title || '未识别岗位' }} ·
          识别术语 {{ (parsed.terms || []).length }} 个 · 需求 {{ (parsed.requirements || []).length }} 条
        </span>
      </div>
      <div class="pad-18">
        <div class="row-gap">
          <span class="badge plain" v-for="t in parsed.terms" :key="t">{{ t }}</span>
          <span class="hint" v-if="!(parsed.terms || []).length">没识别到技术术语</span>
        </div>
        <div class="row-gap mt12" v-if="(parsed.constraints || []).length">
          <span class="hint">硬性条件：</span>
          <span class="badge plain" v-for="(c, i) in parsed.constraints" :key="i">{{ c.text || c.kind }}</span>
        </div>

        <div v-for="cat in ['must','duty','nice']" :key="cat">
          <div class="section-title" v-if="grouped(cat).length">{{ CAT_LABEL[cat] }}（{{ grouped(cat).length }}）</div>
          <div class="req-row" v-for="(r, i) in grouped(cat)" :key="i">
            <div><span class="badge" :class="r.priority === 'high' ? 'high' : r.priority === 'medium' ? 'medium' : 'low'">{{ PRIO_LABEL[r.priority] || r.priority }}</span></div>
            <div>
              <div class="txt">{{ r.text }}</div>
              <div class="ev">{{ (r.terms || []).length ? '识别术语：' + r.terms.join('、') : '未识别到技术术语' }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>`,
};
