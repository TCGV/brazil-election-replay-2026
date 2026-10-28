# Etapa 3 — Testes de hipóteses

[English (US)](README.md) · **Português (Brasil)** · [Etapas do estudo](../README.md)

Cada hipótese tem uma pasta própria com relatório principal em Markdown, código de análise, testes e evidências. A avaliação ocorre uma hipótese por vez. O resultado pode identificar uma inconsistência, não encontrar um sinal nas verificações definidas ou permanecer inconclusivo; não se pressupõe a refutação.

| ID | Hipótese | Dificuldade de identificação | Avaliação (0–10) | Situação e resultado |
|---|---|---|---|---|
| **H1** | Inconsistências entre votos, comparecimento e eleitorado; duplicação de registros | Baixa | **1/10** | [Concluída: sinais centrais ausentes, com ressalvas na identidade de eleitorado](01-accounting-integrity/REPORT.pt-BR.md#avaliação-na-escala) |
| **H2** | Combinações atípicas de comparecimento e concentração de votos em seções comparáveis | Média | **6/10** | [Concluída: apoio parcial à associação estatística, sem causa artificial demonstrada](02-turnout-concentration/REPORT.pt-BR.md#avaliação-na-escala) |
| **H3** | Repetição excessiva de resultados completos entre seções | Média | **5/10 — inconclusiva** | [Concluída: não detecção local com suporte informativo limitado](03-result-repetition/REPORT.pt-BR.md#avaliação-na-escala) |
| H4 | Evolução temporal não explicada pela composição, incluindo tendência residual sutil e gradual | Alta | — | Não iniciada |
| H5 | Mudanças excepcionalmente concentradas em determinadas seções entre turnos | Alta | — | Não iniciada |
| H6 | Associação excepcional entre redução da abstenção e ganho de um finalista | Alta | — | Não iniciada |
| H7 | Redistribuição entre turnos com regularidades ou rupturas pouco plausíveis | Muito alta | — | Não iniciada |

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

Na H1, a nota abrange também a identidade adicional entre aptos, comparecimento e abstenções: nenhum sinal central aprovado apareceu, mas restaram 41 exceções por turno nessa relação. Na H2, as associações previstas aparecem em parte dos testes e alguns contrastes persistem localmente, sem demonstrar origem artificial. Na H3, a referência não detecta excesso, mas seu suporte informativo restrito impede concluir sobre a hipótese ampla. Cada relatório detalha a respectiva justificativa.

## Relatórios e reprodução

Comece pelo [relatório da H1](01-accounting-integrity/REPORT.pt-BR.md). As [instruções de reprodução](01-accounting-integrity/README.md) usam apenas a biblioteca padrão do Python e os dois CSVs nacionais originais; não exigem a base já processada do replay nem as bibliotecas numéricas da etapa 2.

O [relatório da H2](02-turnout-concentration/REPORT.pt-BR.md) acrescenta comparações dentro de município, zona eleitoral e faixas de aptos por seção, incluindo todos os candidatos dos dois turnos. Seu [protocolo](02-turnout-concentration/METHOD.pt-BR.md) distingue casos descritivos de uma referência formal de independência condicional. A H2 utiliza NumPy e Matplotlib, explicita a cobertura parcial dos pares e não equipara associação estatística a manipulação.

O [relatório da H3](03-result-repetition/REPORT.pt-BR.md) inventaria resultados completos iguais em chaves de seções distintas e acrescenta uma referência local de emparelhamento entre blocos. Seu [protocolo](03-result-repetition/METHOD.pt-BR.md) usa momentos racionais exatos e limites conservadores de Cantelli, explicita o suporte informativo extremamente restrito no primeiro turno e não certifica naturalidade. As tabelas maiores estão disponíveis em CSV comprimido. As hipóteses 4–7 não foram analisadas.
