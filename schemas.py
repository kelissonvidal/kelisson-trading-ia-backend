from typing import List, Optional, Literal
from pydantic import BaseModel, Field, validator

class Candle(BaseModel):
    time: int = Field(..., description="Unix seconds")
    open: float
    high: float
    low: float
    close: float
    volume: float

class BaselinePlan(BaseModel):
    E1: float = 0
    E2: float = 0
    E3: float = 0
    stop: float = 0
    TP1: float = 0
    TP2: float = 0
    TP3: float = 0
    last: Optional[float] = 0
    atr: Optional[float] = 0

class BaselineIn(BaseModel):
    plan: Optional[BaselinePlan] = None

class ContextIn(BaseModel):
    allocPct: float = 1
    riskPct: float = 1
    split: List[float] = [25, 50, 25]

    @validator("split")
    def _sum_split(cls, v):
        return v if sum(v) > 0 else [25, 50, 25]

class AnalyzeIn(BaseModel):
    symbol: str = "ETHUSDT"
    tf: str = "4h"
    candles: Optional[List[Candle]] = None
    baseline: Optional[BaselineIn] = None
    context: ContextIn = ContextIn()
    account_id: str = "kelisson"

class BaselineOut(BaseModel):
    lastClose: float
    ema50: float
    ema200: float
    atr14: float
    slopePct: float
    trend: Literal["up", "down", "flat"]

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
    confidence: int
    rationale: str

class AnalyzeOut(BaseModel):
    ok: bool = True
    source: Literal["gpt-4o-mini", "rules-fallback"]
    baseline: BaselineOut
    suggestion: Suggestion
