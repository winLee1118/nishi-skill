# 0003 Hybrid 向量查询 Spec

本 Spec 为项目增加可选向量查询模式。目标是提升语义检索能力，但不破坏当前轻量默认模式。

## 1. 目标

默认模式保持不变：

```text
RAG_MODE=fts
SQLite FTS5/BM25
```

新增可选模式：

```text
RAG_MODE=hybrid
SQLite FTS5/BM25 + 外部 Embedding API + SQLite 向量缓存 + 融合排序
```

设计原则：

```text
不把 embedding API 变成默认依赖
不在仓库提交 API key
不重复计算已有 chunk embedding
BM25 和向量检索并行召回，再融合排序
没有 API key 时自动退回 fts
```

## 2. 当前推荐提供商

当前用户计划使用豆包 / 火山方舟 embedding API：

```text
provider: openai_compatible
base_url: https://ark.cn-beijing.volces.com/api/v3
model: doubao-embedding-vision-251215
dim: 1024
```

当前工程已验证：

```text
doubao-embedding-vision-251215
POST /api/v3/embeddings/multimodal
input: [{"type": "text", "text": "..."}]
response: data.embedding
```

文本 embedding 模型继续使用 OpenAI-compatible `/embeddings`；vision embedding 模型使用 `/embeddings/multimodal`。

API key 必须只放在本机环境变量或 `.env` 文件中。仓库只能提交占位符：

```env
EMBEDDING_API_KEY=
```

不要把真实 key 写入：

```text
.env.example
README.md
docs/
tests/
代码文件
git commit message
issue / PR 描述
```

## 3. 环境变量

```env
RAG_MODE=hybrid
EMBEDDING_PROVIDER=openai_compatible
EMBEDDING_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
EMBEDDING_API_KEY=
EMBEDDING_MODEL=doubao-embedding-vision-251215
EMBEDDING_DIM=1024
VECTOR_STORE=sqlite
VECTOR_CACHE_DB=data/nihaixia.sqlite
```

说明：

```text
EMBEDDING_DIM 可以首次调用后自动记录。
VECTOR_STORE 第一版只做 sqlite。
后续如需 Qdrant，作为 adapter 增加，不替换 sqlite 默认路径。
```

## 4. 数据库设计

新增表：

```sql
CREATE TABLE IF NOT EXISTS chunk_embeddings (
  chunk_id TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  embedding_hash TEXT NOT NULL,
  dim INTEGER NOT NULL,
  vector_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (chunk_id, provider, model)
);

CREATE TABLE IF NOT EXISTS query_embedding_cache (
  query_hash TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  dim INTEGER NOT NULL,
  vector_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (query_hash, provider, model)
);
```

第一版用 `vector_json` 存储，避免引入 sqlite-vec 原生扩展。后续如果性能不足，再加：

```text
sqlite-vec adapter
Qdrant adapter
```

## 5. Embedding 文本

chunk embedding 不直接用原文裸文本，应使用：

```text
context_prefix + topics + entities + aliases + original_text
```

这样可保留：

```text
人纪 / 天纪 / 地纪
课程
章节
术语
别名
引用上下文
```

embedding_hash 计算输入：

```text
provider
model
source_id
chunk_id
contextual_text
topics_json
entities_json
aliases_json
```

只要 hash 不变，就不重新计算。

## 6. 查询流程

`RAG_MODE=fts`：

```text
用户问题
→ SQLite FTS5/BM25
→ metadata/entity rerank
→ top_k
```

`RAG_MODE=hybrid`：

```text
用户问题
→ BM25 召回 top_n
→ query embedding
→ vector cache / chunk_embeddings 语义召回 top_n
→ 合并去重
→ 融合排序
→ top_k
```

融合排序建议：

```text
final_score =
  0.62 * bm25_normalized
  + 0.18 * vector_similarity * lexical_coverage_gate
  + 0.12 * lexical_coverage
  + 0.05 * domain_match
  + 0.03 * rights_status_weight
  + bm25_protection_bonus
```

当前实现额外保护 FTS 基线：

```text
1. 先用 BM25/FTS 召回候选。
2. 对 FTS 候选执行原有 metadata/entity rerank。
3. 保护 FTS rerank 后 top_k，不允许向量结果把它们全部挤出。
4. 向量分数必须经过 lexical_coverage_gate，问题术语覆盖越少，向量影响越弱。
```

如果 embedding API 不可用：

```text
记录 warning
自动回退到 fts
不让 MCP 调用失败
```

## 7. 新增模块

```text
packages/nihaixia_core/embedding.py
packages/nihaixia_core/vector_store.py
packages/nihaixia_core/hybrid_retrieval.py
```

职责：

```text
embedding.py
  - 读取环境变量
  - OpenAI-compatible embedding request
  - provider/model/key 配置检测
  - query cache key

vector_store.py
  - chunk_embeddings 表
  - query_embedding_cache 表
  - cosine similarity
  - cache upsert / read

hybrid_retrieval.py
  - BM25 召回
  - vector 召回
  - score fusion
  - fallback to fts
```

## 8. CLI

新增命令：

```powershell
nihaixia-embedding-status
nihaixia-build-embeddings --db data/nihaixia.sqlite --limit 100
nihaixia-search "桂枝汤和太阳中风" --db data/nihaixia.sqlite --mode hybrid
nihaixia-hybrid-eval --db data/nihaixia.sqlite --cases evals/hybrid_cases.jsonl
```

或者：

```powershell
$env:RAG_MODE="hybrid"
python -m nihaixia_core.cli search "桂枝汤和太阳中风" --db data/nihaixia.sqlite
```

## 9. MCP 行为

`search_sources` 增加可选参数：

```json
{
  "question": "...",
  "domain": "auto",
  "top_k": 5,
  "mode": "auto"
}
```

mode：

```text
auto    # 读取 RAG_MODE
fts     # 强制 BM25
hybrid  # 强制 hybrid，可失败回退
```

返回增加：

```json
{
  "retrieval_mode": "hybrid",
  "fallback": false,
  "warnings": []
}
```

## 10. 安全和密钥规则

必须做到：

```text
.env 被 gitignore
.env.* 被 gitignore
.env.example 只放空值
日志不能打印 EMBEDDING_API_KEY
异常不能包含完整 Authorization header
测试不能硬编码真实 key
.env 只在本机加载，不能进入 git
embedding-status 只能显示 has_api_key=true/false
```

如果 key 已经进入 git：

```text
立即撤销/轮换 key
清理 git history
重新生成 key
```

## 11. 验收标准

无 key：

```text
RAG_MODE=hybrid 时不崩溃
自动回退 fts
eval 仍然通过
```

有 key：

```text
build-embeddings 可以写入 chunk_embeddings
query embedding 可以写入 query_embedding_cache
hybrid search 返回 retrieval_mode=hybrid
同义/长问题召回优于纯 fts 的样例至少 2 个
eval 仍然通过
```

当前执行状态：

```text
chunk_embeddings: 977 / 977
query_embedding_cache: 已写入
hybrid search: retrieval_mode=hybrid, fallback=false
hybrid_eval: 5 tie / 0 regressed / 0 fallback
基础 eval: 9 / 9
```

说明：当前 hybrid 策略先保证不低于 FTS 基线；后续需要扩充更强的同义/长问题评测集，再优化出至少 2 个 improved case。

密钥：

```text
rg "真实 API key" . 不应命中任何仓库文件
git status 不显示 .env 或 .env.local
```
