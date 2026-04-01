"""
產業相對大盤強度（RS）與輪動訊號（規則式）。
資料來源：market_series_daily 的 IDX:TAIEX 與 IND:* proxy 序列。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.industry_sync import INDUSTRY_PROXY_STOCKS

BENCHMARK_ID = "IDX:TAIEX"
TOP_FRAC = 0.2
RANK_DAYS = 5
HIGH_DAYS = 20


@dataclass
class IndustryRow:
    series_id: str
    name: str
    proxy_stock: str
    latest_close: float | None
    daily_return_pct: float | None
    rs_vs_taiex_pct: float | None
    rank: int | None
    avg_rank_5d: float | None
    rotation_signal: bool
    signal_reasons: list[str]


def _load_series_many(db: Session, series_ids: list[str]) -> dict[str, list[tuple[str, float]]]:
    """一次載入多個 series_id 的 (date, close)，依日期升序。"""
    if not series_ids:
        return {}
    uniq = list(dict.fromkeys(series_ids))
    placeholders = ",".join(f":id{i}" for i in range(len(uniq)))
    params = {f"id{i}": sid for i, sid in enumerate(uniq)}
    rows = db.execute(
        text(
            f"SELECT series_id, date, close FROM market_series_daily "
            f"WHERE series_id IN ({placeholders}) ORDER BY series_id, date ASC"
        ),
        params,
    ).fetchall()
    out: dict[str, list[tuple[str, float]]] = {sid: [] for sid in uniq}
    for series_id, dt, close in rows:
        sid = str(series_id)
        d = str(dt)[:10]
        c = float(close or 0)
        if d and c > 0:
            out.setdefault(sid, []).append((d, c))
    return out


def _latest_names_by_series(db: Session, series_ids: list[str]) -> dict[str, str]:
    """各 series 最新一筆日線的 name（顯示用）。"""
    if not series_ids:
        return {}
    uniq = list(dict.fromkeys(series_ids))
    placeholders = ",".join(f":id{i}" for i in range(len(uniq)))
    params = {f"id{i}": sid for i, sid in enumerate(uniq)}
    rows = db.execute(
        text(
            f"""
            SELECT m.series_id, m.name
            FROM market_series_daily m
            INNER JOIN (
                SELECT series_id, MAX(date) AS max_d
                FROM market_series_daily
                WHERE series_id IN ({placeholders})
                GROUP BY series_id
            ) t ON m.series_id = t.series_id AND m.date = t.max_d
            """
        ),
        params,
    ).fetchall()
    return {str(r[0]): str(r[1]) for r in rows}


def _load_series(db: Session, series_id: str) -> list[tuple[str, float]]:
    return _load_series_many(db, [series_id]).get(series_id, [])


def _pct_change(prev: float, cur: float) -> float:
    if prev <= 0:
        return 0.0
    return round((cur / prev - 1) * 100, 4)


def _align(
    bench: list[tuple[str, float]], ind: list[tuple[str, float]]
) -> list[tuple[str, float, float]]:
    bm = dict(bench)
    im = dict(ind)
    common = sorted(set(bm) & set(im))
    return [(d, bm[d], im[d]) for d in common]


def _compute_rs_series(aligned: list[tuple[str, float, float]]) -> list[tuple[str, float, float, float]]:
    """(date, mkt_ret%, ind_ret%, rs%) 日報酬差"""
    out: list[tuple[str, float, float, float]] = []
    for i in range(1, len(aligned)):
        _d0, m0, i0 = aligned[i - 1]
        d1, m1, i1 = aligned[i]
        mr = _pct_change(m0, m1)
        ir = _pct_change(i0, i1)
        out.append((d1, mr, ir, round(ir - mr, 4)))
    return out


def _daily_ranks(
    dates: list[str], rs_by_ind: dict[str, dict[str, float]]
) -> dict[str, dict[str, int]]:
    """每個交易日各產業的 RS 排名（1=最強）"""
    rank_on_day: dict[str, dict[str, int]] = {}
    for d in dates:
        scores = [(sid, rs_by_ind[sid].get(d)) for sid in rs_by_ind]
        scores = [(s, v) for s, v in scores if v is not None]
        scores.sort(key=lambda x: x[1], reverse=True)
        rank_on_day[d] = {s: r + 1 for r, (s, _) in enumerate(scores)}
    return rank_on_day


def compute_rotation(db: Session, lookback: int = 120) -> dict[str, Any]:
    industries_meta = [(f"IND:{name}", name, stock) for name, stock in INDUSTRY_PROXY_STOCKS]
    series_ids = [BENCHMARK_ID] + [sid for sid, _, _ in industries_meta]
    loaded = _load_series_many(db, series_ids)
    bench = loaded.get(BENCHMARK_ID, [])

    if len(bench) < 30:
        return {
            "as_of": None,
            "benchmark": BENCHMARK_ID,
            "note": "尚無足夠大盤序列資料，請先執行產業同步（admin trigger industry 或排程）",
            "industries": [],
        }

    name_map = _latest_names_by_series(db, [sid for sid, _, _ in industries_meta])

    # 最近 lookback 個對齊交易日（以 benchmark 尾端裁切）
    bench_tail = bench[-lookback:] if len(bench) > lookback else bench
    last_dates = [d for d, _ in bench_tail]

    rs_by_ind: dict[str, dict[str, float]] = {}
    aligned_by_ind: dict[str, list[tuple[str, float, float, float]]] = {}
    latest_close: dict[str, float] = {}
    name_by_sid: dict[str, str] = {}

    for sid, ind_name, proxy in industries_meta:
        raw = loaded.get(sid, [])
        if not raw:
            continue
        al = _align(bench, raw)
        rs_seq = _compute_rs_series(al)
        aligned_by_ind[sid] = rs_seq
        rs_by_ind[sid] = {d: rs for d, _, _, rs in rs_seq}
        latest_close[sid] = raw[-1][1]
        name_by_sid[sid] = name_map.get(sid, f"{ind_name}（{proxy}）")

    if not rs_by_ind:
        return {
            "as_of": last_dates[-1] if last_dates else None,
            "benchmark": BENCHMARK_ID,
            "note": "尚無產業 proxy 序列",
            "industries": [],
        }

    # 所有產業 RS 有值的日期聯集（排序）
    all_dates = sorted(set().union(*(set(m.keys()) for m in rs_by_ind.values())))
    all_dates = [d for d in all_dates if d in last_dates]
    if len(all_dates) < RANK_DAYS + 2:
        as_of = all_dates[-1] if all_dates else last_dates[-1]
        return {
            "as_of": as_of,
            "benchmark": BENCHMARK_ID,
            "note": "產業資料對齊後交易日不足",
            "industries": [],
        }

    rank_on_day = _daily_ranks(all_dates, rs_by_ind)
    n_ind = len(rs_by_ind)
    top_k = max(1, int(n_ind * TOP_FRAC + 0.999))

    as_of = all_dates[-1]
    prev_as_of = all_dates[-2] if len(all_dates) > 1 else as_of

    result_rows: list[IndustryRow] = []
    for sid, ind_name, proxy in industries_meta:
        if sid not in rs_by_ind:
            continue
        rs_map = rs_by_ind[sid]
        rs_today = rs_map.get(as_of)
        raw = loaded.get(sid, [])
        dr_ind = None
        if len(raw) >= 2 and raw[-1][0] == as_of:
            dr_ind = _pct_change(raw[-2][1], raw[-1][1])

        rk = rank_on_day.get(as_of, {}).get(sid)
        last5 = all_dates[-RANK_DAYS:]
        ranks_5 = [rank_on_day.get(d, {}).get(sid) for d in last5]
        ranks_5_valid = [x for x in ranks_5 if x is not None]
        avg_r5 = round(sum(ranks_5_valid) / len(ranks_5_valid), 2) if ranks_5_valid else None

        rs_seq = aligned_by_ind.get(sid, [])
        dates_rs = [d for d, _, _, _ in rs_seq]
        rs_only = [r for _, _, _, r in rs_seq]
        rs_ma_now = rs_ma_prev = None
        if dates_rs and as_of in dates_rs:
            idx = dates_rs.index(as_of)
            w_now = rs_only[max(0, idx - RANK_DAYS + 1) : idx + 1]
            rs_ma_now = sum(w_now) / len(w_now) if w_now else None
            hi = idx - 4
            lo = max(0, hi - RANK_DAYS)
            w_prev = rs_only[lo:hi] if hi > lo else []
            rs_ma_prev = sum(w_prev) / len(w_prev) if w_prev else None

        # 20 日新高（proxy 收盤）
        high20 = None
        if raw:
            tail = [c for d, c in raw if d <= as_of][-HIGH_DAYS:]
            if tail:
                high20 = max(tail)
        close_now = latest_close.get(sid)
        momentum_high = close_now is not None and high20 is not None and close_now >= high20 * 0.999

        reasons: list[str] = []
        sig = False
        if avg_r5 is not None and avg_r5 <= top_k:
            reasons.append(f"avg_rank_{RANK_DAYS}d_top{int(TOP_FRAC * 100)}pct")
            sig = True
        if (
            rs_ma_now is not None
            and rs_ma_prev is not None
            and rs_ma_now > rs_ma_prev
            and rs_ma_now > 0
        ):
            reasons.append("rs_ma_improving")
            sig = True
        if momentum_high and rs_today is not None and rs_today > 0:
            reasons.append("nh20_with_positive_rs")
            sig = True

        result_rows.append(
            IndustryRow(
                series_id=sid,
                name=name_by_sid.get(sid, ind_name),
                proxy_stock=proxy,
                latest_close=latest_close.get(sid),
                daily_return_pct=dr_ind,
                rs_vs_taiex_pct=rs_today,
                rank=rk,
                avg_rank_5d=avg_r5,
                rotation_signal=sig,
                signal_reasons=reasons,
            )
        )

    result_rows.sort(key=lambda x: (x.rank is None, x.rank or 999))

    return {
        "as_of": as_of,
        "benchmark": BENCHMARK_ID,
        "top_fraction": TOP_FRAC,
        "rank_window_days": RANK_DAYS,
        "industries": [
            {
                "series_id": r.series_id,
                "name": r.name,
                "proxy_stock": r.proxy_stock,
                "latest_close": r.latest_close,
                "daily_return_pct": r.daily_return_pct,
                "rs_vs_taiex_pct": r.rs_vs_taiex_pct,
                "rank": r.rank,
                "avg_rank_5d": r.avg_rank_5d,
                "rotation_signal": r.rotation_signal,
                "signal_reasons": r.signal_reasons,
            }
            for r in result_rows
        ],
    }


def build_chart_pack(db: Session, days: int = 180) -> dict[str, Any]:
    """正規化到視窗首日=100 的走勢（方便小圖對比）"""
    ind_ids = [f"IND:{n}" for n, _ in INDUSTRY_PROXY_STOCKS]
    loaded = _load_series_many(db, [BENCHMARK_ID] + ind_ids)
    bench = loaded.get(BENCHMARK_ID, [])
    if not bench:
        return {"benchmark": [], "series": {}}

    bench = bench[-days:] if len(bench) > days else bench
    if not bench:
        return {"benchmark": [], "series": {}}

    def norm(pts: list[tuple[str, float]]) -> list[dict[str, Any]]:
        if not pts:
            return []
        base = pts[0][1]
        if base <= 0:
            return []
        return [{"date": d, "close": c, "norm": round(c / base * 100, 4)} for d, c in pts]

    out: dict[str, Any] = {
        "benchmark": norm(bench),
        "series": {},
    }
    d0, d1 = bench[0][0], bench[-1][0]
    for ind_name, proxy in INDUSTRY_PROXY_STOCKS:
        sid = f"IND:{ind_name}"
        raw = loaded.get(sid, [])
        if not raw:
            continue
        raw = raw[-days:] if len(raw) > days else raw
        filtered = [(d, c) for d, c in raw if d0 <= d <= d1]
        if len(filtered) < 5:
            continue
        out["series"][sid] = {
            "label": f"{ind_name}（{proxy}）",
            "proxy_stock": proxy,
            "points": norm(filtered),
        }
    return out
