"""
台股交易日曆工具
使用 exchange_calendars (XTAI) 判斷是否為台灣股市交易日，
並找出最近一個交易日。
"""
from datetime import date, timedelta
from functools import lru_cache


@lru_cache(maxsize=1)
def _get_calendar():
    try:
        import exchange_calendars as xcals
        return xcals.get_calendar("XTAI")
    except Exception:
        return None


def is_trading_day(d: date = None) -> bool:
    """判斷指定日期是否為台股交易日（預設今日）"""
    if d is None:
        d = date.today()
    if d.weekday() >= 5:          # 週六、日直接排除
        return False
    cal = _get_calendar()
    if cal is None:               # 套件異常時 fallback：週一～五視為交易日
        return True
    try:
        return cal.is_session(d.isoformat())
    except Exception:
        return d.weekday() < 5


def latest_trading_day(before: date = None) -> date:
    """回傳 before 當日或之前最近一個台股交易日（預設今日）"""
    if before is None:
        before = date.today()
    cal = _get_calendar()
    if cal is None:
        d = before
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        return d
    try:
        sessions = cal.sessions_in_range("2020-01-01", before.isoformat())
        return sessions[-1].date() if len(sessions) else before
    except Exception:
        return before
