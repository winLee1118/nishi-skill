# 0001 可执行开发 Spec：倪师数字人轻量 Skill / MCP / RAG

## 1. 目标

构建一个轻量、可开源、方便智能体调用的倪师体系项目。

第一阶段不做重型本地模型，不强制 Docker，不把 RAG 框架作为核心依赖。默认能力是：

```text
Markdown 知识库
→ SQLite FTS5/BM25 检索
→ 轻量知识图谱
→ MCP stdio 工具
→ 可控人物语言风格
→ 带引用和安全边界的回答草稿
```

项目定位：

```text
基于已索引资料的 AI 学习助手。
覆盖人纪 / 天纪 / 地纪。
支持知识体系、推理结构、语言风格、性格表达四个蒸馏维度。
```

不做：

```text
不默认依赖本地大模型
不默认启动 Docker
不把未授权资料提交到开源仓库
不冒充倪海厦本人
不编造私人经历或临床经历
不替代医生诊断和治疗
```

## 2. 当前基线

当前仓库已经具备：

```text
skill/ni-haixia-system/SKILL.md
skill/ni-haixia-system/references/
packages/nihaixia_core/
packages/nihaixia_mcp/
knowledge/vault/
knowledge/graph/
evals/
apps/api/
README.md
pyproject.toml
```

当前可运行命令：

```powershell
$env:PYTHONPATH="D:\cto9012\WXAPPS\倪师数字人\packages"
python -m nihaixia_core.cli build-index --vault knowledge/vault --db data/nihaixia.sqlite
python -m nihaixia_core.cli search "桂枝汤和太阳中风的关系" --db data/nihaixia.sqlite
```

当前 MCP 工具：

```text
classify_question
search_sources
get_related_concepts
answer_with_citations
get_persona_guidance
safety_check
```

## 3. 核心设计

### 3.1 四层蒸馏

本项目把“蒸馏”拆成四层，避免把所有目标混成一个模型问题。

```text
知识体系层：资料、课程、章节、术语、引用
推理结构层：原则 -> 格局/辨证 -> 案例 -> 边界
语言风格层：直接、讲课式、先讲原则、重视经典框架
性格表达层：自信但有边界、实用、重体系、少空话
```

四层执行顺序：

```text
先检索证据
再组织推理结构
再应用风格画像
最后检查边界
```

风格不能覆盖证据。没有资料支撑时，必须说资料不足。

### 3.2 默认 RAG

默认 RAG 不使用 embedding：

```text
SQLite FTS5
BM25
中文 n-gram
contextual_text
metadata rerank
```

后续可选增强：

```text
sqlite-vec
外部 embedding API
外部 reranker API
remote RAG API
Qdrant adapter
```

### 3.3 默认调用方式

智能体默认通过 MCP stdio 调用：

```json
{
  "mcpServers": {
    "nihaixia": {
      "command": "python",
      "args": ["-m", "nihaixia_mcp.server"],
      "env": {
        "PYTHONPATH": "D:/cto9012/WXAPPS/倪师数字人/packages",
        "NIHAIXIA_DB": "D:/cto9012/WXAPPS/倪师数字人/data/nihaixia.sqlite",
        "NIHAIXIA_GRAPH": "D:/cto9012/WXAPPS/倪师数字人/knowledge/graph"
      }
    }
  }
}
```

## 4. 数据 Spec

### 4.1 Markdown 知识文件

每个知识文件必须使用 Markdown + YAML frontmatter。

```md
---
id: renji-shanghan-taiyang-guizhi-001
title: 桂枝汤与太阳中风
domain: renji
course: 伤寒论
chapter: 太阳病
topics: [太阳病, 桂枝汤, 营卫不和]
entities: [桂枝汤, 太阳中风, 营卫]
source_type: note
timestamp: "00:23:18"
rights_status: authorized
---

正文内容。
```

必填字段：

```text
id
title
domain
course
chapter
rights_status
```

推荐字段：

```text
topics
entities
source_type
timestamp
page
source_url
```

### 4.2 domain 枚举

```text
renji   # 人纪：中医、经典、经方、针灸、本草、案例
tianji  # 天纪：易经、干支、五行、命理、象数
diji    # 地纪：阳宅、阴宅、方位、形势、理气
cross   # 跨域
unknown # 未分类，仅用于暂存
```

### 4.3 rights_status 枚举

```text
authorized  # 明确授权或自有资料
public      # 适合公开索引和引用的资料
unknown     # 权利状态不明，只能本地实验
```

验收规则：

```text
公开发布数据不得包含 rights_status=unknown 的正式资料。
回答引用 unknown 资料时必须降权，并提示资料状态不明。
```

## 5. MCP Tool Spec

### 5.1 classify_question

用途：判断问题属于哪个领域。

输入：

```json
{
  "question": "桂枝汤和太阳中风是什么关系？"
}
```

输出：

```json
{
  "domain": "renji"
}
```

验收：

```text
中医/经方/针灸问题 -> renji
易经/干支/五行/命理问题 -> tianji
阳宅/阴宅/方位/风水问题 -> diji
多领域问题 -> cross 或由调用方显式指定
```

### 5.2 search_sources

用途：检索资料片段。

输入：

```json
{
  "question": "桂枝汤和太阳中风是什么关系？",
  "domain": "auto",
  "top_k": 5
}
```

输出：

```json
{
  "results": [
    {
      "chunk_id": "c10160de41316f87",
      "source_id": "renji-shanghan-taiyang-guizhi-demo",
      "title": "桂枝汤与太阳中风示例",
      "domain": "renji",
      "course": "伤寒论",
      "chapter": "太阳病",
      "timestamp": "demo",
      "snippet": "...",
      "score": 27.6,
      "topics": ["太阳病", "桂枝汤"],
      "entities": ["桂枝汤", "太阳中风"],
      "rights_status": "public"
    }
  ]
}
```

验收：

```text
必须返回 chunk_id 和 source_id
必须返回 domain/course/chapter
必须返回 snippet
top_k 必须生效
domain != auto 时必须按领域过滤
```

### 5.3 get_related_concepts

用途：查询轻量知识图谱。

输入：

```json
{
  "concept": "五行",
  "depth": 1
}
```

输出：

```json
{
  "concept": "五行",
  "relations": [
    {
      "from": "五行",
      "relation": "connects",
      "to": "天纪",
      "evidence": "demo"
    }
  ]
}
```

验收：

```text
depth=1 返回一跳关系
不存在概念时返回空数组，不报错
```

### 5.4 get_persona_guidance

用途：返回语言风格和性格画像指导。

输入：

```json
{
  "domain": "renji",
  "style_intensity": "medium"
}
```

输出：

```json
{
  "domain": "renji",
  "persona": {
    "style_intensity": "medium",
    "identity": "AI study assistant based on indexed and authorized Ni Haixia system materials.",
    "instructions": [
      "Use a study-assistant identity; do not claim to be Ni Haixia.",
      "Give the core principle first, then explain the pattern and example."
    ],
    "avoid": [
      "Do not say '我是倪海厦'.",
      "Do not invent personal memories, clinical encounters, or private authority."
    ]
  }
}
```

style_intensity：

```text
none    # 中性学习助手
low     # 轻微讲课风格
medium  # 默认：原则先行、表达直接
high    # 更强讲课节奏，但仍不冒充本人
```

验收：

```text
必须返回 identity/instructions/avoid
high 也不能允许身份冒充
unknown style_intensity 回退到 medium
```

### 5.5 answer_with_citations

用途：返回带引用的回答草稿和风格指导。

输入：

```json
{
  "question": "用讲课风格解释桂枝汤和太阳中风",
  "domain": "auto",
  "top_k": 5,
  "style_intensity": "medium"
}
```

输出：

```json
{
  "domain": "renji",
  "persona": {},
  "answer": "以下为基于已索引资料的回答草稿...",
  "citations": [
    {
      "source_id": "...",
      "chunk_id": "...",
      "title": "...",
      "course": "...",
      "chapter": "...",
      "timestamp": "..."
    }
  ],
  "safety_notes": [
    "本回答仅供学习和资料检索，不构成诊断、处方或治疗建议。"
  ]
}
```

验收：

```text
必须先检索再生成草稿
必须返回 citations 数组
必须返回 persona
必须返回 safety_notes
无检索结果时不能编造引用
```

### 5.6 safety_check

用途：返回安全边界。

输入：

```json
{
  "question": "我失眠要不要用某个方？",
  "domain": "renji"
}
```

输出：

```json
{
  "domain": "renji",
  "safety_notes": [
    "本回答仅供学习和资料检索，不构成诊断、处方或治疗建议。"
  ]
}
```

验收：

```text
医疗问题必须提示不构成诊断/处方/治疗建议
天纪/地纪问题必须避免绝对化、恐吓式判断
身份问题必须避免冒充本人
```

## 6. 回答 Spec

默认回答结构：

```text
分类：
简要结论：
资料依据：
体系解释：
风格化讲解：
注意边界：
引用：
```

短问题可以压缩，但必须保留：

```text
结论
依据
引用或资料不足说明
必要边界
```

风格化讲解要求：

```text
先看原则
再看所属体系
再解释机制
再给例子
最后给边界
```

禁用模式：

```text
我是倪海厦
我当年临床
我保证
一定会
处方如下
你不用去看医生
```

## 7. 开发任务

### 7.1 P0：稳定当前轻量闭环

目标：确保当前仓库从资料到 MCP 可调用。

任务：

```text
[ ] 保持 Skill 校验通过
[ ] 保持 build-index 可运行
[ ] 保持 search 可运行
[ ] 保持 MCP server 可导入
[ ] README 命令与实际入口一致
```

验收命令：

```powershell
$env:PYTHONUTF8="1"
$env:PYTHONDONTWRITEBYTECODE="1"
$env:PYTHONPATH="D:\cto9012\WXAPPS\倪师数字人\packages"

python -B C:\Users\cto90\.codex\skills\.system\skill-creator\scripts\quick_validate.py skill\ni-haixia-system
python -B -m nihaixia_core.cli build-index --vault knowledge/vault --db data/nihaixia.sqlite
python -B -m nihaixia_core.cli search "桂枝汤和太阳中风" --db data/nihaixia.sqlite --top-k 1
python -B -c "from nihaixia_mcp.server import answer_with_citations; print('mcp import ok')"
```

通过标准：

```text
Skill is valid!
build-index 返回 sources/chunks
search 返回至少 1 条结果
mcp import ok
```

### 7.2 P1：补齐自动化评测

目标：用 JSONL 评测检索、风格、安全。

新增文件：

```text
packages/nihaixia_core/eval_runner.py
evals/retrieval_cases.jsonl
evals/safety_cases.jsonl
```

新增命令：

```text
nihaixia-eval
```

评测输入：

```json
{
  "id": "demo-renji-001",
  "question": "桂枝汤和太阳中风是什么关系？",
  "domain": "renji",
  "must_find": ["桂枝汤", "太阳中风"],
  "must_avoid": ["我是倪海厦"]
}
```

评测输出：

```json
{
  "total": 3,
  "passed": 3,
  "failed": 0,
  "cases": []
}
```

验收：

```text
检索样例 top3 命中 must_find
风格样例不出现 must_avoid
安全样例返回 safety_notes
```

### 7.3 P2：增强中文检索

目标：提升中文术语检索准确度。

任务：

```text
[ ] 支持 aliases 字段
[ ] entities 写入 SQLite entities 表
[ ] 检索时用 concepts/aliases 扩展 query
[ ] rerank 增加 entity 命中加权
```

新增/修改文件：

```text
packages/nihaixia_core/ingest.py
packages/nihaixia_core/retrieval.py
packages/nihaixia_core/graph.py
knowledge/graph/entities.jsonl
```

验收：

```text
搜索“桂枝方”能命中“桂枝汤”
搜索“住宅方位”能命中“阳宅方位”
搜索“五行和人纪”能返回跨域关联
```

### 7.4 P3：补齐 MCP 契约测试

目标：保证 MCP 工具输出结构稳定。

新增文件：

```text
tests/test_mcp_contracts.py
tests/test_retrieval.py
tests/test_persona.py
```

验收：

```text
pytest 通过
每个 MCP tool 返回字段稳定
answer_with_citations 无结果时不编造 citation
```

### 7.5 P4：可选 LLM Adapter

目标：在不破坏轻量默认模式的前提下，支持外部 LLM 生成最终回答。

新增文件：

```text
packages/nihaixia_core/llm.py
```

环境变量：

```text
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
```

新增 MCP 参数：

```text
generate_final: bool = false
```

默认行为：

```text
generate_final=false 时仍返回回答草稿
没有 LLM_API_KEY 时不报错，只返回草稿
```

验收：

```text
无 API key 可运行
有 API key 可生成最终回答
最终回答必须保留 citations/safety_notes
```

## 8. 版本路线

```text
v0.1 当前：Skill + SQLite FTS5 + MCP 基础工具 + 风格层
v0.2：eval runner + 检索/风格/安全评测
v0.3：aliases + entity query expansion + 图谱增强
v0.4：pytest MCP contract tests
v0.5：可选 LLM adapter
v0.6：可选 sqlite-vec / remote RAG adapter
v1.0：文档稳定、示例完善、开源发布
```

## 9. 完成定义

项目达到第一版可开源时，必须满足：

```text
README 中文说明完整
Skill 校验通过
本地示例数据可 build-index
search_sources 可返回引用片段
answer_with_citations 可返回 persona/citations/safety_notes
风格层可控，不冒充本人
无本地模型依赖
无 Docker 强依赖
未授权资料不进入仓库
```

最终验证命令：

```powershell
$env:PYTHONUTF8="1"
$env:PYTHONDONTWRITEBYTECODE="1"
$env:PYTHONPATH="D:\cto9012\WXAPPS\倪师数字人\packages"

python -B C:\Users\cto90\.codex\skills\.system\skill-creator\scripts\quick_validate.py skill\ni-haixia-system
python -B -m nihaixia_core.cli build-index --vault knowledge/vault --db data/nihaixia.sqlite
python -B -m nihaixia_core.cli search "天干地支和五行" --db data/nihaixia.sqlite --top-k 1
python -B -c "from nihaixia_core.persona import persona_guidance; print(persona_guidance('renji','medium')['style_intensity'])"
python -B -c "from nihaixia_mcp.server import get_persona_guidance; print(get_persona_guidance('renji','high')['persona']['style_intensity'])"
```

