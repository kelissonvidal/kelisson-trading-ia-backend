import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict
from schemas import AnalyzeIn, AnalyzeOut, Suggestion
from services import fetch_binance_klines, TF_TO_BINANCE, compute_baseline, build_rules_fallback, rr_from
from llm import try_llm_suggestion

ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS","").split(",") if o.strip()]
if not ALLOWED_ORIGINS:
    ALLOWED_ORIGINS = ["*"]  # você pode apertar isso em produção

app = FastAPI(title="kelisson-trading-ia-backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def health():
    return {"ok": True, "service": "kelisson-trading-ia-backend"}

@app.post("/analyze", response_model=AnalyzeOut)
async def analyze(payload: AnalyzeIn):
    # 1) Candles
    candles = payload.candles
    if not candles or len(candles) < 50:
        interval = TF_TO_BINANCE.get(payload.tf, "4h")
        try:
            candles = await fetch_binance_klines(payload.symbol, interval, 400)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Binance error: {e}")

    # 2) Baseline
    base = compute_baseline(candles)
    base_dict: Dict[str, float] = {
        "lastClose": base.lastClose,
        "ema50": base.ema50,
        "ema200": base.ema200,
        "atr14": base.atr14,
        "slopePct": base.slopePct,
        "trend": base.trend,
    }

    # 3) Try LLM
    use_split = payload.context.split or [25, 50, 25]
    try:
        sug: Suggestion = try_llm_suggestion(base_dict, use_split)
        source = "gpt-4o-mini"
    except Exception:
        # 4) Rules fallback
        lvls = build_rules_fallback(base)
        rr1, rr2, rr3 = rr_from(lvls, use_split)
        sug = Suggestion(
            E1=lvls["E1"], E2=lvls["E2"], E3=lvls["E3"],
            stop=lvls["stop"],
            TP1=lvls["TP1"], TP2=lvls["TP2"], TP3=lvls["TP3"],
            RR1=rr1, RR2=rr2, RR3=rr3,
            confidence=55 if base.trend != "flat" else 50,
            rationale="Plano gerado por regras objetivas com base em ATR/EMA e tendência."
        )
        source = "rules-fallback"

    return AnalyzeOut(
        ok=True,
        source=source, 
        baseline=base,
        suggestion=sug
    )

