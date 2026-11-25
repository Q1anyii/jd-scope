/* 公司档案：一家公司 = 一个本地文件夹，简历 / 策略 / JD / 报告都在一起。 */

import { api } from "../api.js";
import { state, toast, loadCompanies, openEditor, shortDate } from "../store.js";

const { reactive, ref, onMounted } = window.Vue;

export const Companies = {
  name: "companies",
  setup() {
    const form = reactive({ open: false, name: "", job_id: "", base_id: "" });
    const jobs = ref([]);
    const bases = ref([]);
    const saving = ref(false);
    const strategy = reactive({ open: false, id: 0, name: "", text: "", saving: false });

    const openCreate = async () => {
      form.open = true;
      form.name = "";
      form.job_id = "";
      form.base_id = "";
      try {
        const [j, b] = await Promise.all([api.listJobs({ sort: "newest" }), api.listBases()]);
        jobs.value = j.items || [];
        bases.value = b.items || [];
      } catch (err) {
        toast(err.message, "err");
      }
    };

    const pickJob = () => {
      const job = jobs.value.find((j) => String(j.id) === String(form.job_id));
      if (job && !form.name.trim()) form.name = job.company;
    };

    const create = async () => {
      if (!form.name.trim() && !form.job_id) {
        toast("填公司名，或选一个已入库岗位", "err");
        return;
      }
      saving.value = true;
      try {
        const res = await api.createCompany({
          name: form.name.trim(),
          job_id: form.job_id || null,
          base_id: form.base_id || null,
        });
        form.open = false;
        await loadCompanies();
        toast(`已建档：${res.company.name}`, "ok");
        openEditor(res.company.id);
      } catch (err) {
        toast(err.message, "err");
      } finally {
        saving.value = false;
      }
    };

    const editStrategy = async (c) => {
      try {
        const d = await api.getCompany(c.id);
        strategy.id = c.id;
        strategy.name = d.name;
        strategy.text = d.strategy || "";
        strategy.open = true;
      } catch (err) {
        toast(err.message, "err");
      }
    };

    const saveStrategy = async () => {
      strategy.saving = true;
      try {
        await api.saveCompanyStrategy(strategy.id, strategy.text);
        strategy.open = false;
        await loadCompanies();
        toast("策略已写回 strategy.md", "ok");
      } catch (err) {
        toast(err.message, "err");
      } finally {
        strategy.saving = false;
      }
    };

    const openFolder = async (c) => {
      try {
        await api.openCompanyFolder(c.id);
      } catch (err) {
        toast(err.message, "err");
      }
    };

    const remove = async (c) => {
      if (!window.confirm(`删除「${c.name}」的建档记录？\n文件夹和里面的简历会保留在磁盘上，不会被删。`)) return;
      try {
        await api.deleteCompany(c.id);
        await loadCompanies();
        toast("已删除记录，文件夹保留", "ok");
      } catch (err) {
        toast(err.message, "err");
      }
    };

    onMounted(() => { loadCompanies().catch((e) => toast(e.message, "err")); });

    return {
      s: state, form, jobs, bases, saving, strategy,
      openCreate, pickJob, create, editStrategy, saveStrategy, openFolder, remove,
      openEditor, shortDate,
    };
  },
  template: `
  <div>
    <div class="view-head">
      <h1>公司档案</h1>
      <p>每个公司一个文件夹：成品简历用 <code>姓名-岗位名-简历.html / .pdf</code>；<code>jd / report / strategy</code> 用 <code>公司-岗位名-</code> 前缀；<code>resume.json</code> 是编辑器草稿。改完直接在编辑器里导出，一条龙走完。</p>
    </div>

    <div class="panel">
      <div class="panel-head">
        <h2>档案列表</h2>
        <span class="hint">{{ (s.companies || []).length }} 家</span>
        <button class="primary" @click="openCreate">新建公司档案</button>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>公司</th><th>关联岗位</th><th>结论</th><th>文件</th><th>更新</th><th style="width:1%">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in (s.companies || [])" :key="c.id">
              <td>
                <div class="strong">{{ c.name }}
                  <span class="badge plain" v-if="c.kind === 'general'">通用</span>
                </div>
                <div class="hint mono">{{ c.folder }}</div>
              </td>
              <td>
                <div class="hint" v-if="c.kind === 'general'">母版 · 不属于任何公司</div>
                <template v-else>
                  <div>{{ c.job_title || '—' }}</div>
                  <div class="hint" v-if="c.job_company">{{ c.job_company }}</div>
                </template>
              </td>
              <td>
                <div class="row-gap">
                  <span class="badge" :class="c.score >= 72 ? 'ok' : c.score >= 55 ? 'warn' : 'bad'" v-if="c.job_title">{{ c.score }}</span>
                  <span class="hint">{{ c.verdict || '—' }}</span>
                </div>
              </td>
              <td>
                <div class="row-gap">
                  <span class="badge plain" :style="c.files && c.files.resume ? '' : 'opacity:.38'">简历</span>
                  <span class="badge plain" :style="c.files && c.files.html ? '' : 'opacity:.38'">HTML</span>
                  <span class="badge plain" :style="c.files && c.files.pdf ? '' : 'opacity:.38'">PDF</span>
                  <span class="badge plain" :style="c.files && c.files.strategy ? '' : 'opacity:.38'">策略</span>
                  <span class="badge plain" v-if="c.files && c.files.jd">JD</span>
                </div>
              </td>
              <td class="hint">{{ shortDate(c.updated_at) }}</td>
              <td style="white-space:nowrap">
                <div class="actions">
                  <button class="mini" @click="openEditor(c.id)">打开编辑器</button>
                  <button class="mini" @click="editStrategy(c)">策略</button>
                  <button class="mini" @click="openFolder(c)">文件夹</button>
                  <button class="mini" v-if="c.kind !== 'general'" @click="remove(c)">删除记录</button>
                </div>
              </td>
            </tr>
            <tr v-if="!(s.companies || []).length">
              <td colspan="6">
                <div class="empty">
                  还没有公司档案。从「岗位」页打开一份 JD，点「建公司档案」，或在这里直接新建。
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <Teleport to="body">
      <div class="backdrop" v-if="form.open" @click.self="form.open = false"></div>
      <div class="modal-wrap" v-if="form.open">
        <div class="modal">
          <div class="modal-head">
            <h3>新建公司档案</h3>
            <p>会在数据目录的 <code>resumes/</code> 下建一个以公司名命名的文件夹；同名自动加序号，绝不覆盖。</p>
          </div>
          <div class="modal-body">
            <div class="form-grid">
              <label class="field">公司名
                <input v-model="form.name" placeholder="选岗位会自动填公司名">
              </label>
              <label class="field">关联岗位
                <select v-model="form.job_id" @change="pickJob">
                  <option value="">不关联（只建文件夹）</option>
                  <option v-for="j in jobs" :key="j.id" :value="j.id">{{ j.company }} · {{ j.title }}</option>
                </select>
              </label>
              <label class="field span2">起始基底
                <select v-model="form.base_id">
                  <option value="">用编辑器默认模板</option>
                  <option v-for="b in bases" :key="b.id" :value="b.id">{{ b.code }} · {{ b.intent }}</option>
                </select>
              </label>
            </div>
            <p class="hint">选 HTML 基底时，编辑器第一次打开会自动把 HTML 解析成可编辑结构；选编辑器导出的 JSON 则直接接着改。</p>
          </div>
          <div class="modal-foot">
            <button class="ghost" @click="form.open = false">取消</button>
            <button class="primary" @click="create" :disabled="saving">{{ saving ? '创建中…' : '创建并打开编辑器' }}</button>
          </div>
        </div>
      </div>

      <div class="backdrop" v-if="strategy.open" @click.self="strategy.open = false"></div>
      <div class="modal-wrap" v-if="strategy.open">
        <div class="modal">
          <div class="modal-head">
            <h3>{{ strategy.name }} · 策略</h3>
            <p>直接编辑 <code>strategy.md</code>，和这家公司的简历放在同一个文件夹里。</p>
          </div>
          <div class="modal-body">
            <textarea v-model="strategy.text" rows="20" class="mono" spellcheck="false"></textarea>
          </div>
          <div class="modal-foot">
            <button class="ghost" @click="strategy.open = false">取消</button>
            <button class="primary" @click="saveStrategy" :disabled="strategy.saving">{{ strategy.saving ? '保存中…' : '保存' }}</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>`,
};
