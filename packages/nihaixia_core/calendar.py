from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from calendar import monthrange
from zoneinfo import ZoneInfo


STEMS = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
BRANCHES = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
ELEMENTS = {"甲": "木", "乙": "木", "丙": "火", "丁": "火", "戊": "土", "己": "土", "庚": "金", "辛": "金", "壬": "水", "癸": "水", "子": "水", "丑": "土", "寅": "木", "卯": "木", "辰": "土", "巳": "火", "午": "火", "未": "土", "申": "金", "酉": "金", "戌": "土", "亥": "水"}
YIN_YANG = {"甲": "阳", "乙": "阴", "丙": "阳", "丁": "阴", "戊": "阳", "己": "阴", "庚": "阳", "辛": "阴", "壬": "阳", "癸": "阴"}
ZODIACS = ["鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪"]
HIDDEN_STEMS = {
    "子": ["癸"],
    "丑": ["己", "癸", "辛"],
    "寅": ["甲", "丙", "戊"],
    "卯": ["乙"],
    "辰": ["戊", "乙", "癸"],
    "巳": ["丙", "戊", "庚"],
    "午": ["丁", "己"],
    "未": ["己", "丁", "乙"],
    "申": ["庚", "壬", "戊"],
    "酉": ["辛"],
    "戌": ["戊", "辛", "丁"],
    "亥": ["壬", "甲"],
}
GROWTH_SEQUENCE = ["长生", "沐浴", "冠带", "临官", "帝旺", "衰", "病", "死", "墓", "绝", "胎", "养"]
GROWTH_BRANCHES_BY_STEM = {
    "甲": ["亥", "子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌"],
    "乙": ["午", "巳", "辰", "卯", "寅", "丑", "子", "亥", "戌", "酉", "申", "未"],
    "丙": ["寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥", "子", "丑"],
    "丁": ["酉", "申", "未", "午", "巳", "辰", "卯", "寅", "丑", "子", "亥", "戌"],
    "戊": ["寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥", "子", "丑"],
    "己": ["酉", "申", "未", "午", "巳", "辰", "卯", "寅", "丑", "子", "亥", "戌"],
    "庚": ["巳", "午", "未", "申", "酉", "戌", "亥", "子", "丑", "寅", "卯", "辰"],
    "辛": ["子", "亥", "戌", "酉", "申", "未", "午", "巳", "辰", "卯", "寅", "丑"],
    "壬": ["申", "酉", "戌", "亥", "子", "丑", "寅", "卯", "辰", "巳", "午", "未"],
    "癸": ["卯", "寅", "丑", "子", "亥", "戌", "酉", "申", "未", "午", "巳", "辰"],
}
NAYIN_BY_PAIR = [
    "海中金",
    "炉中火",
    "大林木",
    "路旁土",
    "剑锋金",
    "山头火",
    "涧下水",
    "城头土",
    "白蜡金",
    "杨柳木",
    "泉中水",
    "屋上土",
    "霹雳火",
    "松柏木",
    "长流水",
    "沙中金",
    "山下火",
    "平地木",
    "壁上土",
    "金箔金",
    "覆灯火",
    "天河水",
    "大驿土",
    "钗钏金",
    "桑柘木",
    "大溪水",
    "沙中土",
    "天上火",
    "石榴木",
    "大海水",
]

LUNAR_INFO = [
    0x04BD8, 0x04AE0, 0x0A570, 0x054D5, 0x0D260, 0x0D950, 0x16554, 0x056A0, 0x09AD0, 0x055D2,
    0x04AE0, 0x0A5B6, 0x0A4D0, 0x0D250, 0x1D255, 0x0B540, 0x0D6A0, 0x0ADA2, 0x095B0, 0x14977,
    0x04970, 0x0A4B0, 0x0B4B5, 0x06A50, 0x06D40, 0x1AB54, 0x02B60, 0x09570, 0x052F2, 0x04970,
    0x06566, 0x0D4A0, 0x0EA50, 0x06E95, 0x05AD0, 0x02B60, 0x186E3, 0x092E0, 0x1C8D7, 0x0C950,
    0x0D4A0, 0x1D8A6, 0x0B550, 0x056A0, 0x1A5B4, 0x025D0, 0x092D0, 0x0D2B2, 0x0A950, 0x0B557,
    0x06CA0, 0x0B550, 0x15355, 0x04DA0, 0x0A5D0, 0x14573, 0x052D0, 0x0A9A8, 0x0E950, 0x06AA0,
    0x0AEA6, 0x0AB50, 0x04B60, 0x0AAE4, 0x0A570, 0x05260, 0x0F263, 0x0D950, 0x05B57, 0x056A0,
    0x096D0, 0x04DD5, 0x04AD0, 0x0A4D0, 0x0D4D4, 0x0D250, 0x0D558, 0x0B540, 0x0B6A0, 0x195A6,
    0x095B0, 0x049B0, 0x0A974, 0x0A4B0, 0x0B27A, 0x06A50, 0x06D40, 0x0AF46, 0x0AB60, 0x09570,
    0x04AF5, 0x04970, 0x064B0, 0x074A3, 0x0EA50, 0x06B58, 0x055C0, 0x0AB60, 0x096D5, 0x092E0,
    0x0C960, 0x0D954, 0x0D4A0, 0x0DA50, 0x07552, 0x056A0, 0x0ABB7, 0x025D0, 0x092D0, 0x0CAB5,
    0x0A950, 0x0B4A0, 0x0BAA4, 0x0AD50, 0x055D9, 0x04BA0, 0x0A5B0, 0x15176, 0x052B0, 0x0A930,
    0x07954, 0x06AA0, 0x0AD50, 0x05B52, 0x04B60, 0x0A6E6, 0x0A4E0, 0x0D260, 0x0EA65, 0x0D530,
    0x05AA0, 0x076A3, 0x096D0, 0x04BD7, 0x04AD0, 0x0A4D0, 0x1D0B6, 0x0D250, 0x0D520, 0x0DD45,
    0x0B5A0, 0x056D0, 0x055B2, 0x049B0, 0x0A577, 0x0A4B0, 0x0AA50, 0x1B255, 0x06D20, 0x0ADA0,
    0x14B63, 0x09370, 0x049F8, 0x04970, 0x064B0, 0x168A6, 0x0EA50, 0x06B20, 0x1A6C4, 0x0AAE0,
    0x0A2E0, 0x0D2E3, 0x0C960, 0x0D557, 0x0D4A0, 0x0DA50, 0x05D55, 0x056A0, 0x0A6D0, 0x055D4,
    0x052D0, 0x0A9B8, 0x0A950, 0x0B4A0, 0x0B6A6, 0x0AD50, 0x055A0, 0x0ABA4, 0x0A5B0, 0x052B0,
    0x0B273, 0x06930, 0x07337, 0x06AA0, 0x0AD50, 0x04B55, 0x04B60, 0x0A570, 0x054E4, 0x0D160,
    0x0E968, 0x0D520, 0x0DAA0, 0x16AA6, 0x056D0, 0x04AE0, 0x0A9D4, 0x0A2D0, 0x0D150, 0x0F252,
    0x0D520,
]
LUNAR_BASE_DATE = date(1900, 1, 31)

JIE_TERMS = [
    ("小寒", 1),
    ("立春", 2),
    ("惊蛰", 3),
    ("清明", 4),
    ("立夏", 5),
    ("芒种", 6),
    ("小暑", 7),
    ("立秋", 8),
    ("白露", 9),
    ("寒露", 10),
    ("立冬", 11),
    ("大雪", 12),
]
SOLAR_TERM_CONSTANTS_20 = {"小寒": 6.11, "大寒": 20.84, "立春": 4.6295, "雨水": 19.4599, "惊蛰": 6.3826, "春分": 21.4155, "清明": 5.59, "谷雨": 20.888, "立夏": 6.318, "小满": 21.86, "芒种": 6.5, "夏至": 22.20, "小暑": 7.928, "大暑": 23.65, "立秋": 8.35, "处暑": 23.95, "白露": 8.44, "秋分": 23.822, "寒露": 9.098, "霜降": 24.218, "立冬": 8.218, "小雪": 23.08, "大雪": 7.9, "冬至": 22.60}
SOLAR_TERM_CONSTANTS_21 = {"小寒": 5.4055, "大寒": 20.12, "立春": 3.87, "雨水": 18.73, "惊蛰": 5.63, "春分": 20.646, "清明": 4.81, "谷雨": 20.1, "立夏": 5.52, "小满": 21.04, "芒种": 5.678, "夏至": 21.37, "小暑": 7.108, "大暑": 22.83, "立秋": 7.5, "处暑": 23.13, "白露": 7.646, "秋分": 23.042, "寒露": 8.318, "霜降": 23.438, "立冬": 7.438, "小雪": 22.36, "大雪": 7.18, "冬至": 21.94}


@dataclass(frozen=True)
class Pillar:
    stem: str
    branch: str
    ganzhi: str
    stem_element: str
    branch_element: str


def parse_datetime(value: str | datetime, timezone: str = "Asia/Shanghai") -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        text = value.strip().replace("T", " ")
        if len(text) == 10:
            dt = datetime.combine(date.fromisoformat(text), time())
        else:
            dt = datetime.fromisoformat(text)
    tz = ZoneInfo(timezone)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def ganzhi_from_index(index: int) -> str:
    return STEMS[index % 10] + BRANCHES[index % 12]


def pillar_from_index(index: int) -> Pillar:
    stem = STEMS[index % 10]
    branch = BRANCHES[index % 12]
    return Pillar(stem, branch, stem + branch, ELEMENTS[stem], ELEMENTS[branch])


def pillar_index_from_ganzhi(ganzhi: str) -> int:
    if len(ganzhi) != 2:
        raise ValueError(f"invalid ganzhi: {ganzhi}")
    stem_index = STEMS.index(ganzhi[0])
    branch_index = BRANCHES.index(ganzhi[1])
    return ((stem_index - branch_index) * 6 + branch_index) % 60


def nayin_for_index(index: int) -> str:
    return NAYIN_BY_PAIR[(index % 60) // 2]


def growth_stage(day_master: str, branch: str) -> str:
    branches = GROWTH_BRANCHES_BY_STEM[day_master]
    return GROWTH_SEQUENCE[branches.index(branch)]


def leap_month(year: int) -> int:
    return LUNAR_INFO[year - 1900] & 0xF


def leap_month_days(year: int) -> int:
    if leap_month(year) == 0:
        return 0
    return 30 if (LUNAR_INFO[year - 1900] & 0x10000) else 29


def lunar_month_days(year: int, month: int) -> int:
    return 30 if (LUNAR_INFO[year - 1900] & (0x10000 >> month)) else 29


def lunar_year_days(year: int) -> int:
    return sum(lunar_month_days(year, month) for month in range(1, 13)) + leap_month_days(year)


def solar_to_lunar(day: date) -> dict[str, object]:
    if day < LUNAR_BASE_DATE or day.year > 2100:
        raise ValueError("builtin lunar table supports dates from 1900-01-31 through 2100-12-31")
    offset = (day - LUNAR_BASE_DATE).days
    year = 1900
    while year <= 2100 and offset >= lunar_year_days(year):
        offset -= lunar_year_days(year)
        year += 1

    leap = leap_month(year)
    is_leap = False
    month = 1
    while month <= 12:
        days = leap_month_days(year) if is_leap else lunar_month_days(year, month)
        if offset < days:
            break
        offset -= days
        if leap == month and not is_leap:
            is_leap = True
        else:
            if is_leap:
                is_leap = False
            month += 1

    lunar_day = offset + 1
    return {
        "year": year,
        "month": month,
        "day": lunar_day,
        "is_leap_month": is_leap,
        "month_name": lunar_month_name(month, is_leap),
        "day_name": lunar_day_name(lunar_day),
        "zodiac": ZODIACS[(year - 4) % 12],
        "year_ganzhi": ganzhi_from_index((year - 4) % 60),
    }


def lunar_month_name(month: int, is_leap: bool = False) -> str:
    names = ["正月", "二月", "三月", "四月", "五月", "六月", "七月", "八月", "九月", "十月", "冬月", "腊月"]
    return ("闰" if is_leap else "") + names[month - 1]


def lunar_day_name(day: int) -> str:
    tens = ["初", "十", "廿", "卅"]
    ones = ["", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十"]
    if day == 10:
        return "初十"
    if day == 20:
        return "二十"
    if day == 30:
        return "三十"
    return tens[(day - 1) // 10] + ones[day % 10]


def solar_term_day(year: int, term: str) -> int:
    if not 1901 <= year <= 2100:
        raise ValueError("solar term approximation supports years from 1901 through 2100")
    constants = SOLAR_TERM_CONSTANTS_20 if year < 2000 else SOLAR_TERM_CONSTANTS_21
    y = year % 100
    return int(y * 0.2422 + constants[term]) - int((y - 1) / 4)


def jie_dates(year: int) -> list[tuple[str, date, int]]:
    return [(name, date(year, month, solar_term_day(year, name)), month) for name, month in JIE_TERMS]


def current_jie(dt: datetime) -> tuple[str, date, int]:
    candidates = jie_dates(dt.year - 1) + jie_dates(dt.year)
    current = candidates[0]
    for item in candidates:
        if item[1] <= dt.date():
            current = item
        else:
            break
    return current


def year_pillar_index(dt: datetime) -> int:
    lichun = date(dt.year, 2, solar_term_day(dt.year, "立春"))
    gz_year = dt.year if dt.date() >= lichun else dt.year - 1
    return (gz_year - 4) % 60


def month_pillar_index(dt: datetime, year_stem_index: int) -> tuple[int, str]:
    term_name, _term_date, term_month = current_jie(dt)
    month_index = (term_month - 2) % 12
    stem_index = ((year_stem_index % 5) * 2 + 2 + month_index) % 10
    branch_index = (2 + month_index) % 12
    return stem_index * 12 + branch_index if False else ((stem_index - branch_index) * 6 + branch_index) % 60, term_name


def julian_day_number(day: date) -> int:
    return day.toordinal() + 1721425


def day_pillar_index(day: date) -> int:
    return (julian_day_number(day) + 49) % 60


def effective_bazi_date(dt: datetime, day_boundary: str = "23:00") -> date:
    if day_boundary == "23:00" and dt.hour >= 23:
        return dt.date() + timedelta(days=1)
    return dt.date()


def hour_branch_index(dt: datetime) -> int:
    return ((dt.hour + 1) // 2) % 12


def hour_pillar_index(day_stem_index: int, branch_index: int) -> int:
    stem_index = ((day_stem_index % 5) * 2 + branch_index) % 10
    return ((stem_index - branch_index) * 6 + branch_index) % 60


def four_pillars(value: str | datetime, timezone: str = "Asia/Shanghai", day_boundary: str = "23:00") -> dict[str, object]:
    dt = parse_datetime(value, timezone)
    effective_day = effective_bazi_date(dt, day_boundary)
    year_index = year_pillar_index(dt)
    year_stem_index = year_index % 10
    month_index, month_term = month_pillar_index(dt, year_stem_index)
    day_index = day_pillar_index(effective_day)
    hour_branch = hour_branch_index(dt)
    hour_index = hour_pillar_index(day_index % 10, hour_branch)
    pillars = {
        "year": asdict(pillar_from_index(year_index)),
        "month": asdict(pillar_from_index(month_index)),
        "day": asdict(pillar_from_index(day_index)),
        "hour": asdict(pillar_from_index(hour_index)),
    }
    return {
        "datetime": dt.isoformat(),
        "timezone": timezone,
        "day_boundary": day_boundary,
        "effective_day": effective_day.isoformat(),
        "month_boundary_term": month_term,
        "pillars": pillars,
        "rules": {
            "year_boundary": "立春",
            "month_boundary": "节气",
            "day_boundary": day_boundary,
            "hour_branch": "23:00-00:59 为子时，之后每两小时一支",
        },
        "notes": [
            "内置 v1 使用 1900-2100 农历表和节气日期级近似；出生时间贴近节气交接日时，建议用权威万年历复核节气精确时刻。",
        ],
    }


def ten_god(day_master: str, target: str) -> str:
    dm_element = ELEMENTS[day_master]
    target_element = ELEMENTS[target]
    same_polarity = YIN_YANG[day_master] == YIN_YANG[target]
    generating = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}
    controlling = {"木": "土", "土": "水", "水": "火", "火": "金", "金": "木"}
    if dm_element == target_element:
        return "比肩" if same_polarity else "劫财"
    if generating[dm_element] == target_element:
        return "食神" if same_polarity else "伤官"
    if generating[target_element] == dm_element:
        return "偏印" if same_polarity else "正印"
    if controlling[dm_element] == target_element:
        return "偏财" if same_polarity else "正财"
    if controlling[target_element] == dm_element:
        return "七杀" if same_polarity else "正官"
    return ""


def empty_branches(day_index: int) -> list[str]:
    xun_start = day_index - day_index % 10
    occupied = {BRANCHES[(xun_start + offset) % 12] for offset in range(10)}
    return [branch for branch in BRANCHES if branch not in occupied]


def normalize_gender(gender: str) -> str:
    normalized = gender.strip().lower()
    if normalized in {"male", "man", "m", "男", "乾"}:
        return "male"
    if normalized in {"female", "woman", "f", "女", "坤"}:
        return "female"
    return "unknown"


def luck_direction(year_stem: str, gender: str) -> str:
    normalized = normalize_gender(gender)
    if normalized == "unknown":
        return "unknown"
    yang_year = YIN_YANG[year_stem] == "阳"
    return "forward" if (yang_year and normalized == "male") or (not yang_year and normalized == "female") else "backward"


def all_jie_dates_for_range(start_year: int, end_year: int) -> list[date]:
    values: list[date] = []
    for year in range(start_year, end_year + 1):
        values.extend(item[1] for item in jie_dates(year))
    return sorted(values)


def nearest_luck_boundary(day: date, direction: str) -> date:
    candidates = all_jie_dates_for_range(day.year - 1, day.year + 2)
    if direction == "forward":
        for candidate in candidates:
            if candidate > day:
                return candidate
    else:
        for candidate in reversed(candidates):
            if candidate < day:
                return candidate
    return day


def add_months(day: date, months: int) -> date:
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(day.day, monthrange(year, month)[1]))


def luck_start(day: date, direction: str) -> dict[str, object]:
    if direction == "unknown":
        return {
            "age_years": None,
            "age_months": None,
            "start_date": "",
            "boundary_date": "",
            "days_to_boundary": None,
        }
    boundary = nearest_luck_boundary(day, direction)
    days = abs((boundary - day).days)
    total_months = max(1, round(days * 4))
    start = add_months(day, total_months)
    return {
        "age_years": total_months // 12,
        "age_months": total_months % 12,
        "start_date": start.isoformat(),
        "boundary_date": boundary.isoformat(),
        "days_to_boundary": days,
    }


def luck_cycles(
    birth_day: date,
    month_index: int,
    year_stem: str,
    gender: str,
    day_master: str,
    count: int = 8,
) -> dict[str, object]:
    direction = luck_direction(year_stem, gender)
    if direction == "unknown":
        return {
            "direction": "unknown",
            "start": luck_start(birth_day, direction),
            "cycles": [],
            "rules": [
                "大运顺逆需提供性别：阳男阴女顺，阴男阳女逆。",
                "起运 v1 按出生日期到前后节气的日期差估算，三日折一年，一日折四个月。",
            ],
        }
    step = 1 if direction == "forward" else -1
    start = luck_start(birth_day, direction)
    start_years = int(start["age_years"] or 0)
    start_months = int(start["age_months"] or 0)
    cycles = []
    for offset in range(count):
        index = (month_index + step * (offset + 1)) % 60
        pillar = asdict(pillar_from_index(index))
        cycles.append(
            {
                "order": offset + 1,
                "start_age": {"years": start_years + offset * 10, "months": start_months},
                "end_age": {"years": start_years + offset * 10 + 9, "months": start_months},
                "pillar": pillar,
                "nayin": nayin_for_index(index),
                "ten_god": ten_god(day_master, pillar["stem"]),
                "growth_stage": growth_stage(day_master, pillar["branch"]),
            }
        )
    return {
        "direction": direction,
        "direction_label": "顺行" if direction == "forward" else "逆行",
        "start": start,
        "cycles": cycles,
        "rules": [
            "阳男阴女顺行，阴男阳女逆行。",
            "从月柱起排大运，顺行取后一柱，逆行取前一柱。",
            "起运 v1 按出生日期到前后节气的日期差估算，三日折一年，一日折四个月。",
        ],
    }


def annual_fortunes(start_year: int, years: int, day_master: str) -> list[dict[str, object]]:
    safe_years = max(0, min(years, 120))
    fortunes = []
    for year in range(start_year, start_year + safe_years):
        index = (year - 4) % 60
        pillar = asdict(pillar_from_index(index))
        fortunes.append(
            {
                "year": year,
                "pillar": pillar,
                "nayin": nayin_for_index(index),
                "ten_god": ten_god(day_master, pillar["stem"]),
                "growth_stage": growth_stage(day_master, pillar["branch"]),
            }
        )
    return fortunes


def bazi_chart(
    value: str | datetime,
    timezone: str = "Asia/Shanghai",
    gender: str = "unknown",
    location: str = "",
    use_true_solar_time: bool = False,
    day_boundary: str = "23:00",
    luck_cycle_count: int = 8,
    annual_start_year: int | None = None,
    annual_years: int = 10,
) -> dict[str, object]:
    dt = parse_datetime(value, timezone)
    fp = four_pillars(dt, timezone=timezone, day_boundary=day_boundary)
    pillars = fp["pillars"]
    day_master = pillars["day"]["stem"]
    stem_sequence = {key: pillars[key]["stem"] for key in ("year", "month", "day", "hour")}
    ten_gods = {key: ("日主" if key == "day" else ten_god(day_master, stem)) for key, stem in stem_sequence.items()}
    hidden = {key: HIDDEN_STEMS[pillars[key]["branch"]] for key in ("year", "month", "day", "hour")}
    pillar_indices = {key: pillar_index_from_ganzhi(pillars[key]["ganzhi"]) for key in ("year", "month", "day", "hour")}
    nayin = {key: nayin_for_index(pillar_indices[key]) for key in ("year", "month", "day", "hour")}
    growth_stages = {key: growth_stage(day_master, pillars[key]["branch"]) for key in ("year", "month", "day", "hour")}
    element_summary = {element: 0 for element in ["木", "火", "土", "金", "水"]}
    for key in ("year", "month", "day", "hour"):
        element_summary[pillars[key]["stem_element"]] += 1
        element_summary[pillars[key]["branch_element"]] += 1
    day_index = day_pillar_index(date.fromisoformat(fp["effective_day"]))
    lunar = solar_to_lunar(dt.date())
    annual_start = annual_start_year if annual_start_year is not None else dt.year
    return {
        "input": {
            "datetime": fp["datetime"],
            "timezone": timezone,
            "gender": normalize_gender(gender),
            "location": location,
            "use_true_solar_time": use_true_solar_time,
        },
        "rules": fp["rules"],
        "lunar": lunar,
        "pillars": pillars,
        "ten_gods": ten_gods,
        "hidden_stems": hidden,
        "nayin": nayin,
        "growth_stages": growth_stages,
        "five_elements": {
            "summary": element_summary,
            "stems": [pillars[key]["stem_element"] for key in ("year", "month", "day", "hour")],
            "branches": [pillars[key]["branch_element"] for key in ("year", "month", "day", "hour")],
        },
        "day_master": day_master,
        "empty_branches": empty_branches(day_index),
        "luck_cycles": luck_cycles(
            dt.date(),
            pillar_indices["month"],
            pillars["year"]["stem"],
            gender,
            day_master,
            count=luck_cycle_count,
        ),
        "annual_fortunes": annual_fortunes(annual_start, annual_years, day_master),
        "month_boundary_term": fp["month_boundary_term"],
        "notes": [
            *fp["notes"],
            "四柱排盘结果用于传统命理学习和结构分析，不作绝对命运判断。",
            "use_true_solar_time 当前为预留参数；v1 不自动按出生地经度校正真太阳时。",
            "大运起运 v1 使用日期级节气差近似；正式排盘请用精确节气时刻复核。",
        ],
    }


def calendar_report(value: str | datetime, timezone: str = "Asia/Shanghai") -> dict[str, object]:
    dt = parse_datetime(value, timezone)
    return {
        "input": {"datetime": dt.isoformat(), "timezone": timezone},
        "lunar": solar_to_lunar(dt.date()),
        "ganzhi": four_pillars(dt, timezone=timezone),
    }
