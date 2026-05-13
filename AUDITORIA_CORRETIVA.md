# Auditoria Corretiva - dev-enerlink

Data: 2026-05-13

## 1. O que foi corrigido

- Discovery deixou de depender de seed pequeno como fonte principal.
- Implementada ingestao ampla da base RFB/Casa dos Dados em SQLite.
- Script `setup_database.py` suporta multiplas UFs, nacional, chunks separados, limite operacional, download pulavel e metadados.
- Provider `SQLiteLocal` passou a consultar tabela rica com filtros dinamicos e paginacao.
- Corrigido schema do filtro para incluir `termo`, `nome`, `cnae`, `estado`, `cidade`, `porte`, `natureza_juridica`, `situacao`, `mei`, `quantidade` e `pagina`.
- Criados indices de busca para UF, cidade, CNAE, porte, situacao, natureza juridica, MEI e ranking.
- Removido indice caro e desnecessario em `empresas_base`, que travava a fase final da ingestao.
- Banco atual reparado com indices e `ingestion_meta` consistente.
- Ranking ajustado para favorecer nome fantasia, LTDA, contatos e completude.
- Normalizacao do lead ajustada para exibir nome fantasia quando disponivel.
- Fallback permanece operacional: `SQLiteLocal -> SeedDataset -> CasaDosDados`.
- Enrichment permanece posterior ao discovery e limitado para nao travar a busca.
- Frontend atualizado para filtros amplos e chips de demo multiestado.
- README e relatorios atualizados para o estado real.

## 2. O que ainda e gargalo

- A base operacional atual tem 200.000 empresas, nao a ingestao nacional completa.
- A rodada atual usa `Estabelecimentos1.zip`; para cobertura total e necessario importar `Estabelecimentos0-9.zip`.
- A ingestao nacional completa demanda muito tempo e disco.
- Alguns contatos da Receita Federal sao ausentes; email/telefone dependem do cadastro publico.
- APIs externas ainda dependem de rede, credenciais e rate limits.

## 3. O que funciona

- Discovery local por SQLite em SP, RJ, MG, PR, BA, PE e RS.
- Busca por termo/segmento, cidade, estado, CNAE, porte, natureza juridica, situacao e MEI.
- Paginacao e limite por quantidade.
- Fallback para seed/API quando o SQLite retorna pouco ou falha.
- Health check do backend.
- Cache em memoria.
- Frontend consumindo o backend com filtros sincronizados.
- Validacao real por HTTP.

## 4. O que continua limitado

- Cobertura nacional completa ainda nao foi materializada na tabela `empresas`.
- MEI Recife retornou apenas 8 leads na fatia atual.
- Scoring ainda e heuristico; bom para demo, mas pode evoluir com score por segmento, recencia e qualidade de contato.
- Enrichment nao deve ser usado como discovery principal.

## 5. Performance atual

- Banco SQLite: 10.11 GB.
- `empresas_base`: 67.642.315 registros.
- `simples`: 48.097.045 registros.
- `empresas`: 200.000 registros operacionais.
- Media das buscas frias validadas: aproximadamente 412ms.
- Busca mais rapida: 46ms.
- Busca mais lenta: 1437ms com fallback/enrichment.
- Cache quente: chamadas repetidas geralmente abaixo de 120ms de parede.

## 6. Quantidade de leads retornados

| Busca | Retornados |
|---|---:|
| Sao Paulo tecnologia | 20 |
| Sorocaba contabilidade | 15 |
| Sao Paulo marketing | 20 |
| Sao Paulo LTDA | 20 |
| Sao Paulo ampla | 20 |
| Rio de Janeiro tecnologia | 20 |
| Minas Gerais mercados | 20 |
| Parana LTDA Curitiba | 20 |
| Bahia restaurantes | 20 |
| Pernambuco MEI Recife | 8 |
| Rio Grande do Sul clinicas | 20 |

## 7. Providers utilizados

- Discovery principal: `SQLiteLocal`.
- Fallback discovery: `SeedDataset`, `CasaDosDados`.
- Enrichment: `BrasilAPI`, `CNPJWS`, `CNPJa`, `ReceitaWS`.
- Cache: `MemoryCache` por padrao, `RedisCache` opcional.

## 8. Qualidade do discovery

O discovery esta funcional para demonstracao real. As buscas retornam empresas reais em multiplos estados e segmentos, com nomes comerciais mais convincentes quando disponiveis.

Exemplos validados:

- `RAMOS TECNOLOGIA DA INFORMACAO` em tecnologia/SP.
- `ABILITY` em tecnologia/RJ.
- `MIX CAFE` em restaurantes/BA.
- `CLINICA VETERINARIA SANTA FE` em clinicas/RS.
- `SAANGA GRILL` em LTDA/Curitiba.

## 9. Estado geral do sistema

Estado: funcional, estavel para demo e pronto para evolucao incremental. O projeto ja demonstra o motor de leads B2B com discovery local real, fallback e performance aceitavel.

## 10. Proximos passos recomendados

1. Importar mais chunks de estabelecimentos por prioridade comercial.
2. Rodar ingestao nacional sem `--limit` em uma janela longa.
3. Adicionar FTS5 para busca textual ainda mais rapida em nome/segmento.
4. Persistir metricas de validacao para acompanhar regressao.
5. Adicionar testes automatizados com fixture SQLite reduzida.
6. Evoluir scoring por relevancia do segmento, nao apenas completude.
