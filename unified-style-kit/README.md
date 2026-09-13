# FAB 统一风格套件

把 `Advanced_Search_Cube`、`BOHAI_Bank_Manager_Assistant`、`njbank_Marketing_Campaign_Analysis`
三个前端统一成参考图（FAB 金融智能体加速器 / 智能营销页）的视觉语言。

**边界：只统一风格，不改排版。** 三个项目现有的导航结构、页面骨架、DOM 层级全部保留，
本套件只替换颜色、字号、圆角、阴影、描边、图标这一层。

> 原始三个项目的文件一个字都没改动。本文件夹是独立新增的。

---

## 1. 目录

```
unified-style-kit/
├─ README.md                    ← 本文件：迁移指南
├─ tokens/
│  ├─ design-tokens.css         ★ 唯一真源：所有色值/字阶/间距/圆角/阴影
│  └─ tokens.json               同一套 token 的 JSON 版（给 tailwind / JS 图表用）
├─ css/
│  ├─ base.css                  reset + 排版 + 文字工具类 + 图标规格
│  ├─ components.css            按钮/表单/卡片/表格/标签/提示/弹窗/导航构件/Hero/流程条/对话
│  └─ shells.css                五种外壳（都是三个项目**现有**排版的重新着色，不是新排版）
├─ assets/
│  └─ icon-sprite.html          22 个线性图标（24×24 网格、1.6 描边、currentColor）
├─ html/                        ← 双击即可打开，无任何外部依赖（内网可用）
│  ├─ index.html                套件首页
│  ├─ styleguide.html           ★ 设计规范总览：色板/字阶/间距/组件库/使用规则
│  ├─ landing-fab.html          参考图的标准实现（hero + 胶囊流程条 + 能力卡）
│  ├─ demo-topnav.html          BOHAI 排版皮肤样例
│  ├─ demo-iconbar.html         njbank 排版皮肤样例
│  ├─ demo-chat.html            Advanced_Search main/index.html 皮肤样例
│  ├─ demo-search.html          Advanced_Search main/Advanced_Search.html 皮肤样例（三栏）
│  └─ demo-sidebar.html         Advanced_Search admin/*.html 皮肤样例（四页同壳）
├─ react-tailwind/              ← 对应 BOHAI
│  ├─ tailwind.config.js        token → Tailwind theme 映射
│  └─ src/
│     ├─ index.css
│     ├─ ui/index.tsx           Button / Input / Card / Metric / Tag / Alert / Table…
│     ├─ layout/Layout.tsx      改皮后的顶栏外壳（排版与原版一致）
│     └─ pages/Dashboard.tsx    工作台样例
└─ vue/                         ← 对应 njbank
   ├─ fab-theme.css             ★ 最小改动方案：一个 .vue 都不用改
   └─ src/
      ├─ components/ui/*.vue    FabButton / FabCard / FabMetric / FabTag
      └─ views/HomeView.vue     首页样例
```

先看 `html/styleguide.html`，再看 `html/landing-fab.html`，其余按项目对号入座。

---

## 2. 统一后的核心取值

| 项 | 统一值 | Token |
|---|---|---|
| 交互主色 | `#2B6EDD` | `--color-primary` |
| 主色浅底 | `#EAF1FD` | `--color-primary-weak` |
| 主色描边 | `#BFD5F6` | `--color-primary-border` |
| 品牌蓝 / 青 / 紫 | `#0081E4` / `#02A6C9` / `#8D9DF8` | `--fab-brand-blue` / `--fab-brand-cyan` / `--color-violet` |
| 页面底 | `#FFFFFF` | `--bg-page` |
| 浅底区块 | `#F6F9FD` | `--bg-subtle` |
| 卡片描边 / 控件描边 / 行线 | `#E5EFF9` / `#D6E1F3` / `#EEF3FA` | `--border-base` / `--border-strong` / `--border-weak` |
| 文字三级 | `#191919` / `#4A4F58` / `#727472` | `--text-1` / `--text-2` / `--text-3` |
| 正文字号 | **14px / 1.6** | `--fs-body` |
| 圆角 | 控件 6–10px、卡片 14px、弹窗 20px、胶囊全圆 | `--radius-*` |
| 阴影 | 一律浅且带蓝调 `rgba(30,58,110,·)` | `--shadow-*` |
| Hero 渐变 | `#A4C7F0 → #C4DBF8 → #F2F6FB → #FFF` + 右上紫色径向 | `--gradient-hero` |

标志性形态：**全圆胶囊按钮**（白底 + 主色描边 + 主色字）、**点阵 chevron 流程连接器**、
**14px 圆角 + 极浅蓝描边 + 轻阴影的卡片**、**大留白**。

---

## 3. Advanced_Search_Cube 迁移

纯静态 HTML，样式内嵌在每个文件的 `<style>` 里，且**项目内部本来就有两套风格**
（主页深蓝渐变 + 青色点缀，后台 `#2563eb` + slate 灰阶）。

### 6 个页面分三类壳

| 页面 | 体量 | 排版 | 对照样例 |
|---|---|---|---|
| `main/index.html` | 125KB | 顶栏 + 消息流 + 底部输入 | `html/demo-chat.html` |
| `main/Advanced_Search.html` | 190KB | 顶栏 + **三栏**（左 240px 客群栏 / 对话主区 / 右 240px 会话栏）+ 含 MQL 开关的输入区 | `html/demo-search.html` |
| `admin/admin.html` | 107KB | 220px 深色侧栏（带 `.nav-group` 分组）+ 左偏移主区 | `html/demo-sidebar.html` |
| `admin/business_admin.html` | 50KB | 同上 | 同上 |
| `admin/ops_admin.html` | 31KB | 同上 | 同上 |
| `admin/tech_admin.html` | 25KB | 同上 | 同上 |

四个 admin 页共用同一套 `:root` 变量和同一个壳，所以改造时只需要改一次、复制四份。

### 步骤

1. 把 `tokens/design-tokens.css`、`css/base.css`、`css/components.css`、`css/shells.css`
   复制到 `Advanced_Search_Cube/html/css/`。
2. 在四个页面的 `<head>` 里按顺序引入这四个文件（放在原有 `<style>` **之前**）。
3. 把 `assets/icon-sprite.html` 的 `<svg>…</svg>` 内联到每个页面 `<body>` 开头。
   > 内网无 CDN，且 `file://` 下外部 sprite 的 `<use>` 会被浏览器拦截，必须内联。
4. 按下表替换原有 `<style>` 里的写死色值，再把 emoji 图标换成 `<svg class="i"><use href="#i-xxx"></use></svg>`。

> ⚠️ **改之前先看这条**：`main/index.html` 和 `main/Advanced_Search.html` 各有**两个
> `<style>` 块**，第二个整块覆盖第一个（第一个是旧的深蓝主题，第二个是现行的浅色
> 长春花蓝紫主题）。**要改的是第二个块**，改第一个块不会有任何效果。
> 建议顺手把第一个块删掉，否则以后每次改样式都要猜是哪一个在生效。
> 另外第一个块里的 `.welcome-suggestions` / `.welcome-suggestion-btn` 是死代码
> ——静态 DOM 与 JS 里都没有用到，欢迎屏只有一个球和一行标题。

### 色值对照（main/index.html + Advanced_Search.html）

| 原值 | 新值 | 说明 |
|---|---|---|
| `linear-gradient(135deg,#0f1b3d,#1a2a5e)` 顶栏 | `background: var(--bg-elevated)` + `border-bottom: 1px solid var(--border-base)` | 深色顶栏改为浅色 |
| `#2c7da0` 青色点缀 | `var(--color-primary)` | 统一主色 |
| `#f0f2f7 → #e8ecf4` 页面渐变底 | `var(--bg-page)`（纯白） | 参考图 hero 以下全白 |
| 用户气泡 `linear-gradient(135deg,#1a2a5e,#0f1b3d)` | `var(--color-primary)` | |
| 气泡 `border-radius: 18px` | `var(--radius-lg)`（14px） | |
| 输入区 `.input-area` 圆角 26px 悬浮条 | `.fab-inputbar`（圆角 `--radius-2xl`） | 悬浮形态与 `.input-tools` 浮于上方的布局保持不变 |
| `.welcome-title` 30px | `var(--fs-h1)`（28px） | |
| 正文 15px | `var(--fs-body)`（14px） | |
| emoji 图标 | 线性图标 sprite | **同页禁止 emoji 与线性图标混排** |

### Advanced_Search.html 独有构件对照

这一页比 `index.html` 多一层三栏骨架和一批检索专用构件，套件里都备好了对应实现：

| 原类名 | 新类名 | 视觉改动 |
|---|---|---|
| `.groups-sidebar` / `.sidebar-left` / `.sidebar-right` | `.fab-side` / `.fab-side--left` / `.fab-side--right` | 240px 宽度不变；`#e3e8f0` 描边 → `--border-base` |
| `.sidebar-header` | `.fab-side__header` | `#0f1b3d` → `--text-1` |
| `.group-item` / `-name` / `-meta` | `.fab-listitem` / `__name` / `__meta` | hover 底由青色改主色浅底；圆角 10px → `--radius-md` |
| `.spec-row` | `.fab-spec-row` | `#f2f6ff`/`#dbe6fb` → `--color-primary-weak`/`--color-primary-border` |
| `.query-overview` / `.qov-*` | `.fab-queryview` / `__type` `__row` `__k` `__v` | `#eef4ff` → `--bg-subtle`；值列改等宽字体 |
| `.thinking-step` / `-header` / `-content` | `.fab-think` / `__header` / `__body` | 保留折叠形态；`#c25b2c` 错误色 → `--color-warning` |
| `.suggestion-btn` / `.hot` | `.fab-chip-btn` / `.is-hot` | 青色渐变胶囊 → 主色描边胶囊（与参考图流程节点同形态） |
| `.result-column-tools` / `.result-pager` | `.fab-resulttools` | 合并为一条工具栏，分页复用 `.fab-pagination__btn` |
| `.group-tag-picker` / `-presets` / `-custom` | `.fab-tagpicker` / `__list` / `__custom` | 选中态由青色改主色浅底 |
| `.mql-toggle` | `.fab-switch` + `.fab-switch-inline` | `#2c7da0` → `--color-primary` |
| `.saved-group-banner` | `.fab-tag--pill fab-tag--primary` | 青色渐变实心 → 主色浅底胶囊标签 |
| `.markdown-body` | 复用 `.fab-table-wrap` + `.fab-table` | 表头渐变改 `--bg-subtle` 平涂 |
| `.identity-error-banner` | `.fab-alert fab-alert--danger` | |

### 色值对照（admin/*.html，四页通用）

| 原值 | 新值 |
|---|---|
| `--primary: #2563eb` | `#2B6EDD` |
| `--primary-light: #eff6ff` | `--color-primary-weak` `#EAF1FD` |
| `--primary-dark: #1d4ed8` | `--color-primary-hover` `#1F5BC4` |
| `--text-main: #1e293b` | `--text-1` `#191919` |
| `--text-sub: #64748b` | `--text-3` `#727472` |
| `--border: #e2e8f0` | `--border-base` `#E5EFF9` |
| `--bg: #f8fafc` | `--bg-subtle` `#F6F9FD` |
| `--danger: #dc2626` / `--success: #16a34a` | `--color-danger` `#D92B2B` / `--color-success` `#12A150` |
| 侧栏 `linear-gradient(180deg,#1e3a8a,#1e40af,#2563eb)` | `linear-gradient(180deg,#17499F,#1F5BC4,#2B6EDD)` |
| 卡片 `border-radius: 12px` | `var(--radius-lg)`（14px） |
| 正文 14px | 不变（已经是基准） |
| `admin.html` 的 `.nav-group` / `.nav-group-title` | `.fab-sidenav-group` / `__title` |

### 两个 main 页面的功能差异（迁移时别弄混）

| 功能 | `index.html` | `Advanced_Search.html` |
|---|---|---|
| 左右侧栏 | 无 | 左「会话记录」（刷新/清空）、右「我的客群」（刷新） |
| 顶栏 | 品牌 + 在线 | 品牌 + 身份 + 在线 + 「语义管理」外链 |
| 身份错误横幅 | 无 | 有 |
| 输入区工具 | 新会话 / MQL视图 / **用户ID** | 新会话 / MQL视图（无用户ID） |
| 消息操作 | 👍 / 👎 | 👍 / 👎 / 保存客群 / 客户洞察 |
| 弹窗 | 反馈意见 | 反馈意见 + 保存为客群（含标签选择器） |

对照页：`html/demo-chat.html`、`html/demo-search.html`、`html/demo-sidebar.html`。

---

## 4. BOHAI_Bank_Manager_Assistant 迁移

React + TS + Tailwind，`tailwind.config.js` 的 `theme.extend` 是空的，全在用原生调色板。

### 步骤

1. `react-tailwind/tailwind.config.js` → 覆盖 `frontend/tailwind.config.js`
2. `react-tailwind/src/index.css` → 覆盖 `frontend/src/index.css`
3. `react-tailwind/src/ui/index.tsx` → 放到 `frontend/src/ui/index.tsx`
4. `react-tailwind/src/layout/Layout.tsx` → 覆盖 `frontend/src/components/Layout.tsx`
   （排版与原版一字不差，只换了 className 的视觉取值）
5. 逐页把手写的 className 串换成 `ui/` 里的组件。
   `Workstation.tsx`(343KB)、`Settings.tsx`(138KB)、`Products.tsx`(101KB) 建议用下面的全局替换先扫一遍。

### 类名对照（可直接做全局替换）

| 原类名 | 新类名 |
|---|---|
| `text-blue-600` / `text-blue-700` / `text-blue-800` | `text-primary` |
| `bg-blue-600` / `bg-blue-500` | `bg-primary` |
| `bg-blue-50` | `bg-primary-weak` |
| `border-blue-500` | `border-primary` |
| `bg-gray-50`（页面底） | `bg-page` |
| `bg-gray-50`（区块浅底） | `bg-subtle` |
| `bg-gray-100` | `bg-sunken` |
| `text-gray-900` | `text-t1` |
| `text-gray-700` | `text-t2` |
| `text-gray-500` / `text-gray-600` | `text-t3` |
| `text-gray-400` | `text-t4` |
| `border` / `border-gray-200` | `border-line` |
| `border-gray-300` | `border-line-strong` |
| `rounded-md` / `rounded-lg` 混用 | 控件 `rounded-md`、卡片 `rounded-lg` |
| `shadow-sm` / `shadow-md` / `shadow-lg` 混用 | 静态 `shadow-xs`、hover `shadow-md`、弹窗 `shadow-lg` |
| `text-[10px]` / `text-xs`…`text-xl` 的响应式堆叠 | 统一 `text-xs` / `text-sm` / `text-base` / `text-h4`…`text-h1` |
| `bg-blue-500` `bg-green-500` `bg-purple-500` 图标色块 | 去掉色块，改线性图标 + `text-primary` 数值 |

### 注意

- 新 `fontSize` 只保留 10 档，**不要再写 `text-[10px]` 这类任意值**，
  写了会绕过规范（Tailwind 仍会生成，但违反约定）。
- 顶栏在 md~lg 之间把导航文字截成前 4 个字的行为**予以保留**（只把 `text-[10px]`
  换成字阶内的 `text-2xs`），不改变任何显示逻辑。
- 页面底由 `bg-gray-50` 改成纯白 `bg-page`，卡片靠描边和极轻阴影区分层次。

对照页：`html/demo-topnav.html`。

---

## 5. njbank_Marketing_Campaign_Analysis 迁移

Vue 3 + 手写 CSS。好消息是它已经把颜色抽成了 `:root` 变量，所以**改动量最小**。

### 步骤（推荐，一个 `.vue` 都不用改）

1. 复制 `vue/fab-theme.css` → `frontend/src/assets/fab-theme.css`
2. 复制 `tokens/design-tokens.css` → `frontend/src/assets/design-tokens.css`
   （并把 `fab-theme.css` 顶部的 `@import '../tokens/design-tokens.css'`
   改成 `@import './design-tokens.css'`）
3. `frontend/src/main.js` 里加一行：

   ```js
   import './assets/styles.css'
   import './assets/fab-theme.css'   // ← 在原样式之后
   ```

这一层做三件事：重映射旧变量、补上变量表达不了的字号/圆角/阴影、修掉原文件里约 30 处硬编码色值。

### 变量对照

| 旧变量 | 旧值 | 新值 |
|---|---|---|
| `--primary` | `#165DFF` | `#2B6EDD` |
| `--ph` | `#0E47CC` | `#1F5BC4` |
| `--pl` | `#E8F0FF` | `#EAF1FD` |
| `--danger` / `--d` | `#F53F3F` | `#D92B2B` |
| `--bg` | `#F7F8FA` | `#FFFFFF` |
| `--border` | `#E5E6EB` | `#E5EFF9` |
| `--t1` | `#1D2129` | `#191919` |
| `--t2` | `#4E5969` | `#4A4F58` |
| `--t3` | `#86909C` | `#727472` |
| `--r` | `6px` | `10px` |

### 还需要人工处理的

- 原 `styles.css` 里有约 30 处**没有走变量**的硬编码（`#00B42A`、`#FF7D00`、`#E8FFEA`、
  `#5B21AB`、`#C5D8FF`、`#c9cdd4` 等）。`fab-theme.css` 已经覆盖了其中绝大部分，
  但如果后续新增样式，请一律走 token。
- 原文件有**重复定义的段落**（`.mbk` / `.modal` / `.mh` / `.hmcards` / `.tpl-ph` 等各出现两次），
  建议顺手清理，否则以后改样式容易改到不生效的那一份。
- 类名极度缩写（`.sc` `.sh` `.fi` `.tb2`）已经影响可维护性。新页面建议用
  `vue/src/components/ui/*.vue` 里的 `Fab*` 组件，老页面保持不动。
- 正文由 13px 抬到 14px 后，紧凑型表格的行高会略增，注意检查一屏行数是否还满足需要。

对照页：`html/demo-iconbar.html`。

---

## 6. 落地检查清单

改完一个页面，对照这几条自查：

- [ ] 代码里没有写死的十六进制色值、`blue-600` 这类原生调色板类、`text-[10px]` 这类任意字号
- [ ] 一屏只有一个主按钮
- [ ] 同一层级元素的圆角一致（卡片全部 14px，控件全部 6–10px）
- [ ] 静态卡片阴影不超过 `--shadow-xs`；`--shadow-md` 只出现在 hover
- [ ] 同一页面只有一套线性图标，没有 emoji 混排
- [ ] 没有小于 11px 的文字（唯一例外：njbank 52px 图标栏的图标标签 9px）
- [ ] 留白都是 4 的倍数（卡内 20px、卡间 16px、区块间 48px）
- [ ] 渐变只出现在 hero / 品牌标识 / 深色侧栏，内容区是白底或 `--bg-subtle`
- [ ] 表格数值列右对齐并加了 `.num`（等宽数字）
- [ ] 键盘 Tab 能看到清晰的焦点圈
- [ ] 390px 窄屏下页面不产生横向滚动条（表格/图表各自在 `overflow-x:auto` 容器内滚动）
- [ ] **排版没变**：导航结构、页面骨架与改动前一致

---

## 7. 以后怎么调整风格

改 `tokens/design-tokens.css` 一个文件即可，三个项目跟着变。
如果同时改了色值，记得同步 `tokens/tokens.json` 和 `react-tailwind/tailwind.config.js`
（这两处是给 Tailwind 和 JS 图表用的镜像）。
