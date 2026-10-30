# H7 — Revisão da interpretação e apresentação

[Relatório principal](REPORT.pt-BR.md) · [Protocolo original de execução](METHOD.pt-BR.md) · [Reprodução](README.md)

Esta revisão substitui o enquadramento descritivo da publicação inicial, no commit `c632074dca55adf984f4ea8f2be4e43dd8e674a2`. O percentual mencionado como exemplo na conversa não constitui referência de avaliação. Não se adota um corte percentual arbitrário para classificar o resultado.

## Critério de interpretação

As frequências municipais são descrições do arquivo. No universo bruto, **5.411 de 5.571 municípios (97,1280%)** apresentam crescimento relativo maior para Lula. Esse percentual, isoladamente, não determina raridade estatística nem identifica efeito de campanha ou outra causa.

A comparação formal usa outra população: a coorte pareada dos **5.564 municípios-alvo**, com prevalência condicional de **97,1064%**. Nas 4.999 alocações de cada referência, as médias desse escore são **99,2273% por seção** e **98,8869% por bloco de local**. Em ambas, todas as realizações têm escore superior ao observado; o teste previsto de excesso na cauda superior tem **p ajustado por Holm = 1**. Portanto, não há detecção de excesso de prevalência **nessas referências**. Não se testa uma cauda adicional após conhecer os resultados.

As referências preservam as trajetórias observadas e examinam sua distribuição territorial condicionada à composição inicial. Elas não fornecem a probabilidade de um resultado nacional como esse em uma eleição natural, não demonstram sua origem e não estimam efeitos de campanha. A qualificação estatística deve sempre identificar a população, a estatística, a referência e a cauda do teste.

Os contrastes máximos entre perfis iniciais continuam detectados, com **p ajustado = 0,002** em cada referência. Isso sustenta a avaliação ordinal de **6/10** já justificada no relatório; a nota não é medida estatística de intensidade nem probabilidade de manipulação. Nenhum resultado numérico ou teste foi alterado nesta revisão.

## Continuidade da evidência

O protocolo original, seu hash, o código de cálculo e validação e as evidências numéricas permanecem como registro da execução realizada. As menções ao exemplo e os campos históricos `reaches99_*` das tabelas e do código ficam **sem função avaliativa**: não entram nos cinco escores, nas simulações, nos valores-p, em Holm ou na nota. Sua presença documenta a publicação inicial e não estabelece uma régua vigente.

A revisão retira as comparações com esse exemplo do relatório, dos índices, das instruções de leitura e do gráfico descritivo. Mantém percentuais efetivamente medidos, inclusive quando seu valor numérico é superior ao exemplo. O gerador de gráficos verifica as frações pelos numeradores e denominadores, sem consultar os campos históricos. O manifesto dos gráficos registra o hash desta revisão. A [verificação da revisão](evidence/revision-validation.json) documenta a continuidade dos cálculos e as conferências de apresentação.
