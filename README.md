# Motor de Leads B2B - dev-enerlink

Sistema local de discovery, fallback, enrichment e scoring de leads B2B brasileiros.

## Status Atual

Estado em 2026-05-13:

- Download RFB/Casa dos Dados concluido para a rodada ampla.
- SQLite operacional em `backend/data/empresas.db`.
- Tamanho atual do banco: 10.11 GB.
- `empresas_base`: 67.642.315 registros.
- `simples`: 48.097.045 registros.
- `empresas`: 200.000 empresas operacionais para discovery.
- Cobertura validada: SP, RJ, MG, PR, BA, PE e RS.
- Discovery principal: `SQLiteLocal`.
- Fallback: `SQLiteLocal -> SeedDataset -> CasaDosDados`.
- Enrichment: APIs externas apenas complementam leads ja encontrados.
- Frontend premium em `frontend/`, com landing em `/` e dashboard em `/app/`.
- Frontend/backend sincronizados com filtros dinamicos, sem alteracao das rotas existentes.

Importante: a base atual e ampla para validacao real, mas ainda nao e a ingestao nacional completa. Ela usa todos os arquivos `Empresas0-9`, `Simples.zip`, `Estabelecimentos1.zip`, UFs selecionadas e limite operacional de 200.000 empresas.

## Status do Discovery

Validacao funcional em 2026-05-13:

- O sistema retorna empresas reais em multiplos estados.
- A busca nao esta limitada a SP, tecnologia ou seed dataset.
- O provider principal usado nas buscas validadas foi `SQLiteLocal`.
- O discovery aplica fallback progressivo quando os filtros sao restritivos demais.
- `BrasilAPI` pode aparecer como enrichment/fallback complementar em buscas mais especificas, como MEI em Recife.
- Avisos de fallback, quando existem, sao retornados em `errors` e devem ser tratados como informacao operacional no frontend quando a resposta principal trouxe leads.

## Fallback Inteligente

A Enerlink nao retorna vazio sem antes tentar ampliar a busca. A ordem aplicada pelo discovery e:

1. Tentar os filtros originais.
2. Remover cidade e buscar no estado.
3. Flexibilizar termo/nome exato.
4. Remover CNAE e manter segmento/regiao aproximados.
5. Buscar apenas por estado.
6. Buscar geral sem filtros restritivos.

Quando algum passo ampliado e usado, a API mantem o contrato atual e adiciona um aviso em `errors`, por exemplo:

```text
Resultados ajustados para ampliar a busca: cidade removida; busca ampliada para o estado
```

O frontend exibe esse aviso como informacao operacional: "Resultados ajustados para ampliar a busca".

Garantias praticas:

- Se houver empresas possiveis na base local, o sistema tenta retornar leads.
- Os resultados continuam ordenados por qualidade/score.
- O fallback prioriza a menor ampliacao necessaria antes de abrir a busca completamente.
- A regra nao cria dados ficticios; se a base estiver vazia ou indisponivel, a resposta ainda refletira essa limitacao real.

## Cobertura Real

Cobertura operacional validada na base atual:

- Estados: SP, RJ, MG, PR, BA, PE e RS.
- Segmentos testados: tecnologia, servicos, comercio, restaurantes, empresas LTDA, clinicas, mercados e MEI.
- Cidades testadas: Sao Paulo, Rio de Janeiro, Salvador, Curitiba, Recife, Porto Alegre e outras cidades retornadas por busca ampla estadual.

Limitacoes reais:

- A base atual e uma amostra operacional ampla, nao a ingestao nacional completa.
- Algumas combinacoes muito restritivas de cidade, porte, CNAE e termo podem retornar poucos resultados.
- Em combinacoes extremas, o sistema pode retornar leads aproximados e informar que a busca foi ampliada.
- APIs externas sao enrichment/fallback; o discovery confiavel deve priorizar `SQLiteLocal`.
- Para demonstracoes, prefira buscas com segmento + UF e adicione cidade quando a regiao ja tiver sido validada.

## Setup Rapido

```powershell
cd "C:\Users\DELL\Downloads\dev-enerlink\dev-enerlink\backend"
py -3.12 -m venv venv
.\venv\Scripts\pip.exe install -r requirements.txt
.\venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Em outro terminal:

```powershell
cd "C:\Users\DELL\Downloads\dev-enerlink\dev-enerlink\frontend"
..\backend\venv\Scripts\python.exe -m http.server 5500 --bind 127.0.0.1
```

Abrir:

```text
http://127.0.0.1:5500/
http://127.0.0.1:5500/app/
```

## Frontend Premium

Arquivos principais:

- `frontend/index.html`: landing page da Enerlink.
- `frontend/app/index.html`: dashboard do gerador de leads.
- `frontend/styles.css`: design system, light/dark mode, animacoes, skeleton loading e tabela.
- `frontend/script.js`: integracao com `/health` e `/api/v1/leads/generate`, tema persistido em `localStorage`, logs internos e renderizacao dos resultados.

Recursos de UX:

- Dark mode e light mode persistidos.
- Skeleton loading durante a busca.
- Fade-in dos resultados.
- Ordenacao visual por score.
- Destaque dos melhores leads.
- Indicadores de quantidade, tempo, provider e status do sistema.
- Log no console com filtros aplicados, quantidade encontrada, tempo e providers usados.
- Banner visual quando o fallback inteligente amplia a busca.
- Timeline da busca: base local, fallback, score e leads prontos.
- Empty state orientativo com botao para ampliar busca e sugestoes clicaveis.
- Cards guiados no primeiro acesso ao dashboard.
- Dicas contextuais quando os filtros ficam especificos demais.
- Score com badge, icone e barra visual.

## Ingestao Receita Federal

Validacao ampla multiestado, mais rapida:

```powershell
cd "C:\Users\DELL\Downloads\dev-enerlink\dev-enerlink\backend"
.\venv\Scripts\python.exe scripts\setup_database.py --ufs SP,RJ,MG,PR,BA,PE,RS --company-chunks all --estab-chunks 1 --limit 200000 --force
```

Reusar arquivos ja baixados:

```powershell
.\venv\Scripts\python.exe scripts\setup_database.py --ufs SP,RJ,MG,PR,BA,PE,RS --company-chunks all --estab-chunks 1 --limit 200000 --force --skip-download
```

Ingestao por UF:

```powershell
.\venv\Scripts\python.exe scripts\setup_database.py --ufs RJ --company-chunks all --estab-chunks all --force
```

Ingestao nacional completa:

```powershell
.\venv\Scripts\python.exe scripts\setup_database.py --national --chunks all --force
```

A ingestao nacional completa pode demorar bastante e exigir muito espaco em disco. Para demo e validacao do motor, use a ingestao multiestado limitada.

## Filtros Suportados

O endpoint `POST /api/v1/leads/generate` aceita:

- `termo`: segmento livre, por exemplo tecnologia, marketing, contabilidade, mercado, restaurante, clinica, industria, MEI, LTDA.
- `nome`: razao social ou nome fantasia.
- `cnae`: CNAE completo ou prefixo.
- `estado`: UF.
- `cidade`: municipio.
- `porte`: MEI, ME, EPP, DEMAIS.
- `natureza_juridica`: codigo ou texto, por exemplo Limitada.
- `situacao`: ATIVA por padrao.
- `mei`: booleano.
- `quantidade` e `pagina`.

Exemplo:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/leads/generate" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"termo":"tecnologia","estado":"RJ","cidade":"Rio de Janeiro","quantidade":20}'
```

## Validacao

Subir backend e rodar:

```powershell
cd "C:\Users\DELL\Downloads\dev-enerlink\dev-enerlink\backend"
powershell -ExecutionPolicy Bypass -File .\scripts\validate_discovery_api.ps1
```

Resultado validado em 2026-05-13:

| Busca | Retornados | Tempo API | Providers | Top lead |
|---|---:|---:|---|---|
| Sao Paulo tecnologia | 20 | 609ms | SQLiteLocal | RAMOS TECNOLOGIA DA INFORMACAO |
| Sorocaba contabilidade | 15 | 1437ms | SQLiteLocal, SeedDataset, BrasilAPI | AUDIT PLUS |
| Sao Paulo marketing | 20 | 702ms | SQLiteLocal | ADVISE |
| Sao Paulo LTDA | 20 | 156ms | SQLiteLocal | 007 AUTO MARCAS |
| Sao Paulo ampla | 20 | 156ms | SQLiteLocal | 007 AUTO MARCAS |
| Rio de Janeiro tecnologia | 20 | 296ms | SQLiteLocal | ABILITY |
| Minas Gerais mercados | 20 | 468ms | SQLiteLocal | 1000 FESTAS E CIA |
| Parana LTDA Curitiba | 20 | 78ms | SQLiteLocal | SAANGA GRILL |
| Bahia restaurantes | 20 | 46ms | SQLiteLocal | MIX CAFE |
| Pernambuco MEI Recife | 8 | 656ms | SQLiteLocal, BrasilAPI | 00.372.507 EDUARDA NEVES DE SOUZA LEAO |
| Rio Grande do Sul clinicas | 20 | 62ms | SQLiteLocal | CLINICA VETERINARIA SANTA FE |

Validacao premium executada em 2026-05-13:

| Busca | Retornados | Tempo API | Providers | Observacao |
|---|---:|---:|---|---|
| Sao Paulo tecnologia | 10 | 109ms | SQLiteLocal | Empresas reais em Sao Paulo |
| Rio de Janeiro servicos | 10 | 155ms | SQLiteLocal | Empresas reais no Rio de Janeiro |
| Minas Gerais comercio | 10 | 405ms | SQLiteLocal | Diversidade de cidades em MG |
| Bahia restaurantes | 10 | 47ms | SQLiteLocal | Empresas reais em Salvador |
| Parana empresas LTDA | 10 | 61ms | SQLiteLocal | Empresas reais em Curitiba |
| Pernambuco MEI | 8 | 561ms | SQLiteLocal, BrasilAPI | Poucos resultados, mas nao vazio; fallback avisou SeedDataset/CasaDosDados sem quebrar |

Validacao de fallback inteligente em 2026-05-13:

| Cenario extremo | Retornados | Tempo API | Providers | Fallback aplicado |
|---|---:|---:|---|---|
| Cidade inexistente + tecnologia SP | 10 | 2094ms | SQLiteLocal | Cidade removida, busca ampliada para SP |
| Segmento raro + RJ | 10 | 578ms | SQLiteLocal, BrasilAPI | Cidade removida, busca ampliada para RJ |
| CNAE inexistente + restaurantes BA | 10 | 109ms | SQLiteLocal | CNAE removido, segmento aproximado |
| Filtros extremos PE | 10 | 78ms | SQLiteLocal | Apenas estado mantido |
| Busca extrema sem UF | 10 | 3764ms | SQLiteLocal | Busca geral sem filtros restritivos |

## Demo Flow

Melhores buscas para demonstracao:

- Tecnologia no RJ: `termo=tecnologia`, `estado=RJ`, `cidade=Rio de Janeiro`.
- Servicos no RJ: `termo=servicos`, `estado=RJ`, `cidade=Rio de Janeiro`.
- Comercio em MG: `termo=comercio`, `estado=MG`.
- Restaurantes em Salvador: `termo=restaurante`, `estado=BA`, `cidade=Salvador`.
- Clinicas em Porto Alegre: `termo=clinica`, `estado=RS`, `cidade=Porto Alegre`.
- Mercados em MG: `termo=mercado`, `estado=MG`.
- LTDA em Curitiba: `termo=LTDA`, `estado=PR`, `cidade=Curitiba`.
- Tecnologia em Sao Paulo: `termo=tecnologia`, `estado=SP`, `cidade=Sao Paulo`.
- MEI em Recife: `termo=MEI`, `estado=PE`, `cidade=Recife`, `porte=MEI`.

Para maior chance de resultado em demonstracoes:

- Comece com segmento + UF.
- Use cidade quando ela estiver nos exemplos validados.
- Evite combinar termo muito especifico, CNAE, porte e cidade ao mesmo tempo na primeira busca.

## Endpoints

- `GET /health`
- `POST /api/v1/leads/generate`
- `GET /api/v1/providers/status`
- `GET /api/v1/providers/health`
- `GET /docs`

## Variaveis

```env
CASADOSDADOS_API_KEY=
DEFAULT_TIMEOUT=15
ENRICHMENT_TIMEOUT=10
MAX_RETRIES=2
RETRY_BACKOFF_FACTOR=1.0
CACHE_TTL_SECONDS=1800
CACHE_MAX_ENTRIES=500
REDIS_ENABLED=false
REDIS_URL=redis://localhost:6379/0
MAX_ENRICHMENT_CONCURRENT=3
MAX_ENRICHMENT_LEADS=6
ENRICHMENT_MODE=balanced
```

## Troubleshooting

| Problema | Solucao |
|---|---|
| Backend offline | Rodar `.\venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000` dentro de `backend`. |
| Frontend nao acessa API | Confirmar frontend em `127.0.0.1:5500` e backend em `127.0.0.1:8000`. |
| Busca vazia | Verificar `backend/data/empresas.db` e rodar `scripts\validate_discovery_api.ps1`. |
| Banco sem indices | Rodar novamente `setup_database.py` atualizado ou recriar a ingestao com `--skip-download`. |
| Ingestao muito lenta | Usar `--estab-chunks 1 --limit 200000` para demo; usar `--chunks all` apenas para nacional completa. |
| Download falha na Receita oficial | O script tenta o mirror Casa dos Dados automaticamente. |
| Enrichment lento | Manter `ENRICHMENT_MODE=balanced` e `MAX_ENRICHMENT_LEADS=6`. |
| Casa dos Dados sem retorno | Configurar `CASADOSDADOS_API_KEY`; discovery local continua funcionando sem ela. |
