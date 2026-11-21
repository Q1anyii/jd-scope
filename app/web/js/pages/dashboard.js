/* 概览：跨岗位聚合，回答“该补什么”。 */

import { state } from "../store.js";

const { computed } = window.Vue;

export const Dashboard = {
  name: "dashboard",
  setup() {
    const s = state;

    const cards = computed(() => {
      const sum = s.summary || {};
      return [
        { k: "岗位总数", v: sum.jobs || 0, unit: "", sub: "已录入台账" },
        { k: "平均匹配度", v: sum.avg_score || 0, unit: "/100", sub: "全部岗位均分" },
        { k: "待补缺口", v: sum.gaps_open || 0, unit: "", sub: "未处理的差集" },
        { k: "已投递", v: sum.applied || 0, unit: "", sub: "有投递记录" },
        {
          k: "回复率",
          v: sum.reply_rate === null || sum.reply_rate === undefined ? "—" : sum.reply_rate,
          unit: sum.reply_rate === null || sum.reply_rate === undefined ? "" : "%",
          sub: `回复 ${sum.replied || 0} / 投递 ${sum.applied || 0}`,
        },
      ];
    });

    const terms = computed(() => ((s.stats && s.stats.term_demand) || []).slice(0, 10));
    const termMax = computed(() => Math.max(1, ...terms.value.map((t) => t.jobs)));
    const hot = computed(() => ((s.stats && s.stats.gap_hotspots) || []).slice(0, 9));
    const hotMax = computed(() => Math.max(1, ...hot.value.map((g) => g.jobs)));
    const cities = computed(() => ((s.stats && s.stats.city_demand) || []).slice(0, 8));
    const cityMax = computed(() => Math.max(1, ...cities.value.map((c) => c.count)));
    const uncovered = computed(() => ((s.stats && s.stats.uncovered) || []).slice(0, 10));
    const perf = computed(() => (s.stats && s.stats.base_performance) || []);

    const width = (value, max) => Math.max(6, Math.round((value / max) * 100)) + "%";

    return { s, cards, terms, termMax, hot, hotMax, cities, cityMax, uncovered, perf, width };
  },
  template: `
  <div>
    <div class="view-head">
      <h1>概览</h1>
      <p>单个岗位只看匹配度没有意义，多个岗位叠起来才看得出该补什么。这里只统计、不做评价。</p>
    </div>

    <div class="cards">
      <div class="stat" v-for="c in cards" :key="c.k">
        <div class="k">{{ c.k }}</div>
        <div class="v">{{ c.v }}<small v-if="c.unit">{{ c.unit }}</small></div>
        <div class="sub">{{ c.sub }}</div>
      </div>
    </div>

    <div v-if="uncovered.length" class="panel">
      <div class="panel-head">
        <h2>高频未覆盖技能</h2>
        <span class="hint">多个岗位反复要求、但当前基底里没有</span>
      </div>
      <div class="pad-18 row-gap">
        <span class="badge bad" v-for="u in uncovered" :key="u.term">{{ u.term }} · {{ u.jobs }} 家</span>
      </div>
    </div>

    <div class="grid2">
      <div class="panel">
        <div class="panel-head">
          <h2>技能需求榜</h2>
          <span class="hint">家数 = 有多少岗位要求过</span>
        </div>
        <div v-if="s.statsLoading" class="pad-18"><div class="skel" v-for="n in 4" :key="n" style="margin:8px 0"></div></div>
        <div v-else-if="terms.length" class="bars">
          <div class="bar-row" v-for="t in terms" :key="t.term">
            <div class="name" :title="t.term">{{ t.term }}</div>
            <div class="track"><div class="fill" :style="'width:' + width(t.jobs, termMax)"></div></div>
            <div class="val">
              <span class="badge" :class="t.covered ? 'ok' : 'bad'">{{ t.covered ? '已覆盖' : '零覆盖' }}</span>
            </div>
          </div>
        </div>
        <div v-else class="empty">
          <svg width="46" height="46" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4">
            <rect x="3" y="4" width="18" height="16" rx="3"/><path d="M7 9h10M7 13h6"/>
          </svg>
          还没有岗位。先去「JD 入库」录一条，聚合才有意义。
        </div>
      </div>

      <div class="panel">
        <div class="panel-head">
          <h2>缺口热点</h2>
          <span class="hint">同一类差集在多少个岗位反复出现</span>
        </div>
        <div v-if="hot.length" class="bars">
          <div class="bar-row" v-for="(g, i) in hot" :key="i">
            <div class="name" :title="g.requirement">{{ g.requirement }}</div>
            <div class="track"><div class="fill warn" :style="'width:' + width(g.jobs, hotMax)"></div></div>
            <div class="val">{{ g.jobs }} 家</div>
          </div>
        </div>
        <div v-else class="empty">
          <svg width="46" height="46" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4">
            <path d="M12 3 3 7.5l9 4.5 9-4.5L12 3Z"/><path d="M3 12.5 12 17l9-4.5"/>
          </svg>
          暂无缺口记录。缺口只记「JD 明确要求但简历未覆盖」的差集。
        </div>
      </div>
    </div>

    <div class="grid2">
      <div class="panel">
        <div class="panel-head"><h2>基底表现</h2><span class="hint">用完的基底 × 投递结果</span></div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>基底</th><th>用了几次</th><th>已投</th><th>回复率</th><th>均分</th></tr></thead>
            <tbody>
              <tr v-for="b in perf" :key="b.code">
                <td><strong>{{ b.code }}</strong><div class="hint">{{ b.intent }}</div></td>
                <td class="num">{{ b.used }}</td>
                <td class="num">{{ b.applied }}</td>
                <td class="num">{{ b.reply_rate === null ? '—' : b.reply_rate + '%' }}</td>
                <td class="num">{{ b.avg_score }}</td>
              </tr>
              <tr v-if="!perf.length"><td colspan="5"><div class="empty">还没有登记基底</div></td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="panel">
        <div class="panel-head"><h2>城市分布</h2><span class="hint">投递重心落在哪</span></div>
        <div v-if="cities.length" class="bars">
          <div class="bar-row" v-for="c in cities" :key="c.city">
            <div class="name">{{ c.city }}</div>
            <div class="track"><div class="fill" :style="'width:' + width(c.count, cityMax)"></div></div>
            <div class="val">{{ c.count }}</div>
          </div>
        </div>
        <div v-else class="empty">
          <svg width="46" height="46" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4">
            <path d="M12 21s7-6.1 7-11a7 7 0 1 0-14 0c0 4.9 7 11 7 11Z"/><circle cx="12" cy="10" r="2.6"/>
          </svg>
          暂无城市数据
        </div>
      </div>
    </div>
  </div>`,
};
