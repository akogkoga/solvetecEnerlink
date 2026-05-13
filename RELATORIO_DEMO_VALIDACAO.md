# Relatorio de Validacao da Demo

Data: 2026-05-13

## Melhorias Realizadas

- Download da base RFB/Casa dos Dados concluido para a rodada ampla.
- Banco SQLite local reconstruido para discovery real em sete UFs.
- Provider SQLite generalizado para filtros dinamicos: UF, cidade, CNAE, termo, nome, porte, natureza juridica, situacao e MEI.
- Ingestao passou a aceitar multiplos arquivos, multiplas UFs, ingestao nacional e limite operacional para smoke test.
- Indices operacionais criados na tabela `empresas`.
- Removido gargalo de indice caro em `empresas_base` que nao era usado pelo discovery.
- Ranking melhorado para priorizar leads ativos, completos, com contato, nome fantasia e sociedades limitadas quando ha empate.
- Display do lead passou a preferir `nome_fantasia`, melhorando a percepcao da demo.
- Validacao HTTP multiestado expandida em `backend/scripts/validate_discovery_api.ps1`.

## Qualidade Atual do Discovery

O discovery principal agora e local e abrangente dentro da base importada. As APIs externas nao fazem o discovery principal; elas entram apenas como fallback/enrichment.

Base atual:

| Tabela | Registros |
|---|---:|
| empresas_base | 67.642.315 |
| simples | 48.097.045 |
| empresas | 200.000 |

Distribuicao da tabela operacional:

| UF | Empresas |
|---|---:|
| SP | 85.959 |
| MG | 28.602 |
| RS | 24.057 |
| PR | 21.329 |
| RJ | 20.661 |
| BA | 12.822 |
| PE | 6.570 |

## Validacao Real da API

Backend em `http://127.0.0.1:8000`.

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

## Velocidade Media

- Media das 11 buscas frias: aproximadamente 412ms de API.
- Melhor busca fria: Bahia restaurantes, 46ms.
- Pior busca fria: Sorocaba contabilidade, 1437ms, porque combinou fallback/enrichment.
- Com cache quente, as chamadas repetidas ficaram geralmente entre 5ms e 120ms de parede.

## Melhores Fluxos Para Demo

- Tecnologia RJ: mostra resultado nacional fora de SP e top lead claro.
- Restaurantes Salvador: retorna restaurantes reais com nome comercial.
- Clinicas Porto Alegre: mostra nome fantasia convincente.
- Mercados MG: mostra varejo alimentar em outro estado.
- LTDA Curitiba: demonstra filtro juridico/localidade.
- Tecnologia Sao Paulo: fluxo rapido e familiar.

## Gargalos Restantes

- A tabela operacional tem 200.000 empresas, nao a base nacional completa.
- Apenas `Estabelecimentos1.zip` foi importado nesta rodada; a ingestao nacional completa precisa `--chunks all` sem `--limit`.
- Alguns segmentos amplos ainda podem retornar negocios relacionados por nome fantasia/CNAE aproximado.
- MEI Recife retornou 8 resultados na fatia importada; nao esta vazio, mas ainda e limitado pelo chunk atual.
- Enrichment externo depende de disponibilidade/rate limit/API key.

## Estado Geral

Estado: demo funcional, convincente e validada por API real. O motor ja retorna empresas reais em multiplos estados, com fallback operacional e performance aceitavel para demonstracao.
