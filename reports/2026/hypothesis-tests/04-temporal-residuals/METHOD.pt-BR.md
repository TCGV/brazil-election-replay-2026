# Protocolo da H4 — Evolução temporal após considerar a composição

[Relatório principal](REPORT.pt-BR.md) · [Reprodução](README.md)

Protocolo definido antes de relacionar a votação dos candidatos com a ordem temporal nesta entrega. O reconhecimento prévio limitou-se ao esquema, à cobertura, ao tamanho dos grupos e à dispersão de seus horários. Não constitui pré-registro externo. O manifesto da execução registra seu hash; alterações posteriores exigem nova versão identificada, sem reescrever silenciosamente o protocolo.

## Hipótese e alcance

**Hipótese:** a evolução da votação ao longo da apuração apresenta desvios residuais — inclusive tendências sutis e graduais ou contribuições abruptas — que não são explicados pela composição observada das seções dentro das referências locais definidas. **Dificuldade de identificação: alta.**

Analisar os dois turnos separadamente, incluindo as 13 candidaturas nominais do primeiro e as duas do segundo. O teste é bilateral: vantagens ou desvantagens temporais para qualquer candidatura são tratadas com a mesma regra. Não pressupor uma causa artificial nem antecipar a refutação.

Os horários são os campos de primeira totalização parcial e recebimento de BU dos arquivos fornecidos. A reconstrução é retrospectiva: não equivale ao histórico de atualizações efetivamente divulgado ao público nem permite observar alterações intermediárias do registro de uma seção.

## Fontes, coorte e relógio

- Reler os dois CSVs nacionais originais de votação e detalhe, sem concatenar arquivos estaduais sobrepostos. Conferir hashes contra a etapa 1 e a auditoria contábil e reconciliar os votos e categorias por seção.
- Unidade: seção/turno, sem misturar turnos. Para uma candidatura existente no turno, sua linha ausente pode corresponder a zero somente após a reconciliação. Campo numérico ausente nunca vira zero.
- Elegibilidade básica: seção instalada e não anulada, pelo menos 50 aptos, comparecimento positivo e pelo menos 50 votos nominais. Não condicionar a inclusão à votação de qualquer candidato.
- Para a coorte temporal comum, exigir também identificação válida do local de votação e os dois horários válidos. Publicar exclusões exclusivas na ordem: situação; aptos; comparecimento; nominais; local; horários. A exigência dos dois horários permite comparar primeira totalização e BU no mesmo conjunto de seções; eventuais exclusões limitam a generalização.
- Usar a convenção ingênua de relógio declarada como Hora TSE, com datas completas e sem conversão de fuso não comprovada. Truncar segundos para o minuto. Todos os empates de um minuto entram juntos; não desempatar por voto, seção ou ordem de leitura.
- A primeira totalização é a fonte primária. BU é sensibilidade descritiva, usando os mesmos pares de slots e as mesmas permutações, sem acrescentar uma família de valores-p.

## Duas referências locais previamente definidas

Avaliar **as duas referências**, sem escolher a que produza o resultado desejado:

1. **Zona e porte da seção (`zone_size`):** UF + município + zona eleitoral + faixa de aptos `floor(log(aptos)/log(1,25))`.
2. **Local e porte da seção (`place_size`):** os mesmos campos, acrescentando o local de votação.

Ambas preservam a composição por UF, município e zona a cada minuto e condicionam o porte da seção pela faixa. A segunda preserva ainda o local de votação a cada minuto. Como capital, região e porte municipal são constantes dentro de município, suas contagens de seções por minuto também ficam preservadas. Os pesos por votos nominais podem variar ao redistribuir seções, sendo recalculados em cada realização.

A referência por zona permite investigar contrastes entre locais da mesma zona, mas deixa heterogeneidade entre esses locais sem controle. A referência por local controla esse fator com mais detalhe; se as seções de um local entram quase ao mesmo tempo, pode condicionar para fora uma mudança coordenada que atinja todo o local. Mais controle não significa automaticamente mais capacidade de detectar toda forma de desvio.

Manter estratos unitários nas tabelas, nas curvas e nos denominadores: não contribuem informação para o embaralhamento. Não exigir um mínimo arbitrário de 30 seções. Publicar, por referência/turno/UF, grupos, seções em grupos com pares, minutos distintos e distribuição dos intervalos entre primeiro e último horário de cada grupo. Informar suporte informativo por candidatura: seções em estratos com pelo menos dois minutos distintos e resíduos não constantes. Não interpretar estratos constantes ou sem dispersão temporal como evidência de naturalidade.

## Composição e resíduos

Para cada grupo `g` e candidato `c`, definir:

```text
N_g = soma dos votos nominais das seções do grupo
p_gc = soma dos votos do candidato no grupo / N_g
r_ic = votos_ic − p_gc * nominais_i
```

Os resíduos somam zero dentro de cada grupo. `p_gc` usa os próprios resultados finais do grupo: é uma decomposição retrospectiva da composição, não uma previsão externa, um contrafactual causal ou uma estimativa treinada independentemente. A referência não detecta mudanças que alterem uniformemente a preferência final de todo o grupo.

Em cada minuto, a soma acumulada dos votos previstos `p_gc * nominais_i` define a curva de composição observada. Sua diferença para a curva efetiva é o resíduo acumulado. Para a visualização da participação corrente, dividir ambas as somas pelo total nominal acumulado corrente. Esse percentual residual corrente é distinto dos escores formais abaixo, normalizados pelo nominal **final** da coorte.

Calcular contagens e totais com inteiros. Resíduos, curvas e escores usam `float64`. Relações exatamente proporcionais devem ser identificadas com contagens inteiras; arredondamento numérico não deve criar suporte informativo. Conferir fechamento final dos resíduos com tolerância documentada no código e no manifesto.

## Permutação e estatísticas primárias

Em cada grupo, redistribuir uniformemente **o payload completo da seção** entre os pares fixos de slots `(minuto da primeira totalização, minuto do BU)`. A candidatura, o total nominal e as demais categorias de uma seção se deslocam juntos. Preservar suas identidades contábeis, as somas locais e nacionais, a quantidade de seções em cada minuto e o contexto definido pelo grupo. Não embaralhar contagens de candidatos isoladamente.

Usar todos os minutos do período entre o primeiro e o último horário da coorte, incluindo minutos sem chegada, sem selecionar uma janela depois de olhar a curva. Seja `N` o total nominal final da coorte e `x_i` o posto intermediário do minuto da seção na ordem nacional da coorte, dividido pelo número de seções e centrado em 0,5. Se `a_m` seções ocorreram antes do minuto e `b_m` até ele, `x_i = (a_m+b_m)/(2*n_seções) − 0,5`. Esse posto mantém os empates completos e mede avanço por seções, sem impor duração uniforme ao relógio. A centralização não altera o escore porque os resíduos somam zero.

Para cada candidato/turno/referência, calcular três escores bilaterais:

```text
G = 100 * abs(soma_i x_i * r_ic) / N
C = 100 * max_m abs(soma_{tempo_i <= m} r_ic) / N
M = 100 * max_m abs(soma_{tempo_i = m} r_ic) / N
```

- **G — tendência gradual:** associação linear residual com a ordem de entrada. Guardar também seu sinal antes do módulo. É um escore de covariância temporal normalizado; não é uma inclinação convencional nem a mudança, em pontos percentuais, entre o começo e o fim da curva.
- **C — excursão acumulada:** maior desvio residual acumulado. Pode responder tanto a tendências graduais quanto a mudanças mais concentradas; não o denominar exclusivamente teste de ruptura.
- **M — contribuição abrupta de um minuto:** maior lote residual em um minuto. A normalização pelo total final prioriza magnitude na coorte; lotes pequenos ou alterações repartidas por vários minutos podem ter menor sensibilidade. O horário do máximo não identifica uma causa, uma alteração do arquivo ou um evento oficial.

As unidades são pontos percentuais do nominal final para C/M e a correspondente covariância normalizada para G. Não transformar resíduos em estimativa de votos artificiais. A posição temporal dos máximos é descritiva; o teste já considera a busca em todos os minutos e não fornece valor-p para uma seção ou minuto individual.

## Simulação e multiplicidade

- **4.999 permutações** por turno e referência; `model_id=0` para zona/porte e `1` para local/porte. A realização `rep`, numerada de 0 a 4.998, usa `SeedSequence([20261028, turno, model_id], spawn_key=(rep,))`, equivalente ao filho `rep` de `SeedSequence([20261028, turno, model_id]).spawn(4999)`. Assim, o fluxo de cada realização independe do número de processos, da divisão em lotes e da ordem de execução. Usar NumPy `default_rng`/PCG64 e guardar versão, código, parâmetros e fingerprints.
- A mesma realização fornece os três escores para todas as candidaturas e as duas fontes de horário. Permutações de grupos distintos são independentes; todos os candidatos de uma seção compartilham a mesma atribuição.
- Valor-p primário: `(1 + número de escores simulados >= escore observado − tolerância)/(4.999 + 1)`. Usar tolerância de `1e-12` nas unidades dos escores e registrar o valor no manifesto. Resolução mínima `0,0002`; nunca reportar p igual a zero.
- Aplicar Holm a 5% à família fixa de **90 testes**: 15 combinações candidato/turno × três escores × duas referências. Não selecionar candidatos, uma referência, um escore ou uma janela pelo menor valor-p.
- Referência sem variabilidade possível é não aplicável, com motivo explícito; usar p=1 apenas internamente para manter a família de 90. Verificar teoricamente a ausência de suporte, sem classificá-la como naturalidade.
- Guardar os vetores simulados de escores em cache local para auditoria independente. Publicar observado, sinal quando pertinente, expectativa/quantis simulados, excedências, valor-p bruto, ajuste e decisão. Faixas simuladas são referências do modelo, não intervalos de confiança da eleição.

As curvas de BU são sensibilidade emparelhada. Não calcular novos valores-p primários ou ajustar a decisão por sua aparência. Publicar suas magnitudes e indicar diferenças de ordenação e suporte.

Para apresentar envelopes, guardar as curvas simuladas de resíduo acumulado em uma grade fixa de avanço de 0%, 1%, …, 100% das seções. Em cada ponto positivo, usar o primeiro minuto cujo acumulado atinge a fração desejada, incluindo todos os empates; em 0%, usar o ponto anterior às chegadas, com resíduo zero. Os valores são `100*resíduo acumulado/Nfinal`. Publicar quantis de 2,5% e 97,5% ponto a ponto: não são bandas simultâneas nem intervalos de confiança. A estatística C continua examinando todos os minutos, não apenas essa grade. Preservar os três escores de cada permutação e as curvas da grade, sem exigir armazenamento das curvas simuladas completas por minuto.

## Sensibilidades descritivas e recortes

Sem novas decisões formais, recalcular os valores observados e a cobertura para local sem faixa de aptos e para piso de 100 nominais nas duas referências. Alterar uma definição por vez. Não escolher um desses desenhos como substituto do primário depois dos resultados.

Publicar curvas nacionais por minuto e resumos descritivos por UF e marcos de avanço, com denominadores explícitos. Lula e Flávio Bolsonaro têm cores vermelho e azul nas figuras correspondentes. Os recortes por UF não formam novos testes selecionados; sinais estaduais permanecem descritivos. Candidatos e turnos não se confundem com observações independentes.

## Interpretação e validação

Rejeitar a permutabilidade local significa que a votação residual acompanha a ordem temporal além do admitido pela referência. Transporte, transmissão em lotes, distribuição de seções dentro do local, composição individual não observada e outros fatores legítimos podem produzir esse resultado. Nem as duas referências nem uma nota qualitativa distinguem sozinhas essas causas de uma origem artificial. Não detecção não prova naturalidade, sobretudo para mudanças coordenadas dentro de todo um estrato ou para dados ausentes.

Uma implementação independente deve reler as fontes, conferir coorte, agrupamentos, cobertura, resíduos, curvas, máximos, escores observados e ajustes. A partir dos vetores preservados, conferir excedências, valores-p e Holm; explicitar se a geração de todas as permutações foi ou não repetida de forma independente. Os controles artificiais devem incluir tendência gradual, lote abrupto, heterogeneidade legítima controlada ou não pelas duas referências, empates de minuto, singleton, referência constante, todos os candidatos deslocando juntos e preservação de totais. Usar enumerações pequenas para verificar a referência finita quando viável.

Método, código, evidências, testes, figuras e relatório ficam nesta pasta. Fontes e resultados anteriores permanecem inalterados. A avaliação de 0 a 10 será uma síntese qualitativa justificada depois dos resultados, conforme a rubrica do índice; não será probabilidade de manipulação nem conversão dos valores-p.
