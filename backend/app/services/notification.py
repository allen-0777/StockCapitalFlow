import os
import logging
import aiohttp
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

# Status constants — imported by admin.py to avoid string literals
STEP_OK = "ok"
STEP_ERROR = "error"
JOB_OK = "ok"
JOB_PARTIAL = "partial_error"
JOB_ERROR = "error"


def _token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "")


def _chat_id() -> str:
    return os.getenv("TELEGRAM_CHAT_ID", "")


async def send_message(message: str) -> None:
    """Send a Telegram message. Truncates at 4096 chars. Never raises."""
    token = _token()
    chat_id = _chat_id()
    if not token or not chat_id:
        logger.warning("[notification] TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set, skipping")
        return

    message = message[:4096]
    url = TELEGRAM_API.format(token=token)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"},
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning(f"[notification] Telegram returned {resp.status}: {body[:200]}")
    except Exception as e:
        logger.warning(f"[notification] Failed to send Telegram message: {e}")


async def send_job_result(
    job: str,
    steps: list[dict],
    got_date,
    expected_date,
) -> None:
    """Send job result summary to Telegram. Call once after all retries."""
    has_error = any(s.get("status") == STEP_ERROR for s in steps)
    all_error = all(s.get("status") == STEP_ERROR for s in steps)

    if all_error:
        emoji, label = "❌", "失敗"
    elif has_error:
        emoji, label = "⚠️", "部分失敗"
    else:
        emoji, label = "✅", "完成"

    date_str = str(got_date) if got_date else str(expected_date)
    lines = [f"{emoji} <b>{job}</b> {label} ({date_str})"]

    for s in steps:
        fn = s.get("fn", "")
        status = s.get("status", "")
        duration = s.get("duration_s")
        error = s.get("error")
        rows = s.get("rows")

        if status == STEP_OK:
            parts = []
            if rows:
                parts.append(f"{rows:,} 筆")
            if duration is not None:
                parts.append(f"{duration:.1f}s")
            detail = " | ".join(parts)
            lines.append(f"✓ {fn} — {detail}")
        else:
            lines.append(f"✗ {fn} — {error or '未知錯誤'}")

    if got_date and expected_date and got_date != expected_date:
        lines.append(f"<i>日期不符: 預期 {expected_date}, 實際 {got_date}</i>")

    await send_message("\n".join(lines))


async def send_daily_digest(db: Session) -> None:
    """Send daily digest with latest available data. Works on holidays."""
    chip_row = db.execute(
        text("""
            SELECT date, foreign_buy, trust_buy, dealer_buy,
                   margin_long, margin_short,
                   tx_foreign_long, tx_foreign_short
            FROM daily_chips
            WHERE stock_id = '0000'
            ORDER BY date DESC LIMIT 1
        """)
    ).fetchone()

    if not chip_row:
        await send_message("📊 每日彙整：資料庫尚無資料")
        return

    opt_row = db.execute(
        text("""
            SELECT date, pc_ratio, call_max_strike, put_max_strike
            FROM daily_options
            ORDER BY date DESC LIMIT 1
        """)
    ).fetchone()

    d = chip_row[0]
    foreign = chip_row[1] or 0
    trust = chip_row[2] or 0
    dealer = chip_row[3] or 0
    margin_long_kth = chip_row[4] or 0
    margin_short = chip_row[5] or 0
    tx_fl = chip_row[6] or 0
    tx_fs = chip_row[7] or 0

    margin_long_yi = round(margin_long_kth / 100000, 2)
    tx_net = tx_fl - tx_fs

    def sign(v: float) -> str:
        return f"+{v:.1f}" if v >= 0 else f"{v:.1f}"

    lines = [
        f"📊 <b>每日彙整 {d}</b>",
        f"法人: 外資 {sign(foreign)}億 | 投信 {sign(trust)}億 | 自營 {sign(dealer)}億",
        f"融資: {sign(margin_long_yi)}億 | 融券: {margin_short:+,} 張",
        f"台指外資: 多 {tx_fl:,} 空 {tx_fs:,} 淨 {tx_net:+,}",
    ]

    if opt_row:
        pc = opt_row[1]
        call_s = opt_row[2]
        put_s = opt_row[3]
        lines.append(f"選擇權: P/C={pc}% | 壓力 {call_s} | 支撐 {put_s}")

    await send_message("\n".join(lines))
