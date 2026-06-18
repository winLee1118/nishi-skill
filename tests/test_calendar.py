from __future__ import annotations

from datetime import date

from nihaixia_core.calendar import (
    bazi_chart,
    day_pillar_index,
    four_pillars,
    ganzhi_from_index,
    growth_stage,
    nayin_for_index,
    solar_to_lunar,
)
from nihaixia_mcp.server import convert_calendar, get_bazi_chart, get_fengshui_time, get_ganzhi, get_ziwei_inputs


def test_solar_to_lunar_chinese_new_year_2024() -> None:
    lunar = solar_to_lunar(date(2024, 2, 10))

    assert lunar["year"] == 2024
    assert lunar["month"] == 1
    assert lunar["day"] == 1
    assert lunar["month_name"] == "正月"
    assert lunar["day_name"] == "初一"
    assert lunar["zodiac"] == "龙"
    assert lunar["year_ganzhi"] == "甲辰"


def test_four_pillars_uses_lichun_and_jie_month_boundaries() -> None:
    before_lichun = four_pillars("2024-02-03 12:00")
    after_lichun = four_pillars("2024-02-10 08:30")
    after_jingzhe = four_pillars("2024-03-06 12:00")

    assert before_lichun["pillars"]["year"]["ganzhi"] == "癸卯"
    assert after_lichun["pillars"]["year"]["ganzhi"] == "甲辰"
    assert after_lichun["pillars"]["month"]["ganzhi"] == "丙寅"
    assert after_lichun["pillars"]["day"]["ganzhi"] == "甲辰"
    assert after_lichun["pillars"]["hour"]["ganzhi"] == "戊辰"
    assert after_jingzhe["pillars"]["month"]["ganzhi"] == "丁卯"


def test_day_pillar_jdn_calibration() -> None:
    # Public calendar examples list 2120-04-23 as a Gengchen day.
    assert ganzhi_from_index(day_pillar_index(date(2120, 4, 23))) == "庚辰"


def test_bazi_chart_contains_study_fields() -> None:
    chart = bazi_chart("2024-02-10 08:30", gender="unknown", annual_start_year=2026, annual_years=3)

    assert chart["day_master"] == "甲"
    assert chart["ten_gods"]["day"] == "日主"
    assert chart["hidden_stems"]["hour"] == ["戊", "乙", "癸"]
    assert chart["nayin"]["year"] == "覆灯火"
    assert chart["nayin"]["hour"] == "大林木"
    assert chart["growth_stages"]["month"] == "临官"
    assert set(chart["five_elements"]["summary"]) == {"木", "火", "土", "金", "水"}
    assert chart["empty_branches"]
    assert chart["luck_cycles"]["direction"] == "unknown"
    assert chart["annual_fortunes"][0]["pillar"]["ganzhi"] == "丙午"
    assert chart["annual_fortunes"][0]["nayin"] == "天河水"
    assert "四柱排盘结果用于传统命理学习和结构分析" in "\n".join(chart["notes"])


def test_nayin_and_growth_stage_tables() -> None:
    assert nayin_for_index(0) == "海中金"
    assert nayin_for_index(40) == "覆灯火"
    assert growth_stage("甲", "寅") == "临官"
    assert growth_stage("甲", "卯") == "帝旺"
    assert growth_stage("癸", "卯") == "长生"


def test_luck_cycles_for_male_and_female_direction() -> None:
    male_chart = bazi_chart("2024-02-10 08:30", gender="男", luck_cycle_count=2, annual_years=0)
    female_chart = bazi_chart("2024-02-10 08:30", gender="女", luck_cycle_count=2, annual_years=0)

    assert male_chart["luck_cycles"]["direction"] == "forward"
    assert male_chart["luck_cycles"]["cycles"][0]["pillar"]["ganzhi"] == "丁卯"
    assert female_chart["luck_cycles"]["direction"] == "backward"
    assert female_chart["luck_cycles"]["cycles"][0]["pillar"]["ganzhi"] == "乙丑"


def test_calendar_mcp_tools_return_contracts() -> None:
    converted = convert_calendar("2024-02-10")
    pillars = get_ganzhi("2024-02-10 08:30")
    chart = get_bazi_chart("2024-02-10 08:30", gender="男", annual_start_year=2026, annual_years=2)
    ziwei = get_ziwei_inputs("2024-02-10 08:30")
    fengshui = get_fengshui_time("2024-02-10 08:30")

    assert converted["lunar"]["day_name"] == "初一"
    assert pillars["pillars"]["hour"]["ganzhi"] == "戊辰"
    assert chart["pillars"]["year"]["ganzhi"] == "甲辰"
    assert chart["luck_cycles"]["cycles"][0]["pillar"]["ganzhi"] == "丁卯"
    assert chart["annual_fortunes"][0]["year"] == 2026
    assert "lunar" in ziwei
    assert "nayin" in ziwei
    assert "完整星曜排盘" in "\n".join(ziwei["notes"])
    assert fengshui["nayin"]["year"] == "覆灯火"
    assert fengshui["month_boundary_term"] == "立春"


def test_calendar_mcp_tools_return_structured_errors() -> None:
    out_of_range = get_bazi_chart("1800-01-01 12:00")
    bad_timezone = get_ganzhi("2024-02-10 08:30", timezone="Mars/Olympus")

    assert out_of_range["error"]["type"] == "ValueError"
    assert "supports" in out_of_range["error"]["message"]
    assert bad_timezone["error"]["type"] == "ZoneInfoNotFoundError"
