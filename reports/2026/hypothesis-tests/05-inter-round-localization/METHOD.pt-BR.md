# Protocolo da H5 — Mudanças localizadas entre turnos

[Relatório principal](REPORT.pt-BR.md) · [Reprodução](README.md)

Este protocolo é definido antes de calcular as mudanças de votação entre turnos nesta entrega. O reconhecimento prévio se limita ao esquema, ao pareamento das chaves, aos denominadores, às situações cadastrais e ao suporte estrutural dos grupos. Não constitui pré-registro externo. Seu hash será registrado no manifesto da execução; alterações posteriores exigem uma versão identificada, sem reescrita silenciosa.

## Hipótese e alcance

**Hipótese:** as mudanças entre turnos apresentam valores excepcionalmente localizados em determinadas seções, além do movimento de seções comparáveis. **Dificuldade de identificação: alta.**

A avaliação tem duas partes complementares: uma **triagem descritiva por seção**, que registra diferenças grandes em relação a outros pares locais, e uma **referência formal de concentração entre locais de votação**. A segunda parte não é um teste da quantidade ou magnitude marginal de todas as mudanças extremas: as permutações preservam essas mudanças observadas e examinam como elas se distribuem entre locais. Essa distinção limita qualquer conclusão sobre a hipótese ampla.

Os dois turnos entram no mesmo pareamento; não são duas amostras independentes de eleitores. Não se inferem transferências individuais, motivações de voto ou uma causa artificial a partir das diferenças agregadas.

## Fontes, pareamento e elegibilidade

- Reler os dois CSVs nacionais originais de votação e detalhe, com hashes conferidos contra as fontes das etapas anteriores e reconciliação das categorias por seção. Não concatenar arquivos estaduais sobrepostos.
- Parear por `UF + município + zona + seção`, no mesmo ano e cargo presidencial. O código de eleição e o turno distinguem os registros de origem, mas não fazem parte da chave física usada para relacionar os dois turnos. Chaves ambíguas ou mais de uma eleição presidencial por turno no recorte exigem diagnóstico, não agregação silenciosa.
- Publicar inventário completo das chaves encontradas em ambos os turnos e apenas em um deles. Chaves sem contraparte permanecem como diagnóstico de cobertura e não recebem uma mudança inventada.
- Para uma candidatura existente, a ausência de sua linha pode representar zero depois da reconciliação dos totais. Uma quantidade numérica ausente nunca vira zero.
- Na coorte principal, exigir, nos dois turnos: seção instalada e não anulada; pelo menos 50 aptos; comparecimento positivo; e pelo menos 50 votos nominais. Exigir também pelo menos 50 votos somados dos dois finalistas no primeiro turno, local de votação conhecido e igual entre turnos, e razão `max(aptos_1, aptos_2)/min(aptos_1, aptos_2) <= 1,25`.
- Aplicar exclusões exclusivas nesta ordem: falta de contraparte; situação da seção; aptos abaixo de 50; comparecimento não positivo; nominais abaixo de 50; soma dos finalistas no primeiro turno abaixo de 50; identificação de local ausente; local alterado; razão de aptos acima de 1,25. Publicar denominadores e exclusões por UF e no agregado nacional, incluindo exterior.
- Ter a mesma chave e o mesmo local é uma aproximação de continuidade cadastral, não comprovação de que exatamente as mesmas pessoas votaram. Mudanças de composição podem ocorrer mesmo com o mesmo número de aptos. Não exigir horários de apuração para esse pareamento: a pergunta é entre turnos, não sobre sua ordem de chegada.

## Medidas comparáveis entre turnos

Há 13 candidaturas nominais no primeiro turno e duas no segundo. Para evitar interpretar a simples saída das demais candidaturas como um deslocamento entre finalistas, definir:

```text
F_t = votos_13,t + votos_22,t
q_t = votos_13,t / F_t
delta_i = 100 * (q_2,i - q_1,i)
```

`delta` é uma mudança em pontos percentuais da participação **condicional aos dois finalistas**. Não é ganho de votos absolutos, não usa todos os nominais no primeiro turno e não remove todas as possíveis mudanças de composição do público votante. Para o candidato 22, a mudança condicional é exatamente `-delta`; os dois sentidos são avaliados sem duplicar testes complementares.

Publicar também, como diagnóstico, as participações de cada finalista sobre todos os nominais de cada turno, suas diferenças e os ganhos de contagens. Esses diagnósticos não identificam de onde vieram os votos adicionais. Não ajustar nem classificar uma mudança como artificial com base somente em seu sinal.

Usar contagens inteiras e razões não arredondadas. A faixa de preferência inicial é `min(19, floor(20*votos_13,1/F_1))`, calculada com inteiros, para intervalos de cinco pontos percentuais; a participação de 100% entra no último intervalo. Faixas de aptos são `floor(log(aptos_1)/log(1,25))`.

## Triagem descritiva por seção

Para cada seção elegível, seus pares primários são as **outras** seções da coorte com mesma UF, município, zona, local de votação, faixa de aptos do primeiro turno e faixa de preferência inicial de cinco pontos percentuais. A seção avaliada é excluída do cálculo de sua referência.

Com pelo menos quatro outros pares, calcular a mediana de `delta` dos pares e o contraste `delta_i - mediana_dos_outros`. Marcar prioridade descritiva quando o módulo desse contraste atingir **10 pontos percentuais**, com tolerância de `1e-12` nas unidades de pontos percentuais. Publicar todas as seções e todos os contrastes comparáveis, não apenas as prioridades. Sem quatro pares, registrar suporte insuficiente, sem classificar a seção como normal ou anômala.

O corte de 10 pontos é um filtro de magnitude, não um valor-p individual ou uma estimativa de votos artificiais. Não acrescentar um corte de MAD ou uma quota de percentis que possa parecer mais precisa do que permitem poucos pares. Não tratar as comparações sobrepostas como observações independentes.

Como contexto descritivo adicional, recalcular o contraste usando outros pares do mesmo local e faixa de aptos, sem a faixa de preferência inicial, mantendo o mínimo de quatro. Mudança de contraste, atenuação ou persistência nesse recorte não determina a causa da diferença. A preferência inicial pode se associar legitimamente à mudança por teto das proporções, mobilização, composição e regressão à média; as faixas não removem completamente essas relações ou o erro de uma preferência medida por contagens finitas.

## Referência formal de concentração entre locais

Avaliar duas referências previamente definidas, sem escolher a que produzir o resultado desejado:

1. **`zone_size`:** UF + município + zona + faixa de aptos do primeiro turno.
2. **`zone_size_baseline`:** os mesmos campos, acrescentando a faixa de preferência inicial de cinco pontos percentuais.

Para cada estrato `g`, calcular a média simples de `delta` por seção e o resíduo `r_i = delta_i - media_g(delta)`. O peso igual por seção é uma escolha explícita; não interpretar essa média como o percentual agregado de votos do grupo. A soma dos resíduos de cada estrato é zero. A referência com preferência inicial controla parte da heterogeneidade adicional; a comparação entre referências não é uma identificação causal desse fator.

Cada par de seções entre turnos constitui um **payload completo e inseparável**, contendo os dois conjuntos de contagens e seus denominadores. Redistribuir esses pares inteiros entre os slots fixos do mesmo estrato. A mesma atribuição se aplica a todos os votos de ambos os turnos; não permutar candidatos ou turnos separadamente. Os slots retêm UF, município, zona e identificação do local de votação; seus tamanhos por local permanecem fixos. As faixas definidas pelo estrato também são preservadas. Deslocar o resíduo do par é matematicamente equivalente para os escores abaixo, porque a média de seu estrato é invariável.

Os alvos formais são os locais com **pelo menos cinco seções da coorte**, definidos antes de examinar suas mudanças. Todas as seções permanecem nas permutações, inclusive as de locais sem cinco membros; suas trocas podem informar a distribuição nos alvos. Para cada alvo `l`, sejam `n_l` seu número fixo de slots e `S_l` a soma dos resíduos atribuídos a eles:

```text
RMS = sqrt( soma_l(S_l^2 / n_l) / soma_l(n_l) )
MAX = max_l abs(S_l) / sqrt(n_l)
```

RMS é a raiz da média quadrática das médias residuais locais, ponderada pelo número de seções; sua unidade é ponto percentual. MAX multiplica o módulo da média local por `sqrt(n_l)` e tem unidade de ponto percentual vezes raiz de seção. **MAX não é um escore-z nem uma estatística studentizada pela variância de cada local.** Ambos examinam concentração nos dois sentidos, via quadrados ou módulos. O teste de MAX já inclui a busca entre todos os alvos; não fornece um valor-p para um local, seção ou UF individual.

Publicar, para todos os locais, a média residual, seu sinal, as contagens e os componentes dos escores. Totais, quantis e ordenações descritivas não classificam os locais como manipulados. Nenhum resíduo é convertido em estimativa de votos artificiais.

## Simulação, suporte e multiplicidade

- Usar **4.999 permutações por referência**, NumPy `default_rng`/PCG64 e semente-base `20261029`. A realização `rep`, de 0 a 4.998, usa `SeedSequence([20261029, model_id], spawn_key=(rep,))`, com IDs 0 para `zone_size` e 1 para `zone_size_baseline`. Guardar versão, código e fingerprints; os subfluxos tornam o resultado independente do número de processos ou da divisão em lotes.
- A mesma realização calcula RMS e MAX. Publicar observado, média e quantis simulados de 2,5% e 97,5%, excedências, valor-p e decisão. Os quantis são referências condicionais, não intervalos de confiança da eleição.
- Valor-p unilateral para excesso: `(1 + simulacoes_com_escore >= observado - 1e-12)/(4999 + 1)`, com tolerância nas unidades de cada escore e resolução mínima `0,0002`. Nunca publicar p igual a zero.
- Aplicar Holm a 5% à família fixa de **quatro testes**, dois escores por duas referências. Não duplicar para os finalistas, cujas mudanças condicionais são complementares, nem selecionar uma referência ou um escore pelo menor valor-p.
- Publicar cobertura por estrato e local, distinguindo grupos unitários, variação de `delta`, multiplicidade de locais e se os slots podem alterar algum agregado-alvo. Um alvo e um local não alvo podem fornecer informação; grupos exclusivamente não alvos não afetam os escores.
- Resíduos e locais variáveis não garantem que os módulos RMS/MAX tenham variabilidade possível. Verificar variação por testemunhas de escores distintos; sem testemunha, enumerar órbitas pequenas quando viável. Se não for possível comprovar variabilidade ou constância, interromper e diagnosticar, em vez de publicar não detecção. Referências constantes comprovadas são não aplicáveis, com motivo; recebem p=1 apenas internamente no ajuste conservador da família.
- Guardar escores e atribuições suficientes para conferir a execução. Uma implementação independente deve reler as fontes e reconstruir pareamento, denominadores, coorte, grupos, contrastes, locais, escores, excedências e Holm. Explicitar quantas atribuições completas foram novamente geradas e quais verificações apenas recalculam os resultados a partir dos caches preservados.

## Sensibilidades descritivas e validação

Sem novas decisões formais, recalcular as magnitudes e a cobertura com faixas de preferência inicial de 2,5 e 10 pontos percentuais; apenas pares com aptos exatamente iguais entre turnos; piso de 100 votos dos finalistas no primeiro turno; e mínimo de dez seções por local-alvo. Alterar uma definição por vez, informar novos denominadores e não selecionar um desses desenhos como substituto do primário depois de observar os resultados. Recalcular os alvos quando a coorte mudar, distinguindo essa mudança de composição de uma variação do escore.

Recortes por UF, mudanças sobre todos os nominais e ganhos de contagens são descritivos, sem novas famílias selecionadas. Os gráficos dos candidatos mantêm vermelho para Lula e azul para Flávio Bolsonaro; uma medida simétrica ou de concentração pode usar cores neutras.

Testes artificiais devem cobrir: chaves sem contraparte, duplicações e mudanças cadastrais; efeitos mecânicos da saída dos demais candidatos; complemento exato das mudanças condicionais; exclusão da própria seção dos pares; empates e fronteiras de faixas; grandes contrastes isolados e movimentos legítimos homogêneos; concentração entre locais e heterogeneidade inicial controlada ou não pelas duas referências; alvos pequenos, estatísticas constantes e preservação do payload dos dois turnos. Pequenas enumerações devem conferir os escores e a referência finita quando viável.

## Limites de interpretação

A referência formal preserva a distribuição de mudanças entre seções. Por isso, não determina se a quantidade ou a magnitude nacional dos casos extremos é natural; testa sua **alocação entre locais**, nos contextos definidos. Uma alteração que atinja uniformemente todo um estrato pode ser condicionada para fora do teste. A triagem por seção e o teste de concentração respondem perguntas distintas e precisam aparecer separadamente no relatório.

Mobilização, campanha, distribuição do eleitorado, comparecimento e outras mudanças legítimas podem produzir deslocamentos diferentes entre locais e seções. As faixas observadas não caracterizam demografia individual nem todos esses fatores. Rejeitar a referência não identifica uma causa artificial; não rejeitá-la não demonstra naturalidade. A continuidade das chaves e dos hashes não autentica os resultados contra boletins ou cadastro independentes.

Método, código, testes, evidências, gráficos e relatório ficam nesta pasta. Caches locais são separados dos artefatos publicados. A nota de 0 a 10 será uma síntese qualitativa justificada depois dos resultados, conforme a rubrica do índice, sem interpretação de probabilidade de manipulação ou transformação de valor-p.
