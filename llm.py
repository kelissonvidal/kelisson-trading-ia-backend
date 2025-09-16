import json
import os
from typing import Dict, Any, List
from .schemas import Suggestion

# Prefer new SDK if available; fallback to chat.completions
_OPENAI_MODE = None
try:
    from openai import OpenAI
    _OPENAI_MODE = "responses"  # we'll try responses first
    _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except Exception:
    _client = None
    _OPENAI_MODE = None

def _coerce_suggestion(obj: Dict[str, Any]) -> Suggestion:
    # Defensive parsing
    def num(x): 
        try: return float(x)
        except: return 0.0
    def intval(x):
        try: 
            v = int(float(x))
            return max(0, min(100, v))
        except:
            return 0
    return Suggestion(
        E1=num(obj.get("E1", 0)),
        E2=num(obj.get("E2", 0)),
        E3=num(obj.get("E3", 0)),
        stop=num(obj.get("stop", 0)),
        TP1=num(obj.get("TP1", 0)),
        TP2=num(obj.get("TP2", 0)),
        TP3=num(obj.get("TP3", 0)),
        RR1=num(obj.get("RR1", 0)),
        RR2=num(obj.get("RR2", 0)),
        RR3=num(obj.get("RR3", 0)),
        confidence=intval(obj.get("confidence", 0)),
        rationale=str(obj.get("rationale", ""))[:2000]
    )

def build_prompt(baseline: Dict[str, float], context_split: List[float]) -> str:
    return f"""
Você é um assistente de trading disciplinado. Gere um plano LONG/SHORT objetivo para ETHUSDT (spot), 
ajustando entradas E1/E2/E3, STOP, TP1/TP2/TP3, RR1/RR2/RR3 (com base no preço médio ponderado por split {context_split}), 
confidence (0–100) e rationale curta. 
Use coerência com ATR (volatilidade) e tendência (EMA50 vs EMA200, slope da EMA200).

CONDIÇÕES ATUAIS (baseline):
- lastClose: {baseline['lastClose']}
- ema50: {baseline['ema50']}
- ema200: {baseline['ema200']}
- atr14: {baseline['atr14']}
- slopePct: {baseline['slopePct']}
- trend: {baseline['trend']}

RETORNE APENAS JSON (sem texto fora do JSON) no formato:
{{
  "E1":float,"E2":float,"E3":float,"stop":float,
  "TP1":float,"TP2":float,"TP3":float,
  "RR1":float,"RR2":float,"RR3":float,
  "confidence":int,
  "rationale":"string concisa (até 280 caracteres)"
}}
Regras: números reais, coerentes com ATR/tendência; se neutro, adote leve viés de mean-reversion.
"""

def try_llm_suggestion(baseline: Dict[str, float], split: List[float]) -> Suggestion:
    if not _client or not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("LLM unavailable")
    model = os.getenv("MODEL", "gpt-4o-mini")
    prompt = build_prompt(baseline, split)

    # Try Responses API
    if _OPENAI_MODE == "responses":
        try:
            resp = _client.responses.create(
                model=model,
                input=prompt,
                response_format={"type":"json_object"},
                max_output_tokens=500,
            )
            text = resp.output_text
            data = json.loads(text)
            return _coerce_suggestion(data)
        except Exception:
            # Fallback to chat.completions
            pass

    try:
        cc = _client.chat.completions.create(
            model=model,
            messages=[{"role":"user","content":prompt}],
            response_format={"type":"json_object"},
            temperature=0.2,
        )
        content = cc.choices[0].message.content
        data = json.loads(content)
        return _coerce_suggestion(data)
    except Exception as e:
        raise RuntimeError(f"LLM error: {e}")
