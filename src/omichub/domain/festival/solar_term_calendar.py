"""24 节气日期表（2025-2035）

MVP 阶段不引入天文计算库，采用预计算表。仅覆盖配置中使用的节气；
年份超出范围时返回 None，由调用方降级处理。
"""

from datetime import date
from typing import Final

# 预计算 2025-2035 年配置中用到的节气日期
SOLAR_TERM_DATES: Final[dict[int, dict[int, tuple[int, int]]]] = {
    # 立春 index=0
    0: {
        2025: (2, 3),
        2026: (2, 4),
        2027: (2, 4),
        2028: (2, 4),
        2029: (2, 3),
        2030: (2, 4),
        2031: (2, 4),
        2032: (2, 4),
        2033: (2, 3),
        2034: (2, 4),
        2035: (2, 4),
    },
    # 夏至 index=10
    10: {
        2025: (6, 21),
        2026: (6, 21),
        2027: (6, 21),
        2028: (6, 21),
        2029: (6, 21),
        2030: (6, 21),
        2031: (6, 21),
        2032: (6, 21),
        2033: (6, 21),
        2034: (6, 21),
        2035: (6, 21),
    },
    # 秋分 index=15
    15: {
        2025: (9, 23),
        2026: (9, 23),
        2027: (9, 23),
        2028: (9, 22),
        2029: (9, 23),
        2030: (9, 23),
        2031: (9, 23),
        2032: (9, 22),
        2033: (9, 23),
        2034: (9, 23),
        2035: (9, 23),
    },
    # 冬至 index=22
    22: {
        2025: (12, 21),
        2026: (12, 22),
        2027: (12, 22),
        2028: (12, 21),
        2029: (12, 21),
        2030: (12, 22),
        2031: (12, 22),
        2032: (12, 21),
        2033: (12, 21),
        2034: (12, 22),
        2035: (12, 22),
    },
}


def get_solar_term_date(year: int, term_index: int) -> date | None:
    """获取指定年份、节气索引对应的公历日期。

    Args:
        year: 公历年份
        term_index: 节气索引 0-23

    Returns:
        日期或 None（未覆盖）
    """
    table = SOLAR_TERM_DATES.get(term_index)
    if not table:
        return None
    month_day = table.get(year)
    if not month_day:
        return None
    return date(year, month_day[0], month_day[1])


__all__ = ["get_solar_term_date", "SOLAR_TERM_DATES"]
