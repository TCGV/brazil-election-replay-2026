# Execução de 27/10/2026

O replay foi executado integralmente sobre os dois CSVs nacionais recuperados do Git LFS do repositório. Este registro descreve os **arquivos fornecidos**, sem autenticar seu conteúdo contra outra fonte externa.

## Cobertura e intervalos

Foram lidos 5.731.614 registros de votação e 998.496 registros de detalhe. As duas fontes contêm 2026, os dois turnos, as 27 UFs e `ZZ` (exterior).

| Eleição | Turno | Seções com votos | Primeira totalização: intervalo de minutos | Votos de todas as classes |
|---|---|---:|---|---:|
| 6257 | 1 | 499.206 | 04/10/2026 17:08 a 05/10/2026 02:58 | 125.275.835 |
| 6258 | 2 | 499.205 | 25/10/2026 17:05 a 25/10/2026 23:21 | 128.236.074 |

Horários em **Hora TSE**, sem offset confirmado. A série por recebimento tem os mesmos limites em minutos entre as seções com votos, embora os instantes e curvas sejam diferentes. Minutos vazios também são escritos: 591 minutos no primeiro turno e 377 no segundo, para cada referência. Cada CSV temporal tem 10.373 linhas de dados (uma linha por minuto/votável).

## Verificações

- SHA-256 e tamanho dos dois arquivos correspondem exatamente aos ponteiros Git LFS versionados.
- Os 19 totais por eleição/turno/votável foram conferidos por uma segunda acumulação independente, diretamente nos CSVs: nenhuma diferença.
- 998.411 chaves de seção na votação, todas pareadas com um detalhe único. Nenhuma chave duplicada no detalhe ou grupo repetido seção/votável na votação.
- Há 85 chaves somente no detalhe: 42 no primeiro turno e 43 no segundo. Todas têm zero votos nas quatro categorias e zero comparecimento. Não foram criados eventos de votos para elas.
- As quatro categorias do detalhe puderam ser comparadas em todas as 998.411 seções pareadas, sem métricas ausentes e sem divergências.
- Nenhum voto ficou fora de qualquer curva por falta/invalidade de horário ou problema de pareamento. A soma dos incrementos e o acumulado final de cada votável coincidem com o resultado final.
- Nas seções com ambos os horários, a média recebimento→primeira totalização foi de 147,876 segundos no primeiro turno e 25,697 segundos no segundo. Não foram observados intervalos negativos. Isso não mede latência de publicação.
- 19 testes de integração com fixtures sintéticas passaram. O HTML foi renderizado no Chromium e foram verificadas seleção de turno, referência, medida e consulta de valores, sem erros JavaScript. Os quatro SVGs passaram na validação XML.

## Entregáveis e reprodução

- [Relatório interativo](../reports/2026/replay-report.html), com comparação das duas referências e seleção de turno.
- [Relatório completo da execução](../reports/2026/report.md).
- [CSV principal](../reports/2026/replay-first-totalization-minute.csv) e [CSV de recebimento](../reports/2026/replay-bu-received-minute.csv).
- [Resultados finais](../reports/2026/final-results.csv) e [manifesto de proveniência](../reports/2026/input-manifest.json).
- Evidências adicionais em `reports/2026/independent-validation.json`, `reports/2026/output-validation.json` e `reports/2026/browser-validation.json`.

As saídas completas permanecem em `output/`, ignoradas pelo Git. Uma seleção de CSVs compactos, manifesto, evidências e gráficos está versionada em `reports/2026/` para consulta no GitHub. Para reproduzir em uma pasta nova:

```bash
PYTHONPATH=src python3 -m election_replay --output output/replay-nova-execucao
```

A implementação, comandos e decisões estão em [README.md](../README.md) e [decisions.md](decisions.md). O resultado temporal é uma reconstrução retrospectiva aproximada, não o histórico certificado de publicações do TSE.
