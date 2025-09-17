import math
import os
from typing import List, Tuple, Dict
import httpx
from schemas import Candle, BaselineOut, Suggestion

BINANCE_BASE = os.getenv("BINANCE_BASE", "https://api.binance.com")

def ema(series: List[float], span: int) -> List[float]:
    if not series or span <= 1:
        return series[:]
    alpha = 2 / (span + 1)
    out = [series[0]]
    s = series[0]
    for x in series[1:]:
        s = alpha * x + (1 - alpha) * s
        out.append(s)
    return out

def atr14(candles: List[Candle]) -> List[float]:
    if not candles or len(candles) < 2:
        return [0.0 for _ in candles]
    tr = []
    prev_close = candles[0].close
    for c in candles:
        tr_curr = max(
            c.high - c.low,
            abs(c.high - prev_close),
            abs(prev_close - c.low),
        )
        tr.append(tr_curr)
        prev_close = c.close
    return ema(tr, 14)

def compute_baseline(candles: List[Candle]) -> BaselineOut:
    closes = [c.close for c in candles]
    last = closes[-1]
    ema50 = ema(closes, 50)[-1] if len(closes) >= 50 else last
    ema200_series = ema(closes, 200)
    ema200 = ema200_series[-1] if len(closes) >= 200 else last
    atr_series = atr14(candles)
    atr_val = atr_series[-1] if atr_series else 0.0

    slopePct = 0.0
    if len(ema200_series) > 6:
        slope = ema200_series[-1] - ema200_series[-6]
        slopePct = (slope / last) if last else 0.0

    if abs(ema50 - ema200) / (last if last else 1) < 0.002 and abs(slopePct) < 0.0005:
        trend = "flat"
    else:
        trend = "up" if (ema50 >= ema200 and slopePct >= 0) else "down"

    return BaselineOut(
        lastClose=round(last, 2),
        ema50=round(ema50, 2),
        ema200=round(ema200, 2),
        atr14=round(atr_val, 2),
        slopePct=round(slopePct, 5),
        trend=trend,
    )

def build_rules_fallback(base: BaselineOut) -> Dict[str, float]:
    atr = max(base.atr14, 1.0)
    if base.trend == "up":
        E1 = base.lastClose - 0.8 * atr
        E2 = base.lastClose - 1.1 * atr
        E3 = base.lastClose - 1.4 * atr
        stop = min(E3 - 0.4 * atr, base.ema200 - 0.3 * atr)
        TP1 = base.lastClose + 0.9 * atr
        TP2 = base.lastClose + 1.3 * atr
        TP3 = base.lastClose + 1.7 * atr
    elif base.trend == "down":
        E1 = base.lastClose + 0.8 * atr
        E2 = base.lastClose + 1.1 * atr
        E3 = base.lastClose + 1.4 * atr
        stop = max(E3 + 0.4 * atr, base.ema200 + 0.3 * atr)
        TP1 = base.lastClose - 0.9 * atr
        TP2 = base.lastClose - 1.3 * atr
        TP3 = base.lastClose - 1.7 * atr
    else:  # flat -> leve mean reversion
        E1 = base.lastClose - 0.6 * atr
        E2 = base.lastClose
        E3 = base.lastClose + 0.6 * atr
        stop = base.lastClose - 1.2 * atr
        TP1 = base.lastClose + 0.8 * atr
        TP2 = base.lastClose + 1.2 * atr
        TP3 = base.lastClose + 1.6 * atr

    return {
        "E1": round(E1, 2),
        "E2": round(E2, 2),
        "E3": round(E3, 2),
        "stop": round(stop, 2),
        "TP1": round(TP1, 2),
        "TP2": round(TP2, 2),
        "TP3": round(TP3, 2),
    }

def rr_from(levels: Dict[str, float], split: List[float]) -> Tuple[float, float, float]:
    w = split if sum(split) > 0 else [25, 50, 25]
    ws = sum(w)
    avg = (levels["E1"] * w[0] + levels["E2"] * w[1] + levels["E3"] * w[2]) / ws
    risk = abs(avg - levels["stop"])
    def rr(tp): return round(abs(tp - avg) / risk, 2) if risk > 0 else 0.0
    return rr(levels["TP1"]), rr(levels["TP2"]), rr(levels["TP3"])

async def fetch_binance_klines(symbol: str, interval: str, limit: int = 400) -> List[Candle]:
    url = f"{BINANCE_BASE}/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url)
        r.raise_for_status()
        data = r.json()
    out = []
    for k in data:
        out.append(Candle(
            time=int(k[0] // 1000),
            open=float(k[1]),
            high=float(k[2]),
            low=float(k[3]),
            close=float(k[4]),
            volume=float(k[5]),
        ))
    return out

TF_TO_BINANCE = {"1h": "1h", "4h": "4h", "D": "1d", "1d": "1d"}

