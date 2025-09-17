# kelisson-trading-ia-backend

FastAPI para planos de trade com IA + fallback por regras.

## Endpoints
- `GET /` → `{"ok":true,"service":"kelisson-trading-ia-backend"}`
- `POST /analyze` → conforme contrato (envie candles para evitar 422)

## Env (Render)
- `OPENAI_API_KEY` (você configura)
- `MODEL=gpt-4o-mini`
- `ALLOWED_ORIGINS=https://simbadigital.com.br,https://www.simbadigital.com.br`
- (opcional) `BINANCE_BASE=https://api.binance.com`

## Deploy
