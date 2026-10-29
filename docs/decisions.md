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

As sete hipóteses aprovadas têm índice em `reports/2026/hypothesis-tests/`. A primeira entrega executou somente a H1. Cada hipótese concentra relatório Markdown, código, testes e evidências em uma subpasta; não foram alterados os resultados das etapas anteriores. A dificuldade de identificação mede esforço analítico e de interpretação, não probabilidade de manipulação. O resultado não é definido antecipadamente como refutação.

A H1 lê diretamente os dois CSVs nacionais, sem depender de agregações prévias do replay. Uma implementação usa SQLite temporário; outra usa parser e dicionários independentes, sem importar os módulos da análise principal. As contagens são inteiras e exaustivas, sem amostragem, teste de significância ou tolerância numérica. Chaves repetidas são identificadas antes da soma; diferenças opostas em seções distintas não se cancelam na decisão. Os hashes das fontes são comparados também com o manifesto da etapa 1.

A soma do detalhe inclui votos nominais, brancos, nulos, legenda e anulados em separado, cada categoria uma vez. `QT_VOTOS_LEGENDA` é conferido explicitamente, embora não tenha sido retido na base do replay. Ausências e valores inválidos são registrados e não viram zero; apenas a ausência de linhas de votação para uma chave existente no detalhe é confrontada com um vetor vazio de votos, acompanhada de diagnóstico próprio de cobertura. As 85 ocorrências reais nesse diagnóstico têm votos e comparecimento zerados.

As 82 divergências de `aptos = comparecimento + abstenções` permanecem no resultado bruto: são 41 seções físicas do exterior, não instaladas, repetidas nos dois turnos, com 423 aptos por turno e sem votos, comparecimento ou abstenções registrados. O leiaute não explicita essa convenção; a sinalização de não instalação contextualiza a diferença, mas não a resolve de forma independente. Não se declara a hipótese ampla integralmente refutada, nem se somam os mesmos 423 aptos como eleitorado distinto dos dois turnos. Checagens gerais e por estrato se sobrepõem e não representam ocorrências adicionais.

Os grandes bancos temporários são removidos após o processamento. A pasta local `.work/` da hipótese é ignorada no Git para reproduções e versões provisórias. Evidências compactas, hashes e testes com corrupção sintética ficam versionados ao lado do relatório. A conferência interna não autentica os arquivos externamente e não detecta, por si só, mudanças coordenadas que preservem suas identidades contábeis.

## H2 — Comparecimento e concentração de votos entre pares locais

O protocolo da segunda hipótese está em `reports/2026/hypothesis-tests/02-turnout-concentration/METHOD.pt-BR.md`. Foi fixado antes do cálculo das caudas, após reconhecer apenas esquema, candidaturas, elegibilidade e suporte dos grupos. Não é um pré-registro externo. Foram incluídas todas as candidaturas nominais: 13 no primeiro turno e duas no segundo. Na entrega da H2, as hipóteses 3–7 ainda não haviam sido avaliadas.

Os dois arquivos nacionais são relidos diretamente e seus hashes são confrontados com a etapa 1 e a H1 concluídas. A unicidade seção/votável é uma pré-condição conferida na H1 para exatamente os mesmos arquivos; o carregamento da H2 verifica novamente chaves de detalhe, categorias e vetores completos de candidatos por seção. Ausência de linha de uma candidatura existente é zero; ausência de métrica não é. O cache NumPy é local, ignorado, identificado por hashes das fontes, pré-condições e código, e nunca substitui a validação independente dos originais.

A comparação principal usa município, zona e faixas geométricas de aptos com razão 1,25, exigindo pelo menos 30 seções elegíveis. A cobertura fica próxima de 70%; os casos sem suporte não são classificados como ausência de anomalia. As duas caudas superiores de 5% são calculadas com empates conservadores. A prioridade exige também 5 pontos de comparecimento e 10 pontos de votação acima das medianas. Esses cortes são descritivos e não atribuem valores-p individuais nem estimam votos artificiais.

A referência formal testa independência condicional entre as caudas, preservando suas margens por estrato. Usa 19.999 realizações por candidatura/turno, semente `20261028` e Holm na família fixa de 15 comparações. Associação legítima, heterogeneidade dentro da zona e diferenças de precisão das proporções podem rejeitar essa referência; ela não define naturalidade eleitoral. A votação do candidato não é tratada como complemento de outro no primeiro turno. Sensibilidades alteram um parâmetro por vez e são descritivas, sem seleção de novos valores-p.

O contexto do mesmo local de votação exclui a própria seção e exige quatro outros pares elegíveis, de porte próximo. Persistência, atenuação e insuficiência são categorias descritivas. Nenhuma delas certifica origem natural ou artificial. Mudanças que atinjam a maioria de um grupo podem escapar de uma referência interna. A implementação independente usa razões exatas para a triagem primária e regenera todos os 299.985 valores simulados; as sensibilidades alternativas não são recalculadas por essa segunda implementação, limitação declarada no relatório e no JSON de validação.

Código, evidências, testes e quatro figuras PNG/SVG permanecem na pasta da H2. Fontes, resultados das etapas 1/2 e artefatos da H1 foram preservados. O registro principal é Markdown; não foi criada uma inferência sobre voto individual nem uma classificação de seções como fraudulentas.

## H3 — Repetição de vetores completos em seções distintas

O protocolo da terceira hipótese está em `reports/2026/hypothesis-tests/03-result-repetition/METHOD.pt-BR.md`, definido antes de calcular suas frequências. A H3 distingue chaves duplicadas, já verificadas na H1, de valores iguais em seções distintas. Os dois turnos são separados e todos os candidatos entram nas assinaturas inteiras, junto de brancos, nulos, legenda, separados e comparecimento. Uma assinatura estendida acrescenta aptos e abstenções. Seções sem atividade e pequenas positivas permanecem em inventários separados; coincidência não recebe automaticamente interpretação de cópia.

O inventário nacional é exaustivo, mas a referência formal é mais restrita: emparelhamento entre o vetor de candidatos e o bloco de comparecimento/categorias especiais dentro de UF, município, zona, total nominal exato e faixa de aptos com razão 1,25. Redistribuir o vetor inteiro preserva somas e marginais observadas. O teste condiciona a frequência do próprio bloco de candidatos, não avalia todas as formas de repetição e não cobre automaticamente pares entre localidades.

Momentos, limites unilaterais de Cantelli e ajuste de Holm na família fixa de dois turnos usam frações racionais. Os limites são conservadores, não valores-p exatos; não há simulação ou semente. Estratos unitários e constantes permanecem na cobertura, mas são distinguidos dos que têm variância positiva. O primeiro turno tem somente um estrato informativo, com sete seções; o segundo, 1.575, com 12.182. Esse alcance impede interpretar não detecção como refutação ampla da H3.

As sensibilidades, previamente definidas, alteram geografia, faixa ou piso nominal e permanecem descritivas. Uma implementação independente relê os originais e confere todos os vetores repetidos, membros, estratos primários e momentos exatos. As tabelas maiores usam `.csv.gz`, com todas as linhas preservadas e comandos de leitura/decompressão no README. Cache, logs provisórios e referências locais ficam em `.work/`, ignorado pelo Git. Código, relatório Markdown e figuras ficam na pasta da H3; fontes e artefatos anteriores foram preservados. As hipóteses 4–7 não foram executadas.

## Escala de avaliação e autonomia dos relatórios

A pedido do usuário, os índices em português e inglês e os relatórios/READMEs individuais passam a apresentar uma escala de 0 (integralmente refutada) a 10 (integralmente confirmada). Trata-se de síntese qualitativa e ordinal, atribuída após as análises com justificativa explícita, não de um teste adicional, transformação de valor-p, probabilidade de manipulação ou medida de votos suspeitos. A avaliação abrange os dois turnos no recorte de cada hipótese. Notas não devem ser somadas ou promediadas em uma medida de risco.

Foram atribuídas H1 = 1/10, considerando a ausência dos sinais centrais e a ressalva da identidade contábil adicional; H2 = 6/10, pelo apoio parcial às associações estatísticas sem demonstração de causa artificial; H3 = 5/10, como convenção de conclusão inconclusiva diante do alcance informativo limitado. O ponto 5 não representa 50% de chance nem evidência positiva de anomalia. Os extremos se restringem ao escopo verificável definido, sem autenticar fontes externamente.

Os documentos individuais deixam de listar o andamento das demais hipóteses; o índice concentra esse acompanhamento. Referências técnicas entre análises permanecem quando necessárias à procedência e à reprodução. Protocolos fixados antes dos resultados, cálculos, evidências numéricas e figuras não foram alterados. Os inventários de arquivos são atualizados para refletir a revisão documental.

## H4 — Ordem temporal residual em duas referências locais

O protocolo está em `reports/2026/hypothesis-tests/04-temporal-residuals/METHOD.pt-BR.md`, fixado antes de relacionar votação e ordem nesta entrega. A inspeção prévia mostrou que muitas seções do mesmo local chegam no mesmo minuto ou em intervalos curtos. Foram definidas duas referências complementares: município/zona/faixa de aptos e o mesmo recorte acrescentando o local de votação. Ambas são testadas, sem selecionar a que produza o resultado desejado. A segunda controla diferenças entre locais, mas pode condicionar para fora um movimento coordenado de todo o local.

O carregador relê os CSVs originais, confere os hashes da etapa 1 e da auditoria contábil e reconcilia candidatos e categorias por seção. A coorte exige instalação, ausência de anulação, pelo menos 50 aptos e 50 nominais, comparecimento positivo, local conhecido e ambos os horários válidos. Exclusões são exclusivas e independentes da votação de qualquer candidato. Horários mantêm a convenção Hora TSE, sem inferir fuso; segundos são truncados para o minuto e todos os empates entram juntos. A extração retrospectiva não contém o histórico completo das atualizações públicas ou das alterações intermediárias de cada registro.

Para cada grupo/candidato, o resíduo é `votos_i − participação_final_do_grupo * nominais_i`. A participação usa os próprios resultados finais: a decomposição é retrospectiva, sem previsão externa. Proporcionalidade exata é reconhecida com produtos cruzados inteiros. Grupos unitários e sem dispersão temporal permanecem na cobertura e nos denominadores, sem serem classificados como naturais. São publicados também intervalos temporais e suporte por candidatura, pois ter pares não garante capacidade de comparação.

Os três escores examinam todos os minutos: covariância residual com o posto temporal médio (G), máximo do resíduo acumulado (C) e máximo da contribuição de um minuto (M). Os denominadores formais usam o nominal final da coorte; a diferença corrente de participação tem outro denominador e aparece separadamente. G não é uma inclinação convencional nem o ganho percentual entre início e fim. Deslocar o vetor de resíduos de uma seção inteira equivale, para esses escores, a redistribuir seu payload completo dentro do grupo, pois a participação final do grupo permanece invariante.

São 4.999 permutações por turno/referência, semente-base `20261028`, PCG64 e subfluxos por realização independentes dos processos. Todos os candidatos compartilham a mesma atribuição; os pares de horários também. A primeira totalização forma a família primária fixa de 90 testes, com valores-p de mais um e ajuste de Holm a 5%. BU é sensibilidade emparelhada, sem novos valores-p. Faixas de 2,5–97,5% são quantis de referência; os envelopes de curva são ponto a ponto na grade fixa de avanço, sem interpretação de intervalo de confiança ou banda simultânea.

A aplicabilidade dos escores em módulo exige variação comprovada, além de resíduos e horários variáveis. Duas realizações com escores distintos fornecem uma testemunha de possibilidade. Sem essa testemunha, órbitas pequenas são enumeradas para distinguir constância de variabilidade; se a órbita ultrapassar o limite e a dúvida persistir, a análise interrompe em vez de publicar uma não detecção. Referências constantes comprovadas recebem não aplicável, com p=1 apenas no ajuste conservador da família.

Local sem faixa e piso de 100 nominais nas duas referências são sensibilidades descritivas predefinidas. Recortes estaduais não recebem novos testes selecionados. Uma implementação independente usa outro parser e outros cálculos para reconstruir todas as tabelas, auditar escores/bandas a partir dos caches e repetir as atribuições 0 e 1 de cada execução. Isso não equivale a gerar novamente todas as 19.996 permutações. Código, testes, evidências, quatro figuras e relatório Markdown permanecem na pasta da H4; caches grandes ficam em `.work/`, ignorado pelo Git.

A avaliação qualitativa da H4 é 6/10: há apoio parcial a associações residuais nas referências definidas. Dos 90 testes primários, 40 detectaram desvios e 50 não; esses resultados dependentes não representam 90 ocorrências independentes. No primeiro turno, a referência por local mantém G/C para cinco candidaturas, incluindo os finalistas; no segundo, nenhum escore dessa referência é detectado após Holm. Acrescentar o local reduz fortemente as magnitudes em ambos os turnos, sem que essa comparação forneça uma porcentagem causalmente explicada ou uma estimativa de votos artificiais. A cobertura temporal e os movimentos condicionados para fora do teste impedem uma conclusão ampla de naturalidade ou de origem artificial.

## H5 — Mudanças pareadas entre turnos e concentração entre locais

O protocolo em `reports/2026/hypothesis-tests/05-inter-round-localization/METHOD.pt-BR.md` foi fixado antes de calcular as mudanças entre turnos. A inspeção estrutural reconheceu chaves, denominadores e mudanças cadastrais. As mesmas 499.248 chaves físicas aparecem nos dois turnos, mas continuidade da chave não prova identidade dos eleitores. A coorte de 497.833 pares exige elegibilidade básica nos dois turnos, pelo menos 50 votos dos finalistas no primeiro, local conhecido e igual, e razão simétrica de aptos até 1,25. Não se exclui qualquer mudança de aptos: a maior parte é de apenas um eleitor, e esse filtro descartaria muitos pares sem necessidade.

A participação condicional `votos_13/(votos_13+votos_22)` torna o denominador comparável entre turnos. Sua mudança em pontos percentuais é distinta da mudança sobre todos os nominais e do ganho de contagens, que permanecem publicados como diagnósticos. A medida do candidato 22 é exatamente oposta; não se duplicam testes complementares. Os dados agregados não identificam transferências individuais ou as causas de mudanças no público votante.

A triagem por seção exige quatro outros pares do mesmo local, faixa de aptos e faixa inicial de cinco pontos percentuais. Usa mediana sem a própria seção e corte de magnitude de dez pontos, sem valor-p individual ou corte de MAD instável com poucos pares. O contexto adicional sem faixa inicial amplia a cobertura, mas continua descritivo. Há duas prioridades entre 152.003 seções com comparação estrita, ambas em Porto/ZZ, e 16 no contexto mais amplo de 363.150. Os restantes pares não são classificados como normais por falta de suporte. São publicados todos os pares e contrastes, sem amostragem.

A referência formal responde outra pergunta: concentração entre locais, preservando a distribuição marginal das mudanças. Redistribui o par completo de contagens dos dois turnos dentro de município, zona e faixa de aptos, com e sem controle adicional da preferência inicial. O resíduo usa média simples de mudança por seção dentro do estrato, sem confundi-la com participação agregada de votos. Os locais-alvo têm pelo menos cinco seções da coorte. RMS é a raiz da média quadrática ponderada das médias residuais locais; MAX multiplica o módulo da média local pela raiz do número de seções. MAX não é escore-z e seu valor-p global não pertence ao local que atinge o máximo.

São 4.999 permutações por referência, PCG64, semente `20261029` e subfluxos por realização, independentes dos processos. Os quatro testes primários detectam concentração após Holm, com p ajustado 0,0008. Com preferência inicial controlada, RMS observado é 0,66569 ponto percentual, diante da média simulada de 0,51499; MAX é 20,91395 pontos percentuais vezes raiz de seção. Isso demonstra associação além da referência de alocação definida, sem determinar se o número ou a magnitude nacional dos extremos é natural. Referências constantes exigem prova, e uma ausência de testemunha de variação não é automaticamente classificada como não detecção.

As sensibilidades, predefinidas, alteram uma definição por vez: faixas iniciais de 2,5/10 pontos, igualdade exata de aptos, piso inicial de 100 votos dos finalistas e locais-alvo com dez seções. Uma implementação independente relê os originais e reconstrói todas as tabelas e sensibilidades; confere ranks e Holm dos escores retidos e repete as atribuições 0 e 1 das duas referências. As 9.998 atribuições completas não são integralmente geradas uma segunda vez. As 32.563.485 verificações de integridade não são observações estatísticas independentes.

Após os resultados, uma extração contextual separada seleciona automaticamente todas as prioridades estritas e todas as seções dos locais que atingem MAX, incluindo empates. Relê o detalhe original, confere chaves, quantidades, linhas e hashes e publica 18 registros de nove seções, sem novos testes ou alteração dos cálculos. Os nomes originais COLÉGIO EQUIPE em São Paulo e ISEP em Porto acrescentam contexto documental, mas não explicam a causa dos sinais ou caracterizam os indivíduos. A seleção e sua natureza posterior ficam registradas em manifesto próprio.

A nota da H5 é 6/10, como apoio parcial à hipótese estatística: contrastes localizados e concentração foram encontrados, com cobertura limitada e alcance formal distinto da naturalidade de todos os extremos. Não é probabilidade de manipulação. Fontes e artefatos anteriores são preservados; código, evidências completas comprimidas, quatro figuras e Markdown ficam na pasta da H5. Os grandes caches permanecem em `.work/`, ignorado pelo Git.
