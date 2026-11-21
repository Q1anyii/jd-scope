# 2026-11-21 · 前端换代 + 数据目录可自定义

第二轮：把 743 行的原生 DOM 拼装换成 Vue 3，并把「数据只能待在默认目录」这件事解决掉。

## 1. 前端上车 Vue，但不引入构建链

原本的 `app.js` 是 743 行模板字符串 + 每次操作整块重写 `innerHTML` + 事后重新绑事件。
页面一多，这种写法的维护成本是线性上升的：新增一个筛选条件，就要同时改渲染、改空态、改事件重绑。

选型：**Vue 3.5.13 全局构建**（`vue.global.prod.js`，157 KB，MIT，放进 `app/web/vendor/` 随仓库分发）。
理由：
- 是真正的框架（响应式、组件、模板编译），不是手写状态机；
- **没有 Node、没有 build 步骤**——页面由 7 个可读的 `.js` 模块组成，改完刷新就生效；
- 打包仍然是 `--add-data app\web` 一把带走，`git clone` 即可构建，不依赖 npm registry；
- 离线可用，不引 CDN，符合「本地单机」的定位。

代价：`vue.global.prod.js` 走运行时模板编译（`new Function`），确定没有 CSP 限制的场景才安全。本工具只监听 127.0.0.1 且不加载外部内容，可以接受。

结构：`js/api.js`（请求层）、`js/store.js`（唯一 reactive 状态 + 加载动作）、`js/pages/*.js`（6 个页面组件）、`js/main.js`（壳）。
详情抽屉用 `<Teleport to="body">` 挂到 body，避免被父级 overflow 裁掉；`?view=` / `?job=<id>` 支持直达，方便排查与截图。

## 2. 数据目录可自定义：指针与数据必须分开

需求是「设置里能把数据放到别的位置」。这里有个鸡生蛋问题：
如果把「用户选的数据目录」存在数据库里，那么数据库自己在哪就取决于这个设置——先有鸡还是先有蛋。

处置：两层路径。
- `config_root()`：固定位置（`%LOCALAPPDATA%\JDScope`），只放 `location.json`；
- `data_home()`：数据库、报告、备份的实际位置，优先级 `JDSCOPE_HOME` > `location.json` > 配置根。

新增 `app/location.py` 负责切换的完整流程：规范化 → 建目录 → 写测试文件验可写 → 判定目标是空目录还是已有库 → 迁移或接管 → 打开目标库并建表验证 → 原子写指针。
**每一步验证都在写指针之前**，所以切换失败时指针一定还指向原来那个能用的目录。

两个语义刻意分开：
- 目标目录是空的 + 勾选迁移 → 复制数据库（先 `wal_checkpoint(TRUNCATE)`，失败则连 `-wal/-shm` 一起复制）与 `reports/`、`backups/`；
- 目标目录已有数据库 + 勾选迁移 → **报错拒绝**，不覆盖任何文件；取消勾选则「接管」该目录现有数据。
- 「恢复默认」反向同理：默认目录已有旧库就接管，没有就把当前数据复制回去。

数据库连接是「每请求新建、用完即关」（原本就是这样），所以切换后不需要重启进程，下一次请求自然连到新库。

## 3. Windows 8.3 短名把路径改写了（自测发现）

`Path.resolve()` 在 Windows 上会把 `D:\CacheMigration\...` 解析成 `D:\CACHEM~1\...`，
于是界面显示出一个用户从没见过的路径，测试里 `data_home() != 预期` 也全红。

处置：改用 `os.path.abspath(expanduser(...))`，不做符号链接解析；路径比较单独用 `normcase + abspath`，
避免大小写与尾斜杠造成的「看起来不同其实相同」。

## 4. 岗位列表的「缺失项」恒为 0（重写前端时才暴露）

`/api/jobs` 的 SELECT 列表里没有 `score_json`，但后面又对它做 `json.loads(...)`，
结果每一行的 `score_json` 永远是 `{}`，前端算 `coverage.missing` 永远是 0。

处置：SELECT 补上 `score_json`；同时给列表加了排序白名单（`score` / `score_asc` / `newest` / `oldest`），
拒绝把参数直接拼进 SQL。

## 5. 验证时的两个环境坑

- `Start-Process -WindowStyle Hidden` 会把 pywebview 的窗口一起隐藏，
  枚举窗口时看着像「启动失败」。验证窗口要用普通启动，只有 `--serve-only` 才适合隐藏。
- 无头 Chrome 的 `--screenshot` 只能截首屏，无法点击。给页面加了 `?view=` 与 `?job=<id>` 直达参数，
  各页面与详情抽屉都能被独立截图核对（5 个页面 + 抽屉均已肉眼确认）。WebView2 里的真实渲染另用 `PrintWindow` 抓窗口位图确认。

## 6. 其它

- 删除旧前端 `app/web/app.js`、`app/web/style.css`；测试里对 `/app.js` 的断言改为 `/js/main.js` 与 `/vendor/vue.global.prod.js`。
- 新增 13 个数据目录用例（迁移 / 接管 / 冲突拒绝 / 环境变量锁定 / 指针损坏回退 / 接口冒烟），全量 37 个用例通过。
- 版本号 `0.1.0 → 0.2.0`。
