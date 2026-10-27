# Replay da apuração presidencial de 2026

[English (US)](README.md) | **Português (Brasil)**

Reconstrução **retrospectiva e aproximada** da evolução minuto a minuto a partir dos dois CSVs nacionais presentes em `data/`. Os votos disponíveis na extração são atribuídos ao horário da seção: isso não reproduz necessariamente revisões nem a sequência de publicações do painel do TSE.

O processamento identifica os turnos e códigos de eleição presentes, inclui o exterior (`ZZ`) e produz duas séries separadas: **primeira totalização parcial** e **recebimento do BU**. Não cria um turno que não exista nos arquivos.

## Resultados publicados

Os resultados compactos da execução validada dos dois turnos estão versionados em [reports/2026/](reports/2026/):

- [Relatório interativo](reports/2026/replay-report.html): baixe o HTML e abra no navegador. Ele é autônomo; o visualizador de arquivos do GitHub não executa a página interativa.
- [CSV por primeira totalização](reports/2026/replay-first-totalization-minute.csv) e [CSV por recebimento do BU](reports/2026/replay-bu-received-minute.csv).
- [Totais finais](reports/2026/final-results.csv), [relatório da execução](reports/2026/report.md) e [manifesto de entrada](reports/2026/input-manifest.json).
- Gráficos exportáveis: [primeiro turno](reports/2026/charts/election-6257-turn-1-first_partial_totalization.svg) e [segundo turno](reports/2026/charts/election-6258-turn-2-first_partial_totalization.svg).

O candidato **13 (Lula) usa vermelho**, e o candidato **22 (Flávio Bolsonaro) usa azul**, em ambos os turnos, referências temporais e medidas. Os demais candidatos usam uma paleta separada. As cores são associadas explicitamente aos números; o programa não infere orientação política.

## Executar

Requisitos: Python **3.12+**, SQLite **3.39+** (incluído no Python deste ambiente) e Git LFS para recuperar os arquivos de entrada. O replay original não exige pacotes externos, servidor, token adicional ou banco de dados a instalar. Execute na raiz do checkout existente; não é necessário criar um worktree.

```bash
# Inicialize o LFS neste checkout e recupere somente as duas entradas necessárias:
git lfs install --local
git lfs pull --include='data/votacao_secao_2026_BR/votacao_secao_2026_BR.csv,data/detalhe_votacao_secao_2026/detalhe_votacao_secao_2026_BR.csv' --exclude=''

# Gera resultados em uma pasta nova, sem sobrescrever execuções anteriores:
PYTHONPATH=src python3 -m election_replay --output output/replay

# Validação automatizada com pequenos dados sintéticos:
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Abra `output/replay/replay-report.html` no navegador para explorar as curvas (arquivo autônomo, sem CDN ou servidor). O relatório textual está em `output/replay/report.md` e os gráficos exportáveis em `output/replay/charts/*.svg`.

Os CSVs de entrada somam cerca de **1,92 GB**; reserve espaço também para o cache LFS, a base intermediária SQLite e as saídas. A ingestão usa lotes e o relacionamento/agregação usa SQLite em disco. Gráficos usam até 2.400 pontos por candidato/fonte; os CSVs preservam **todos os minutos**. O tempo de execução depende do disco/CPU.

Para reexecutar, escolha outra pasta (`--output output/replay-02`). Diretórios não vazios são recusados. Falhas posteriores à criação da saída deixam um manifesto com `status: failed`; seus arquivos parciais não são resultados concluídos. Ponteiros LFS são recusados antes de gerar saídas.

Outras opções:

```bash
PYTHONPATH=src python3 -m election_replay --help
PYTHONPATH=src python3 -m election_replay --year 2026 \
  --votes data/votacao_secao_2026_BR/votacao_secao_2026_BR.csv \
  --details data/detalhe_votacao_secao_2026/detalhe_votacao_secao_2026_BR.csv \
  --output output/nova-execucao
```

`--max-minutes` limita o intervalo por eleição/turno/fonte a 600.000 minutos por padrão; excedê-lo **aborta**, sem truncar a série. Inspecione horários antes de aumentar o limite. `--synthetic` identifica visualmente dados artificiais e deve ser usado em demonstrações; os testes não representam resultados eleitorais.

O registro da execução validada dos dois turnos está em [docs/results-2026.md](docs/results-2026.md).

## Análise geográfica do ritmo da apuração

A análise de regiões, UFs, capitais, porte municipal e São Paulo está consolidada no [relatório em português](reports/2026/geography/REPORT.pt-BR.md), com [gráficos e tabelas de evidências](reports/2026/geography/). Comparam-se os dois turnos tanto em progresso nacional/estadual equivalente quanto em horários fixos. Porte municipal significa **eleitorado registrado**, não população residente; não se inferem características demográficas individuais ou mecanismos causais.

Para reproduzir, primeiro gere a base do replay conforme os comandos acima:

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements-analysis.txt
PYTHONPATH=src python3 -m election_replay.geography_run --output output/geography-new
```

Esse fluxo opcional utiliza Matplotlib e NumPy para figuras e controles descritivos. Ele verifica os hashes das fontes, reutiliza `output/replay/replay.sqlite` somente para leitura e gera uma base separada, CSVs de evidências, figuras PNG/SVG, Markdown e HTML autônomo. Pastas anteriores não vazias são preservadas. O relatório versionado registra esta execução; em fontes atualizadas, refaça os cálculos e revise as conclusões.

## Saídas

| Arquivo | Conteúdo |
|---|---|
| `input-manifest.json` | Caminhos, tamanhos, SHA-256, datas de extração observadas, escopo, status e verificações |
| `report.md` | Resumo da execução, cobertura, totais e limitações |
| `replay-report.html`, `charts/*.svg` | Gráfico interativo e versões exportáveis por eleição/turno/fonte |
| `replay-first-totalization-minute.csv` | Série pela primeira totalização parcial |
| `replay-bu-received-minute.csv` | Série por recebimento do BU |
| `final-results.csv` | Totais por eleição/turno/votável no Brasil, incluindo ZZ quando presente |
| `final-results-uf.csv`, `final-results-municipality.csv`, `final-results-section.csv` | Mesmos totais em recortes geográficos |
| `untimed-votes.csv` | Votos fora de cada curva: sem detalhe, detalhe duplicado, horário ausente ou inválido |
| `data-quality.csv`, `section-coverage.csv` | Cobertura e diagnóstico do pareamento |
| `duplicate-details.csv`, `vote-aggregation.csv`, `candidate-names.csv` | Duplicidades, agregação de registros de voto e variantes de nomes |
| `reconciliation.csv` | Divergências internas entre votação e totais por categoria do detalhe |
| `section-exceptions.csv` | Horários problemáticos, situações excepcionais, flags ausentes e inconsistências auxiliares |
| `timestamp-latency.csv` | Intervalo entre recebimento e primeira totalização; não mede divulgação pública |
| `replay.sqlite` | Intermediário persistido para auditoria e novas consultas |

As execuções geradas ficam em `output/`, ignorado pelo Git. Uma seleção de artefatos compactos da execução validada fica versionada em `reports/2026/`; a base intermediária e os grandes recortes por seção não são incluídos ali.

Saídas CSV usam **UTF-8 e vírgula**. Entradas são lidas em **Latin-1 com ponto e vírgula**, conforme os PDFs locais. `election_code` corresponde a `CD_ELEICAO`; `turno` a `NR_TURNO`; códigos de seção/localidade são canonicamente numéricos. `minute` é `AAAA-MM-DD HH:MM:00`, em **Hora TSE**, sem atribuir um offset não confirmado. `uf_scope=BR` na curva representa o consolidado nacional, não um filtro sobre `SG_UF`.

`sections_in_minute` e `cumulative_sections` são contagens globais de seções daquele turno/fonte, repetidas para cada votável: **não devem ser somadas entre candidatos**. `percentage_valid_votes` é percentual de votos nominais acumulados **na curva**; não usa os votos excluídos por falta de horário. Fica vazio para classes especiais e quando não há denominador nominal.

## Metodologia e decisões

Veja [docs/decisions.md](docs/decisions.md). Os arquivos `BRASIL` e estaduais não são concatenados ao nacional, evitando sobreposição. Resultados finais partem da votação, independentemente do sucesso do pareamento temporal. Todas as duplicidades no detalhe são colocadas em quarentena para as curvas; não se escolhe arbitrariamente um horário.

A conservação de votos é verificada para cada eleição/turno/votável/fonte: **votos na curva + votos sem horário utilizável = resultado final**. A reconciliação é apenas entre as duas entradas; ausência de divergências não significa concordância quando métricas estão ausentes, nem certificação externa do resultado.

Fontes esperadas: [TSE — Resultados 2026](https://dadosabertos.tse.jus.br/dataset/resultados-2026) e os dois `leiame.pdf` mantidos em `data/`. A autenticidade externa das extrações não é certificada por este programa.
