/* 缺口库：只记差集，可标状态、生成面试应答口径。 */

import { api } from "../api.js";
import { state, toast, PRIO_LABEL, loadGaps, loadBoot } from "../store.js";

const { computed, ref, watch } = window.Vue;

export const Gaps = {
  name: "gaps",
  setup() {
    const s = state;
    const busy = ref({});       // 每条缺口独立的“生成中”标记
    const expanded = ref({});   // 应答展开状态

    watch(() => [s.gapPriority, s.gapStatus], () => loadGaps().catch((e) => toast(e.message, "err")));

    const filtered = computed(() => {
      const kw = s.gapQuery.trim().toLowerCase();
      if (!kw) return s.gaps;
      return s.gaps.filter((g) =>
        (g.requirement || "").toLowerCase().includes(kw)
        || (g.company || "").toLowerCase().includes(kw)
        || (g.title || "").toLowerCase().includes(kw)
        || (g.resume_state || "").toLowerCase().includes(kw));
    });

    const setStatus = async (gap, value) => {
      try {
        await api.updateGap(gap.id, { status: value });
        gap.status = value;
        await loadBoot();
        toast("已更新", "ok");
      } catch (err) { toast(err.message, "err"); }
    };

    const answer = async (gap) => {
      busy.value[gap.id] = true;
      try {
        const out = await api.answerGap(gap.id);
        if (out.answer) {
          gap.answer = out.answer;
          expanded.value[gap.id] = true;
          toast("已生成应答口径", "ok");
        } else {
          toast(out.error || "模型没有返回内容", "err");
        }
      } catch (err) { toast(err.message, "err"); }
      finally { busy.value[gap.id] = false; }
    };

    const toggle = (gap) => { expanded.value[gap.id] = !expanded.value[gap.id]; };

    return { s, busy, expanded, filtered, PRIO_LABEL, setStatus, answer, toggle };
  },
  template: `
  <div>
    <div class="view-head">
      <h1>缺口库</h1>
      <p>只记「JD 明确要求、但简历没有覆盖」的差集。状态和补课动作会跟着岗位重算自动保留，不会被冲掉。</p>
    </div>

    <div class="panel">
      <div class="pad-18">
        <div class="row-gap">
          <input class="grow" v-model="s.gapQuery" placeholder="搜要求 / 公司 / 简历现状">
          <select v-model="s.gapPriority" style="width:132px">
            <option value="">全部优先级</option>
            <option value="high">高</option>
            <option value="medium">中</option>
            <option value="low">低</option>
          </select>
          <select v-model="s.gapStatus" style="width:132px">
            <option value="open">未处理</option>
            <option value="learning">补课中</option>
            <option value="closed">已补上</option>
            <option value="">全部</option>
          </select>
          <span class="hint">共 {{ filtered.length }} 条</span>
        </div>
      </div>

      <div class="table-wrap">
        <table>
          <thead><tr><th>优先级</th><th>来自</th><th>JD 要求</th><th>简历现状</th><th>状态</th><th>面试应答</th></tr></thead>
          <tbody>
            <tr v-for="g in filtered" :key="g.id">
              <td><span class="badge" :class="g.priority">{{ PRIO_LABEL[g.priority] || g.priority }}</span></td>
              <td>{{ g.company || '—' }}<div class="hint">{{ g.title || '' }}</div></td>
              <td>
                <div>{{ g.requirement }}</div>
                <div class="hint" v-if="g.gap">差在：{{ g.gap }}</div>
              </td>
              <td class="muted">{{ g.resume_state || '—' }}</td>
              <td>
                <select :value="g.status" style="width:112px" @change="setStatus(g, $event.target.value)">
                  <option value="open">未处理</option>
                  <option value="learning">补课中</option>
                  <option value="closed">已补上</option>
                </select>
              </td>
              <td>
                <div class="row-gap">
                  <button class="mini" @click="answer(g)" :disabled="busy[g.id]">
                    {{ busy[g.id] ? '生成中…' : (g.answer ? '重新生成' : '生成应答') }}
                  </button>
                  <button class="mini" v-if="g.answer" @click="toggle(g)">{{ expanded[g.id] ? '收起' : '展开' }}</button>
                </div>
                <div class="hint mt8" v-if="g.answer && expanded[g.id]" style="color:var(--sub)">{{ g.answer }}</div>
              </td>
            </tr>
            <tr v-if="!filtered.length">
              <td colspan="6"><div class="empty">
                <svg width="46" height="46" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4">
                  <path d="M12 3 3 7.5l9 4.5 9-4.5L12 3Z"/><path d="M3 12.5 12 17l9-4.5"/><path d="M3 17.5 12 22l9-4.5"/>
                </svg>
                {{ s.gapQuery ? '没有匹配的缺口' : '这个筛选条件下没有缺口' }}
              </div></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>`,
};
