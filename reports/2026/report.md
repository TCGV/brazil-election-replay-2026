# Replay retrospectivo da apuração presidencial

Reconstrução aproximada: os votos finais de cada seção são associados retrospectivamente ao horário registrado. Não é um histórico certificado das atualizações públicas do TSE.

Horários preservados em **Hora TSE**, sem inferência de offset UTC. Cada linha representa o acumulado ao fim do minuto; por exemplo, 17:00 inclui eventos de 17:00:00 até antes de 17:01:00.

## Entradas

| Fonte | Bytes | SHA-256 |
|---|---:|---|
| votes | 1572813473 | `9c35200e1c613d8cc76b255a1d6c824cf5dba63a995c1e86b893c348722fcad8` |
| details | 350832764 | `bb25a47159af3c628e3e7d0b78819f9c43a11eda66ed36f22ef0a2c2d5caf5bd` |

A data de coleta é desconhecida; datas de extração observadas estão no manifesto. Os originais não são modificados.

## Evolução temporal

| Eleição | Turno | Referência | Primeiro minuto | Último minuto | Votos com horário | Votos fora da curva | Seções com horário |
|---|---|---|---|---|---:|---:|---:|
| 6257 | 1 | first_partial_totalization | 2026-10-04 17:08:00 | 2026-10-05 02:58:00 | 125275835 | 0 | 499206 |
| 6258 | 2 | first_partial_totalization | 2026-10-25 17:05:00 | 2026-10-25 23:21:00 | 128236074 | 0 | 499205 |
| 6257 | 1 | bu_received | 2026-10-04 17:08:00 | 2026-10-05 02:58:00 | 125275835 | 0 | 499206 |
| 6258 | 2 | bu_received | 2026-10-25 17:05:00 | 2026-10-25 23:21:00 | 128236074 | 0 | 499205 |

Turnos efetivamente encontrados na votação: 1, 2. Não foram criados turnos ausentes.

## Resultado final recontado

| Eleição | Turno | Número | Nome/classe | Classe | Votos |
|---|---|---|---|---|---:|
| 6257 | 1 | 22 | FLAVIO NANTES BOLSONARO | nominal | 56104503 |
| 6257 | 1 | 13 | LUIZ INÁCIO LULA DA SILVA | nominal | 53879538 |
| 6257 | 1 | 96 | VOTO NULO | null | 3669003 |
| 6257 | 1 | 70 | AUGUSTO JORGE CURY | nominal | 3448569 |
| 6257 | 1 | 14 | RENAN ANTONIO FERREIRA DOS SANTOS | nominal | 2675887 |
| 6257 | 1 | 55 | RONALDO RAMOS CAIADO | nominal | 2605148 |
| 6257 | 1 | 95 | VOTO BRANCO | blank | 2300798 |
| 6257 | 1 | 30 | ROMEU ZEMA NETO | nominal | 326488 |
| 6257 | 1 | 80 | SAMARA MARTINS DA SILVA FEITOSA | nominal | 122911 |
| 6257 | 1 | 16 | HERTZ DA CONCEICAO DIAS | nominal | 43103 |
| 6257 | 1 | 27 | CLARIANA ZACARKIM BARAO | nominal | 40043 |
| 6257 | 1 | 21 | EDMILSON SILVA COSTA | nominal | 22693 |
| 6257 | 1 | 35 | WILSON GRASSI JUNIOR | nominal | 16881 |
| 6257 | 1 | 29 | RUI COSTA PIMENTA | nominal | 15024 |
| 6257 | 1 | 28 | LEONARDO ALVES DE ARAUJO | nominal | 5246 |
| 6258 | 2 | 13 | LUIZ INÁCIO LULA DA SILVA | nominal | 64256232 |
| 6258 | 2 | 22 | FLAVIO NANTES BOLSONARO | nominal | 59826041 |
| 6258 | 2 | 96 | VOTO NULO | null | 2723305 |
| 6258 | 2 | 95 | VOTO BRANCO | blank | 1430496 |

## Qualidade e cobertura

- Seções na votação: 998411; no detalhe: 998496; pareadas sem duplicidade: 998411.
- Chaves duplicadas no detalhe: 0; todas ficam fora das curvas, preservadas nos totais finais.
- Divergências de categoria/seção na reconciliação interna: 0 (consulte `reconciliation.csv`).
- Reconciliação compara apenas métricas presentes em seções com detalhe único; zero divergências não comprova concordância quando métricas faltam. A contagem de comparações por classe está em `data-quality.csv` e no manifesto.
- Conservação verificada por eleição/turno/votável e por referência: votos na curva + votos sem horário utilizável = total final.
- O percentual divide apenas votos nominais acumulados com horário utilizável. Brancos, nulos e anulados/apurados em separado não entram no denominador.
- Sem detalhe, detalhe duplicado, timestamp ausente e timestamp inválido são contabilizados separadamente em `untimed-votes.csv`.

| Eleição | Turno | UF | Seções na votação | Votos |
|---|---|---|---:|---:|
| 6257 | 1 | AC | 2270 | 488330 |
| 6257 | 1 | AL | 7101 | 1938428 |
| 6257 | 1 | AM | 8157 | 2234549 |
| 6257 | 1 | AP | 1914 | 476562 |
| 6257 | 1 | BA | 35476 | 9053601 |
| 6257 | 1 | CE | 23765 | 5910471 |
| 6257 | 1 | DF | 6969 | 1831396 |
| 6257 | 1 | ES | 9844 | 2352282 |
| 6257 | 1 | GO | 15686 | 3971587 |
| 6257 | 1 | MA | 18093 | 4160343 |
| 6257 | 1 | MG | 52062 | 12637274 |
| 6257 | 1 | MS | 7106 | 1541220 |
| 6257 | 1 | MT | 8287 | 2052133 |
| 6257 | 1 | PA | 20827 | 5066504 |
| 6257 | 1 | PB | 10712 | 2683988 |
| 6257 | 1 | PE | 21418 | 5911062 |
| 6257 | 1 | PI | 10225 | 2240883 |
| 6257 | 1 | PR | 27142 | 6841457 |
| 6257 | 1 | RJ | 37675 | 9859802 |
| 6257 | 1 | RN | 8115 | 2171013 |
| 6257 | 1 | RO | 4698 | 991080 |
| 6257 | 1 | RR | 1519 | 332772 |
| 6257 | 1 | RS | 27547 | 6702903 |
| 6257 | 1 | SC | 17326 | 4648159 |
| 6257 | 1 | SE | 5923 | 1439082 |
| 6257 | 1 | SP | 103656 | 26431992 |
| 6257 | 1 | TO | 4384 | 965196 |
| 6257 | 1 | ZZ | 1309 | 341766 |
| 6258 | 2 | AC | 2270 | 453654 |
| 6258 | 2 | AL | 7101 | 1951632 |
| 6258 | 2 | AM | 8157 | 2192059 |
| 6258 | 2 | AP | 1914 | 429975 |
| 6258 | 2 | BA | 35476 | 9422047 |
| 6258 | 2 | CE | 23765 | 6024843 |
| 6258 | 2 | DF | 6969 | 1868280 |
| 6258 | 2 | ES | 9844 | 2409214 |
| 6258 | 2 | GO | 15686 | 4047280 |
| 6258 | 2 | MA | 18093 | 4127771 |
| 6258 | 2 | MG | 52062 | 13044203 |
| 6258 | 2 | MS | 7106 | 1594460 |
| 6258 | 2 | MT | 8287 | 2085334 |
| 6258 | 2 | PA | 20827 | 4989573 |
| 6258 | 2 | PB | 10712 | 2743560 |
| 6258 | 2 | PE | 21418 | 6126467 |
| 6258 | 2 | PI | 10225 | 2239830 |
| 6258 | 2 | PR | 27142 | 7059339 |
| 6258 | 2 | RJ | 37675 | 10077449 |
| 6258 | 2 | RN | 8115 | 2232823 |
| 6258 | 2 | RO | 4698 | 988489 |
| 6258 | 2 | RR | 1519 | 308597 |
| 6258 | 2 | RS | 27547 | 6889638 |
| 6258 | 2 | SC | 17326 | 4762303 |
| 6258 | 2 | SE | 5923 | 1466659 |
| 6258 | 2 | SP | 103656 | 27364389 |
| 6258 | 2 | TO | 4384 | 954763 |
| 6258 | 2 | ZZ | 1308 | 381443 |

A UF ZZ representa exterior e é incluída quando presente, sem inferir ausência pelo tamanho de outros arquivos.

## Artefatos

- `replay-report.html`: visualização interativa autônoma; `charts/*.svg`: gráficos exportáveis.
- `replay-*-minute.csv`: séries integrais, inclusive minutos sem novos eventos.
- `final-results*.csv`: votos por Brasil, UF, município e seção.
- `section-coverage.csv`, `duplicate-details.csv`, `section-exceptions.csv`: diagnóstico do pareamento e das exceções.
- `timestamp-latency.csv`: diferença recebimento → primeira totalização para detalhes únicos com ambos os horários; não é latência de publicação.
- `candidate-names.csv` e `vote-aggregation.csv`: variações de nome e agregação de linhas repetidas.
- `replay.sqlite`: base intermediária auditável em disco; `input-manifest.json`: proveniência, escopo, formatos, verificações e status.

## Limitações

A verificação é interna aos dois arquivos selecionados; não há comparação independente com um resultado oficial externo. Horários e quantidades podem refletir extrações, retotalizações e situações jurídicas diferentes. Seções anuladas/não instaladas e origens incomuns são listadas, mas seus votos não são descartados automaticamente. Na ausência de dado nominal detalhado de situação jurídica por candidato, os nominais são classificados operacionalmente como números diferentes de 95/96/97. Esta classificação não certifica a validade jurídica de cada voto.
