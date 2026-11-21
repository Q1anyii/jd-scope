/* 个人档案：只用于硬性条件判定，存在本机数据库，不进代码库。 */

import { api } from "../api.js";
import { state, toast, loadBoot } from "../store.js";

const { reactive, computed, ref } = window.Vue;

export const Profile = {
  name: "profile",
  setup() {
    const s = state;
    const form = reactive({
      education: "", major: "", years: 0, cities: "", certs: "", notes: "",
    });
    const saving = ref(false);
    const savedAt = computed(() => {
      const t = (s.profile && s.profile.updated_at) || "";
      return t ? "上次保存 " + t.slice(0, 16).replace("T", " ") : "";
    });

    const fill = () => {
      const p = s.profile || {};
      form.education = p.education || "";
      form.major = p.major || "";
      form.years = p.years || 0;
      form.cities = p.cities || "";
      form.certs = p.certs || "";
      form.notes = p.notes || "";
    };
    fill();

    const save = async () => {
      saving.value = true;
      try {
        await api.saveProfile({ ...form, years: Number(form.years || 0) });
        await loadBoot();
        toast("档案已保存", "ok");
      } catch (err) { toast(err.message, "err"); }
      finally { saving.value = false; }
    };

    return { s, form, saving, savedAt, save };
  },
  template: `
  <div>
    <div class="view-head">
      <h1>个人档案</h1>
      <p>只参与硬性条件判定：学历、年限、英语、意向城市。存在本机数据库里，不进代码库、不上传。</p>
    </div>

    <div class="panel">
      <div class="pad-18">
        <div class="form-grid">
          <label class="field">学历
            <select v-model="form.education">
              <option value="">未填</option>
              <option>博士</option><option>硕士</option><option>本科</option>
              <option>大专</option><option>中专</option><option>高中</option>
            </select>
          </label>
          <label class="field">专业<input v-model="form.major" placeholder="如 软件工程"></label>
          <label class="field">工作年限<input v-model="form.years" type="number" min="0" step="0.5"></label>
          <label class="field">意向城市<input v-model="form.cities" placeholder="逗号分隔，如 深圳,东莞"></label>
          <label class="field span2">证书<input v-model="form.certs" placeholder="如 CET-6、软考中级"></label>
          <label class="field span2">备注<textarea v-model="form.notes" rows="4" placeholder="可选，写给自己看的上下文"></textarea></label>
        </div>
        <div class="row-gap mt12">
          <button class="primary" @click="save" :disabled="saving">{{ saving ? '保存中…' : '保存档案' }}</button>
          <span class="hint">{{ savedAt }}</span>
        </div>
      </div>
    </div>
  </div>`,
};
