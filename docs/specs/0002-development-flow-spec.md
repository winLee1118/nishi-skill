# 0002 开发流程 Spec

这个文档定义项目从当前骨架走到第一版可开源的具体开发顺序。

原则：

```text
先闭环，再增强。
先可验证，再加功能。
先轻量默认，再可选扩展。
每一步都必须有产出物和验收命令。
```

## 阶段 0：确认当前工程可运行

目的：确认本地骨架没有坏，后续开发基于稳定起点。

要做：

```text
1. 校验 Skill 格式。
2. 构建示例 SQLite 索引。
3. 跑一次人纪/天纪/地纪搜索。
4. 确认 MCP server 可导入。
```

命令：

```powershell
$env:PYTHONUTF8="1"
$env:PYTHONDONTWRITEBYTECODE="1"
$env:PYTHONPATH="D:\cto9012\WXAPPS\倪师数字人\packages"

python -B C:\Users\cto90\.codex\skills\.system\skill-creator\scripts\quick_validate.py skill\ni-haixia-system
python -B -m nihaixia_core.cli build-index --vault knowledge/vault --db data/nihaixia.sqlite
python -B -m nihaixia_core.cli search "桂枝汤和太阳中风" --db data/nihaixia.sqlite --top-k 1
python -B -m nihaixia_core.cli search "天干地支和五行" --db data/nihaixia.sqlite --top-k 1
python -B -m nihaixia_core.cli search "阳宅方位分析" --db data/nihaixia.sqlite --top-k 1
python -B -c "from nihaixia_mcp.server import answer_with_citations; print('mcp import ok')"
```

产出：

```text
data/nihaixia.sqlite
```

通过标准：

```text
Skill is valid!
三类搜索都有结果
输出 mcp import ok
```

进入下一阶段条件：

```text
阶段 0 全部通过。
```

## 阶段 1：建立评测系统

目的：后续每次改检索、风格、安全，都有自动化判断，不靠感觉。

要做：

```text
1. 新增 eval runner。
2. 把现有 evals/questions.jsonl 和 evals/style_cases.jsonl 纳入评测。
3. 新增 safety cases。
4. 新增命令 nihaixia-eval。
```

新增文件：

```text
packages/nihaixia_core/eval_runner.py
evals/safety_cases.jsonl
```

修改文件：

```text
pyproject.toml
```

评测类型：

```text
retrieval：检查 top_k 结果是否包含 must_find
style：检查 persona guidance 和回答草稿不包含 must_avoid
safety：检查 safety_notes 是否存在必要边界
```

命令：

```powershell
nihaixia-eval --db data/nihaixia.sqlite --eval-dir evals
```

如果未安装包，用：

```powershell
python -B -m nihaixia_core.eval_runner --db data/nihaixia.sqlite --eval-dir evals
```

产出：

```text
控制台 JSON 报告
```

期望输出：

```json
{
  "total": 9,
  "passed": 9,
  "failed": 0
}
```

通过标准：

```text
所有 demo eval 通过
失败时能显示 case id 和原因
```

进入下一阶段条件：

```text
nihaixia-eval 稳定通过。
```

## 阶段 2：增强资料入库规范

目的：让真实资料能被稳定整理和追踪。

要做：

```text
1. 扩展 frontmatter 支持 page/source_url/aliases。
2. 入库时校验必填字段。
3. 对 rights_status=unknown 输出警告。
4. 生成 ingestion report。
```

修改文件：

```text
packages/nihaixia_core/schemas.py
packages/nihaixia_core/ingest.py
packages/nihaixia_core/cli.py
```

新增字段：

```text
page
source_url
aliases
notes
```

命令：

```powershell
python -B -m nihaixia_core.cli build-index --vault knowledge/vault --db data/nihaixia.sqlite
```

产出：

```json
{
  "sources": 3,
  "chunks": 3,
  "warnings": []
}
```

通过标准：

```text
缺少 id/title/domain/course/chapter/rights_status 时有 warning
unknown 权利状态有 warning
不阻断本地实验
```

进入下一阶段条件：

```text
评测系统仍通过。
```

## 阶段 3：增强中文检索准确度

目的：在不引入本地 embedding 的前提下，提高术语命中率。

要做：

```text
1. 读取 knowledge/graph/entities.jsonl 中的 aliases。
2. 检索时把别名扩展到 query。
3. rerank 增加 entity/alias 命中加权。
4. 增加跨域概念扩展。
```

修改文件：

```text
packages/nihaixia_core/graph.py
packages/nihaixia_core/retrieval.py
packages/nihaixia_core/text.py
knowledge/graph/entities.jsonl
evals/questions.jsonl
```

新增验收问题：

```text
桂枝方 -> 桂枝汤
住宅方位 -> 阳宅方位
木火土金水 -> 五行
```

命令：

```powershell
python -B -m nihaixia_core.cli search "桂枝方和太阳表虚" --db data/nihaixia.sqlite --top-k 3
python -B -m nihaixia_core.cli search "住宅方位" --db data/nihaixia.sqlite --top-k 3
python -B -m nihaixia_core.eval_runner --db data/nihaixia.sqlite --eval-dir evals
```

通过标准：

```text
别名问题能命中目标资料
原有三类检索不退化
eval 全部通过
```

进入下一阶段条件：

```text
检索 eval 通过率达到 100% demo cases。
```

## 阶段 4：完善人物风格蒸馏

目的：让语言风格和性格表达可控、可测、可调用。

阶段 4 的产品定位：

```text
不是冷硬的安全提示器。
是一个基于资料和风格画像生成的透明数字分身。
普通学习场景要有拟人临场感、讲课节奏和性格表达。
风险场景才柔性收束边界，不反复用生硬免责声明打断体验。
```

要做：

```text
1. 固化 style_intensity 的输出规则。
2. 增加 style_profile 数据结构。
3. answer_with_citations 返回 style_prompt。
4. 增加风格评测：must_include / must_avoid。
5. 增加 boundary_policy：ordinary / risky / forbidden 三层柔性边界。
```

修改文件：

```text
packages/nihaixia_core/persona.py
packages/nihaixia_mcp/server.py
skill/ni-haixia-system/references/persona-style.md
evals/style_cases.jsonl
```

阶段 4C-2 已完成：

```text
1. 从本地剪映字幕拆分后的 16 个视频来源抽取 220 条短风格样本。
2. 生成 knowledge/persona/style-fingerprint-v0.2.json。
3. persona.py 默认读取 v0.2 指纹。
4. style_prompt 使用 style_digest 轻量摘要，不再注入完整 profile。
5. private 字幕和 raw-videos 继续保持本地忽略，不进入开源仓库。
```

阶段 4C-3 已完成：

```text
1. answer_with_citations 保持旧字段兼容，同时新增 evidence_plan / style_plan / safety_plan / persona_composition。
2. evidence_plan 明确 citation、retrieval_mode、top source、warnings 和 limitations。
3. style_plan 明确 style_intensity、v0.2 fingerprint、domain_focus 和 compact style_prompt。
4. safety_plan 明确 risk_level、medical_intent、identity_request、absolute_fate_request 和 must_not。
5. tests/test_mcp_contracts.py 已增加普通场景与高风险边界契约测试。
```

style_profile 建议字段：

```json
{
  "tone": "direct",
  "reasoning_order": ["principle", "pattern", "example", "boundary"],
  "personality": ["confident_but_bounded", "practical", "classical_source_aware"],
  "language": ["plain_chinese", "teacher_like", "structured"],
  "presence": "digital_avatar",
  "boundary": "soft_contextual",
  "forbidden": ["我是倪海厦", "我当年临床", "我保证"]
}
```

命令：

```powershell
python -B -c "from nihaixia_core.persona import persona_guidance; import json; print(json.dumps(persona_guidance('renji','high'), ensure_ascii=False, indent=2))"
python -B -m nihaixia_core.eval_runner --db data/nihaixia.sqlite --eval-dir evals
```

通过标准：

```text
none/low/medium/high 都有明确差异
high 也不允许冒充本人
style eval 通过
```

进入下一阶段条件：

```text
风格层可控，且不破坏安全边界。
```

## 阶段 5：补 MCP 契约测试

目的：保证外部智能体调用时，工具输入输出稳定。

已执行 5B：

```text
1. tests/test_mcp_contracts.py 扩展到 classify_question / search_sources / get_related_concepts / answer_with_citations / get_persona_guidance / safety_check。
2. tests/test_calendar.py 扩展 Calendar/Bazi MCP 工具契约和结构化错误返回。
3. Calendar/Bazi MCP 工具遇到日期越界、非法时区时返回 {"error": {...}}，不直接炸掉调用。
4. classify_domain 增加常见人纪症状/用药意图词，避免口干、胃胀等问题落到 auto。
```

要做：

```text
1. 加 pytest。
2. 对每个 MCP tool 对应的核心函数做 contract test。
3. 测无结果、空问题、非法 style_intensity 等边界情况。
```

新增文件：

```text
tests/test_retrieval.py
tests/test_persona.py
tests/test_mcp_contracts.py
tests/test_calendar.py
```

修改文件：

```text
pyproject.toml
```

命令：

```powershell
python -m pip install -e .[dev]
pytest
```

通过标准：

```text
pytest 全部通过
answer_with_citations 一定返回 domain/persona/answer/citations/safety_notes
search_sources 一定返回 results
get_persona_guidance 一定返回 persona
Calendar/Bazi 工具错误输入返回结构化 error
```

进入下一阶段条件：

```text
pytest 和 eval runner 都通过。
```

## 阶段 5A：Calendar/Bazi MCP 易学时间底座

目的：为天纪、地纪、紫微、四柱命理、风水择日等场景提供确定性时间换算工具，避免 LLM 自行心算干支、农历、四柱。

已执行：

```text
1. 新增 packages/nihaixia_core/calendar.py。
2. 新增 MCP 工具：convert_calendar / get_ganzhi / get_bazi_chart / get_ziwei_inputs / get_fengshui_time。
3. 新增 CLI：nihaixia-calendar / nihaixia-ganzhi / nihaixia-bazi。
4. 新增 tests/test_calendar.py。
5. README 和 Skill workflow 已写明：遇到干支、农历、四柱、紫微、风水择日，先调用 Calendar/Bazi 工具。
```

v1 边界：

```text
农历表支持 1900-01-31 到 2100-12-31。
节气为日期级近似；出生时间贴近节气交接时，应使用权威万年历复核。
use_true_solar_time 当前是预留参数，不自动按经度校正。
紫微和风水工具只返回时间底座，不做完整星曜盘或完整择日体系。
```

阶段 5A-2 已完成：

```text
1. 四柱基础盘增加纳音。
2. 增加以日主看四支的十二长生。
3. 增加大运：阳男阴女顺行，阴男阳女逆行，从月柱起排。
4. 增加流年：指定起始年份和年份数量，返回流年干支、纳音、十神、十二长生。
5. MCP/CLI 增加 luck_cycle_count / annual_start_year / annual_years 参数。
```

## 阶段 6：可选 LLM Adapter

目的：在保持轻量默认模式的前提下，允许用户接外部模型生成最终回答。

要做：

```text
1. 新增 OpenAI-compatible adapter。
2. answer_with_citations 增加 generate_final=false 默认参数。
3. 无 API key 时继续返回草稿，不报错。
4. 有 API key 时生成最终回答，并保留 citations/safety_notes。
```

新增文件：

```text
packages/nihaixia_core/llm.py
```

修改文件：

```text
packages/nihaixia_mcp/server.py
.env.example
README.md
```

环境变量：

```text
LLM_PROVIDER=openai_compatible
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
```

命令：

```powershell
python -B -c "from nihaixia_core.llm import is_configured; print(is_configured())"
```

通过标准：

```text
不配置 API key 时项目仍完整可用
配置 API key 后可生成 final_answer
final_answer 不丢引用和安全提示
```

进入下一阶段条件：

```text
LLM 是增强能力，不成为默认依赖。
```

## 阶段 7：文档和开源整理

目的：让外部用户能安装、理解、调用。

要做：

```text
1. 更新 README 快速开始。
2. 增加 MCP 客户端配置示例。
3. 增加资料整理指南。
4. 增加 release checklist。
5. 确认 data/*.sqlite 不提交。
```

新增文件：

```text
docs/knowledge-authoring.md
docs/mcp-client-config.md
docs/release-checklist.md
```

命令：

```powershell
git status --short
```

通过标准：

```text
README 能从零跑通
docs 能说明如何新增资料
没有未授权资料
没有 SQLite 索引库进入 git
```

## 总执行顺序

严格按这个顺序做：

```text
0. 确认当前工程可运行
1. 建立评测系统
2. 增强资料入库规范
3. 增强中文检索准确度
4. 完善人物风格蒸馏
5. 补 MCP 契约测试
6. 可选 LLM Adapter
7. 文档和开源整理
```

不要提前做：

```text
不要在阶段 1 前接大模型
不要在阶段 3 前引入向量库
不要在阶段 5 前扩很多 MCP 工具
不要在第一版前做复杂前端
```

## 每阶段完成定义

每个阶段结束都要满足：

```text
1. 对应代码或文档已落盘
2. 验收命令已执行
3. 失败项已记录或修复
4. git status 可解释
5. 不引入重型默认依赖
```

## 阶段 3A：增加可选 Hybrid 向量查询

目的：在保持 `RAG_MODE=fts` 默认轻量模式的前提下，增加外部 embedding API 增强检索。

设计依据：

```text
docs/specs/0003-hybrid-vector-search-spec.md
```

要做：

```text
1. 新增 embedding adapter，支持 OpenAI-compatible API。
2. 新增 SQLite 向量缓存表 chunk_embeddings / query_embedding_cache。
3. 新增 build-embeddings 命令。
4. 新增 hybrid_retrieval：BM25 + vector + metadata/entity fusion。
5. search_sources 增加 mode 参数：auto / fts / hybrid。
6. 无 API key 时自动回退 fts。
7. README 和 .env.example 增加配置示例，但不写真实 key。
```

修改/新增文件：

```text
packages/nihaixia_core/embedding.py
packages/nihaixia_core/vector_store.py
packages/nihaixia_core/hybrid_retrieval.py
packages/nihaixia_core/retrieval.py
packages/nihaixia_core/cli.py
packages/nihaixia_mcp/server.py
apps/api/main.py
.env.example
README.md
docs/specs/0003-hybrid-vector-search-spec.md
```

本地配置示例：

```powershell
$env:RAG_MODE="hybrid"
$env:EMBEDDING_PROVIDER="openai_compatible"
$env:EMBEDDING_BASE_URL="https://ark.cn-beijing.volces.com/api/v3"
$env:EMBEDDING_MODEL="doubao-embedding-vision-250615"
$env:EMBEDDING_API_KEY="<放在本机环境变量，不提交>"
```

验收命令：

```powershell
python -B -m nihaixia_core.cli build-embeddings --db data/nihaixia.sqlite --limit 20
python -B -m nihaixia_core.cli search "桂枝汤为什么不是看到症状就用" --db data/nihaixia.sqlite --mode hybrid --top-k 5
python -B -m nihaixia_core.eval_runner --db data/nihaixia.sqlite --eval-dir evals --fail-on-error
```

通过标准：

```text
无 EMBEDDING_API_KEY 时 search --mode hybrid 自动回退 fts。
有 EMBEDDING_API_KEY 时 chunk_embeddings 有记录。
hybrid search 返回结果不低于 fts 基线。
eval 仍然 100% 通过。
仓库中不能出现真实 API key。
```

进入下一阶段条件：

```text
Hybrid 是可选增强，不影响默认 fts。
密钥安全检查通过。
```

## 阶段 3B：真实 Embedding 接入和效果评测

目的：在不提交密钥、不增加重型默认依赖的前提下，让外部 embedding API 可以被安全配置、构建缓存，并和 FTS 做可量化对比。

要做：

```text
1. 增加 .env 安全加载：只读本机 .env，不提交，不覆盖系统环境变量。
2. 增加 embedding-status：只输出 provider/base_url/model/configured/has_api_key，不输出 key。
3. 增加 hybrid_cases.jsonl：覆盖长问题、同义问法、跨领域问题。
4. 增加 hybrid-eval：同一批问题分别跑 fts / hybrid，输出 improved/tie/regressed/fallback。
5. README 增加 3B 验收命令。
6. 无 key 时所有命令安全降级；有 key 时能构建 chunk_embeddings 和 query_embedding_cache。
```

修改/新增文件：

```text
packages/nihaixia_core/env.py
packages/nihaixia_core/embedding.py
packages/nihaixia_core/cli.py
packages/nihaixia_core/hybrid_eval.py
evals/hybrid_cases.jsonl
pyproject.toml
README.md
```

本机 `.env` 示例：

```env
RAG_MODE=hybrid
EMBEDDING_PROVIDER=openai_compatible
EMBEDDING_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
EMBEDDING_MODEL=doubao-embedding-vision-250615
EMBEDDING_API_KEY=<只放本机，不提交>
```

验收命令：

```powershell
python -B -m nihaixia_core.cli embedding-status
python -B -m nihaixia_core.cli build-embeddings --db data/nihaixia.sqlite --limit 20
python -B -m nihaixia_core.hybrid_eval --db data/nihaixia.sqlite --cases evals/hybrid_cases.jsonl
python -B -m nihaixia_core.eval_runner --db data/nihaixia.sqlite --eval-dir evals --fail-on-error
```

通过标准：

```text
无 key 时 embedding-status 不显示密钥，build-embeddings 安全退出，hybrid-eval 标记 fallback。
有 key 时 chunk_embeddings 有记录，hybrid-eval 至少无 regressed。
eval 仍然 100% 通过。
仓库中不能出现真实 API key。
```
