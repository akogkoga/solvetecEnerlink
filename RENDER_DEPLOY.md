# Deploy no Render

Este projeto esta preparado para subir como um unico Web Service no Render.

## Arquitetura

- FastAPI serve a API, a landing page e o dashboard no mesmo dominio publico.
- O frontend usa a mesma origem em producao, evitando URL fixa para `localhost`.
- O SQLite principal pode ser configurado por `SQLITE_DB_PATH`.
- Se `empresas.db` nao existir no servidor, o app continua online usando `backend/data/seed_cnpjs.json` e providers externos configurados.

## Blueprint

O arquivo `render.yaml` cria um Web Service Python:

- Build: `pip install -r backend/requirements.txt`
- Start: `cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT`
- Health check: `/health`

Depois de commitar e enviar para o GitHub, use:

```text
https://dashboard.render.com/blueprint/new?repo=https://github.com/akogkoga/solvetecEnerlink
```

## Banco SQLite grande

O arquivo local `backend/data/empresas.db` tem cerca de 10 GB e esta corretamente fora do Git.

Para uma URL publica de demo, o deploy pode rodar sem esse arquivo usando o seed local. Para o motor completo com a base SQLite:

1. Use um plano pago de Web Service no Render.
2. Adicione um Persistent Disk com mount path:

```text
/opt/render/project/src/backend/storage
```

3. Envie o arquivo local `empresas.db` para o disco do servico.
4. Confirme que a variavel esta assim:

```text
SQLITE_DB_PATH=/opt/render/project/src/backend/storage/empresas.db
```

5. Redeploy o servico.

## Variaveis opcionais

- `CASADOSDADOS_API_KEY`: melhora fallback/enrichment quando preenchida.
- `REDIS_ENABLED`: manter `false` enquanto nao houver Redis configurado.
- `CORS_ORIGINS`: so precisa ser preenchida se separar frontend e backend em dominios diferentes.
