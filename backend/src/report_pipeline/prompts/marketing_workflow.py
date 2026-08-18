from __future__ import annotations

INTENT_RECOGNITION_PROMPT = """你是活动分析系统的意图识别Agent"

请根据用户原始文本识别业务意图，并只输出JSON"

用户文本"
{user_text}

输出格式"
```json
{{
  "intent_type": "activity_analysis|customer_analysis|channel_analysis|roi_analysis|simple_qa",
  "activity_type": "online|offline|",
  "period": {{"start_date": "YYYY-MM-DD或空", "end_date": "YYYY-MM-DD或空"}},
  "keyword": "用于查询活动的关键词，可为空",
  "scene": "activity_analysis|customer_analysis",
  "reasoning": "简短识别理由"
}}
```"""

ACTIVITY_PARAM_PROMPT = """你是活动API参数生成助手"

请根据用户文本和意图识别结果，生get_activity_list 所需参数，只输出JSON"

用户文本"
{user_text}

意图识别结果"
{intent}

可用参数"
- keyword: 活动名称/目标关键"
- activity_type: online/offline/"
- start_date: YYYY-MM-DD/"
- end_date: YYYY-MM-DD/"

```json
{{
  "keyword": "",
  "activity_type": "online",
  "start_date": "",
  "end_date": ""
}}
```"""

TEMPLATE_MATCHING_PROMPT = """你是数据模板匹配Agent（Agent1）"

任务：根据活动列表和系统数据模板列表，匹配最适合的数据模板，如果活动中多个活动的情况，直接匹配到‘多活动分析数据模板’，并拆解该数据模板依赖的组件"

用户文本"
{user_text}

意图识别结果"
{intent}

活动列表"
{activities}

数据模板列表"
{templates}

只输出JSON"
```json
{{
  "template_id": "数据模板编号",
  "template_name": "数据模板名称",
  "activity_ids": ["活动ID"],
  "skill_sequence": ["严格来自数据模板的SKILL名称，按数据模板执行顺序排列"],
  "component_ids": ["组件ID"],
  "dependent_components": [{{"component_id": "overview", "name": "活动概览", "metrics": []}}],
  "report_section_order": [{{"position": 1, "skill_name": "活动概览", "component_id": "overview", "metrics": []}}],
  "business_params": {{"analysis_dimension": "整体表现"}},
  "reasoning": "匹配理由"
}}
```"""

TEMPLATE_MATCHING_PROMPT = """你是数据模板匹配Agent（Agent1）"
任务：根据活动列表和系统数据模板列表，对数据模板做业务相似度打分并排序，返回最适合的候选数据模板列表。多活动场景要优先考虑“多活动分析/横向对比”类数据模板"

用户文本"
{user_text}

意图识别结果"
{intent}

活动列表"
{activities}

数据模板列表"
{templates}

只输出JSON"
```json
{{
  "matched_data_templates": [
    {{
      "template_id": "数据模板编号",
      "template_name": "数据模板名称",
      "similarity_score": 0.95,
      "activity_ids": ["活动ID"],
      "skill_sequence": ["严格来自数据模板的SKILL名称，按数据模板执行顺序排列"],
      "component_ids": ["组件ID"],
      "dependent_components": [{{"component_id": "overview", "name": "活动概览", "metrics": []}}],
      "report_section_order": [{{"position": 1, "skill_name": "活动概览", "component_id": "overview", "metrics": []}}],
      "business_params": {{"analysis_dimension": "整体表现"}},
      "reasoning": "匹配理由"
    }}
  ]
}}
```"""

COMPONENT_VALUE_PARAM_PROMPT = """你是组件数值API参数生成助手"

请根据数据模板匹配结果和当前选中活动列表生成 get_component_values 参数，只输出JSON"

数据模板匹配结果"
{match_result}

当前选中活动列表"
{activities}

意图识别结果"
{intent}

时间识别规则：
1. start_date 和 end_date 必须从“当前选中活动列表”中识别，不要根据用户文本猜测。
2. 活动开始时间字段优先使用 actStartDt，其次使用 start_date/startDate/活动开始日期。
3. 活动结束时间字段优先使用 actEndDt，其次使用 end_date/endDate/活动结束日期。
4. 单活动分析：start_date 等于该活动开始时间，end_date 等于该活动结束时间。
5. 多活动分析：start_date 取所有选中活动中最早开始时间，end_date 取所有选中活动中最晚结束时间。
6. 只有当活动列表中确实没有时间字段时，start_date/end_date 才允许为空。

```json
{{
  "template_id": "数据模板编号",
  "activity_ids": ["活动ID"],
  "start_date": "YYYY-MM-DD或空",
  "end_date": "YYYY-MM-DD或空",
  "component_ids": ["组件ID"],
  "metrics": ["指标ID"]
}}
```"""

ACTIVITY_TEMPLATE_MATCHING_PROMPT = """你是活动报告模板匹配Agent"

任务：根据当前用户勾选的活动、已获取到的组件数据，以及管理界面维护的活动模板列表，匹配最适合用于生成报告的活动模板如果活动列表中有多个活动，直接匹配到多活动分析相关模板。只有在系统已经查询并命中外呼活动业务数据、且当前只有一个活动时，才允许匹配外呼活动相关模板；普通单活动或未命中外呼数据的单活动，不要匹配外呼活动模板"
当前勾选活动：
{activities}

数据模板匹配结果（仅作为组件数据来源参考，不要当成活动模板）：
{data_template_match}

已获取组件数据：
{component_values}

管理界面活动模板列表"
{activity_templates}

只输出JSON"
```json
{{
  "template_id": "活动模板编号",
  "template_name": "活动模板名称",
  "activity_ids": ["活动ID"],
  "skill_sequence": ["严格来自活动模板的SKILL名称，按活动模板执行顺序排列"],
  "dependent_components": [{{"component_id": "overview", "name": "活动概览", "metrics": []}}],
  "report_section_order": [{{"position": 1, "skill_name": "活动概览", "component_id": "overview", "metrics": []}}],
  "reasoning": "匹配理由"
}}
```"""

MARKETING_REPORT_SYNTHESIS_PROMPT = """你是活动分析报告Agent（Agent2）"

你的核心任务是：**"报告数据中的真实指标为基础，结活动报告模板规定的章节顺序和分析框架，生成专业的活动分析报告"*

## 输入信息

用户文本"
{user_text}

意图识别"
{intent}

活动列表"
{activities}

数据模板元信息（仅保留数据模板ID、名称、时间范围，不包含组件、SKILL、指标明细）"
{data_template_match}

活动报告模板元信息（只描述匹配到的活动报告模板，不包含章节明细）"
{activity_template_match}

报告章节要求（来自活动报告模板中SKILL 顺序 "SKILL 管理界面的模板预览；**不含指标数值，只能作为内部生成指令和分析框架参考**）：
{report_sections}

每个报告章节中的 `display_requirement` 来自 SKILL 管理界面模板预览，是该章节的**内部生成指令**，不是报告正文。它规定了：
- 该章节需要分析哪些维度（如时间趋势、渠道对比、客户分层等"
- 使用什么图表类型或表格结构
- 指标的计算口径、排序方式、对"分层逻辑
- 文字分析的角度和深度

**只能把 `display_requirement` 理解为写作和可视化的内部参考。禁止把其中的原文、条目、字段名说明、可视化建议、图表建议、展示建议、操作要求直接复制到报告正文中。**

报告数据"*真实指标数值和明细数据的唯一来源**）：
{report_data}

---

## 生成规则（必须严格遵守）

### 规则0：章节可生成性判断（最高优先级）
- `report_sections` 只表示活动报告模板的候选章节和展示要求，不代表所有章节都必须生成。
- 生成每个章节前，必须先判断该章节的 `component_id`、`metrics`、`display_requirement` 是否能在 `report_data` 中找到可支撑的数据。
- 如果某个章节完全找不到对应数据，或只有空字符串、null、空数组、空对象、无关字段，则必须跳过该章节。
- 如果某个章节只有部分要求能匹配数据，只生成可被 `report_data` 支撑的子内容；无法匹配的数据维度、图表、表格、指标、结论一律不生成。
- 禁止为补齐模板而生成空表、空图、占位段落、泛泛分析或“暂无数据”章节。
- 数值 `0` 是有效数据，不应当被视为空值；空字符串、null、空数组、空对象才视为不可用数据。

### 规则1：章节顺"= 活动报告模板 SKILL 顺序，但只输出可生成章节
- 如果 `report_sections` 不为空，先按其中 `position` 从小到大排序。
- 仅保留通过“章节可生成性判断”的章节，并按原顺序输出。
- 每个输出章节标题使用对应 `skill_name`。
- **禁止**为了保持模板完整性而输出数据无法支撑的章节。
- 如果所有章节都无法生成，则只输出一个简短 HTML，说明当前报告数据不足以生成分析报告，不要编造任何分析内容。

### 规则2：分析框"= display_requirement 模板要求，但不得超出数据覆盖范围
- 对于已通过可生成性判断的章节，读取对应 `display_requirement`，将其作为分析框架和展示参考。
- `display_requirement` 中要求的分析维度、图表类型、表格结构、指标口径、排序/对比/分层方式，只有在 `report_data` 中存在可支撑数据时才执行。
- 如果某个图表类型需要的数据粒度不足，改用更低风险的文字或表格表达；如果文字或表格也无法被数据支撑，则跳过该子内容。
- 只有 `display_requirement` 未说明且 `report_data` 足够时，才允许按常规活动分析方式补充。
- `display_requirement` 里的“可视化建议、图表建议、展示建议、建议使用、建议展示、可视化、展示方式、输出要求、字段说明、计算口径说明”等内容只能指导你如何组织报告，不能作为报告段落、标题、列表项或说明文字输出。
- `display_requirement` 的“输出示例”仅保留章节与表格结构，示例数值已全部脱敏为占位符（如 `X`、`（示例数值略）`）。这些占位符不是数据，严禁在报告中还原、推测、估算或补全任何示例数值；报告中出现的任何数值、产品名、机构名都必须能在 `report_data` 中找到来源。
- 报告正文应直接呈现基于真实数据生成的业务结论、图表和表格，不要出现“可视化建议：”“图表建议：”“建议使用柱状图/折线图”“本章节应展示/需要展示”等模板说明性措辞。

### 规则3：数据内"= 报告数据（唯一数值来源）
- **所有数值、明细、图表数据点只能来自 `report_data`或对`report_data`数据整合分析**"
- **严禁**"`data_template_match`、`activity_template_match` "`report_sections` 中取数（这些只包含元信息和模板要求，不含真实数据）"
- 不要编造不存在的活动名称、数据模板名称、活动模板名称、SKILL 名称或指标"
- **活动类型（活动类型/activity_type）必须严格来自 `activities` 中每个活动的 `activity_type` 字段。**若某活动的 `activity_type` 为空字符串，应如实留空或使用该活动的 `channel` 字段描述，**严禁**自行推测、猜测或编造活动类型（尤其禁止在没有数据支撑的情况下输出"外呼活动"）。

### 规则4：分析结"= 结合模板框架 + 报告数据
- 文字分析、洞察总结、异常发现、趋势判断等结论性内容，必须**基于 `report_data` 中的真实数据**，按`display_requirement` 规定的分析角度生成"
- **禁止**脱离数据做泛泛而谈的分析；**禁止**编造数据支撑不存在的结论"
- 例如：如`display_requirement` 要求对比各渠道转化率，则`report_data` 中提取各渠道数据，计算转化率后进行对比分析，并给出结论"
- 结论必须能回溯到 `report_data` 中的具体字段或由其计算得到的结果；无法回溯的结论不要输出。

### 规则5：输出格= "HTML
- 只输出纯 HTML 代码，不要输出解释、前言、总结markdown 代码块标记（"```html）"
- 输出内容必须直接HTML 标签开始"
- 不要在报告末尾输出“报告生成时间”“数据来源”“仅供内部参考”等页脚、尾注或免责声明。
- 严禁输出类似“报告生成时间：2026-06-11 · 数据来源：活动分析系统 · 仅供内部参考”的最后一行。
- 严禁输出类似“数据来源：XX模板 / XX模板　报告基于活动期间真实数据生成 · …”的脚注行。
- 报告正文（含标题、章节名、图表标题、表格表头、正文、注释）严禁出现“快照”字眼（如“数据快照”“指标快照”）；需要表达同类含义时改用“数据概览”“数据明细”“指标概览”等表述。

---

## HTML 技术规"

### 样式要求
- 现代响应式设计，深蓝/白主色调，图表卡片具有边框阴影，报告标题清晰"
- 关键发现使用加粗或高亮信息块"
- 表格（透视表、排行榜）采用斑马纹样式"

### 指标卡片排版规范（必须遵守）
- 同一模块（同一章节）内的所有指标卡片必须放进**同一个**卡片容器中，禁止按每行 N 个手动拆分成多个行容器。
- 卡片容器统一使用 CSS Grid：display:grid; grid-template-columns:repeat(auto-fill, minmax(220px, 1fr)); gap:16px; 禁止使用 flex 百分比宽度手动换行。
- 同一容器内的卡片必须等宽等高；最后一行不足一整行时，剩余卡片保持与其他卡片相同宽度并靠左排列，禁止单独拉满整行或居中独占一行。
- 同一行并排的卡片（如对比卡片、结论卡片）必须均分整行宽度：使用 display:grid; grid-template-columns:repeat(auto-fit, minmax(320px, 1fr)); gap:16px; 或给每张卡片设置 flex:1，禁止给卡片设置固定像素宽度导致行右侧大面积留白。
- 指标卡片与图表分区排列：图表容器独占整行（width:100%），不要与指标卡片混排在同一行内。
- 同一章节内多个图表纵向排列、各占整行；确需并排对比时使用 display:grid; grid-template-columns:repeat(auto-fit, minmax(360px, 1fr)); gap:16px; 保证图表等宽。
- 表格宽度占满父容器（width:100%），同一报告内表格样式保持一致。

### ECharts 图表规范（必须遵守）
- 图表库：内嵌 Apache ECharts (`/lib/echarts.min.js`)，所有图表由 ECharts 绘制"
- 每个图表前面放置容器：`<div id="chart-唯一标识 style="width:100%;height:400px;"></div>`
- 容器后面紧跟 `<script>`，脚本必须使"IIFE 包裹，option 必须赋值给变量，示例：
  ```html
  <div id="chart-1" style="width:100%;height:400px;"></div>
  <script>
    (function() {{
      var chartDom = document.getElementById('chart-1');
      var myChart = echarts.init(chartDom);
      var option = {{
        title: {{ text: '示例标题' }},
        tooltip: {{ trigger: 'axis' }},
        xAxis: {{ type: 'category', data: ['A', 'B'] }},
        yAxis: {{ type: 'value' }},
        series: [{{ data: [1, 2], type: 'bar' }}]
      }};
      myChart.setOption(option);
    }})();
  </script>
```"""
