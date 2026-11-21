# 2026-11-21 第三阶段：AI 候选、公司档案、内嵌编辑器

三条需求的共同点是「别让系统替用户拍板」。落地时按这个原则做取舍：

## 1. AI 只出候选，勾选才入库

- 新增 `POST /api/jobs/parse-ai`：调模型拆 JD，返回条目（正文 / 分类 / 优先级 / 术语 / 理由），**不写库**。
- 服务端同时跑一遍规则解析，给每条候选打 `duplicate` 标记（规则已识别的），前端默认不勾；用户仍可手动勾。
- 入库沿用原 `POST /api/jobs`，多一个 `ai_items` 字段：只把勾选的条目并进 `parsed["requirements"]`，再走同一套 `evaluate()`，所以 AI 条目和规则条目**同构**，一样参与打分、一样生成缺口。
- `requirements` 增加 `source`（`rule` / `ai`），详情页给 AI 条目单独挂 `AI` 徽标。
- 重算（`POST /api/jobs/{id}/analyze`）会先读回该岗位 `source='ai'` 的条目再合并，否则一重算就全丢——这是本轮修的一个逻辑坑。
- 面试口径改为「候选」：`/api/gaps/{id}/answer` 不再直接 `UPDATE`，前端给可编辑 textarea，「采用」才 PATCH 写库。
- 改写建议原本就是「未采用 / 已采用」状态，保持不变。

## 2. 公司档案：一家公司一个文件夹

`app/companies.py`，落在当前数据目录的 `resumes/<公司名>/`：

```
jd.txt          JD 原文
strategy.md     策略骨架（结论 / 四维 / 缺口 / 改写与投递动作），可直接编辑
report.md       建档时的分析摘要
resume.json     编辑器完整状态（事实源）
resume.html     导出的成品快照
base.html       HTML 基底原文，编辑器首次导入后删除
```

- 同名公司自动加 `-2`、`-3`，绝不覆盖已有目录。
- 数据库只存文件夹名（`companies.folder`），不存绝对路径，换数据目录/换机器都能用。
- 删除只删数据库记录，文件夹保留——简历是资产，不能跟着一条记录消失。
- `strategy.md` 自动写入岗位结论、四维百分比、前 6 条必备要求（AI 条目带「（AI）」）、缺口清单，等于把既有定制工作流的骨架搬进产品里。

## 3. 内嵌编辑器

- 原文件 `简历编辑器.html` 整份复制为 `app/web/editor/index.html`（148KB，单文件、无外部依赖），静态路由补了「以 `/` 结尾 → `index.html`」。
- 只打四处补丁：
  1. `STORE_KEY` 加 `:company-<id>` 命名空间，多家公司草稿互不覆盖；
  2. `save()` 里追加 900ms 防抖 POST `/api/companies/<id>/resume`；
  3. 启动序列后异步 bootstrap：先读 `resume.json`；没有就读 `base.html`，复用编辑器自带 `parseResumeHtml()` 解析，成功后调 `adopt-base` 删掉基底文件；
  4. 顶栏加公司条：公司名、回写状态、`← JDScope`、`保存简历 HTML 到公司档案`。
- 隐私处理：回写前把 `state.ai.key` 置空，API Key 只留本机 localStorage；重新载入服务端状态时，若服务端 key 为空则沿用本机 key，本次会话仍可用编辑器自带的 AI 对齐。
- 事实源选 `resume.json` 而不是 HTML：HTML 无法无损再编辑，JSON 可以反复改，导出 HTML 只是投递快照。

## 4. 数据模型 v2 迁移

`SCHEMA_VERSION = 2`，`COLUMN_PATCHES` 在 `init_db()` 里用 `PRAGMA table_info` 检测后 `ALTER TABLE ADD COLUMN`：

- `bases.kind`（`html` / `json`）
- `requirements.source`（`rule` / `ai`）
- 新表 `companies`

老库升级不清数据：迁移测试里直接造了一个 v1 表结构的库，升级后数据仍在、新列有默认值、`schema_version` 变 2。

## 踩到的坑

1. `jobs` 表没有 `verdict_reason` 列，理由存在 `score_json` 里；`_report()` 直接取列导致 `IndexError`。改为解析 `score_json`。
2. 编辑器启动是同步 `renderEditor→applyLayout→renderPreview→applyZoom`，异步注入 state 必须在之后**手动再跑一遍**这四个，并补 `checkOverflow()`；否则预览是空的。
3. 编辑器「导入 HTML」原本会弹 `confirm`，桥接里不能复用整段交互，只复用 `parseResumeHtml()` 的纯解析结果。
4. 公司页操作列 4 个按钮在 `flex-wrap: wrap` 的容器里被压成竖排；新增 `.actions`（`flex-wrap: nowrap`）修正。
5. 无头 Chrome 复用已有实例时 `--dump-dom` 会静默返回空；必须带独立的 `--user-data-dir`。

## 验收

- `python -m unittest discover -s tests`：**52 用例全绿**（新增 15：公司档案文件/接口/v2 迁移、AI 条目收敛与重算保留）。
- 端到端实测：HTML 基底 → 建档 → 打开编辑器 → 自动解析出 2 个模块（姓名「张三」）→ `resume.json` 落盘 3555B → `base.html` 已删除。
- 截图：`docs/ui-companies.png`、`docs/ui-editor.png`。
