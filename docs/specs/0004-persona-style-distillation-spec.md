# 0004 人物风格蒸馏 Spec

目标：在保持 Skill + MCP 轻量级调用的前提下，让数字分身具备更自然的讲课临场感、人物语言节奏和性格表达，同时不冒充本人、不做声音克隆、不替代诊断处方。

## 阶段 4A：公开视频小样本风格指纹

已执行。

资料来源：

```text
Bilibili: 【完整版】倪海厦针灸大成字幕版（人纪）
URL: https://www.bilibili.com/video/BV1NeuczHEPm/
```

处理方式：

```text
1. 确认页面可访问。
2. 检查 Bilibili 字幕 API 和播放器字幕菜单。
3. 确认无独立字幕轨，字幕为画面内嵌。
4. 使用 Chrome 少量截图抽样。
5. 只提炼语言结构、讲课动作和人格特征，不保存长篇逐字稿。
```

产出文件：

```text
knowledge/persona/nihaixia-video-style-fingerprint-v0.1.md
```

已沉淀风格动作：

```text
问题式推进
生活物件举例
先讲操作判断再补原因
正反对比收边界
轻微玩笑感
```

验收命令：

```powershell
$env:PYTHONPATH="packages"
python -B -m nihaixia_core.eval_runner --db data/nihaixia.sqlite --eval-dir evals --fail-on-error
python -B -m nihaixia_core.hybrid_eval --db data/nihaixia.sqlite --cases evals/hybrid_cases.jsonl --fail-on-regression
```

当前验收结果：

```text
eval_runner: 12/12 passed
hybrid_eval: 5 tie / 0 regressed / 0 fallback
```

## 阶段 4B：风格指纹数据化

已执行。

要做：

```text
1. 新增 knowledge/persona/style-fingerprint.schema.json。
2. 把 v0.1 Markdown 中的 teaching_moves / sentence_rhythm / personality_marks 转成 JSON。
3. persona.py 从静态常量迁移为读取 JSON，读取失败时回退默认内置 profile。
4. 为 style_intensity 增加更细粒度权重：questioning、example_density、humor、boundary_visibility。
5. 增加单元测试，保证无外部模型、无向量库时也能返回 persona guidance。
```

通过标准：

```text
get_persona_guidance 返回 video_style_fingerprint
style eval 通过
无 API key 时也可运行
```

产出文件：

```text
knowledge/persona/style-fingerprint.schema.json
knowledge/persona/style-fingerprint-v0.1.json
tests/test_persona.py
```

实现说明：

```text
persona.py 从 knowledge/persona/style-fingerprint-v0.1.json 读取风格指纹。
读取失败或 JSON 结构不完整时，自动回退内置默认 profile。
style_intensity 已增加 questioning / example_density / humor / boundary_visibility 权重。
```

## 阶段 4C-2：字幕样本扩充与轻量 Prompt 接入

已执行。

目的：

```text
用本地已导出的剪映字幕扩大人物风格样本，让数字分身的讲课节奏、短问句、对比判断、操作先行解释更稳定。
同时保持 Skill + MCP 轻量调用：运行时只注入风格摘要，不注入完整 profile、完整字幕或长样本。
```

处理方式：

```text
1. 将剪映导出的总 SRT 保存到 private 忽略目录。
2. 按本地视频素材时长拆分成 16 个 source SRT。
3. 从拆分字幕中抽取短样本，按 人纪 / 天纪 / 地纪 / 访谈 分布。
4. 生成 style-samples-v0.2.jsonl，只保存短样本和结构标注。
5. 生成 knowledge/persona/style-fingerprint-v0.2.json。
6. persona.py 改为读取 v0.2，并将完整 profile 压缩为 style_digest 注入 style_prompt。
```

样本规模：

```text
total: 220
人纪: 80
天纪: 60
地纪: 30
访谈: 50
```

产出文件：

```text
tools/extract_style_samples_from_srt.py
materials/bilibili-style-sources/samples/style-samples-v0.2.jsonl
knowledge/persona/style-fingerprint-v0.2.json
packages/nihaixia_core/persona.py
tests/test_persona.py
```

通过标准：

```text
load_style_fingerprint() 加载 version=0.2
persona style_prompt 包含风格摘要
persona style_prompt 不包含 profile= 完整结构
完整字幕和原始视频仍在 private/raw-videos 忽略目录
```

## 阶段 4C：回答生成侧风格编排

已执行。

要做：

```text
1. answer_with_citations 增加 persona_composition 字段。
2. 把回答拆成 evidence_plan、style_plan、safety_plan。
3. 普通问题不硬性免责声明。
4. 高风险问题保留数字分身口吻，但柔性收边界。
5. 增加端到端样例：普通学习、身份要求、诊断处方、天纪断语。
```

通过标准：

```text
回答结构可解释
风格不覆盖引用
边界不机械、不冒充本人
```

实现说明：

```text
answer_with_citations 现在保持旧字段不变，同时新增：

evidence_plan
style_plan
safety_plan
persona_composition

evidence_plan 负责说明 citation 数量、retrieval_mode、top source、warnings、limitations。
style_plan 负责说明 style_intensity、数字分身身份、v0.2 fingerprint version、domain_focus 和 compact style_prompt。
safety_plan 负责说明 risk_level、medical_intent、identity_request、absolute_fate_request、boundary_style 和 must_not。
persona_composition 负责给外部智能体最终组装顺序：先 evidence，再 style，再 safety，最后 answer。
```

新增验收：

```text
tests/test_mcp_contracts.py
pytest -q tests -p no:cacheprovider
```
