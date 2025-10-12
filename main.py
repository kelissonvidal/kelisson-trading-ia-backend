import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict
from schemas import AnalyzeIn, AnalyzeOut, Suggestion
from services import (
    fetch_binance_klines, 
    TF_TO_BINANCE, 
    compute_baseline, 
    build_rules_fallback, 
    rr_from
)
from llm import try_llm_suggestion

ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS","").split(",") if o.strip()]
if not ALLOWED_ORIGINS:
    ALLOWED_ORIGINS = ["*"]

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
    return {"ok": True, "service": "kelisson-trading-ia-backend", "version": "2.0-enhanced"}

@app.post("/analyze", response_model=AnalyzeOut)
async def analyze(payload: AnalyzeIn):
    """
    Endpoint melhorado que recebe technicalContext do frontend
    e usa análise técnica completa na IA
    """
    
    # =====================================================
    # 1) OBTER CANDLES
    # =====================================================
    candles = payload.candles
    if not candles or len(candles) < 50:
        interval = TF_TO_BINANCE.get(payload.tf, "4h")
        try:
            candles = await fetch_binance_klines(payload.symbol, interval, 400)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Binance error: {e}")

    # =====================================================
    # 2) CALCULAR BASELINE
    # =====================================================
    base = compute_baseline(candles)
    base_dict: Dict[str, float] = {
        "lastClose": base.lastClose,
        "ema50": base.ema50,
        "ema200": base.ema200,
        "atr14": base.atr14,
        "slopePct": base.slopePct,
        "trend": base.trend,
    }

    # =====================================================
    # 3) EXTRAIR TECHNICAL CONTEXT (NOVO!)
    # =====================================================
    technical_context = payload.technicalContext
    
    # Log para debug
    if technical_context:
        quality = technical_context.get('quality', 'N/A')
        confluences = technical_context.get('confluences', 0)
        print(f"📊 Technical Context received:")
        print(f"   • Quality: {quality}")
        print(f"   • Confluences: {confluences}")
        print(f"   • Warnings: {len(technical_context.get('warnings', []))}")
    else:
        print("⚠️  No technical context received from frontend")

    # =====================================================
    # 4) TENTAR LLM COM CONTEXTO TÉCNICO
    # =====================================================
    use_split = payload.context.split or [25, 50, 25]
    
    try:
        # Passa technical_context para a IA
        sug: Suggestion = try_llm_suggestion(
            base_dict, 
            use_split,
            technical_context  # ✨ NOVO: Passa análise técnica completa
        )
        source = "gpt-4o-mini" if os.getenv("LLM_PROVIDER") == "openai" else "claude-sonnet-4"
        
        print(f"✅ LLM analysis complete (confidence: {sug.confidence}%)")
        
    except Exception as e:
        print(f"❌ LLM failed: {e}")
        print("🔄 Using rules-based fallback...")
        
        # =====================================================
        # 5) FALLBACK: Regras Objetivas
        # =====================================================
        lvls = build_rules_fallback(base)
        rr1, rr2, rr3 = rr_from(lvls, use_split)
        
        # Se tiver technical context, ajustar confiança baseado na qualidade
        confidence = 55
        if technical_context:
            quality = technical_context.get('quality', 'razoável')
            if quality == 'excelente':
                confidence = 70
            elif quality == 'boa':
                confidence = 65
            elif quality == 'razoável':
                confidence = 55
            else:  # ruim
                confidence = 45
        elif base.trend != "flat":
            confidence = 55
        else:
            confidence = 50
        
        rationale = f"""⚠️ FALLBACK: Análise baseada em regras objetivas

Tendência: {base.trend.upper()}
ATR: ${base.atr14:.2f}
        
O plano foi gerado usando:
• Entradas baseadas em distâncias de ATR a partir do preço atual
• Stop loss calculado considerando suporte e volatilidade
• Take profits em níveis de resistência estimados

"""
        if technical_context:
            warnings = technical_context.get('warnings', [])
            if warnings:
                rationale += f"\nAvisos técnicos:\n"
                for w in warnings:
                    rationale += f"• {w}\n"
        
        rationale += f"\nRecomendação: Valide manualmente antes de operar."
        
        sug = Suggestion(
            E1=lvls["E1"], 
            E2=lvls["E2"], 
            E3=lvls["E3"],
            stop=lvls["stop"],
            TP1=lvls["TP1"], 
            TP2=lvls["TP2"], 
            TP3=lvls["TP3"],
            RR1=rr1, 
            RR2=rr2, 
            RR3=rr3,
            confidence=confidence,
            rationale=rationale.strip(),
            trend=base.trend
        )
        source = "rules-fallback"

    # =====================================================
    # 6) RETORNAR RESPOSTA
    # =====================================================
    return AnalyzeOut(
        ok=True,
        source=source, 
        baseline=base,
        suggestion=sug
    )