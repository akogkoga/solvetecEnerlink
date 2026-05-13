# 🗺️ dev-enerlink — Project Map

## Stack
- Backend: Python 3.12, FastAPI, Uvicorn, Pydantic, httpx, cloudscraper
- Frontend: HTML, CSS, JavaScript (vanilla)
- Cache: Redis (opcional) ou memória
- Porta padrão: 5500

## Folder Structure
```
backend/
  main.py                          → FastAPI app + CORS + /health
  start_server.py                  → Auto-restart + validação + logs
  start_backend.bat                → Launcher Windows (duplo clique)
  requirements.txt                 → Dependências Python
  logs/backend.log                 → Logs persistentes (auto-criado)
  app/
    api/endpoints.py               → /leads/generate, /providers/status, /providers/health
    core/config.py                 → Configurações (URLs, timeouts, keys)
    core/logging_config.py         → Logging UTF-8 + arquivo
    models/schemas.py              → Pydantic schemas
    services/lead_generator.py     → Orquestrador principal
    services/provider_manager.py   → Discovery + enrichment chain
    services/cache.py              → Cache híbrido Redis/memória
    services/scorer.py             → Scoring 0-100
    services/deduplicator.py       → Remove duplicados por CNPJ
    services/health_tracker.py     → Métricas de saúde por provider
    integrations/base.py           → BaseAPIAdapter com retry + health
    integrations/casadosdados.py   → Discovery: Casa dos Dados v5
    integrations/brasilapi.py      → Enrichment: BrasilAPI
    integrations/cnpjws.py         → Enrichment: CNPJ.ws
    integrations/cnpja.py          → Enrichment: CNPJá Open
    integrations/receitaws.py      → Enrichment: ReceitaWS
frontend/
  index.html                       → Interface de busca
  script.js                        → Fetch + renderização (BASE_URL centralizada)
  styles.css                       → Estilos visuais
```

## Routes / API
```
GET  /health                       → Health check detalhado (uptime, providers, cache)
GET  /                             → Status básico
POST /api/v1/leads/generate        → Gerar leads por filtros
GET  /api/v1/providers/status      → Configuração dos providers
GET  /api/v1/providers/health      → Métricas de saúde
GET  /docs                         → Swagger UI
```

## Inicialização
```
cd backend
start_backend.bat                  → Recomendado (auto-restart)
-- ou --
.\venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 5500
```

## Last updated: 2026-05-12
