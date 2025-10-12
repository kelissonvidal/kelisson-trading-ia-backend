from pydantic import BaseModel
from typing import List, Optional, Dict, Any

# =====================================================
# CANDLE
# =====================================================

class Candle(BaseModel):
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: float

# =====================================================
# BASELINE OUTPUT
# =====================================================

class BaselineOut(BaseModel):
    lastClose: float
    ema50: float
    ema200: float
    atr14: float
    slopePct: float
    trend: str  # "up", "down", "flat"

# =====================================================
# SUGGESTION (Resposta da IA)
# =====================================================

class Suggestion(BaseModel):
    E1: float
    E2: float
    E3: float
    stop: float
    TP1: float
    TP2: float
    TP3: float
    RR1: float
    RR2: float
    RR3: float
    confidence: int  # 0-100
    rationale: str
    trend: Optional[str] = "flat"  # "up", "down", "flat"

# =====================================================
# ANALYZE INPUT (Request do Frontend)
# =====================================================

class ContextIn(BaseModel):
    allocPct: float
    riskPct: float
    split: Optional[List[float]] = None

class AnalyzeIn(BaseModel):
    symbol: str
    tf: str
    candles: Optional[List[Candle]] = None
    context: ContextIn
    account_id: str
    
    # ✨ NOVO: Technical Context do Frontend
    technicalContext: Optional[Dict[str, Any]] = None

# =====================================================
# ANALYZE OUTPUT (Response para Frontend)
# =====================================================

class AnalyzeOut(BaseModel):
    ok: bool
    source: str  # "gpt-4o-mini", "claude-sonnet-4", "rules-fallback"
    baseline: BaselineOut
    suggestion: Suggestion