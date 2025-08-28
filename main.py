import os, json, time
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from openai import OpenAI

# --- Config ---
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("Defina OPENAI_API_KEY nas variáveis de ambiente.")
client = OpenAI(api_key=OPENAI_API_KEY)

# CORS (em produção, troque "*" pelos seus domínios separados por vírgula)
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "*").split(",")

# Cooldown por conta (anti-flood simples em memória)
LAST_HIT: Dict[str, float] = {}
COOLDOWN_SECONDS = float(os.environ.get("COOLDOWN_SECONDS", "10"))

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Schemas ---
class Candle(BaseModel):
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float

class Plan(BaseModel):
    E1: float
    E2: Optional[float] = None
    E3: Optional[float] = None
    stop: float
    TP1: float
    TP2: float
    TP3: float
    last: float

class Payload(BaseModel):
    symbol: str = Field(..., examples=["ETHUSDT"])
    tf: str = Field(..., examples=["4h"])
    candles: List[Candle]
    baseline: Dict[str, Any]     # {"plan": Plan, ...}
    context: Dict[str, Any]      # {"wallet":..,"fx":..,"allocPct":..,"split":[..],"riskPct":..}
    account_id: Optional[str] = None  # para rate-limit por conta (pego do front)

class Suggestion(BaseModel):
    E1: float
    E2: Optional[float] = None
    E3: Optional[float] = None
    stop: float
    TP1: float
    TP2: float
    TP3: float
    confidence: int
    rationale: str

class Response(BaseModel):
    ok: bool
    source: str
    suggestion: Suggestion

# --- Prompt base (conciso e objetivo) ---
SYSTEM_PROMPT = """Você é um assistente de trading quantitativo.
Receberá um resumo de mercado (último preço, range simples), um plano baseline (E1,E2,E3,STOP,TP1-TP3,last),
e parâmetros de risco do usuário (allocPct, riskPct, split).
Tarefa: retornar ajustes NUMÉRICOS (json) para E1,E2,E3, STOP, TP1,TP2,TP3; um "confidence" 0–100; e um "rationale" curto.
Regras:
- Coerência: STOP < E3 ≤ E2 ≤ E1 < TP1 < TP2 < TP3.
- Não afaste os níveis mais de ±3% do baseline sem justificativa explícita no "rationale".
- Penalize STOP muito apertado quando a volatilidade recente estiver alta (o cliente pode embutir ATR).
- Evite números mágicos: ajuste em função do baseline/last.
- Seja sucinto no "rationale".
Responda APENAS json no formato:
{
  "suggestion": { "E1":..., "E2":..., "E3":..., "stop":..., "TP1":..., "TP2":..., "TP3":..., "confidence":..., "rationale":"..." }
}
"""

def guard_flo(x, default):
    try:
        return float(x)
    except Exception:
        return float(default)

@app.post("/analyze", response_model=Response)
def analyze(p: Payload):
    # --- cooldown simples por account_id (ou por símbolo se não houver) ---
    key = p.account_id or f"{p.symbol}:{p.tf}"
    now = time.time()
    last = LAST_HIT.get(key, 0.0)
    if now - last < COOLDOWN_SECONDS:
        raise HTTPException(429, f"cooldown: aguarde {COOLDOWN_SECONDS - (now-last):.1f}s")

    if not p.candles or "plan" not in p.baseline:
        raise HTTPException(400, "missing-candles-or-baseline")

    closes = [c.close for c in p.candles]
    last_px = closes[-1]
    range_px = (max(closes) - min(closes)) if len(closes) > 2 else 0.0

    # Enxugamos o payload para reduzir tokens
    usr = {
        "symbol": p.symbol,
        "tf": p.tf,
        "last": last_px,
        "range": range_px,
        "baseline": p.baseline.get("plan", {}),
        "context": {
            "allocPct": p.context.get("allocPct"),
            "riskPct": p.context.get("riskPct"),
            "split": p.context.get("split"),
            # ATR opcional (se quiser enviar do front): "atr14": p.context.get("atr14")
        }
    }

    # OpenAI call
    r = client.chat.completions.create(
        model="gpt-4o-mini",
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(usr)}
        ],
    )

    raw = r.choices[0].message.content or "{}"
    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = {}

    base = p.baseline.get("plan", {})
    s = (parsed.get("suggestion") or {})

    def g(k):
        return guard_flo(s.get(k, base.get(k, last_px)), base.get(k, last_px))

    suggestion = {
        "E1": g("E1"),
        "E2": g("E2"),
        "E3": g("E3"),
        "stop": g("stop"),
        "TP1": g("TP1"),
        "TP2": g("TP2"),
        "TP3": g("TP3"),
        "confidence": int(max(0, min(100, int(s.get("confidence", 75))))),
        "rationale": str(s.get("rationale", "Ajustes mínimos em torno do baseline."))
    }

    # marca hit do cooldown
    LAST_HIT[key] = now
    return {"ok": True, "source": "gpt-4o-mini", "suggestion": suggestion}
