# Decisões do experimento

## Prioridade e escopo

As orientações do chat prevalecem sobre o documento anexado `Election-replay-instructions.md`, usado como referência de requisitos e metodologia, não como comprovação de conteúdo dos CSVs. O primeiro objetivo é o replay com CSV e gráficos; foram mantidos os diagnósticos necessários para interpretá-lo. Bash/Python substituem os exemplos PowerShell. Processam-se somente os turnos encontrados, sem exigir os dois.

## Entradas e rastreabilidade

- Somente `votacao_secao_2026_BR.csv` e `detalhe_votacao_secao_2026_BR.csv` compõem o fluxo principal. Nada é concatenado com `BRASIL` ou UFs.
- Originais são abertos somente para leitura. A execução registra SHA-256, tamanho, cabeçalhos e datas de extração presentes; data de coleta fica desconhecida quando não fornecida. Mtime não é tratado como coleta.
- `ANO_ELEICAO` é filtro explícito (2026 por padrão); `CD_CARGO=1`, `DS_CARGO=Presidente` e `SG_UE=BR` são conferidos. Inconsistências de código/nome presidencial causam falha, não descarte silencioso. Escopos observados e descartes ficam no manifesto.
- Ponteiros Git LFS são recusados. Não se calculam eleições sobre ponteiros nem se usam dados sintéticos como substitutos dos resultados reais.

## Modelo e duplicidades

- Chave: eleição + turno + UF + município + zona + seção + cargo. Apenas um ano é selecionado por execução. Códigos numéricos perdem zeros à esquerda para pareamento consistente.
- Votos repetidos na mesma seção/votável são somados, conforme o documento. Esses grupos são reportados; o programa não presume se a repetição significa erro na fonte.
- Nomes não participam da chave. Todas as variantes brutas são inventariadas. O nome de apresentação é o mínimo lexicográfico por votável; o número/código identifica a candidatura.
- **Todas** as chaves com mais de uma linha no detalhe são excluídas das curvas, mesmo que as linhas pareçam idênticas. A regra conservadora evita escolher um timestamp arbitrário e preserva os votos no resultado final e nos diagnósticos.
- Seções apenas na votação continuam nos totais finais e ficam fora das curvas. Seções apenas no detalhe entram no relatório de cobertura, sem inventar votos.

## Horários e curvas

- Referência principal: `DT_PRIM_TOT_PARCIAL_HOR_TSE`; alternativa: `DT_RECEBIMENTO_BU_HOR_TSE`. `DT_GERACAO`/`HH_GERACAO` são proveniência, nunca eventos.
- Formato observado inicialmente no detalhe: `DD/MM/AAAA HH:MM:SS`. O leitor aceita também frações de segundo e formatos locais ISO documentados no código. Valores com offset explícito ou formatos desconhecidos são inválidos, sem conversão adivinhada.
- Os PDFs descrevem “Hora TSE” sem fixar offset nos campos. Preserva-se o relógio local registrado, sem afirmar UTC ou converter para America/Sao_Paulo. A data completa evita fundir dias distintos.
- Timestamp ausente e inválido são motivos distintos. Detalhe faltante/duplicado também é contabilizado. São verificados votos temporais + não temporais = votos finais em cada candidato/turno/fonte.
- Minuto M representa `[M, M+1min)`; acumulado ao fim de M. Todos os minutos entre o primeiro e o último evento utilizável são escritos, com incrementos zero nos intervalos vazios.
- Não há interpolação ou distribuição artificial dos votos dentro da seção. O conjunto completo dos votos da seção entra no minuto de seu horário.
- Branco=95, nulo=96, separado=97. Outros números positivos são tratados operacionalmente como nominais no cargo presidencial. Esses arquivos não permitem certificar a validade jurídica individual por candidato; o percentual deve ser interpretado com essa limitação.
- Percentuais usam apenas nominais temporalmente atribuídos até o minuto. Classes especiais não entram no denominador e recebem percentual vazio.

## Qualidade e visualização

- Reconciliação por seção compara nominal/branco/nulo/separado onde o campo do detalhe está disponível; campos ausentes não viram zero. Quantidades de comparações possíveis e de métricas faltantes também são reportadas.
- Condições anulada/não instalada e origens diferentes da urna eletrônica são reportadas, sem exclusão automática de votos. No detalhe real foram observados `Sim`, `Não` e `Urna Eletrônica`, embora o PDF exemplifique códigos S/N/U; ambos são reconhecidos.
- Diferença recebimento→totalização é um intervalo entre registros, não latência da divulgação pública. Valores negativos são mantidos para diagnóstico.
- CSVs têm todos os minutos. Gráficos podem reduzir pontos, conservando início, fim e extremos por bloco; isso fica indicado no próprio relatório visual. HTML autônomo facilita exploração; SVGs são exportáveis e não exigem serviço externo.
- SQLite em disco, ingestão em lotes e gráficos com leitura em duas passagens evitam carregar arquivos grandes completos em RAM. Somente metadados de escopo e séries reduzidas ficam em memória.
- Pastas de saída não vazias são recusadas. O manifesto distingue execução concluída de falha com saídas parciais. As execuções completas em `output/` são ignoradas pelo Git por serem artefatos reproduzíveis. Uma seleção de CSVs compactos, manifesto, relatório e gráficos da execução validada é copiada para `reports/2026/` e versionada para facilitar o consumo no GitHub, sem incluir o SQLite ou grandes recortes por seção.

## Histórico operacional

O acesso Git inicial funcionou, mas o Git LFS retornou `Resource not accessible by integration`. Após o usuário conceder acesso do App Codex ao repositório no GitHub, o download dos dois CSVs nacionais foi concluído. Os hashes coincidiram com os ponteiros LFS e o processamento integral dos dois turnos terminou com conservação de votos verificada. Veja `docs/results-2026.md`. A implementação não altera autenticação, não usa novos tokens e não baixa outros datasets.

## Apresentação e idiomas

Por solicitação do usuário, o candidato 13 (Lula) usa vermelho `#c62828` e o candidato 22 (Flávio Bolsonaro) usa azul `#1565c0`. O mapeamento é explícito por número e vale para HTML, SVG, turnos, referências temporais e medidas. Os demais candidatos recebem cores de uma paleta separada; não há inferência automática de orientação política.

`README.md` é a versão principal em inglês dos EUA; `README.pt-BR.md` contém a versão em português do Brasil. Links no topo permitem alternar entre elas, pois o GitHub exibe o README principal sem selecionar automaticamente uma tradução.

## Análise geográfica do ritmo da apuração

A análise complementar está em `reports/2026/geography/`. Sua implementação separa preparação dos dados (`geography_data.py`), cálculos (`geography.py`), controles municipais (`geography_controls.py`), figuras (`geography_charts.py`) e consolidação do relatório (`geography_report.py`). O comando `geography_run.py` orquestra a reprodução e executa também a validação independente de `scripts/validate_geography.py`.

- O banco original do replay é aberto somente para leitura e as duas fontes têm seus hashes conferidos antes do novo processamento. Uma nova base analítica fica em `output/`, fora dos artefatos compactos versionados.
- Capitais são identificadas por nome normalizado e UF, com uma lista explícita das 27 capitais conferida nas duas eleições. Brasília/DF é tratada como capital, sem contraparte de interior. Exterior permanece na análise nacional e fora dos grupos domésticos de porte/capital.
- Porte é o número de eleitores aptos agregado por município na primeira rodada disponível, mantido fixo entre turnos. Faixas: até 10 mil, 10–50 mil, 50–200 mil, 200 mil–1 milhão e acima de 1 milhão. Não foi acrescentado dado populacional ou demográfico externo.
- Horário absoluto e estágio relativo são réguas diferentes. Marcos nacionais e paulistas são definidos por número de seções, com todos os empates incluídos; pesos geográficos e percentuais de candidatos usam votos nominais. Os cortes de relógio incluem eventos até HH:MM:00; séries por minuto chegam ao fim do minuto.
- A decomposição substitui a participação interna corrente de cada grupo pela final, mantendo os pesos geográficos correntes. É uma identidade contábil, não identificação causal. Contribuições municipais interpretáveis são centradas na participação final estadual; termos não centrados ficam disponíveis para auditoria.
- Correlações e ajustes municipais dão peso igual a cada município, diferentemente das medianas nacionais por seção. O ajuste com UF e log10 do eleitorado é descritivo e tem suporte limitado para comparações de capitais e não capitais de porte semelhante. Não se inferem renda, idade, escolaridade, perfil urbano/rural ou preferência individual.
- A análise completa requer Matplotlib/NumPy, listados separadamente em `requirements-analysis.txt`. O replay original permanece sem dependências Python externas. A exportação opcional de HTML autônomo para PDF utiliza Playwright/Chromium, sem alterar os cálculos.

## Etapa 2 como registro principal em Markdown

O índice de `reports/2026/` e os READMEs distinguem explicitamente a etapa 1 (reconstrução minuto a minuto) da etapa 2 (composição territorial e porte eleitoral das seções contabilizadas). O caminho já publicado `reports/2026/geography/REPORT.pt-BR.md` é mantido como registro principal da etapa 2; PDF e HTML são complementares. O gerador do relatório produz a mesma organização para evitar divergência entre documentação e novas execuções.

A consolidação cobre todas as cinco regiões e as 27 UFs, com exterior em separado. Percentuais de Lula e Flávio são calculados diretamente para os recortes e os marcos próprios de cada UF; não se infere o segundo candidato como complemento do primeiro no primeiro turno. A análise distingue os marcos do país dos de cada UF, o avanço por número de seções dos pesos por votos nominais, e a magnitude descritiva da evidência estatística.

### Referências formais de ordem aleatória

A pedido do usuário, a consolidação inclui testes formais, não apenas a frase “não foi encontrado um padrão forte”. O desenho foi definido antes da execução:

- 4.999 permutações por eleição/nulo, semente `20261027`, marcos de 10%, 25%, 50%, 75%, 90% e 99%. A unidade trocada é o payload da seção; o conjunto de slots de horário e seus empates fica fixo.
- Nulo global para curvas de avanço por região/UF; nulo dentro de UF para capital/porte e curvas dos candidatos. Percentuais nacionais dos candidatos são avaliados nos dois nulos; percentuais estaduais usam o avanço próprio da UF e o nulo dentro da UF. Contagens de UF/região fixas por construção não geram testes condicionais redundantes.
- A estatística é o maior desvio absoluto da curva em relação à média ponto a ponto das B+1 realizações, incluindo a observada. Essa regra simétrica é aplicada à curva observada e a cada permutação. P-valores usam `(1 + excedências)/(B + 1)`, com resolução mínima `0,0002`; nunca se reporta p igual a zero.
- Holm controla a família primária conjunta dos dois turnos a 5%, sem pressupor independência entre recortes. Primeira totalização é a referência primária. BU reutiliza os mesmos embaralhamentos como sensibilidade e não é outra família para selecionar resultados pelo menor p.
- Envelopes de 2,5–97,5% são ponto a ponto, não simultâneos ou intervalos de confiança populacionais. Pesos nominais por grupo têm envelopes descritivos; os testes primários dos grupos usam conclusão por seções. A decisão formal vem da curva inteira, não da inspeção isolada de pontos fora do envelope.
- “Desvio detectado”, “desvio não detectado” e “não aplicável” são categorias distintas. Ausência de rejeição não prova aleatoriedade ou equivalência; uma magnitude pequena pode ser detectável. Diferença de rejeição entre turnos não é um teste da diferença entre turnos.
- Troca livre de seções preserva tamanho dos lotes temporais, mas não sua composição geográfica/operacional. Rejeitar essa referência não identifica uma causa técnica ou um efeito demográfico individual.

O motor usa arrays numéricos contíguos e até quatro processos independentes, respeitando a cota de CPU. Cada combinação turno/nulo tem seu RNG determinístico e checkpoint próprio, com hashes do código, dados e parâmetros; paralelismo e retomada não reduzem o número de permutações. Os caches de curvas ficam em `output/`, fora do Git. A validação independente reconstrói as observações do banco do replay e audita centros, estatísticas, excedências e Holm a partir desses caches, sem importar o motor ou NumPy.

## Etapa 3 — Hipóteses, começando pela integridade contábil

As sete hipóteses aprovadas têm índice em `reports/2026/hypothesis-tests/`. Somente a H1 foi executada nesta entrega. Cada hipótese concentra relatório Markdown, código, testes e evidências em uma subpasta; não foram alterados os resultados das etapas anteriores. A dificuldade de identificação mede esforço analítico e de interpretação, não probabilidade de manipulação. O resultado não é definido antecipadamente como refutação.

A H1 lê diretamente os dois CSVs nacionais, sem depender de agregações prévias do replay. Uma implementação usa SQLite temporário; outra usa parser e dicionários independentes, sem importar os módulos da análise principal. As contagens são inteiras e exaustivas, sem amostragem, teste de significância ou tolerância numérica. Chaves repetidas são identificadas antes da soma; diferenças opostas em seções distintas não se cancelam na decisão. Os hashes das fontes são comparados também com o manifesto da etapa 1.

A soma do detalhe inclui votos nominais, brancos, nulos, legenda e anulados em separado, cada categoria uma vez. `QT_VOTOS_LEGENDA` é conferido explicitamente, embora não tenha sido retido na base do replay. Ausências e valores inválidos são registrados e não viram zero; apenas a ausência de linhas de votação para uma chave existente no detalhe é confrontada com um vetor vazio de votos, acompanhada de diagnóstico próprio de cobertura. As 85 ocorrências reais nesse diagnóstico têm votos e comparecimento zerados.

As 82 divergências de `aptos = comparecimento + abstenções` permanecem no resultado bruto: são 41 seções físicas do exterior, não instaladas, repetidas nos dois turnos, com 423 aptos por turno e sem votos, comparecimento ou abstenções registrados. O leiaute não explicita essa convenção; a sinalização de não instalação contextualiza a diferença, mas não a resolve de forma independente. Não se declara a hipótese ampla integralmente refutada, nem se somam os mesmos 423 aptos como eleitorado distinto dos dois turnos. Checagens gerais e por estrato se sobrepõem e não representam ocorrências adicionais.

Os grandes bancos temporários são removidos após o processamento. A pasta local `.work/` da hipótese é ignorada no Git para reproduções e versões provisórias. Evidências compactas, hashes e testes com corrupção sintética ficam versionados ao lado do relatório. A conferência interna não autentica os arquivos externamente e não detecta, por si só, mudanças coordenadas que preservem suas identidades contábeis.
