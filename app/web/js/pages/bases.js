/* 基底库：不绑定公司的通用简历母版，系统按术语覆盖自动选型。 */

import { api } from "../api.js";
import { state, toast, loadBases, loadBoot } from "../store.js";

const { reactive, ref } = window.Vue;

export const Bases = {
  name: "bases",
  setup() {
    const s = state;
    const form = reactive({ code: "", intent: "", tags: "", label: "" });
    const picked = ref(null);
    const saving = ref(false);
    const edit = reactive({
      open: false, id: 0, code: "", intent: "", label: "", tags: "",
      content: "", keywords: [], busy: false, error: "",
    });

    const pickFile = async (event) => {
      const file = event.target.files && event.target.files[0];
      if (!file) return;
      picked.value = { name: file.name, text: await file.text() };
      event.target.value = "";
    };

    const create = async () => {
      if (!picked.value) { toast("先导入一份基底文件", "err"); return; }
      if (!form.code.trim() || !form.intent.trim()) { toast("代号和求职意向必填", "err"); return; }
      saving.value = true;
      try {
        const out = await api.createBase({
          code: form.code.trim(),
          intent: form.intent.trim(),
          label: form.label.trim(),
          tags: form.tags,
          content: picked.value.text,
        });
        toast(`已登记，识别 ${out.coverage} 个术语`, "ok");
        picked.value = null;
        Object.keys(form).forEach((k) => { form[k] = ""; });
        await loadBases();
        await loadBoot();
      } catch (err) { toast(err.message, "err"); }
      finally { saving.value = false; }
    };

    const openEdit = async (base) => {
      edit.error = "";
      try {
        const out = await api.getBase(base.id);
        const item = out.item || {};
        Object.assign(edit, {
          open: true,
          id: base.id,
          code: item.code || "",
          intent: item.intent || "",
          label: item.label || "",
          tags: (item.tags || []).join(", "),
          content: item.content || "",
          keywords: item.keywords || [],
          busy: false,
        });
      } catch (err) { toast(err.message, "err"); }
    };

    const closeEdit = () => {
      edit.open = false;
      edit.error = "";
    };

    const saveEdit = async () => {
      edit.error = "";
      if (!edit.code.trim() || !edit.intent.trim()) {
        edit.error = "代号和求职意向必填";
        return;
      }
      if (edit.content.trim().length < 20) {
        edit.error = "基底正文不能为空";
        return;
      }
      edit.busy = true;
      try {
        const out = await api.updateBase(edit.id, {
          code: edit.code.trim(),
          intent: edit.intent.trim(),
          label: edit.label.trim(),
          tags: edit.tags,
          content: edit.content,
        });
        edit.keywords = out.item.keywords || [];
        toast(`已保存，识别 ${out.item.coverage} 个术语`, "ok");
        edit.open = false;
        await loadBases();
        await loadBoot();
      } catch (err) {
        edit.error = err.message;
      } finally {
        edit.busy = false;
      }
    };

    const remove = async (base) => {
      if (!confirm(`删除基底「${base.code}」？已保存岗位的匹配结果不会自动重算。`)) return;
      try {
        await api.deleteBase(base.id);
        await loadBases();
        await loadBoot();
        toast("已删除", "ok");
      } catch (err) { toast(err.message, "err"); }
    };

    return { s, form, picked, saving, edit, pickFile, create, openEdit, closeEdit, saveEdit, remove };
  },
  template: `
  <div>
    <div class="view-head">
      <h1>基底库</h1>
      <p>基底 = 不绑定公司的通用简历母版。只存文本、不记路径，系统按术语命中与覆盖面自动挑一份最接近的。登记后可以随时编辑正文或元信息。</p>
    </div>

    <div class="panel">
      <div class="pad-18">
        <div class="form-grid three">
          <label class="field">代号<input v-model="form.code" placeholder="如 ai-app / backend"></label>
          <label class="field">求职意向<input v-model="form.intent" placeholder="如 AI应用开发工程师"></label>
          <label class="field">标签<input v-model="form.tags" placeholder="逗号分隔，如 ai,agent,rag"></label>
          <label class="field span2">备注<input v-model="form.label" placeholder="可选"></label>
        </div>
        <div class="row-gap mt12">
          <label class="file-btn">导入 HTML / TXT<input type="file" accept=".html,.htm,.txt,.md" hidden @change="pickFile"></label>
          <span class="hint" v-if="picked">已读取 {{ picked.name }}（{{ picked.text.length }} 字符）</span>
          <span class="hint" v-else>未选择文件</span>
          <span class="grow"></span>
          <button class="primary" @click="create" :disabled="saving">{{ saving ? '登记中…' : '登记基底' }}</button>
        </div>
      </div>
    </div>

    <div class="panel">
      <div class="panel-head"><h2>已登记</h2><span class="hint">关键词从正文自动抽取，供匹配使用</span></div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>代号</th><th>求职意向</th><th>类型</th><th>覆盖术语</th><th>标签</th><th>识别到</th><th></th></tr></thead>
          <tbody>
            <tr v-for="b in s.bases" :key="b.id">
              <td><strong>{{ b.code }}</strong><div class="hint">{{ b.label }}</div></td>
              <td>{{ b.intent }}</td>
              <td><span class="badge plain">{{ b.kind === 'json' ? '编辑器 JSON' : 'HTML / 文本' }}</span></td>
              <td class="num">{{ b.coverage }}</td>
              <td>
                <span class="badge low" v-for="t in b.tags" :key="t">{{ t }}</span>
                <span class="hint" v-if="!(b.tags || []).length">—</span>
              </td>
              <td class="hint">{{ (b.keywords || []).slice(0, 10).join('、') }}{{ (b.keywords || []).length > 10 ? ' …' : '' }}</td>
              <td>
                <div class="row-gap">
                  <button class="mini" @click="openEdit(b)">编辑</button>
                  <button class="mini danger" @click="remove(b)">删除</button>
                </div>
              </td>
            </tr>
            <tr v-if="!s.bases.length">
              <td colspan="7"><div class="empty">
                <svg width="46" height="46" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4">
                  <path d="M5 4h9l4 4v12H5z"/><path d="M14 4v4h4"/>
                </svg>
                还没有登记基底。至少登记一份，岗位才能算覆盖。
              </div></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <Teleport to="body">
      <div class="backdrop" v-if="edit.open" @click.self="closeEdit"></div>
      <div class="modal-wrap" v-if="edit.open">
        <div class="modal wide">
          <div class="modal-head">
            <h3>编辑基底</h3>
            <p>改正文会重新抽取关键词、类型与覆盖数；已保存岗位需要到岗位详情点「重算」，才会使用新的基底。</p>
          </div>
          <div class="modal-body scroll">
            <div class="form-grid three">
              <label class="field">代号<input v-model="edit.code" placeholder="如 ai-app"></label>
              <label class="field">求职意向<input v-model="edit.intent" placeholder="如 AI应用开发工程师"></label>
              <label class="field">标签<input v-model="edit.tags" placeholder="逗号分隔"></label>
              <label class="field span3">备注<input v-model="edit.label" placeholder="可选"></label>
            </div>
            <label class="field mt12">正文
              <textarea v-model="edit.content" class="mono base-content" spellcheck="false"
                placeholder="粘贴 HTML 或编辑器 JSON 正文"></textarea>
            </label>
            <div class="row-gap mt8">
              <span class="badge plain">当前识别 {{ (edit.keywords || []).length }} 个术语</span>
              <span class="hint">{{ (edit.keywords || []).slice(0, 14).join('、') }}{{ (edit.keywords || []).length > 14 ? ' …' : '' }}</span>
            </div>
            <p class="hint" style="color:var(--bad)" v-if="edit.error">{{ edit.error }}</p>
          </div>
          <div class="modal-foot">
            <button class="ghost" @click="closeEdit">取消</button>
            <button class="primary" @click="saveEdit" :disabled="edit.busy">{{ edit.busy ? '保存中…' : '保存修改' }}</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>`,
};
