# 倪师数字人 Desktop

Electron + React + Next.js 一体化示例。

## 功能

- 粒子构成的倪师数字人剪影，随听取、思考、朗读状态震荡。
- 文字对话、语音输入入口、TTS 播放入口。
- Next API routes 调用项目 skill/MCP 工具层，并在配置 `MIMO_API_KEY` 后调用 MiMo LLM / ASR / TTS。
- 引用来源、领域模式、skill 调用状态、风格指纹、证据计划和安全边界控制。
- `/api/chat` 使用 SSE 流式输出，前端逐段追加回答文本。

## Skill 调用方式（标准契约）

这个示例是 `docs/specs/0006-chat-orchestration-spec.md` 调用契约的标准实现：所有路由、工具调用和提示词组装都在 Python skill 层的统一入口 `nihaixia_mcp.orchestrator.chat_orchestrate` 完成，桌面端只做透传。入口文件：

- `app/api/chat/route.ts`：调用 `python -m nihaixia_mcp.orchestrator`，按返回契约流式输出。
- `app/api/stt/route.ts`：语音识别。
- `app/api/tts/route.ts`：朗读和可选音色克隆（入口统一做 Markdown 清洗）。

统一入口调用：

```python
from nihaixia_mcp.orchestrator import chat_orchestrate

result = chat_orchestrate(
    "我是1979年11月6日20:30生的男性，我的干支是什么",
    history=[],
    timezone="Asia/Shanghai",
    style_intensity="medium",
)

result["route"]           # calendar / bazi / answer
result["draft_is_final"]  # True 表示 answer_draft 已是最终回答
result["messages"]        # answer 路由时直接交给 OpenAI-compatible LLM
result["citations"]       # 引用来源
result["meta"]            # 领域、persona、安全边界、skill_invocation、skill_result
```

非 Python 调用方（本示例的 Node.js 即是）走子进程 JSON：

```text
echo '{"question": "...", "history": []}' | python -m nihaixia_mcp.orchestrator
```

`chat_orchestrate` 内部自动路由：

- “我是 1979 年 11 月 6 日 20:30 生的男性，干支是什么”这类出生排盘问题走 `get_bazi_chart`，时辰名按实际时柱计算（确定性计算，直接返回最终回答）。
- “今天几号 / 现在天干地支 / 日柱丁火今天运势如何 / 今天流日生我日柱丁丑吗”这类时间相关问题统一走 answer 路由：orchestrator 实时调用 `convert_calendar` + `get_ganzhi`，把当前公历、农历、四柱干支作为「当前时间底座」注入提示词和草稿开头，再结合知识检索和风格指纹由 LLM 生成解读，不再用固定模板直接回复。
- “下周一 / 明天 / 6月18日”这类相对或明确日期指代会被解析成具体公历日期，连同当日干支作为「目标日期底座」一并注入；若问题里还带完整出生信息（如“我是79年11月6日20:30生男，下周一去买车合适吗”），orchestrator 会静默排盘并注入「提问者命盘底座」（四柱、日主），让 LLM 用命主与目标日期流日干支的生克关系做择日解读。
- 路由判定采用加权词项打分（含历史衰减），不是二元正则匹配，换说法的问题也能命中；详见 0006 spec 第 4 节。
- 其余问答走 `answer_with_citations(output_format="chat", history=...)`，返回口语化草稿和组装好的 `messages`。

调用方职责（不要做多余的事）：

- 不要自己拼 system/user prompt，直接用返回的 `messages`。
- `draft_is_final=true` 时直接展示 `answer_draft`，不要再过 LLM。
- 最终展示文本和 TTS 入口用 `sanitizeChatText`（TS）或 `sanitize_chat_text`（Python）清洗残余 Markdown。
- LLM 调用失败时用 `answer_draft` 兜底。

如果配置了 `MIMO_API_KEY`，Next API 会把 skill 组装好的 `messages` 交给 MiMo 做最终自然语言生成；如果没有配置，则直接返回 skill 的口语化草稿。聊天输出为纯对话文本，不包含 Markdown 标题、加粗、编号列表或表格。

## API 流式返回

`POST /api/chat` 的请求示例：

```json
{
  "question": "现在的天干地支是什么",
  "domain": "auto",
  "top_k": 5,
  "mode": "auto",
  "style_intensity": "medium",
  "timezone": "Asia/Shanghai",
  "history": [
    { "role": "user", "content": "我是79年11月6日20:30生的男性，倪师我的干支是什么" },
    { "role": "assistant", "content": "..." }
  ]
}
```

接口返回 `text/event-stream`，事件类型：

- `meta`：先返回领域、引用、人物风格、安全边界、skill 调用信息。
- `delta`：逐段返回回答文本，字段为 `{ "text": "..." }`。
- `done`：返回完整回答和最终元数据。
- `error`：流式调用失败时返回错误信息。

`done` 事件主要字段：

- `answer`：最终可展示回答。
- `citations`：引用来源。
- `persona`：人物风格指纹摘要和风格提示。
- `retrieval_info`：检索模式和回退状态。
- `evidence_plan`：证据使用计划。
- `style_plan`：风格强度、指纹版本和表达规则。
- `safety_plan`：医学、身份、命理/风水边界。
- `persona_composition`：最终回答组装规则。
- `skill_invocation`：本次示例实际调用的 skill/MCP 工具和参数。
- `skill_result`：时间/排盘工具类问题会返回原始结构化工具结果，方便前端或调用方二次展示。

前端会把最近几轮 `history` 随请求传入，后端用它处理“你直接告诉我”“继续说”等省略式追问。示例只保存在当前浏览器页面状态中；刷新页面后历史会清空。如果要跨会话保存，需要调用方自己接数据库或本地存储。

## 启动

```powershell
cd apps/desktop
npm install
npm run dev
```

只预览 Web 端：

```powershell
npm run web
```

## 环境变量

应用会从当前环境读取：

- `MIMO_API_KEY`
- `MIMO_BASE_URL`，默认 `https://api.xiaomimimo.com/v1`
- `MIMO_CHAT_MODEL`，默认 `mimo-v2.5-pro`
- `MIMO_ASR_MODEL`，默认 `mimo-v2.5-asr`
- `MIMO_TTS_MODEL`，默认 `mimo-v2.5-tts`
- `NIHAIXIA_DB`，默认项目根目录 `data/nihaixia.sqlite`
- `PYTHON`，默认 `python`

## 调用链说明

Next.js 运行在 Node.js 中，项目核心 skill 在 Python 包里，所以示例使用 `src/lib/pythonBridge.ts` 启动 Python 子进程，并自动设置：

- `PYTHONPATH=<project>/packages`
- `NIHAIXIA_DB=<project>/data/nihaixia.sqlite`
- `NIHAIXIA_GRAPH=<project>/knowledge/graph`
- `PYTHONIOENCODING=utf-8`
- `PYTHONUTF8=1`

其他应用可以复用同样方式，也可以直接把 `nihaixia_mcp.server` 作为 MCP server 接给自己的 agent（其中包含 `chat_orchestrate` 工具）。关键是不要绕过 `chat_orchestrate` 自己拼 prompt 或自己实现路由，否则容易漏掉知识库、人物风格指纹、安全边界、干支工具和聊天输出格式契约。
