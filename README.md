# 倪师skill

倪师skill 是一个面向 Agent 和 MCP 客户端的倪海厦体系学习工具。它把 Skill 规则、Markdown 知识库、SQLite FTS5 检索、轻量知识图谱、确定性历法/四柱工具和 MCP 服务组合在一起，让客户端可以检索资料、返回引用、按领域组织回答，并保持清晰的安全边界。

它不是“真人冒充”项目，也不替代医生诊断、处方或个人决策。它适合做资料学习、问答检索、风格化讲解、天纪/地纪/人纪知识整理，以及给桌面端、小程序后端或其他 Agent 提供统一调用入口。

## 功能

- 倪师体系问答：按人纪、天纪、地纪、跨域自动分类。
- 本地知识检索：Markdown/YAML 知识库入库到 SQLite，支持 FTS5/BM25 和中文 n-gram。
- 内置试用知识库：包含已导入的 Markdown 资料和 `data/nihaixia.sqlite` 索引库，开箱即可检索示例资料。
- 引用优先回答：返回来源、章节、时间戳、页码、命中片段和回答草稿。
- 统一聊天入口：`chat_orchestrate` 自动路由检索、历法、八字和提示词组装。
- 历法与四柱工具：公历转农历、干支四柱、八字基础盘、紫微/风水时间底座。
- 风格控制：可调讲课式表达，但不冒充本人、不编造私人经历。
- 安全边界：医学、命理、风水等高风险问题会收住诊断、处方、绝对吉凶和恐吓式判断。
- 可扩展 RAG：默认纯 SQLite，可选接入 OpenAI-compatible embedding API 做 hybrid 检索。

## 目录

```text
skill/ni-haixia-system/        # 给 Agent 读取的 Skill
packages/nihaixia_core/        # 入库、检索、历法、图谱、安全与 CLI
packages/nihaixia_mcp/         # MCP stdio 服务与统一聊天编排
knowledge/vault/               # 示例 Markdown 知识库
knowledge/graph/               # entities / relations / taxonomy
apps/api/                      # 可选 FastAPI 接口
apps/desktop/                  # 可选 Next + Electron 桌面端
evals/                         # 检索、风格、安全评测样例
tools/                         # 导入、字幕、OCR、素材处理脚本
```

## 本地安装

需要 Python 3.11+。

```powershell
python -m pip install -e .
```

构建本地索引：

```powershell
nihaixia-build-index --vault knowledge/vault --db data/nihaixia.sqlite
```

仓库已包含一份 `data/nihaixia.sqlite` 试用索引。修改或新增 `knowledge/vault/` 内容后，再运行上面的命令重建索引。

搜索资料：

```powershell
nihaixia-search "桂枝汤和太阳中风的关系" --db data/nihaixia.sqlite
```

调用统一聊天入口：

```powershell
'{"question":"桂枝汤适合什么样的太阳病？"}' | nihaixia-chat
```

历法与四柱：

```powershell
nihaixia-calendar "2024-02-10 08:30"
nihaixia-ganzhi "2024-02-10 08:30"
nihaixia-bazi "2024-02-10 08:30" --gender unknown
```

## 在线安装

当前试用包已发布到 TestPyPI：

```text
https://test.pypi.org/project/nihaixia-system/0.1.0/
```

先从 TestPyPI 安装试用版。`--extra-index-url` 用来从正式 PyPI 拉取依赖包：

```powershell
python -m pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ nihaixia-system==0.1.0
```

安装后验证命令：

```powershell
nihaixia-system --help
nihaixia-search --help
nihaixia-chat --help
```

MCP 客户端可以这样配置：

```json
{
  "mcpServers": {
    "nishi-skill": {
      "command": "python",
      "args": ["-m", "nihaixia_mcp.server"],
      "env": {
        "NIHAIXIA_DB": "D:/path/to/nihaixia.sqlite",
        "NIHAIXIA_GRAPH": "D:/path/to/knowledge/graph"
      }
    }
  }
}
```

如果使用 `uvx` 直接从 TestPyPI 临时运行，可以参考：

```json
{
  "mcpServers": {
    "nishi-skill": {
      "command": "uvx",
      "args": [
        "--index-url",
        "https://test.pypi.org/simple/",
        "--extra-index-url",
        "https://pypi.org/simple/",
        "nihaixia-system==0.1.0"
      ],
      "env": {
        "NIHAIXIA_DB": "D:/path/to/nihaixia.sqlite",
        "NIHAIXIA_GRAPH": "D:/path/to/knowledge/graph"
      }
    }
  }
}
```

TestPyPI 只用于试用和验证。正式发布到 PyPI 后，再把安装命令改成常规 `pip install nihaixia-system` 或 `uvx nihaixia-system`。

## 本地 MCP 配置

开发时可以让 MCP 客户端直接跑源码：

```json
{
  "mcpServers": {
    "nishi-skill": {
      "command": "python",
      "args": ["-m", "nihaixia_mcp.server"],
      "env": {
        "PYTHONPATH": "D:/path/to/ni-shi-skill/packages",
        "NIHAIXIA_DB": "D:/path/to/ni-shi-skill/data/nihaixia.sqlite",
        "NIHAIXIA_GRAPH": "D:/path/to/ni-shi-skill/knowledge/graph"
      }
    }
  }
}
```

推荐客户端优先调用 `chat_orchestrate`。它会自动判断应该走普通检索回答、实时日期/干支底座，还是八字排盘工具。

## MCP 工具

```text
chat_orchestrate       统一聊天入口，推荐优先使用
classify_question      判断问题领域：renji / tianji / diji / cross
search_sources         检索已索引资料片段
answer_with_citations  返回带引用、风格和安全计划的回答草稿
get_related_concepts   查询轻量知识图谱关系
get_persona_guidance   获取可控讲解风格
safety_check           返回医学、命理、风水等问题的边界提示
convert_calendar       公历转农历和基础干支参数
get_ganzhi             返回年、月、日、时四柱干支
get_bazi_chart         返回四柱基础盘
get_ziwei_inputs       返回紫微斗数起盘前置参数
get_fengshui_time      返回地纪/风水/择日学习用时间底座
```

## Python 调用

```python
from nihaixia_mcp.orchestrator import chat_orchestrate

result = chat_orchestrate(
    "桂枝汤为什么不是看到感冒就用？",
    top_k=5,
    mode="auto",
    style_intensity="medium",
)

print(result["answer_draft"])
print(result["citations"])
```

直接检索：

```python
from nihaixia_core.retrieval import search_with_info

results, info = search_with_info(
    "太阳中风 桂枝汤",
    "data/nihaixia.sqlite",
    domain="renji",
    top_k=5,
)
```

## 可选 hybrid 检索

默认模式是 `fts`，不需要外部服务。需要语义召回时，在本地 `.env` 或系统环境变量里配置 embedding：

```env
RAG_MODE=hybrid
EMBEDDING_PROVIDER=openai_compatible
EMBEDDING_BASE_URL=https://your-compatible-endpoint/v1
EMBEDDING_API_KEY=your_key
EMBEDDING_MODEL=your_embedding_model
EMBEDDING_DIM=1024
```

构建向量缓存：

```powershell
nihaixia-embedding-status
nihaixia-build-embeddings --db data/nihaixia.sqlite --limit 100
nihaixia-search "桂枝汤为什么不是看到症状就用" --db data/nihaixia.sqlite --mode hybrid
```

没有配置 embedding 时，`hybrid` 会自动回退到 `fts`。

## 知识库格式

每篇资料使用 Markdown + YAML frontmatter：

```md
---
id: renji-shanghan-taiyang-001
title: 桂枝汤与太阳中风
domain: renji
course: 伤寒论
chapter: 太阳病
topics: [太阳病, 桂枝汤, 营卫不和]
entities: [桂枝汤, 太阳中风, 营卫]
source_type: note
timestamp: "00:23:18"
page: ""
source_url: ""
rights_status: authorized
---

这里写整理后的原文、摘要或学习笔记。
```

`domain` 建议使用：

```text
renji   人纪：中医、经典、经方、针灸
tianji  天纪：易经、干支、五行、命理
diji    地纪：阳宅、阴宅、方位、地理
```

## 测试

```powershell
python -m pytest
nihaixia-eval --db data/nihaixia.sqlite --eval-dir evals --fail-on-error
```

## 合规边界

请只提交可公开、可授权、可复现的内容。不要提交真实 API key、`.env`、未授权原始视频、付费资料、私有字幕、OCR 中间产物或渲染文件。

这个项目的定位是“基于合法资料整理的 AI 学习助手”。它可以学习表达结构和讲解节奏，但不能声称自己是倪海厦本人，不能编造私人经历，也不能替代医生诊断和治疗。
