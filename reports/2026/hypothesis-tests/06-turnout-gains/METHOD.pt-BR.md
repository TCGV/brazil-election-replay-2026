# Protocolo da H6 — Comparecimento e ganhos dos finalistas

[Relatório principal](REPORT.pt-BR.md) · [Reprodução](README.md)

Este protocolo é fixado antes de calcular as associações da H6. Os totais nacionais, o esquema e a coorte pareada já são conhecidos das análises anteriores. Não é um pré-registro externo. Seu hash será gravado no manifesto; mudanças posteriores exigem identificação explícita.

## Hipótese e pergunta verificável

**H6:** a redução da abstenção se associa de maneira excepcional ao ganho de um dos finalistas entre os turnos, além das características iniciais observadas das seções. **Dificuldade de identificação: alta.**

A pergunta formal é de **associação condicional**, não de causalidade ou autenticidade: seções com maior aumento da taxa de comparecimento também apresentam maior mudança de preferência entre finalistas, depois de considerar a composição inicial definida abaixo? Uma relação pode resultar de mobilização, campanha, composição não observada, erro de medida ou outros mecanismos legítimos. A referência estatística não é um modelo completo de uma eleição natural.

## Fontes, pareamento e coorte

Reler os CSVs nacionais originais de detalhe e votação, com hashes e totais conferidos contra os manifestos anteriores. Não depender de uma base de replay ou dos resultados numéricos da H5. O carregador reutiliza código identificado da H5, em cópia local, preservando reconciliação das categorias e rejeição de duplicações.

Parear por `UF + município + zona + seção`, com exatamente uma eleição presidencial por turno; publicar ausências e ambiguidades, sem fabricar contrapartes. Para comparabilidade, aplicar a coorte da H5, nesta ordem de exclusões exclusivas: situação não instalada/anulada em qualquer turno; aptos abaixo de 50; comparecimento não positivo; nominais abaixo de 50; menos de 50 votos somados dos finalistas no primeiro turno; local ausente; local alterado; razão simétrica de aptos acima de 1,25. Publicar os denominadores por UF e Brasil. Exigir ainda `aptos = comparecimento + abstenções` na coorte; falha interrompe a análise, sem exclusão silenciosa.

O piso de finalistas estabiliza a medida de preferência. Chave e local iguais não asseguram que as mesmas pessoas votaram. A análise primária admite pequenas mudanças de aptos e usa taxas com o denominador de cada turno; uma sensibilidade exige aptos idênticos. Só com aptos constantes a redução da contagem de abstenções equivale ao aumento da contagem de comparecimento.

## Medidas e decomposição aritmética

Para a seção `i` e turno `t`, sejam `A` aptos, `T` comparecimento, `V13` e `V22` votos dos finalistas, `N` todos os nominais, `F = V13 + V22` e `O = N - F`.

```text
x = 100 * (T2/A2 - T1/A1)
q_t = V13_t / F_t
y = 100 * (q2 - q1)
```

`x` é o aumento do comparecimento em pontos percentuais do eleitorado; `y` é a mudança, em pontos percentuais, da participação de Lula **condicional aos dois finalistas**. Para Flávio Bolsonaro, essa mudança é exatamente `-y`: não duplicar os testes complementares. Ganho de votos absolutos, mudança sobre todos os nominais e mudança entre finalistas são medidas diferentes. A saída das outras candidaturas pode aumentar os votos dos dois finalistas sem que mude a preferência condicional entre eles.

Publicar os totais originais dos dois turnos e a identidade de contagens:

```text
ΔV13 + ΔV22 = ΔT - Δ(O + brancos + nulos + legenda + separados)
```

A identidade é um balanço, não uma origem individual dos votos. O aumento líquido de comparecimento não mede quantas pessoas entraram: pode haver entradas e saídas simultâneas.

Publicar também, por candidato e seção, a decomposição simétrica exata, com `t=T/A`, `s=Vc/T` e `v=Vc/A`:

```text
100*Δv = 100*((s1+s2)/2)*Δt + 100*((t1+t2)/2)*Δs
```

Os termos são denominados **componente aritmético de comparecimento** e **componente aritmético de composição do voto**. Não são estimativas de transferência individual, de efeito causal da mobilização ou de votos artificiais. A simetria evita privilegiar o primeiro ou o segundo turno como base. Publicar médias simples por seção e somas ponderadas por `A1`, identificadas em suas unidades; quando `A1 != A2`, estas últimas são equivalentes com o eleitorado inicial, não ganhos observados de contagens. O balanço nacional de contagens permanece separado.

## Duas referências condicionais

Definir antes dos resultados:

1. **`zone_baseline`**: UF, município, zona, faixa de aptos do primeiro turno com razão 1,25, faixa de comparecimento inicial `T1/A1` de 5 pontos, faixa de preferência inicial `V13_1/F1` de 5 pontos e faixa de outras candidaturas `O1/T1` de 5 pontos.
2. **`place_baseline`**: os mesmos campos, acrescentando local de votação.

Faixa de aptos: `floor(log(A1)/log(1,25))`. Para proporções, usar inteiros `min(b-1, floor(b*numerador/denominador))`, com `b=20`; valores de 100% ficam na última faixa. A variável de outras candidaturas usa todos os comparecentes como denominador. Não selecionar a referência que produzir o resultado desejado.

Cada referência conserva somente estratos com pelo menos duas seções e **variação exata em x e em y**. Detectar igualdade por razões inteiras reduzidas, não ruído de ponto flutuante. Publicar seções e estratos sem suporte, unitários, com variação só em uma medida e informativos, por UF. Seções fora do suporte não recebem classificação de normalidade. A seleção por variação marginal é invariante às permutações.

## Estatísticas formais

Em cada estrato informativo, centralizar `x` e `y` pelas respectivas médias simples. Com `rx` e `ry` residuais, usar a correlação agrupada:

```text
rho = sum(rx*ry) / sqrt(sum(rx^2)*sum(ry^2))
beta = sum(rx*ry) / sum(rx^2)
```

O escore formal linear é `abs(rho)`, de duas caudas. `beta` é apenas uma magnitude descritiva em pontos de preferência entre finalistas por ponto de comparecimento; não é a fração dos novos votantes que escolheu um candidato. Os pesos são iguais por seção, sem ajuste de independência de eleitores.

Como proteção a extremos e para associação monotônica, calcular uma segunda correlação com **postos médios dentro de cada estrato**, para `x` e `y`, centralizados do mesmo modo. Empates são definidos por igualdade racional exata. Seu escore é o módulo da correlação agrupada dos postos, não uma média das correlações de cada estrato nem a correlação de postos nacional. Os dois escores têm dependência e não contam como evidências independentes.

## Permutações, suporte e multiplicidade

Manter a trajetória de comparecimento `(A1,T1,A2,T2,x)` nos slots e permutar a trajetória de preferência `(V13_1,F1,V13_2,F2,y)` como um bloco dentro de cada estrato informativo. Isso conserva as distribuições marginais e o pareamento interno de cada trajetória. **Não constrói boletins ou uma eleição sintética fisicamente viável:** desacopla duas trajetórias observadas para testar a referência de independência condicional. As faixas iniciais fixas são preservadas, mas os valores contínuos dentro delas não são iguais.

Usar 4.999 atribuições por referência, NumPy/PCG64 e semente-base `20261029`, com `SeedSequence([20261029, 6, model_id], spawn_key=(rep,))`, `model_id=0/1`, `rep=0..4998`. Ordenar estratos lexicograficamente e membros pela chave física; agrupar estratos por tamanho crescente e aplicar `rng.permuted(bucket, axis=1)`. A mesma atribuição calcula os dois escores, inclusive os postos da trajetória permutada. Guardar escores completos, hashes de atribuições selecionadas e fingerprints de código/método/fontes; a divisão em processos não altera a realização.

Valores-p: `(1 + numero_de_escores_simulados >= observado - 1e-12)/(4999+1)`, com tolerância na escala adimensional da correlação. Resolução mínima 0,0002; nunca publicar p zero. Usar Holm a 5% na família fixa de **quatro testes**, dois escores por duas referências. Publicar também as correlações com sinal, inclinações, número de estratos/seções, média e quantis de 2,5% e 97,5% dos módulos simulados e excedências. Quantis são referências condicionais, não intervalos de confiança da eleição. Não gerar valores-p por UF, seção, candidato ou sensibilidade.

Confirmar que cada módulo pode variar por atribuições testemunhas com escores distintos. Sem testemunha, enumerar órbitas pequenas de até 40.320 atribuições; provar constância ou interromper com diagnóstico quando não for possível decidir. Constância comprovada implica teste não aplicável, com motivo e p=1 apenas internamente no ajuste conservador. Não confundir correlação assinada variável com módulo variável.

## Evidência descritiva e sensibilidades fixas

Publicar todas as seções pareadas com denominadores, ganhos, medidas e suporte. Por Brasil, UF e região, apresentar contagens de aptos/comparecimento/votos por turno, mudanças, correlações brutas e condicionais, sem decisões formais adicionais. Tabelas por faixas fixas de `x` (passos de 2 pontos, extremos abertos a partir de -10/+10) mostram número de seções, médias de `y`, ganhos e componentes; são associações agregadas, não fluxos de pessoas.

Recalcular descritivamente ambas as referências, sem novas permutações ou valores-p, alterando uma definição por vez: faixas iniciais de 2,5 pontos; faixas de 10 pontos; aptos exatamente iguais; pelo menos 100 votos dos finalistas no primeiro turno; apenas território nacional; e desfecho `100*q2` em vez da mudança `y` (mantendo os mesmos controles iniciais). Essa última comparação expõe parte da dependência com a medida de base; não elimina todo erro de medida. Incluindo as duas referências primárias, são 14 linhas de sensibilidade.

Os controles por faixas não removem toda heterogeneidade contínua, regressão à média ou relações de amostragem entre taxas medidas nas mesmas contagens. Não há hipótese de eleitores independentes nem teste binomial. Um movimento uniforme de um estrato é condicionado para fora; a associação entre médias de estratos fica fora do teste. Comparar referência por zona e por local pode mostrar atenuação, sem identificar causalmente seu motivo.

## Validação, publicação e interpretação

Testes artificiais cobrem pareamento, exclusões, identidades, decomposição simétrica, denominadores distintos, saída de outras candidaturas, empate racional, fronteiras de faixa, correlação linear/por postos, movimentos sem mudança de preferência, relação positiva e negativa, controle por estrato, preservação das trajetórias, escores constantes e enumeração finita. Uma implementação independente relê as fontes, reconstrói coorte, medidas, grupos e todas as tabelas numéricas e confere ao menos as atribuições 0 e 1 de cada referência. Informar separadamente os resultados de todas as simulações auditados a partir dos escores guardados e as atribuições efetivamente repetidas.

Código, relatório Markdown, testes, CSVs completos comprimidos, gráficos e manifestos ficam nesta pasta. Caches privados ficam em `.work/`, ignorado pelo Git. Lula usa vermelho e Flávio Bolsonaro azul; medidas simétricas podem usar cores neutras. Preservar as fontes e as entregas anteriores.

Rejeitar independência condicional revela uma associação no recorte definido; não demonstra manipulação, origem dos votos ou anormalidade frente a todos os mecanismos legítimos. Não rejeitar não certifica naturalidade. A continuidade dos hashes não autentica externamente os arquivos. A nota de 0 a 10 será uma síntese ordinal justificada após os resultados, conforme a rubrica do índice, sem conversão de valor-p ou probabilidade de fraude.
