from datetime import date, datetime


def parse_date(d: str | date) -> date:
    """Helper to ensure we have a date object."""
    if isinstance(d, date):
        return d

    try:
        ret_date = datetime.strptime(d, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("不正確的日期格式, 請使用 YYYY-MM-DD 格式")

    return ret_date


def validate_dates(
    start_date: str | date, end_date: str | date
) -> str | tuple[str, int]:
    """
    Checks the interval between start_date and end_date.

    Returns:
        1. "invalid" if start_date > end_date
        2. "today is not end" if end_date is today
        3. ("valid", days) if valid
    """
    s = parse_date(start_date)
    e = parse_date(end_date)
    today = date.today()

    if s > e:
        return "起迄日不合法, 結束日期在起始日期之前"

    if e == today:
        return "不能把今天設為結束日期"

    delta = (e - s).days

    return "正確", delta
