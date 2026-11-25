/* 日期范围选择：替代原生 date 输入，统一弹层样式，支持预设与区间选择。 */

const { ref, computed, nextTick, onMounted, onBeforeUnmount } = window.Vue;

const pad = (n) => String(n).padStart(2, "0");
const ymd = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const parse = (s) => {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s || "");
  if (!m) return null;
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return Number.isNaN(d.getTime()) ? null : d;
};
const dayStart = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
const addDays = (d, n) => {
  const out = new Date(d);
  out.setDate(out.getDate() + n);
  return out;
};

export const DateRange = {
  name: "date-range",
  props: {
    from: { type: String, default: "" },
    to: { type: String, default: "" },
    label: { type: String, default: "日期" },
  },
  emits: ["update:from", "update:to"],
  setup(props, { emit }) {
    const open = ref(false);
    const root = ref(null);
    const pop = ref(null);
    const popStyle = ref({ left: "0px", top: "0px" });
    const draftFrom = ref("");
    const draftTo = ref("");
    const view = ref({ y: new Date().getFullYear(), m: new Date().getMonth() });

    const today = dayStart(new Date());
    const todayKey = ymd(today);

    const display = computed(() => {
      if (props.from && props.to) {
        if (props.from === props.to) return props.from;
        const sameYear = props.from.slice(0, 4) === props.to.slice(0, 4);
        return sameYear ? `${props.from} → ${props.to.slice(5)}` : `${props.from} → ${props.to}`;
      }
      if (props.from) return `${props.from} 起`;
      if (props.to) return `截至 ${props.to}`;
      return props.label;
    });
    const filled = computed(() => !!(props.from || props.to));

    const monthTitle = computed(() => `${view.value.y} 年 ${view.value.m + 1} 月`);
    const days = computed(() => {
      const first = new Date(view.value.y, view.value.m, 1);
      const offset = (first.getDay() + 6) % 7; // 周一开头
      const start = addDays(first, -offset);
      return Array.from({ length: 42 }, (_, i) => {
        const d = addDays(start, i);
        return {
          key: ymd(d),
          iso: ymd(d),
          day: d.getDate(),
          out: d.getMonth() !== view.value.m,
          today: ymd(d) === todayKey,
        };
      });
    });

    const draftText = computed(() => {
      if (!draftFrom.value && !draftTo.value) return "未选择日期";
      if (draftFrom.value && draftTo.value) {
        return draftFrom.value === draftTo.value
          ? draftFrom.value
          : `${draftFrom.value} → ${draftTo.value}`;
      }
      return draftFrom.value ? `${draftFrom.value} 起` : `截至 ${draftTo.value}`;
    });

    const place = () => {
      if (!open.value) return;
      const anchor = root.value && root.value.getBoundingClientRect();
      if (!anchor || !pop.value) return;
      const box = pop.value.getBoundingClientRect();
      const gap = 8;
      const maxLeft = Math.max(gap, window.innerWidth - box.width - gap);
      let left = Math.min(Math.max(gap, anchor.left), maxLeft);
      let top = anchor.bottom + gap;
      if (top + box.height > window.innerHeight - gap) {
        top = Math.max(gap, anchor.top - box.height - gap);
      }
      popStyle.value = { left: `${left}px`, top: `${top}px` };
    };

    const syncDraft = () => {
      draftFrom.value = props.from || "";
      draftTo.value = props.to || "";
      const base = parse(draftTo.value) || parse(draftFrom.value) || today;
      view.value = { y: base.getFullYear(), m: base.getMonth() };
    };

    const toggle = async () => {
      if (open.value) {
        open.value = false;
        return;
      }
      syncDraft();
      open.value = true;
      await nextTick();
      place();
    };

    const close = () => { open.value = false; };

    const apply = () => {
      emit("update:from", draftFrom.value);
      emit("update:to", draftTo.value);
      close();
    };

    const clear = () => {
      draftFrom.value = "";
      draftTo.value = "";
      emit("update:from", "");
      emit("update:to", "");
      close();
    };

    const shift = (delta) => {
      const d = new Date(view.value.y, view.value.m + delta, 1);
      view.value = { y: d.getFullYear(), m: d.getMonth() };
    };

    const pick = (day) => {
      if (!draftFrom.value || (draftFrom.value && draftTo.value)) {
        draftFrom.value = day.iso;
        draftTo.value = "";
      } else if (day.iso < draftFrom.value) {
        draftTo.value = draftFrom.value;
        draftFrom.value = day.iso;
      } else {
        draftTo.value = day.iso;
      }
      if (day.out) {
        const d = parse(day.iso);
        view.value = { y: d.getFullYear(), m: d.getMonth() };
      }
    };

    const preset = (key) => {
      const now = dayStart(new Date());
      let f = now;
      let t = now;
      if (key === "7") f = addDays(now, -6);
      if (key === "30") f = addDays(now, -29);
      if (key === "month") f = new Date(now.getFullYear(), now.getMonth(), 1);
      draftFrom.value = ymd(f);
      draftTo.value = ymd(t);
      apply();
    };

    const dayClass = (day) => ({
      out: day.out,
      today: day.today,
      from: day.iso === draftFrom.value,
      to: !!draftTo.value && day.iso === draftTo.value,
      range: !!(draftFrom.value && draftTo.value && day.iso > draftFrom.value && day.iso < draftTo.value),
    });

    const onDocDown = (e) => {
      if (!open.value) return;
      if (root.value && root.value.contains(e.target)) return;
      if (pop.value && pop.value.contains(e.target)) return;
      close();
    };
    const onKey = (e) => { if (e.key === "Escape" && open.value) close(); };
    const onViewport = () => { if (open.value) place(); };

    onMounted(() => {
      document.addEventListener("mousedown", onDocDown);
      document.addEventListener("keydown", onKey);
      window.addEventListener("resize", onViewport);
      window.addEventListener("scroll", onViewport, true);
    });
    onBeforeUnmount(() => {
      document.removeEventListener("mousedown", onDocDown);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("resize", onViewport);
      window.removeEventListener("scroll", onViewport, true);
    });

    return {
      open, root, pop, popStyle, view, days, display, filled, draftText, monthTitle,
      draftFrom, draftTo,
      toggle, close, apply, clear, shift, pick, preset, dayClass,
    };
  },
  template: `
  <div class="date-range" ref="root">
    <button type="button" class="dr-btn" :class="{ on: open || filled }" @click="toggle" :title="display">
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
        <rect x="3" y="5" width="18" height="16" rx="3"/><path d="M3 10h18M8 3v4M16 3v4"/>
      </svg>
      <span class="dr-text">{{ display }}</span>
      <svg class="dr-caret" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
        <path d="M7 10l5 5 5-5"/>
      </svg>
    </button>

    <Teleport to="body">
      <div v-if="open" class="dr-pop" ref="pop" :style="popStyle" role="dialog" aria-label="选择日期范围" @mousedown.stop>
        <div class="dr-head">
          <button type="button" class="dr-nav" @click="shift(-1)" title="上个月">‹</button>
          <strong>{{ monthTitle }}</strong>
          <button type="button" class="dr-nav" @click="shift(1)" title="下个月">›</button>
        </div>

        <div class="dr-presets">
          <button type="button" class="dr-preset" @click="preset('today')">今天</button>
          <button type="button" class="dr-preset" @click="preset('7')">近 7 天</button>
          <button type="button" class="dr-preset" @click="preset('30')">近 30 天</button>
          <button type="button" class="dr-preset" @click="preset('month')">本月</button>
        </div>

        <div class="dr-weekdays">
          <span v-for="w in ['一','二','三','四','五','六','日']" :key="w">{{ w }}</span>
        </div>
        <div class="dr-grid">
          <button type="button" v-for="d in days" :key="d.key"
                  class="dr-day" :class="dayClass(d)" :aria-label="d.iso" @click="pick(d)">{{ d.day }}</button>
        </div>

        <div class="dr-foot">
          <button type="button" class="dr-clear" @click="clear">清空</button>
          <span class="dr-sel">{{ draftText }}</span>
          <button type="button" class="dr-apply" :disabled="!draftFrom && !draftTo" @click="apply">应用</button>
        </div>
      </div>
    </Teleport>
  </div>`,
};
