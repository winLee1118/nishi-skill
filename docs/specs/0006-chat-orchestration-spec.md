# 0006 聊天编排与调用契约 Spec

## 1. 目标

把「问题路由、工具调用、提示词组装、输出格式契约」全部收敛到 Python skill 层的统一入口 `nihaixia_mcp.orchestrator.chat_orchestrate`，让任何调用方（桌面应用、微信小程序后端、CLI、其他 Agent）都不需要自己实现编排逻辑。

`apps/desktop` 是这个契约的标准示例：它只做「传参 → 拿 messages → 调自己的 LLM → 清洗 → 流式输出」。

## 2. 聊天输出格式契约

聊天通道（含 TTS）输出纯对话文本：

```text
不用 # 井号标题
不用 ** 星号加粗
不用 1. 2. 3. 数字加点编号列表
不用表格、项目符号、代码块
需要分点时用口语串联着讲（先讲哪个、再讲哪个、最后补一句）
```

这条规则有三层保障：

1. skill 草稿层：`answer_with_citations(output_format="chat")` 默认产出口语化草稿，医疗追问等内容写成连续的问句，不再用编号清单。
2. 提示词层：`nihaixia_core.persona.CHAT_FORMAT_RULES` 注入 `style_prompt`、`instructions` 和编排后的 system prompt。
3. 清洗兜底层：`nihaixia_core.chat_text.sanitize_chat_text`（Python）与 `apps/desktop/src/lib/chatText.ts`（TS 镜像）在最终输出和 TTS 入口去除残余 Markdown 符号，行首编号转为「一是/二是」等口语连接词。

需要旧的结构化草稿时，调用方可显式传 `output_format="report"`。

## 3. 统一入口

### 3.1 三种接入方式

```text
1. Python import：
   from nihaixia_mcp.orchestrator import chat_orchestrate
   result = chat_orchestrate("现在的天干地支是什么", history=[...])

2. MCP 工具（nihaixia-system 服务上的 chat_orchestrate）：
   适合 Codex / Claude / Cursor 等 Agent 直接调用。

3. 子进程 JSON（非 Python、非 MCP 的调用方，如 Node.js）：
   echo '{"question": "..."}' | python -m nihaixia_mcp.orchestrator
   或安装包后使用 nihaixia-chat 命令。
```

环境变量与现有约定一致：`NIHAIXIA_DB`、`NIHAIXIA_GRAPH`、`RAG_MODE`、`PYTHONPATH`。

### 3.2 输入字段

```json
{
  "question": "用户问题（必填）",
  "history": [{ "role": "user|assistant", "content": "..." }],
  "timezone": "Asia/Shanghai",
  "domain": "auto | renji | tianji | diji | cross",
  "top_k": 5,
  "mode": "auto | fts | hybrid",
  "style_intensity": "none | low | medium | high"
}
```

`history` 取最近 8 条；用于追问理解（“你直接告诉我”“继续说”）、出生信息回溯和领域分类兜底。

### 3.3 返回契约

```json
{
  "route": "bazi | answer | error",
  "answer_draft": "口语化回答或草稿",
  "draft_is_final": true,
  "messages": [
    { "role": "system", "content": "..." },
    { "role": "user", "content": "..." }
  ],
  "citations": [],
  "meta": {
    "domain": "tianji",
    "persona": {},
    "safety_notes": [],
    "medical_intent": "none",
    "retrieval_info": {},
    "evidence_plan": {},
    "style_plan": {},
    "safety_plan": {},
    "persona_composition": {},
    "skill_invocation": {},
    "skill_result": {}
  }
}
```

字段语义：

```text
route            # 命中的路由：八字排盘、知识问答（含时间底座注入）、错误
draft_is_final   # true 表示 answer_draft 已是最终回答（确定性工具产出，不需要 LLM）
messages         # route=answer 时返回，调用方直接交给自己的 OpenAI-compatible LLM
answer_draft     # route=answer 时是草稿，LLM 不可用时可作离线回答
citations        # 引用来源，调用方展示用；不允许新增 citations 之外的来源
meta             # 展示与审计用元数据；不应再拼进提示词
```

### 3.4 调用方职责（必须遵守）

```text
1. 不要自己拼 system/user prompt，直接用返回的 messages。
2. 不要自己实现 calendar/bazi 路由或干支计算。
3. draft_is_final=true 时直接展示 answer_draft，不要再过 LLM。
4. 最终展示文本和 TTS 入口要过一次 sanitize（Python 或 TS 版本均可）。
5. LLM 调用失败时，用 answer_draft 兜底，不要返回空回答。
```

## 4. 内部路由规则（加权意图打分）

路由不用二元正则硬匹配，而是加权词项打分（与 `classify_domain` 同思路）：每个信号词带权重，当前问题全权计入，最近 user 历史按 0.5 衰减计入，得分过阈值才触发意图。这样「生我日柱丁丑吗」这类换说法的问题不会因为某个固定 pattern 匹配不上而漏判。

```text
bazi   ：上下文（问题+最近 user 历史）能结构化解析出完整公历出生年月日时（硬条件），
         且「排盘意图」得分过阈值（八字/排盘/命盘 3.0，四柱/乾造/坤造/男命/女命 2.5，干支 2.0，出生 1.5…，阈值 2.0），
         或「直接告诉我/算出来」类追问得分过阈值（阈值 1.0）
answer ：其余全部走 answer_with_citations(output_format="chat", history=...)
```

不再有固定模板的 calendar 路由：时间相关问题统一走 answer 路由，时间底座作为参数注入（见 4.1）。这保证回答始终带人物风格指纹，并能解读生克、运势，而不是机械回报数字。bazi 路由保留是因为排盘是确定性计算，模板输出即正确答案；时辰名按实际时柱地支计算（如 08:15 为辰时、20:30 为戌时），不允许硬编码示例时间。

### 4.1 实时时间底座注入

判定规则有两条，命中任意一条即注入：

```text
a) 加权打分：时间指代得分（今天/今日/现在 2.0，当前/此刻/今晚/明天 1.5…，阈值 1.0）
   与时间主题得分（几号/流日 3.0，日柱/运势/干支/农历 2.5，天干/地支/四柱/八字/时辰/节气/流月/日主 2.0…，阈值 1.5）
   同时过阈值；
b) 目标日期解析：问题或最近 user 历史中能解析出相对/明确日期指代
   （明天/后天/大后天、下周一~下下周日、本周X/这周X、X月X日，最多 3 个），
   出生信息片段（X年X月X日）会被排除，不当作目标日期。
```

命中后 orchestrator 实时调用 `convert_calendar` + `get_ganzhi`，做四件事：

```text
1. 把当前公历、农历、四柱干支（标注「流日即日柱」）作为「当前时间底座」注入 user prompt，
   并附使用指引：先报时间信息，再结合用户问的生克/合冲/运势/择日做学习性解读，不作绝对断语。
2. 解析出的目标日期逐个换算成具体公历日期 + 当日干支（取正午时刻避免子时跨日），
   作为「目标日期底座」拼在时间底座后（如「下周一是 2026-06-15（星期一），流日是 庚申」）。
3. 把口语化时间底座句（含目标日期）置于 answer_draft 开头，离线兜底时用户也能拿到真实干支。
4. 原始工具结果（含 target_dates）放入 meta.skill_result，供前端展示与审计。
```

历史衰减保证追问也能命中：如上一轮问「今天流日是什么」，本轮只说「那生我吗」，历史中的「今天」（2.0×0.5）和「流日」（3.0×0.5）仍可过阈值。

### 4.2 提问者命盘底座注入

answer 路由下，只要问题或最近 user 历史中能结构化解析出完整出生信息（同 bazi 路由的硬条件），orchestrator 就静默调用 `get_bazi_chart` 排盘，把四柱、日柱、日主、生肖作为「提问者命盘底座」注入 user prompt，并附使用指引：择日/运势类问题用命主日柱与目标日期流日干支的生克合冲做学习性分析。与 bazi 路由的区别：bazi 路由是「用户要排盘结果」（模板直出），命盘底座是「排盘结果作为解读素材」（供 LLM 结合 4.1 的目标日期做择日分析）。典型用例：「我是79年11月6日20:30生男，下周一去买车合适吗」会同时注入命盘底座（日主丁）与目标日期底座（下周一流日干支），LLM 据此讲两者的五行生克关系。原始排盘结果放入 meta.skill_result.get_bazi_chart。

## 5. 提示词组装（compose_chat_messages）

system prompt 组成：

```text
style_prompt（含风格指纹摘要 + CHAT_FORMAT_RULES）
身份控制 / 风格强度 / 风格执行要点 / 禁止事项（来自 persona，全部中文）
当前领域、医学意图
数字分身身份说明与对话行为规则
安全边界（safety_notes 拼接）
```

user prompt 组成（精简原则：每个 plan 只提炼一两句中文指令，不再注入完整 JSON）：

```text
用户问题
最近对话（最多 6 条，每条截断 200 字）
当前时间底座 + 目标日期底座（仅命中 4.1 判定时注入）
提问者命盘底座（仅命中 4.2 判定时注入）
检索状态一句话
skill 生成的对话草稿
证据限制（evidence_plan.limitations）
讲解侧重（style_plan.domain_focus）
边界方式 + 硬性边界（safety_plan.boundary_style / must_not）
引用标签
风格硬要求 + 纯对话文本要求
```

## 6. 评测与测试

```text
evals/style_cases.jsonl   # 风格用例补充禁 Markdown 断言（format_must_avoid）
eval_runner.py            # style 用例对 chat 草稿和 style_prompt 检查格式违规
tests/test_orchestrator.py# 路由判定、八字时辰、出生信息解析、消息组装
tests/test_chat_text.py   # sanitize_chat_text 的标题/加粗/编号/表格清洗
```

## 7. 不做

```text
不在 TS/调用方层重新实现提示词或路由
不把完整 plan JSON 注入提示词
不在聊天通道输出 Markdown
不因为风格改写而编造 citations 之外的来源
```
