# Hipótese 1 — Consistência entre votos, comparecimento e eleitorado

[Índice das hipóteses](../README.pt-BR.md) · [Índice do estudo](../../README.md) · [Reprodução e arquivos](README.md)

**Resultado:** não foram encontrados votos acima do comparecimento, comparecimento acima do eleitorado ou registros duplicados. A soma dos votos também coincide com o comparecimento em todas as seções verificadas. Entretanto, a identidade entre aptos, comparecimento e abstenções apresenta **41 exceções em cada turno**. Por isso, a hipótese ampla **não foi integralmente refutada**.

As exceções correspondem às mesmas 41 seções do exterior, não instaladas, com 423 aptos por turno e nenhum voto. Os leiautes não explicam expressamente como contabilizar suas abstenções.

## Hipótese e dificuldade

**Hipótese aprovada:** “Existem seções com votos acima do comparecimento, comparecimento acima do eleitorado ou duplicação de registros.”

**Dificuldade de identificação: baixa.** As relações contábeis são verificáveis diretamente; explicar diferenças pode exigir documentação adicional.

O teste inclui `aptos = comparecimento + abstenções`, soma das categorias e concordância entre votação e detalhe. As hipóteses 2 a 7 permanecem sem avaliação.

## Dados e cobertura

Foram relidos os dois CSVs nacionais originais de 2026, para presidente (`CD_CARGO=1`, unidade eleitoral `BR`), sem concatenar arquivos sobrepostos. Entraram os dois turnos, **as 27 UFs brasileiras e o exterior (`ZZ`)**.

| Unidade observada | Primeiro turno | Segundo turno |
|---|---:|---:|
| Código da eleição | 6257 | 6258 |
| Linhas de votação por seção/votável | 3.800.511 | 1.931.103 |
| Linhas e chaves únicas de detalhe | 499.248 | 499.248 |
| Seções com linhas de votação | 499.206 | 499.205 |
| Seções de votação com detalhe único correspondente | 499.206 | 499.205 |
| Seções presentes apenas no detalhe | 42 | 43 |
| Seções presentes apenas na votação | 0 | 0 |
| Seções marcadas como instaladas | 499.207 | 499.207 |
| Seções marcadas como não instaladas | 41 | 41 |

São 5.731.614 linhas de votação e 998.496 de detalhe. Somar os turnos não conta eleitores distintos. Os denominadores por UF estão em [coverage.csv](evidence/accounting/coverage.csv).

Os arquivos foram abertos somente para leitura e permaneceram inalterados. Seus SHA-256 coincidem com os registrados na etapa 1:

| Entrada | SHA-256 |
|---|---|
| Votação nacional | `9c35200e1c613d8cc76b255a1d6c824cf5dba63a995c1e86b893c348722fcad8` |
| Detalhe nacional | `bb25a47159af3c628e3e7d0b78819f9c43a11eda66ed36f22ef0a2c2d5caf5bd` |

O [manifesto](evidence/accounting/manifest.json) registra fontes, código e ambiente. As extrações declaradas são de 26/10/2026: 09:49:06 no detalhe e 12:07:25 na votação. Hashes preservados demonstram continuidade dos arquivos, sem certificar autenticidade externa.

## Método de análise

A verificação é **exaustiva e determinística**, com aritmética inteira, sem amostragem, simulações ou valores-p. Uma diferença de um voto já é divergência. A conferência por seção evita que diferenças opostas se cancelem nos totais.

A chave normalizada é `CD_ELEICAO + NR_TURNO + SG_UF + CD_MUNICIPIO + NR_ZONA + NR_SECAO + CD_CARGO`. Para a votação, acrescenta-se `NR_VOTAVEL`. Códigos numéricos são normalizados como inteiros e a UF como sigla maiúscula. A mesma seção em turnos diferentes não é duplicação.

As duplicações são procuradas antes da agregação, distinguindo registros idênticos de chaves repetidas com conteúdo divergente. Detalhes ambíguos não são escolhidos arbitrariamente para reconciliar seções.

Pelo [leiaute da votação, página 5](../../../../data/votacao_secao_2026_BR/leiame.pdf#page=5), os códigos **95, 96 e 97** correspondem, respectivamente, a branco, nulo e anulado apurado em separado. Os demais números positivos são tratados como votos nominais neste recorte presidencial. Votos em separado entram uma única vez no total; não são somados novamente aos nominais ou nulos. `QT_VOTOS_LEGENDA` é auditado explicitamente e deve ser zero neste cargo.

O [leiaute do detalhe](../../../../data/detalhe_votacao_secao_2026/leiame.pdf#page=4) define aptos, comparecimento e abstenções na página 4, e as categorias de voto na página 5. A identidade completa utilizada é:

```text
nominais + brancos + nulos + legenda + anulados em separado = comparecimento
aptos = comparecimento + abstenções
```

Campos vazios, `#NULO`, `#NE`, `-1` e `-3` são informação indisponível, nunca zero. Quantidades inválidas ou negativas são registradas separadamente. Não houve esses problemas nas entradas analisadas.

A ausência de linhas de votação para uma chave de detalhe é distinguida de um campo numérico ausente. O primeiro caso pode ser comparado como total de votos zero, acompanhado do diagnóstico de cobertura; o segundo não pode ser preenchido com zero. As 85 linhas apenas de detalhe são publicadas individualmente.

### Registro das 22 verificações

Identificadores em [checks.csv](evidence/accounting/checks.csv): “detalhe” significa registro seção/turno; “votação”, linha seção/votável; “chave”, grupo com a mesma identificação.

| Identificador | Relação verificada | Unidade |
|---|---|---|
| `detail_quantities_complete` | Oito quantidades do detalhe disponíveis | Detalhe |
| `detail_quantities_nonnegative` | Quantidades do detalhe não negativas | Detalhe |
| `turnout_le_electorate` | Comparecimento ≤ aptos | Detalhe |
| `abstentions_le_electorate` | Abstenções ≤ aptos | Detalhe |
| `electorate_identity` | Aptos = comparecimento + abstenções | Detalhe |
| `electorate_identity_installed` | Mesma identidade, seções instaladas | Detalhe |
| `electorate_identity_not_installed` | Mesma identidade, seções não instaladas | Detalhe |
| `installation_status_known` | Indicador de instalação reconhecido | Detalhe |
| `detail_votes_equal_turnout` | Cinco categorias = comparecimento | Detalhe |
| `presidential_legend_zero` | Votos de legenda iguais a zero | Detalhe |
| `vote_quantities_complete` | Quantidade de votos disponível | Votação |
| `vote_quantities_nonnegative` | Quantidade de votos não negativa | Votação |
| `unique_detail_key` | Um detalhe por chave | Chave de detalhe |
| `unique_vote_key` | Uma linha por seção/votável | Chave de votação |
| `vote_section_has_unique_detail` | Toda seção de votação tem detalhe único | Seção com votação |
| `positive_detail_has_votes` | Detalhe com atividade tem linhas de votação | Seção com atividade |
| `source_votes_le_turnout` | Votos do arquivo ≤ comparecimento | Seção com detalhe único |
| `source_votes_equal_turnout` | Votos do arquivo = comparecimento | Seção com detalhe único |
| `reconcile_nominal` | Nominais concordam entre arquivos | Seção com detalhe único |
| `reconcile_blank` | Brancos concordam entre arquivos | Seção com detalhe único |
| `reconcile_null_votes` | Nulos concordam entre arquivos | Seção com detalhe único |
| `reconcile_separate` | Separados concordam entre arquivos | Seção com detalhe único |

As 22 verificações se sobrepõem. O CSV informa `universe` (universo), `eligible` (casos no recorte), `compared` (comparações possíveis), `violations` (divergências) e `not_comparable` (elegíveis indisponíveis). `BR` é o total nacional; não deve ser somado às UFs. Nenhuma comparação elegível ficou indisponível.

## Resultados

| Sinal procurado | Primeiro turno | Segundo turno |
|---|---:|---:|
| Votos acima do comparecimento | 0 | 0 |
| Comparecimento acima dos aptos | 0 | 0 |
| Abstenções acima dos aptos | 0 | 0 |
| Duplicação de chave de detalhe | 0 | 0 |
| Duplicação de chave seção/votável | 0 | 0 |
| Divergência entre categorias de voto dos arquivos | 0 | 0 |
| Divergência entre soma dos votos e comparecimento | 0 | 0 |
| Aptos ≠ comparecimento + abstenções, sem excluir seções | **41** | **41** |
| Mesma divergência em seções instaladas | 0 de 499.207 | 0 de 499.207 |
| Mesma divergência em seções não instaladas | **41 de 41** | **41 de 41** |

As reconciliações cobrem 499.248 seções por turno, incluindo detalhes sem linhas de votação e com zero votos. Seções com linhas de votação são 499.206 e 499.205. As exceções de eleitorado se restringem a `ZZ`.

### Totais nacionais dos arquivos

| Quantidade | Primeiro turno | Segundo turno |
|---|---:|---:|
| Aptos | 158.745.502 | 158.745.502 |
| Comparecimento | 125.275.835 | 128.236.074 |
| Abstenções registradas | 33.469.244 | 30.509.005 |
| Votos nominais | 119.306.034 | 124.082.273 |
| Brancos | 2.300.798 | 1.430.496 |
| Nulos | 3.669.003 | 2.723.305 |
| Legenda | 0 | 0 |
| Anulados em separado | 0 | 0 |
| Total de votos do arquivo de votação | 125.275.835 | 128.236.074 |
| Aptos − comparecimento − abstenções | **423** | **423** |

Não foi acrescentado nenhum valor às abstenções para fechar a conta. Os valores publicados preservam os registros originais. O detalhamento nacional e por UF está em [totals.csv](evidence/accounting/totals.csv).

### As 41 seções do exterior

As mesmas chaves físicas — UF, município, zona e seção — apresentam a diferença nos dois turnos, com os mesmos quantitativos. Todas têm `ST_SECAO_INSTALADA=Não`, `ST_SECAO_ANULADA=Não` e `DS_ORIGEM_VOTO=Totalização`. Somam 423 aptos em cada turno; comparecimento, abstenções e todas as categorias de voto são zero.

Esses registros não acrescentam votos a candidato algum. Contudo, a marcação “não instalada” contextualiza a diferença sem explicá-la documentalmente: o leiaute não estabelece uma exceção expressa à identidade. Não se conclui que as 423 pessoas deveriam ser reclassificadas como abstencionistas; isso exigiria uma regra externa que não foi verificada aqui.

[violations.csv](evidence/accounting/violations.csv) contém **164 linhas**, porque cada uma das 82 ocorrências seção/turno aparece na identidade geral e no recorte de não instaladas. São **82 ocorrências distintas, relativas a 41 seções físicas**, não 164 seções. O campo `difference` é o resíduo da relação especificada pelo identificador; seu sinal depende da fórmula do teste. `record_json` preserva os valores e a linha de origem da ocorrência.

### Os 85 detalhes sem linhas de votação

| Turno e contexto | Registros | Aptos | Comparecimento | Abstenções | Votos |
|---|---:|---:|---:|---:|---:|
| Primeiro: não instaladas, Totalização | 41 | 423 | 0 | 0 | 0 |
| Primeiro: instalada, Sistema de apuração | 1 | 72 | 0 | 72 | 0 |
| Segundo: não instaladas, Totalização | 41 | 423 | 0 | 0 | 0 |
| Segundo: instaladas, Sistema de apuração | 2 | 102 | 0 | 102 | 0 |

Todas são de `ZZ`. As três ocorrências instaladas têm abstenção integral e a identidade fecha. Elas são distintas das 82 exceções de eleitorado. O inventário completo está em [zero-vote-details-only.csv](evidence/accounting/zero-vote-details-only.csv), e os agrupamentos por situação, origem e UF em [detail-context.csv](evidence/accounting/detail-context.csv).

## Validação, reprodução e alcance

A [conferência independente](evidence/independent-validation.json) relê os CSVs sem importar a análise principal. O [comparador](code/compare_validations.py) confronta resultados, cobertura, totais, exceções e hashes em [validation-comparison.json](evidence/validation-comparison.json). A análise principal usa SQLite temporário; a independente usa estruturas em memória. Ambas dependem dos mesmos arquivos e significados documentados.

O confronto e as verificações de integridade totalizaram **4.478 comparações exatas, sem diferenças**. Foram exigidos os 22 identificadores em cada um dos 58 recortes nacionais/UF, sem omissões ou duplicações. Os **20 testes de implementação passaram**, incluindo exemplos com erros contábeis que se cancelariam no total, dados ausentes, duplicações e evidências alteradas. A saída está em [test-results.txt](evidence/test-results.txt). O [inventário de artefatos](evidence/artifact-manifest.json) permite conferir os hashes do relatório, código e evidências publicados.

O [README](README.md) contém os comandos de reprodução. O código e os testes ficam em [code/](code/); as evidências compactas, em [evidence/](evidence/). [input-issues.csv](evidence/accounting/input-issues.csv), [duplicate-details.csv](evidence/accounting/duplicate-details.csv) e [duplicate-votes.csv](evidence/accounting/duplicate-votes.csv) têm somente cabeçalhos porque não registraram ocorrências, não porque foram omitidas verificações. Os testes de implementação usam casos artificiais separados dos resultados eleitorais.

**Conclusão:** os sinais centrais da hipótese aprovada não apareceram nos arquivos fornecidos. A auditoria adicional encontrou a exceção de eleitorado descrita e, por isso, não permite afirmar que todas as relações contábeis fecham sem ressalvas. As exceções permanecem publicadas e sem explicação externa confirmada.

O teste demonstra consistência interna nas relações efetivamente verificadas. Não confronta os registros com boletins de urna autenticados ou cadastro independente de eleitores, não reconstitui o histórico oficial de publicação e não detecta uma alteração coordenada que preserve todas essas relações. Também não avalia preferências eleitorais, padrões temporais ou transferências entre turnos: esses temas pertencem às hipóteses seguintes.
