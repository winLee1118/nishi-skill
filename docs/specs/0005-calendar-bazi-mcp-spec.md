# 0005 Calendar/Bazi MCP 易学时间底座 Spec

## 阶段 5A：干支、农历、四柱基础盘

已执行。

目标：

```text
为天纪、地纪、紫微、四柱命理、风水择日等场景提供确定性时间换算工具。
LLM 不再自行心算干支、农历、四柱，而是先调用 MCP 工具。
```

默认规则：

```text
timezone: Asia/Shanghai
year_boundary: 立春
month_boundary: 节气
day_boundary: 23:00 子时换日
use_true_solar_time: false
```

MCP 工具：

```text
convert_calendar
get_ganzhi
get_bazi_chart
get_ziwei_inputs
get_fengshui_time
```

CLI：

```powershell
nihaixia-calendar "2024-02-10"
nihaixia-ganzhi "2024-02-10 08:30"
nihaixia-bazi "2024-02-10 08:30" --gender unknown
```

v1 输出：

```text
公历转农历
年柱 / 月柱 / 日柱 / 时柱
十神
藏干
五行统计
空亡
纳音
十二长生
大运
流年
紫微起盘前置参数
风水/择日时间底座
```

v1 边界：

```text
内置农历表支持 1900-01-31 到 2100-12-31。
节气为日期级近似；贴近节气交接时刻的出生盘，应使用权威万年历复核。
use_true_solar_time 是预留参数，当前不按出生地经度自动校正。
大运起运 v1 使用日期级节气差近似：三日折一年，一日折四个月。
get_ziwei_inputs 不生成完整紫微星曜盘。
get_fengshui_time 不生成完整择日体系。
输出只用于传统文化学习和结构分析，不作绝对命运判断。
```

产出文件：

```text
packages/nihaixia_core/calendar.py
packages/nihaixia_core/cli.py
packages/nihaixia_mcp/server.py
tests/test_calendar.py
README.md
skill/ni-haixia-system/SKILL.md
```

验收命令：

```powershell
$env:PYTHONPATH="packages"
pytest -q tests/test_calendar.py -p no:cacheprovider
pytest -q tests -p no:cacheprovider
python -B -c "from nihaixia_mcp.server import get_bazi_chart; print(get_bazi_chart('2024-02-10 08:30')['pillars'])"
```

## 阶段 5B 补充：MCP 契约测试

已执行。

Calendar/Bazi 工具补充契约：

```text
convert_calendar 正常返回 lunar + ganzhi
get_ganzhi 正常返回 pillars + rules
get_bazi_chart 正常返回 pillars / ten_gods / hidden_stems / five_elements / empty_branches
get_ziwei_inputs 正常返回紫微起盘前置参数和边界说明
get_fengshui_time 正常返回地纪/风水/择日时间底座
日期越界或非法时区时返回 {"error": {"type": ..., "message": ...}}
```

对应测试：

```text
tests/test_calendar.py
tests/test_mcp_contracts.py
```

## 阶段 5A-2：增强四柱排盘

已执行。

增强字段：

```text
nayin: 年/月/日/时四柱纳音
growth_stages: 以日主天干看四支十二长生
luck_cycles: 大运顺逆、起运估算、每步大运干支/纳音/十神/十二长生
annual_fortunes: 指定年份起的流年干支/纳音/十神/十二长生
```

大运规则：

```text
阳男阴女顺行，阴男阳女逆行。
从月柱起排大运，顺行取后一柱，逆行取前一柱。
起运 v1 按出生日期到前后节气的日期差估算，三日折一年，一日折四个月。
```

新增/修改：

```text
packages/nihaixia_core/calendar.py
packages/nihaixia_core/cli.py
packages/nihaixia_mcp/server.py
tests/test_calendar.py
README.md
```
