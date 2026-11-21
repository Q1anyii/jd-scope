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

## 5. 补充：通用简历工作台入口

反馈很直接：编辑器原先只能从岗位详情进，等于被藏起来了。

- 侧栏新增常驻「简历工作台」，点击即打开通用简历母版；不再需要先找一条岗位。
- 通用简历不是内存里的临时草稿，而是 `resumes/_通用简历/` 的独立档案：`resume.json` / `resume.html` / `strategy.md`。
- 数据模型：`companies.kind` 增 `general`（schema v3），母版在列表里置顶、带「通用」标；`POST /api/resume/general` 幂等，第一次自动建档，之后直接返回同一条。
- 删除保护：通用简历是母版，接口层拒绝删除记录；公司记录仍然「删记录、留文件夹」。
- 复用同一套编辑器桥接：`?company=<id>` 对母版一样成立，回写 / 导出 HTML 无需第二套代码。
- 文件夹优先复用已存在的 `_通用简历`（数据库丢了也能接管旧文件），没有才新建。
- 测试补 4 个：幂等、置顶且不可删、接管已有文件夹、HTTP 入口；总计 **56 用例全绿**。

## 6. 补充：编辑器 AI 接管 App 设置 + 页面宽度

第二条反馈：编辑器里还要另填一遍 API Key，而且主界面宽屏不跟着放大。

**AI 对齐 JD 不再单独配一套**

- 没有推倒重写编辑器：排版、分页、导出这些成熟逻辑重写风险大，桥接一层就够。
- 新增 `POST /api/editor/chat`：编辑器只发 `messages`，服务端从「设置」里取 `base_url` / `model` / `api_key` 调 `llm.chat()`，顺手补 `max_tokens` 与 `response_format=json_object`。
- Key 不进浏览器：嵌入模式不读编辑器的 `state.ai.key`，也不把 Key 写进页面；独立打开编辑器时仍保留原来的直连模式。
- 嵌入模式隐藏「API 设置」按钮和三个端点输入，只留一行只读提示 + 回设置页链接。
- 公司 `jd.txt` 在 bootstrap 时自动灌进「目标 JD」，省去从岗位详情复制一遍。

**布局**

- 根因不是 flex 写错，而是 `.main { max-width: 1320px }`：窗口放大时被钳住，缩小反而正常。
- 改为 `max-width: none` + flex column，主区吃掉侧栏外的全部宽度；`.cards` / `.grid2` / `.grid3` 换 `auto-fit + minmax`，窄屏媒体查询保留。
- 1920×1080 截图确认：概览 5 张统计卡铺满、公司表格贴右，无右侧大片留白。

**踩到的坑**

6. JD 预灌最初放在 `if(loaded)` 渲染之后，`state.ai.jd` 有值但设置面板已画完，输入框仍显示空占位；改为在 `renderEditor()` 之前赋值，空白档案分支补一次 `renderEditor()`。
7. 代理错误里 `error` 是字符串而不是 OpenAI 的 `{error:{message}}`，前端取值要兼容两种形状，否则只显示「HTTP 400」。

## 7. 补充：打印空白页、岗位信息编辑、导出后打开文件夹

**打印一页内容变成两页**

- 现象：A4 预览显示「单页 · 余 488pt」，打印机 / 另存为 PDF 却出两页，第二页是空白。
- 根因不是内容超长，而是打印 CSS 仍保留 `.page { min-height:297mm }`：A4 盒子的高度正好等于纸张高度，浏览器按 0.1px 的舍入差判成溢出，末尾多切一页。
- 修复：`@media print` 里把 `.page` 的 `min-height` / `height` 交还内容（`min-height:0; height:auto`），同时给 `html/body` 归零高度。
- 复现/验收：同一份 488pt 简历，修复前 `chrome --print-to-pdf` 生成 2 页，修复后 1 页。

**岗位信息可编辑**

- 详情抽屉新增「编辑信息」：公司名、岗位名、城市、来源、链接都能改；保存后 `PATCH /api/jobs/<id>` 更新并刷新详情与列表。
- 后端原来只允许 status / decision / city / url / source，这次把 `company` / `title` 加入白名单，并对空公司名、空岗位名直接拒绝。
- 只改元信息，不重算 JD 需求；改岗位名不会重命名已建的公司文件夹，避免误动用户文件。

**导出后的提示条带文件夹按钮**

- 编辑器提示条改成可带一个右侧动作按钮；`toast(msg, action)` 生成按钮并延长到 5.2s，按钮单独 `pointer-events:auto`，不影响其他 toast 点击穿透。
- 「保存简历 HTML 到公司档案」成功后，提示条右侧出现「打开文件夹」，调用 `POST /api/companies/<id>/open` 直接打开公司档案目录。
- 打印媒体里继续隐藏 `.toast`，按钮不会进 PDF。

## 8. 补充：去掉系统打印，改内置 PDF 预览，并归档到公司目录

**为什么不再走打印**

- 用户两次截图里 Chrome 打印预览都显示 2 页，而编辑器 A4 预览是一页；第一次是 `min-height:297mm` 顶满页底被 0.1px 舍入切出空白页，修完确实 1 页。
- 第二次是内容本身略微超过一页（9 个项目实测超出 1 页 281pt），打印预览如实显示 2 页；继续在打印 CSS 上打补丁只会让「预览一页、打印两页」的错位反复出现。
- 因此移除顶栏「打印 · 矢量」按钮和 `exportPdf()`，内置「导出 PDF」成为唯一 PDF 路径：先大窗预览，红色虚线标出 A4 分页位置，确认后直接生成文件，不再经过系统打印对话框。

**内置 PDF 导出的三个坑**

1. `openPdfPreview()` 原来先测量、后显示弹窗；`#pdfModal` 处于 `hidden` 时 `offsetHeight` 为 0，`pdfPageCount()` 把多页误判成单页。改为先 `hidden = false` 再测量，9 项目档案正确显示「共 2 页 · 按 A4 分页」。
2. `buildExportBox()` 原写死 `height:1122px; overflow:hidden`，超过一页的内容会被裁掉，多页切片分支实际是死代码。改成 `min-height:1122px; height:auto; overflow:visible`，让 canvas 拿到完整内容再切片。
3. 组件未加载时不再回退 `window.print()`，只提示检查网络；避免用户以为点的是内置导出，实际又弹回打印窗口。

**PDF 归档公司目录**

- 新增 `POST /api/companies/<id>/pdf`：前端把 jsPDF 的 Blob 转 base64 上传，服务端校验长度、`%PDF` 文件头与 32MB 上限后写入公司文件夹的 `resume.pdf`。
- 已有 `resume.pdf` 时 `save_pdf()` 直接返回 `skipped: true`，不覆盖旧文件；岗位/公司回到 `exported` 状态，`detail().files.pdf` 与公司列表的「PDF」徽标同步亮起。
- 编辑器导出流程：`pdf.save()` 先落地本地下载，再 `archiveCompanyPdf()` 上传归档；成功提示「PDF 已下载，并归档到公司文件夹：resume.pdf」，右侧仍带「打开文件夹」按钮；已有文件时提示「未覆盖」。
- 嵌入公司档案时「导出 HTML」按钮继续隐藏，避免与公司条的「保存简历 HTML 到公司档案」重复；独立打开编辑器仍保留本地 HTML 下载。

## 9. 补充：设置页可改两类模型提示词

**需求**

设置页「模型端点」下要能直接改提示词，并区分 JD 分析与简历改写；两页都要能滚动，长提示词不能把设置页撑爆。

**实现**

- 数据库 `settings` 新增两个键：`prompt_jd_analysis`、`prompt_resume_rewrite`；空字符串表示「用内置默认」，保存时如果内容与默认原文一致也自动清空，避免出现「看着是自定义、实际没变」。
- `llm.py` 导出 `DEFAULT_PROMPTS` 与 `PROMPT_LABELS`，新增 `_effective_prompt()`：有自定义值就用自定义，否则回落 `SYSTEM_PARSE` / `SYSTEM_SUGGEST`。
- `parse_jd_items()` 与 `suggest_rewrite()` 的 system message 改为读取配置里的提示词；`settings_dict()` 把当前值与默认原文一并下发，前端不需要另存一份文案。
- 设置页新增两个页签：「JD 分析提示词」用于「JD 入库」的 AI 解析，「简历改写提示词」用于岗位详情「生成改写建议」；每个 textarea 固定高度、`overflow-y:auto`，长内容在框内滚动。
- 操作：保存提示词、填入默认（把默认原文灌进输入框，再点保存即恢复）、未保存修改提示；后端 20000 字符上限，超长直接拒绝。
- 明确边界：编辑器里的 AI 对齐仍使用编辑器自己的 System Prompt；设置页这两个只控制主程序的两类任务，避免两套 schema 混用导致 JSON 解析失败。

**验收**

- 66 用例全绿；新增 3 个：默认值与保存/恢复、超长拒绝、自定义提示词确实进入 `messages[0]`。
- 临时实例截图确认两个页签都能切换，textarea 固定高度且可滚动；`POST /api/settings` 保存后 `GET` 能读回，自定义值真实生效。

## 验收

- `python -m unittest discover -s tests`：**66 用例全绿**（新增 PDF 归档与设置页提示词：首次写入、二次 `skipped` 且内容不变；提示词默认、保存、恢复与模型注入）。
- 打印：修复前 2 页 / 修复后 1 页（同一份 488pt 简历，Chrome `--print-to-pdf`）。
- 内置 PDF：9 项目档案预览显示 2 页，导出文件实际 2 页（`/Type /Page` 计数），归档 `resume.pdf` 1,321,370B；再次上传同公司返回 `skipped: true`，文件 mtime 与内容不变。
- 早前端到端实测：HTML 基底 → 建档 → 打开编辑器 → 自动解析出 2 个模块（姓名「张三」）→ `resume.json` 落盘 3555B → `base.html` 已删除。
- 截图：`docs/ui-companies.png`、`docs/ui-editor.png`；另以 1920×1080 检查宽屏铺满。
