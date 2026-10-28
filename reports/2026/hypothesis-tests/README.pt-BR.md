# Etapa 3 — Testes de hipóteses

[English (US)](README.md) · **Português (Brasil)** · [Etapas do estudo](../README.md)

Cada hipótese tem uma pasta própria com relatório principal em Markdown, código de análise, testes e evidências. A avaliação ocorre uma hipótese por vez. O resultado pode identificar uma inconsistência, não encontrar um sinal nas verificações definidas ou permanecer inconclusivo; não se pressupõe a refutação.

| ID | Hipótese | Dificuldade de identificação | Situação |
|---|---|---|---|
| **H1** | Inconsistências entre votos, comparecimento e eleitorado; duplicação de registros | Baixa | [Concluída, com exceções contábeis documentadas](01-accounting-integrity/REPORT.pt-BR.md) |
| **H2** | Combinações atípicas de comparecimento e concentração de votos em seções comparáveis | Média | [Concluída: triagem local e referência de associação](02-turnout-concentration/REPORT.pt-BR.md) |
| H3 | Repetição excessiva de resultados completos entre seções | Média | Não iniciada |
| H4 | Evolução temporal não explicada pela composição, incluindo tendência residual sutil e gradual | Alta | Não iniciada |
| H5 | Mudanças excepcionalmente concentradas em determinadas seções entre turnos | Alta | Não iniciada |
| H6 | Associação excepcional entre redução da abstenção e ganho de um finalista | Alta | Não iniciada |
| H7 | Redistribuição entre turnos com regularidades ou rupturas pouco plausíveis | Muito alta | Não iniciada |

A dificuldade indica o esforço para detectar e interpretar um sinal com os dados disponíveis, não a probabilidade de manipulação. Consistência interna não autentica as fontes de forma independente nem revela transferências individuais de voto.

Comece pelo [relatório da H1](01-accounting-integrity/REPORT.pt-BR.md). As [instruções de reprodução](01-accounting-integrity/README.md) usam apenas a biblioteca padrão do Python e os dois CSVs nacionais originais; não exigem a base já processada do replay nem as bibliotecas numéricas da etapa 2.

O [relatório da H2](02-turnout-concentration/REPORT.pt-BR.md) acrescenta comparações dentro de município, zona eleitoral e faixas de aptos por seção, incluindo todos os candidatos dos dois turnos. Seu [protocolo](02-turnout-concentration/METHOD.pt-BR.md) distingue casos descritivos de uma referência formal de independência condicional. A H2 utiliza NumPy e Matplotlib, explicita a cobertura parcial dos pares e não equipara associação estatística a manipulação. As hipóteses 3–7 não foram analisadas.
