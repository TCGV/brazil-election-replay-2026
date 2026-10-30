# Etapa 3 — Testes de hipóteses

[English (US)](README.md) · **Português (Brasil)** · [Etapas do estudo](../README.md)

Cada hipótese tem uma pasta própria com relatório principal em Markdown, código de análise, testes e evidências. A avaliação ocorre uma hipótese por vez. O resultado pode identificar uma inconsistência, não encontrar um sinal nas verificações definidas ou permanecer inconclusivo; não se pressupõe a refutação.

| ID | Hipótese | Dificuldade de identificação | Avaliação (0–10) | Situação e resultado |
|---|---|---|---|---|
| **H1** | Inconsistências entre votos, comparecimento e eleitorado; duplicação de registros | Baixa | **1/10** | [Concluída: sinais centrais ausentes, com ressalvas na identidade de eleitorado](01-accounting-integrity/REPORT.pt-BR.md#avaliação-na-escala) |
| **H2** | Combinações atípicas de comparecimento e concentração de votos em seções comparáveis | Média | **6/10** | [Concluída: apoio parcial à associação estatística, sem causa artificial demonstrada](02-turnout-concentration/REPORT.pt-BR.md#avaliação-na-escala) |
| **H3** | Repetição excessiva de resultados completos entre seções | Média | **5/10 — inconclusiva** | [Concluída: não detecção local com suporte informativo limitado](03-result-repetition/REPORT.pt-BR.md#avaliação-na-escala) |
| **H4** | Evolução temporal não explicada pela composição, incluindo tendência residual sutil e gradual | Alta | **6/10** | [Concluída: apoio parcial a padrões residuais; controle por local atenua os desvios](04-temporal-residuals/REPORT.pt-BR.md#avaliação-na-escala) |
| **H5** | Mudanças excepcionalmente concentradas em determinadas seções entre turnos | Alta | **6/10** | [Concluída: contrastes locais e concentração entre locais; triagem com cobertura parcial](05-inter-round-localization/REPORT.pt-BR.md#avaliação-na-escala) |
| **H6** | Associação excepcional entre redução da abstenção e ganho de um finalista | Alta | **6/10** | [Concluída: associação condicional positiva e fraca, sem causa artificial demonstrada](06-turnout-gains/REPORT.pt-BR.md#avaliação-na-escala) |
| **H7** | Redistribuição entre turnos com regularidades ou rupturas pouco plausíveis | Muito alta | **6/10** | [Concluída: sem detecção de excesso de prevalência/uniformidade; contrastes entre perfis detectados](07-inter-round-regularity/REPORT.pt-BR.md#avaliação-na-escala) |

A dificuldade indica o esforço para detectar e interpretar um sinal com os dados disponíveis, não a probabilidade de manipulação. Consistência interna não autentica as fontes de forma independente nem revela transferências individuais de voto.

## Escala de avaliação

**0 — Integralmente refutada → 10 — Integralmente confirmada.** A nota é uma síntese qualitativa e ordinal do apoio à hipótese estatística descrita, considerando resultados, cobertura e limitações dos dois turnos. Foi atribuída após as análises; não é uma estatística calculada pelos protocolos, probabilidade de manipulação, percentual de votos suspeitos ou conversão de valor-p.

| Nota | Leitura |
|---|---|
| 0 | Integralmente refutada no escopo verificável definido |
| 1–2 | Predominantemente refutada, com ressalvas ou exceções delimitadas |
| 3–4 | Apoio fraco ou pouco consistente à hipótese |
| 5 | Inconclusiva: informação insuficiente para posicionar a conclusão em uma das direções |
| 6–7 | Apoio parcial à hipótese estatística, com limitações relevantes |
| 8–9 | Apoio forte à hipótese estatística no escopo analisado |
| 10 | Integralmente confirmada no escopo verificável definido |

**5 não significa 50% de chance nem evidência positiva de anomalia.** A nota sempre acompanha sua justificativa; diferenças entre notas não têm magnitude estatística comparável e não devem ser somadas ou usadas em uma média de “risco”. As hipóteses não avaliadas ficam sem nota. Os extremos 0 e 10 se referem à hipótese e ao recorte testado, sem certificar a autenticidade externa das fontes ou atribuir uma causa aos padrões.

Na H1, a nota abrange também a identidade adicional entre aptos, comparecimento e abstenções: nenhum sinal central aprovado apareceu, mas restaram 41 exceções por turno nessa relação. Na H2, as associações previstas aparecem em parte dos testes e alguns contrastes persistem localmente, sem demonstrar origem artificial. Na H3, a referência não detecta excesso, mas seu suporte informativo restrito impede concluir sobre a hipótese ampla. Na H4, sinais graduais e acumulados persistem na referência por local no primeiro turno, com magnitudes pequenas; no segundo, não há detecção nessa referência após Holm. Na H5, há dois contrastes descritivos grandes entre as seções comparáveis e concentração formal entre locais, sem testar a naturalidade da distribuição marginal de mudanças. Na H6, há associação positiva e fraca entre aumento do comparecimento e mudança relativa para Lula, com quatro rejeições após Holm; a referência não distingue mobilização legítima de origem artificial nem identifica fluxos de eleitores. Na H7, a frequência bruta de 97,1280% por crescimento relativo é descritiva; os testes de alocação não detectam excesso de prevalência direcional ou uniformidade nas caudas previstas, mas detectam contrastes entre perfis iniciais adjacentes, sem causa artificial demonstrada. Cada relatório detalha a respectiva justificativa.

## Relatórios e reprodução

Comece pelo [relatório da H1](01-accounting-integrity/REPORT.pt-BR.md). As [instruções de reprodução](01-accounting-integrity/README.md) usam apenas a biblioteca padrão do Python e os dois CSVs nacionais originais; não exigem a base já processada do replay nem as bibliotecas numéricas da etapa 2.

O [relatório da H2](02-turnout-concentration/REPORT.pt-BR.md) acrescenta comparações dentro de município, zona eleitoral e faixas de aptos por seção, incluindo todos os candidatos dos dois turnos. Seu [protocolo](02-turnout-concentration/METHOD.pt-BR.md) distingue casos descritivos de uma referência formal de independência condicional. A H2 utiliza NumPy e Matplotlib, explicita a cobertura parcial dos pares e não equipara associação estatística a manipulação.

O [relatório da H3](03-result-repetition/REPORT.pt-BR.md) inventaria resultados completos iguais em chaves de seções distintas e acrescenta uma referência local de emparelhamento entre blocos. Seu [protocolo](03-result-repetition/METHOD.pt-BR.md) usa momentos racionais exatos e limites conservadores de Cantelli, explicita o suporte informativo extremamente restrito no primeiro turno e não certifica naturalidade. As tabelas maiores estão disponíveis em CSV comprimido.

O [relatório da H4](04-temporal-residuals/REPORT.pt-BR.md) examina tendências graduais, excursões acumuladas e contribuições abruptas por minuto após considerar a composição por zona, local de votação e porte da seção. Seu [protocolo](04-temporal-residuals/METHOD.pt-BR.md) define duas referências, 4.999 permutações por turno/referência e Holm na família fixa de 90 testes de todas as candidaturas. O relatório distingue magnitude, significância e cobertura, sem atribuir causa artificial aos sinais; os [comandos de reprodução](04-temporal-residuals/README.md) preservam as evidências publicadas.

O [relatório da H5](05-inter-round-localization/REPORT.pt-BR.md) pareia as mesmas chaves de seção entre os turnos e separa a mudança condicional entre finalistas do efeito da saída das demais candidaturas. Seu [protocolo](05-inter-round-localization/METHOD.pt-BR.md) distingue a triagem com pares locais de uma referência formal de concentração entre locais, com 4.999 permutações por referência e Holm em quatro testes. As permutações preservam as mudanças observadas: o teste não determina se sua quantidade ou magnitude nacional é natural. A [reprodução](05-inter-round-localization/README.md) inclui as evidências completas comprimidas.

O [relatório da H6](06-turnout-gains/REPORT.pt-BR.md) separa o saldo de comparecimento, o ganho de votos e a mudança de preferência entre finalistas. Seu [protocolo](06-turnout-gains/METHOD.pt-BR.md) define correlações lineares e por postos em duas referências com controles iniciais, 4.999 permutações por referência e Holm em quatro testes. O balanço e a decomposição são aritméticos, sem atribuir os ganhos a eleitores individuais. A [reprodução](06-turnout-gains/README.md) inclui todas as seções, 14 sensibilidades descritivas e os 9.998 escores simulados publicados.

O [relatório da H7](07-inter-round-regularity/REPORT.pt-BR.md) distingue ganho absoluto, ganho de participação nominal e crescimento relativo no censo municipal. Seu [protocolo da execução](07-inter-round-regularity/METHOD.pt-BR.md) define duas referências de alocação territorial, por seções e por blocos de locais, e dez testes de prevalência, dispersão residual baixa e contrastes entre perfis iniciais adjacentes, com Holm. A [revisão vigente](07-inter-round-regularity/METHOD-REVISION.pt-BR.md) retira o percentual ilustrativo como régua e fundamenta a interpretação nas referências estatísticas, sem presumir divisão de sinais em 50%/50% ou determinar a raridade global dos ganhos. A [reprodução](07-inter-round-regularity/README.md) inclui as evidências completas e os 9.998 conjuntos de escores simulados.
