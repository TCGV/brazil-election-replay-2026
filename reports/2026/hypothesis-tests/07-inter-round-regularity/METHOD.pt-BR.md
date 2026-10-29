# Protocolo da H7 — Regularidade e contrastes da redistribuição entre turnos

[Relatório principal](REPORT.pt-BR.md) · [Reprodução](README.md)

Protocolo fixado antes dos cálculos municipais e testes da H7. Os totais nacionais, o esquema e as coortes das análises anteriores já são conhecidos. Não é pré-registro externo. Seu hash integra o manifesto; qualquer alteração posterior exige versão e justificativa explícitas.

## Hipótese e alcance verificável

**H7:** a redistribuição entre turnos apresenta regularidades ou contrastes abruptos além das referências de composição territorial definidas abaixo. **Dificuldade de identificação: muito alta.**

A análise separa um **censo da frequência de melhora municipal**, incluindo a afirmação hipotética de 99%, e testes de **alocação das trajetórias observadas entre municípios**. Os testes examinam prevalência direcional, dispersão residual excepcionalmente baixa e contrastes entre perfis iniciais adjacentes. Não modelam todos os mecanismos de uma eleição natural, nem identificam transferências individuais ou uma causa artificial.

## Fontes, unidades e coorte

Reler os dois CSVs nacionais originais, com hashes/totais conferidos contra os manifestos existentes, reconciliação das categorias e carregador local atribuído ao código anterior. A unicidade de detalhes é verificada diretamente; a de linhas de votação se apoia na auditoria contábil dos mesmos hashes, explicitamente. Não depender das tabelas numéricas das hipóteses anteriores.

Parear por `UF + município + zona + seção`, mantendo eleição/turno e linhas originais como procedência. Exigir uma eleição presidencial por turno, rejeitar ambiguidades e publicar chaves sem contraparte. Aplicar, em ordem, as exclusões exclusivas já utilizadas: seção não instalada/anulada; aptos abaixo de 50; comparecimento não positivo; nominais abaixo de 50; soma dos finalistas no primeiro turno abaixo de 50; local ausente; local alterado; razão simétrica de aptos acima de 1,25. Exigir a identidade de eleitorado e reconciliação das categorias em todos os pares incluídos; falha interrompe a análise, sem exclusão silenciosa.

O censo publica dois universos separados: **todos os registros municipais originais por turno** e **somas da mesma coorte de seções pareadas nos dois turnos**. A chave municipal é `UF + código de município`, não seu nome. Publicar presenças por turno, totais de seções, aptos, nominais, comparecimento, categorias, candidaturas e cobertura da coorte em relação ao bruto. Município sem coorte não desaparece do inventário; medidas sem denominador permanecem indefinidas.

Municípios brasileiros são as unidades das 27 UFs do território nacional. `ZZ` é publicado separadamente como **unidades cadastrais do exterior**, sem tratá-las como municípios brasileiros ou inferir país pelo nome. O censo mantém os registros sem atividade e as ressalvas contábeis originais; o recorte formal usa somente a coorte doméstica. Chave, local e aptos iguais não provam identidade das pessoas que votaram.

## O que significa “melhorou mais”

Sejam `Vc,t` os votos de cada finalista, `N_t` todos os nominais, `F_t=V13,t+V22,t` e `q_t=V13,t/F_t` no município. Publicar valores e diferenças para:

1. **Ganho absoluto:** `Gc=Vc,2−Vc,1`; comparar `G13−G22`.
2. **Ganho de participação nominal:** `Pc=100*(Vc,2/N2−Vc,1/N1)`; comparar `P13−P22`.
3. **Crescimento relativo ao próprio primeiro turno:** `Rc=100*(Vc,2/Vc,1−1)`; comparar `R13−R22`. Base inicial zero implica indefinido, sem pseudocontagem.
4. **Mudança condicional entre finalistas:** `d=100*(q2−q1)`. Para o candidato 22, a mudança é `−d`. Com ambas as bases iniciais positivas, `sign(R13−R22)=sign(d)`: não são evidências independentes.

Comparar sinais usando inteiros Python ou razões exatas; evitar overflow e empates criados por arredondamento. Publicar por Brasil, UF e região os números de unidades com vantagem em cada sentido, empates e indefinições, com denominadores exatos. Contar cada município com peso um; percentuais ponderados por votos são outro resumo, identificado separadamente. Conferir o limiar hipotético por `100*k >= 99*M`, sem arredondar 98,995% para 99%. Mostrar tanto a fração sobre todos os municípios do universo quanto sobre os que têm a medida definida.

Não usar binomial de sinais com probabilidade 1/2: não há motivo para esperar que os dois finalistas melhorem mais em metade dos municípios cada um. A composição inicial e a saída das demais candidaturas importam. Como o segundo turno só tem os finalistas, nas unidades com denominadores positivos valem, em proporções:

```text
P13/100 − P22/100 = 2*(q2−q1) + (1−F1/N1)*(2*q1−1)
G13 − G22 = 2*F2*(q2−q1) + (F2−F1)*(2*q1−1)
```

Essas identidades serão conferidas; descrevem aritmética, não a origem dos votos. Um percentual elevado de melhora pode existir sem um ajuste uniforme artificial. O aumento líquido de comparecimento não conta todas as pessoas que ingressaram, pois entradas e saídas podem ocorrer simultaneamente.

## Duas referências de alocação territorial

As duas referências permutam **trajetórias completas e inseparáveis dos dois turnos**, incluindo todas as contagens e denominadores. Os slots mantêm município de destino e características iniciais por faixas. São referências condicionais de alocação, não eleições sintéticas ou modelos causais da campanha.

- **`section` (ID 0):** a unidade é o par completo de uma seção. Estrato: UF, faixa de aptos iniciais com razão 1,25 e faixas de cinco pontos de `T1/A1`, `V13,1/F1` e `(N1−F1)/T1`.
- **`place_block` (ID 1):** a unidade é o bloco de **todas as seções da coorte do mesmo UF/município/zona/local**, com os dois turnos preservados. Usar os mesmos controles calculados pelas contagens agregadas do bloco. O bloco nunca é desmontado, preservando a dependência interna observada.

Faixa de aptos: `floor(log(A1)/log(1,25))`. Faixas de proporções: `min(b−1, floor(b*numerador/denominador))`, com `b=20`, por inteiros. Permutar somente estratos que contêm pelo menos dois municípios de origem; permutações inteiramente dentro de um município não alteram os agregados e são omitidas. Não filtrar estratos pelo sinal observado das mudanças.

Na referência por seção, os números de seções por município ficam fixos. Na de blocos, os números de slots de locais ficam fixos, mas quantidades de seções e totais municipais podem mudar: devem ser recalculados em cada realização. Mesmo dentro de faixas, os totais iniciais municipais não são preservados exatamente. A comparação entre referências muda a unidade de alocação, os controles agregados e a cobertura; não isola causalmente a dependência local.

Os alvos são municípios com pelo menos **cinco seções da coorte original doméstica**. Esse conjunto e seus códigos ficam fixos. Municípios abaixo do piso continuam no censo e como destinos/doadores das permutações, mas não nos escores. Após permutar blocos, não redefinir alvos pelo novo número de seções. Publicar suporte estrutural por estrato, unidade e município; possibilidade de troca não garante variabilidade de cada escore.

## Cinco escores em cada referência

Reagregar todas as contagens municipais depois de cada atribuição. Para os três escores de prevalência, `M` é o número fixo de municípios-alvo:

```text
Ucount       = max(n(G13>G22), n(G22>G13)) / M
Unominal     = max(n(P13>P22), n(P22>P13)) / M
Uconditional = max(n(q2>q1), n(q1>q2)) / M
```

Empates permanecem no denominador, sem favorecer nenhum sentido. Os escores são simétricos e testam **excesso de prevalência** em cauda superior; publicar também os sentidos separadamente. `Uconditional` cobre a direção do crescimento relativo onde este é definido, sem duplicá-la em outro teste. Frequência nacional de sinais municipais pode variar porque as seções/blocos mudam de município: não permutar apenas municípios já agregados, o que conservaria essa frequência e não responderia à pergunta.

Para os outros escores, calcular em cada seção `d_i=100*(q2−q1)`. Uma unidade carrega `n_u` seções e `D_u=sum_i(d_i)`; na referência por seção, `n_u=1`. Para cada estrato, `mu_g=sum(D_u)/sum(n_u)` e `r_u=D_u−mu_g*n_u`. A média dá peso igual às seções. A unidade inteira, inclusive `n_u` e `r_u`, muda junta. Em cada município, definir `n_m=sum(n_u)` e `R_m=sum(r_u)/n_m`:

```text
Rlow = sqrt(sum_alvos(n_m*R_m^2) / sum_alvos(n_m))
```

`Rlow`, em pontos percentuais, examina **dispersão excepcionalmente baixa** das médias municipais de mudanças por seção, ajustadas aos estratos. Não é a dispersão da mudança calculada pelas proporções agregadas municipais; ambas serão descritas separadamente. Sua cauda formal é inferior. A distribuição marginal de mudanças de seção e sua média global são preservadas; o teste não determina se elas próprias são naturais.

Antes das permutações, ordenar os municípios-alvo **dentro de cada UF** por sua preferência agregada inicial `q1` original, com razões exatas e desempate por código municipal. Fixar todos os pares adjacentes dessa ordem e definir:

```text
Jhigh = max_pares |R_esquerda−R_direita| / sqrt(1/n_esquerda+1/n_direita)
```

`Jhigh` tem unidade de ponto percentual vezes raiz de seção e cauda superior. **Não é escore-z, teste causal de descontinuidade, contraste em um limiar escolhido ou uma ordem geográfica/temporal.** É uma busca ajustada pelo máximo por contrastes entre perfis iniciais adjacentes. Preservar a ordem original mesmo que os totais iniciais mudem dentro das faixas durante a simulação. Publicar todos os pares, o máximo e seus sinais; o valor-p global não pertence individualmente ao par que atinge o máximo. Ausência de pares implica não aplicabilidade.

## Simulações, variabilidade e multiplicidade

Usar **4.999 atribuições por referência**, NumPy/PCG64 e semente-base `20261029`, com `SeedSequence([20261029,7,model_id], spawn_key=(rep,))`, `rep=0..4998`. Ordenar unidades por chave física (seções) ou chave do local (blocos); estratos lexicograficamente; agrupar estratos permutáveis por tamanho crescente, com `rng.permuted(bucket, axis=1)`. Guardar todos os escores, hashes das atribuições 0 e 1 e fingerprints de código, método e fontes, independentemente do número de processos.

Publicar os **9.998 conjuntos completos de cinco escores** em CSV comprimido. Quantis de 2,5% e 97,5% são referências condicionais, não intervalos de confiança da eleição. Valores-p: `(1+excedencias)/(4999+1)`, usando `>= observado−1e-12` para cauda superior e `<= observado+1e-12` para inferior, nas unidades de cada escore. Nunca p zero; resolução mínima 0,0002.

Aplicar Holm a 5% à família fixa de **dez testes** (cinco escores por duas referências). Testes e candidatos são dependentes e não contam como dez irregularidades independentes. Não criar valores-p por município, UF, região, definição alternativa ou par adjacente.

Confirmar variabilidade por atribuições com escores distintos. Sem testemunha, verificar invariância estrutural e enumerar órbitas pequenas de até 40.320 atribuições quando possível; usar aritmética exata para os sinais e prova racional dos escores quadráticos quando viável. Se a constância não puder ser provada nem a variabilidade demonstrada, registrar **variabilidade não resolvida**, sem decisão formal nesse teste. Constância comprovada também implica não aplicabilidade. Ambos usam p=1 apenas internamente no ajuste conservador de Holm; não são “não detecção” ou prova de naturalidade. Preservar as demais análises válidas, em vez de inventar uma conclusão para um escore sem informação demonstrada.

## Sensibilidades, evidências e validação

Sem novos valores-p, recalcular ambos os modelos alterando uma definição por vez: faixas iniciais de 2,5 pontos; de 10 pontos; aptos exatamente iguais entre turnos; piso de 100 votos dos finalistas no primeiro turno; alvos com uma seção; alvos com dez seções. Incluindo os primários, são **14 linhas** de sensibilidade. Recalcular os alvos e a ordem de perfis quando a coorte/piso mudar e publicar os novos denominadores; não selecionar uma alternativa para substituir o primário depois dos resultados.

Publicar censo municipal bruto e da coorte, comparações de ganhos e limiar de 99%, distribuições/quantis das mudanças, assinaturas racionais exatas mais frequentes, todas as unidades da coorte com suporte, estratos, agregados municipais dos dois modelos, pares adjacentes, escores, testes e sensibilidades. Repetições de valores ou saltos são descrições e não recebem por si só um rótulo de irregularidade.

Testes artificiais devem verificar pareamento e exclusões, agregação entre níveis, bases zero, denominadores distintos, identidades mecânicas, crescimento relativo equivalente em direção à mudança condicional, empates exatos/limiar de 99%, movimentos legítimos de composição, concentração direcional sem referência 1/2, uniformidade construída, contraste de perfis, preservação de blocos, alvos fixos quando números de seções mudam, referências constantes e enumeração finita. Uma implementação independente relê as fontes e reconstrói todos os CSVs e as 14 sensibilidades, confere os escores retidos/ranks/Holm e repete as atribuições 0 e 1 das duas referências. Distinguir a auditoria dos 9.998 escores de gerar todas as atribuições novamente.

Método, código, testes, evidências completas comprimidas, gráficos e relatório Markdown ficam nesta pasta. Caches privados ficam em `.work/`, ignorado no Git. Lula usa vermelho e Flávio Bolsonaro azul; medidas simétricas podem usar cores neutras. Preservar as fontes e as entregas anteriores. A nota de 0 a 10 será síntese qualitativa ordinal justificada após os resultados, conforme a rubrica do índice, sem probabilidade de manipulação ou conversão de valor-p.

## Limites de interpretação

As permutações preservam a distribuição empírica das trajetórias de seção ou local. Assim, o teste não certifica a naturalidade de todos os ganhos nacionais ou municipais, nem exclui alterações uniformes condicionadas para fora da referência. O modelo por seção rompe dependência interna de locais; o de blocos conserva essa dependência, mas não toda estrutura municipal. Geografia, composição não observada, campanha, mobilização e seleção de quem compareceu podem produzir os sinais avaliados.

Rejeitar uma referência identifica uma diferença de alocação no recorte definido, sem determinar causa artificial. Não rejeitar não demonstra que o movimento é natural. Hashes conferem continuidade interna, não autenticação independente contra boletins ou cadastro externo. Nenhuma conclusão sobre transferências individuais será obtida dessas contagens agregadas.
