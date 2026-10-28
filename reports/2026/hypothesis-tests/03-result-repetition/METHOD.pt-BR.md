# Protocolo da H3 — Repetição de resultados completos

[Relatório principal](REPORT.pt-BR.md) · [Reprodução](README.md)

Protocolo definido antes de calcular as frequências de repetição da H3 nesta entrega. A escolha utilizou o esquema e a cobertura já conhecidos das etapas anteriores, sem consultar essas frequências. Não constitui pré-registro externo. O manifesto registra seu hash.

## Hipótese e unidade

**Hipótese:** combinações completas de votos por candidato, brancos, nulos e comparecimento se repetem entre seções com frequência superior à esperada para seu contexto. **Dificuldade de identificação: média.**

H1 procurou repetição da chave de uma mesma seção. H3 procura valores iguais em **chaves distintas**. Cada turno é analisado separadamente, com todas as candidaturas nominais existentes nele: 13 no primeiro, duas no segundo. Não se procuram apenas os dois candidatos finalistas no primeiro turno.

## Inventário exaustivo

Assinatura principal: vetor inteiro de todos os votos nominais, brancos, nulos, legenda, anulados em separado e comparecimento. O comparecimento é redundante após a reconciliação, mas permanece explícito. Não arredondar percentuais, não usar apenas o vencedor e não fundir turnos. Ausência de linha de uma candidatura existente pode representar zero após reconciliação; campo numérico ausente não vira zero.

Para cada assinatura com multiplicidade `m ≥ 2`, registrar membros e **pares não ordenados `m*(m−1)/2`**. Esses pares se sobrepõem quando um grupo tem mais de duas seções. Não são votos adicionais nem eventos independentes.

Inventariar as populações abaixo e informar grupos, seções envolvidas, pares, maior multiplicidade e distribuição por comparecimento:

- Todas as linhas de detalhe, sem omitir seções sem atividade.
- Elegíveis: instaladas, não anuladas, pelo menos 50 aptos, comparecimento positivo e pelo menos 50 nominais.
- Pequenas positivas: instaladas e não anuladas, comparecimento positivo, mas aptos ou nominais abaixo de 50.
- Sem atividade: comparecimento zero.
- Outros registros positivos excluídos pela situação, se houver.

“Todas” sobrepõe as demais populações; não deve ser somada a elas. Uma assinatura estendida acrescenta aptos e abstenções como diagnóstico descritivo. O inventário nacional inclui coincidências entre localidades; elas não são automaticamente cobertas pelo teste local.

## Referência primária por blocos

Estrato primário: **UF + município + zona + total nominal exato + faixa de aptos** `floor(log(aptos)/log(1,25))`, dentro do mesmo turno e entre elegíveis. O total nominal exato preserva a soma do vetor de candidatos. Não aplicar mínimo arbitrário de 30 seções: a referência é finita e exata; informar explicitamente estratos unitários, estratos com pares e estratos sem variação possível.

Separar cada resultado em `A`, o vetor completo dos candidatos, e `B`, o comparecimento e as categorias especiais. A referência permite redistribuir **A inteiro** entre seções do mesmo estrato, mantendo B e o cadastro fixos. Preserva todas as somas, o eleitorado e comparecimento de cada seção, a distribuição local dos vetores nominais e a frequência de cada bloco. Embaralhar linhas inteiras seria inútil, pois preservaria as repetições; embaralhar contagens isoladas quebraria as identidades contábeis.

A estatística `X` é a soma dos pares com assinatura completa igual **dentro dos estratos**. Não usar os pares nacionais entre estratos nessa estatística. Em um estrato com `n` seções, `P_A` pares iguais em A e `P_B` pares iguais em B, a expectativa é `P_A*P_B/comb(n,2)`. Estratos unitários contribuem zero.

Calcular expectativa e variância exatas por contagem de pares que compartilham zero ou uma seção, com frações racionais. A implementação e os testes documentam a fórmula e a conferem por enumeração de pequenas permutações. Somar os momentos dos estratos sob redistribuições independentes.

## Decisão conservadora, sem simulação

Com média `E` e variância `V` do total, usar o limite unilateral de Cantelli:

```text
limite_p = V / (V + (X−E)^2), se X > E
limite_p = 1, se X ≤ E
```

Esse é um **limite superior conservador para a probabilidade de cauda**, não um valor-p exato. Quando V=0, a referência é constante: exigir X=E e classificar como não aplicável. Não interpretar ausência de variação como evidência favorável à naturalidade.

Há dois testes primários, um por turno. Aplicar Holm a 5% na família fixa de dois; referências não aplicáveis recebem 1 apenas no cálculo interno do ajuste. Divulgar X, E, V, diferença e limites antes/depois do ajuste. Sem Monte Carlo ou semente, não há erro de simulação; a contrapartida é menor poder que uma distribuição exata completa.

## Sensibilidades descritivas

Alterar uma definição por vez: retirar a faixa de aptos; retirar a zona, preservando município/faixa; retirar zona e faixa; ampliar a razão da faixa para 1,5; elevar o mínimo nominal para 100. Manter sempre total nominal exato e contexto municipal. Publicar cobertura, pares observados, expectativa e variância, sem escolher novos valores-p alternativos.

## O que pode e não pode concluir

A referência pergunta se o **emparelhamento entre os dois blocos** produz repetições além do admitido pela redistribuição local. Não testa a frequência marginal do próprio vetor de candidatos, que fica preservada. Uma alteração que reproduza apenas um bloco ou domine um estrato pode escapar. Relações legítimas entre preferência, comparecimento e votos inválidos também podem violar a referência.

Assim, coincidências não demonstram cópia, rejeição não demonstra manipulação e não detecção não certifica naturalidade. Estratos pequenos, constantes e pares entre localidades têm alcance explicitamente limitado. Nenhum número de pares será convertido em estimativa de votos artificiais.

Uma segunda implementação relerá os originais e verificará assinaturas, membros, grupos, cobertura, momentos racionais e ajuste. Testes artificiais devem incluir empates, seções zeradas, vetores distintos com percentuais iguais, repetição em chaves distintas, casos degenerados, um sinal inserido que preserve as identidades contábeis e exemplos de repetição que a referência condiciona para fora do teste.
