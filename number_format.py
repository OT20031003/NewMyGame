JA_LARGE_UNITS = [
    "",
    "万",
    "億",
    "兆",
    "京",
    "垓",
    "秭",
    "穣",
    "溝",
    "澗",
    "正",
    "載",
    "極",
    "恒河沙",
    "阿僧祇",
    "那由他",
    "不可思議",
    "無量大数",
]


def format_ja_units(value):
    """数値を日本語の大数単位（万, 億, 兆, 京...）で整形する。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value

    if number == 0:
        return "0"

    sign = "-" if number < 0 else ""
    absolute = abs(number)

    if absolute < 10_000:
        if absolute.is_integer():
            return f"{sign}{int(absolute):,}"
        return f"{sign}{absolute:,.1f}"

    rounded = int(round(absolute))
    if rounded == 0:
        return "0"

    parts = []
    unit_index = 0
    while rounded > 0:
        chunk = rounded % 10_000
        if chunk:
            if unit_index < len(JA_LARGE_UNITS):
                unit = JA_LARGE_UNITS[unit_index]
            else:
                unit = f"10^{unit_index * 4}"
            parts.append(f"{chunk}{unit}")
        rounded //= 10_000
        unit_index += 1

    return sign + "".join(reversed(parts))
