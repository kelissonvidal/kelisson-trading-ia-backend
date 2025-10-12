import json
import os
from typing import Dict, Any, List, Optional
from schemas import Suggestion

# =====================================================
# SUPORTE A MÚLTIPLAS APIS (Claude + OpenAI)
# =====================================================

_PROVIDER = os.getenv("LLM_PROVIDER", "openai")  # "openai" ou "claude"
_client = None

if _PROVIDER == "claude":
    try:
        from anthropic import Anthropic
        _client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    except Exception:
        _client = None
elif _PROVIDER == "openai":
    try:
        from openai import OpenAI
        _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    except Exception:
        _client = None

# =====================================================
# HELPER: Coerce Suggestion
# =====================================================

def _coerce_suggestion(obj: Dict[str, Any]) -> Suggestion:
    """Parse response defensively"""
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
        rationale=str(obj.get("rationale", ""))[:3000],
        trend=obj.get("trend", "flat")
    )

# =====================================================
# PROMPT ENRIQUECIDO COM INDICADORES TÉCNICOS
# =====================================================

def build_enhanced_prompt(
    baseline: Dict[str, float], 
    context_split: List[float],
    technical_context: Optional[Dict[str, Any]] = None
) -> str:
    """
    Constrói prompt MUITO mais rico com todos os indicadores técnicos
    enviados pelo frontend
    """
    
    # Baseline básico
    prompt = f"""Você é um analista técnico profissional de criptomoedas especializado em trading.

# TAREFA
Analise ETHUSDT e sugira um plano de trade LONG conservador com:
- 3 pontos de entrada (E1, E2, E3)
- 3 take profits (TP1, TP2, TP3)
- 1 stop loss
- Calcule Risk:Reward para cada TP
- Forneça confiança de 0-100
- Explique DETALHADAMENTE o raciocínio

# DADOS BÁSICOS DO MERCADO
Preço Atual: ${baseline['lastClose']:.2f}
EMA 50: ${baseline['ema50']:.2f}
EMA 200: ${baseline['ema200']:.2f}
ATR (14): ${baseline['atr14']:.2f}
Slope EMA200: {baseline['slopePct']:.5f}
Tendência: {baseline['trend'].upper()}
"""

    # ADICIONAR ANÁLISE TÉCNICA SE DISPONÍVEL
    if technical_context:
        indicators = technical_context.get('technicalIndicators', {})
        signals = technical_context.get('signals', {})
        quality = technical_context.get('quality', 'unknown')
        confluences = technical_context.get('confluences', 0)
        warnings = technical_context.get('warnings', [])
        
        prompt += f"""

# ANÁLISE TÉCNICA COMPLETA (Pré-Calculada pelo Frontend)

## Tendência e Momentum
- Tendência: {indicators.get('trend', 'N/A').upper()}
- Força da Tendência: {indicators.get('trendStrength', 0):.1f}%
- Volatilidade: {indicators.get('volatility', 'N/A').upper()}

## Indicadores de Momentum
- RSI (14): {indicators.get('rsi14', 0):.2f} {'← OVERSOLD!' if indicators.get('rsi14', 50) < 30 else '← OVERBOUGHT!' if indicators.get('rsi14', 50) > 70 else ''}
- RSI (21): {indicators.get('rsi21', 0):.2f}
"""

        # MACD
        macd = indicators.get('macd', {})
        if macd:
            prompt += f"""- MACD: {macd.get('macd', 0):.2f}
- MACD Signal: {macd.get('signal', 0):.2f}
- MACD Histogram: {macd.get('histogram', 0):.2f} {'← BULLISH' if macd.get('histogram', 0) > 0 else '← BEARISH'}
"""

        # EMAs
        prompt += f"""
## Médias Móveis Exponenciais
- EMA 9: ${indicators.get('ema9', 0):.2f}
- EMA 21: ${indicators.get('ema21', 0):.2f}
- EMA 50: ${indicators.get('ema50', 0):.2f}
- EMA 200: ${indicators.get('ema200', 0):.2f}
"""
        if indicators.get('ema9', 0) > indicators.get('ema200', 0):
            prompt += "✓ Preço acima da EMA 200 (tendência de alta)\n"
        else:
            prompt += "✗ Preço abaixo da EMA 200 (tendência de baixa)\n"

        # Bollinger Bands
        bb = indicators.get('bollingerBands', {})
        if bb:
            prompt += f"""
## Bollinger Bands
- Banda Superior: ${bb.get('upper', 0):.2f}
- Banda Média: ${bb.get('middle', 0):.2f}
- Banda Inferior: ${bb.get('lower', 0):.2f}
- %B (posição): {bb.get('percentB', 0)*100:.1f}%"""
            if bb.get('percentB', 0.5) < 0.2:
                prompt += " ← Próximo da banda inferior (possível compra)\n"
            elif bb.get('percentB', 0.5) > 0.8:
                prompt += " ← Próximo da banda superior (cuidado!)\n"
            else:
                prompt += "\n"

        # Pivot Points
        pivots = indicators.get('pivotPoints', {})
        if pivots:
            prompt += f"""
## Pivot Points (Suporte/Resistência)
- R3: ${pivots.get('r3', 0):.2f}
- R2: ${pivots.get('r2', 0):.2f}
- R1: ${pivots.get('r1', 0):.2f}
- Pivot: ${pivots.get('pivot', 0):.2f}
- S1: ${pivots.get('s1', 0):.2f}
- S2: ${pivots.get('s2', 0):.2f}
- S3: ${pivots.get('s3', 0):.2f}
"""

        # Volume
        vol_ratio = indicators.get('volumeRatio', 1.0)
        prompt += f"""
## Volume
- Volume vs Média: {vol_ratio*100:.0f}%"""
        if vol_ratio > 1.5:
            prompt += " ← Volume ALTO (confirmação forte)\n"
        elif vol_ratio < 0.5:
            prompt += " ← Volume BAIXO (aguarde confirmação)\n"
        else:
            prompt += "\n"

        # Sinais Detectados
        bullish = signals.get('bullish', [])
        bearish = signals.get('bearish', [])
        
        if bullish or bearish:
            prompt += f"""
## Sinais Técnicos Detectados
"""
            if bullish:
                prompt += f"✅ SINAIS DE ALTA ({len(bullish)}):\n"
                for sig in bullish[:5]:
                    prompt += f"   • {sig}\n"
            
            if bearish:
                prompt += f"❌ SINAIS DE BAIXA ({len(bearish)}):\n"
                for sig in bearish[:5]:
                    prompt += f"   • {sig}\n"

        # Qualidade e Confluências
        prompt += f"""
## Avaliação de Qualidade
- Classificação: {quality.upper()}
- Confluências: {confluences}/10 indicadores concordam
"""

        # Avisos
        if warnings:
            prompt += f"\n⚠️ AVISOS IMPORTANTES:\n"
            for w in warnings:
                prompt += f"   {w}\n"

    # INSTRUÇÕES CRÍTICAS
    prompt += f"""

# REGRAS CRÍTICAS PARA ANÁLISE

1. **QUALIDADE MÍNIMA**: 
   - Só sugira trades com confiança ≥ 70% quando há pelo menos 3 confluências
   - Se qualidade for "ruim" ou poucos sinais, reduza confiança para 50-60%

2. **RESPEITE A TENDÊNCIA**:
   - Em tendência de ALTA: Entradas em retrações (próximo de EMAs, suportes)
   - Em tendência de BAIXA: Seja EXTREMAMENTE cauteloso ou sugira aguardar
   - Em lateral: Estratégia de mean-reversion

3. **USE OS INDICADORES**:
   - RSI < 30: Forte sinal de compra
   - RSI > 70: Evite entradas
   - MACD bullish + RSI baixo: Setup forte
   - Preço próximo à banda de Bollinger inferior: Oportunidade

4. **SUPORTE E RESISTÊNCIA**:
   - E1, E2, E3 devem estar próximos de SUPORTES (pivots S1/S2/S3 ou EMAs)
   - TP1, TP2, TP3 devem estar próximos de RESISTÊNCIAS (pivots R1/R2/R3)
   - Nunca coloque entradas acima de resistências fortes

5. **STOP LOSS INTELIGENTE**:
   - Stop abaixo do suporte mais próximo
   - Considere ATR: stop = entrada - (1.5 * ATR)
   - Nunca arrisque mais de 2% do capital

6. **RISK:REWARD**:
   - RR1 deve ser ≥ 1.5
   - RR2 deve ser ≥ 2.5
   - RR3 deve ser ≥ 4.0
   - Se não conseguir esses ratios, reduza confiança

7. **SPLITS DE ENTRADA**:
   - Use splits {context_split} para ponderar entrada média
   - E1 = entrada conservadora (primeiro suporte)
   - E2 = entrada principal (melhor suporte)
   - E3 = entrada agressiva (suporte mais distante)

# FORMATO DA RESPOSTA

Retorne APENAS um JSON válido (sem markdown, sem ```):

{{
  "E1": <número>,
  "E2": <número>,
  "E3": <número>,
  "TP1": <número>,
  "TP2": <número>,
  "TP3": <número>,
  "stop": <número>,
  "RR1": <número>,
  "RR2": <número>,
  "RR3": <número>,
  "confidence": <0-100>,
  "trend": "up" ou "down" ou "flat",
  "rationale": "<explicação DETALHADA de 200-500 palavras>"
}}

**IMPORTANTE na rationale:**
- Explique POR QUE escolheu esses níveis
- Cite QUAIS indicadores justificam
- Mencione suportes/resistências usados
- Avalie os riscos
- Se confiança < 70%, explique por quê

**NUNCA:**
- Coloque E1/E2/E3 em ordem errada
- Sugira stop acima das entradas (em LONG)
- Ignore os avisos de volatilidade/volume
- Faça setup ruim só pra forçar uma resposta
"""

    return prompt

# =====================================================
# FUNÇÃO PRINCIPAL: Try LLM Suggestion
# =====================================================

def try_llm_suggestion(
    baseline: Dict[str, float], 
    split: List[float],
    technical_context: Optional[Dict[str, Any]] = None
) -> Suggestion:
    """
    Tenta obter sugestão da IA (Claude ou OpenAI)
    com análise técnica enriquecida
    """
    
    if not _client:
        raise RuntimeError("LLM client not available")
    
    prompt = build_enhanced_prompt(baseline, split, technical_context)
    
    # USAR CLAUDE
    if _PROVIDER == "claude":
        try:
            model = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
            
            message = _client.messages.create(
                model=model,
                max_tokens=2000,
                temperature=0.3,  # Mais conservador
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )
            
            content = message.content[0].text
            
            # Parse JSON
            json_match = content.strip()
            if json_match.startswith("```"):
                # Remove markdown se presente
                lines = json_match.split("\n")
                json_match = "\n".join([l for l in lines if not l.startswith("```")])
            
            data = json.loads(json_match)
            return _coerce_suggestion(data)
            
        except Exception as e:
            raise RuntimeError(f"Claude API error: {e}")
    
    # USAR OPENAI
    elif _PROVIDER == "openai":
        try:
            model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            
            response = _client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            
            content = response.choices[0].message.content
            data = json.loads(content)
            return _coerce_suggestion(data)
            
        except Exception as e:
            raise RuntimeError(f"OpenAI API error: {e}")
    
    else:
        raise RuntimeError(f"Unknown LLM provider: {_PROVIDER}")