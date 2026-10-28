# Protocolo da H2 — Comparecimento e concentração de votos

[Relatório principal](REPORT.pt-BR.md) · [Reprodução](README.md)

Este protocolo foi definido antes de calcular as caudas e os resultados da H2 nesta entrega. O reconhecimento prévio limitou-se ao esquema, candidatos, elegibilidade e tamanho dos grupos. Não constitui um pré-registro externo. Seu hash será registrado no manifesto da execução.

## Pergunta e alcance

**Hipótese:** algumas seções apresentam, simultaneamente, comparecimento e concentração de votos em um candidato muito diferentes das observadas em seções comparáveis. **Dificuldade de identificação: média.**

A avaliação cobre os dois turnos separadamente e todas as candidaturas nominais presentes: 13 no primeiro e duas no segundo. A direção investigada é **comparecimento alto com votação alta**; concentração acompanhada de comparecimento baixo não é este teste.

## Elegibilidade e comparação local

- Usar os dois CSVs nacionais originais, com hashes conferidos contra a etapa 1 e a H1. Não concatenar arquivos estaduais sobrepostos.
- A unidade é seção/turno. Incluir seções instaladas e não anuladas, com pelo menos 50 aptos, comparecimento positivo e pelo menos 50 votos nominais. Não condicionar a inclusão à votação do candidato.
- Classificar exclusões de modo exclusivo nesta ordem: situação da seção; aptos abaixo de 50; comparecimento não positivo; nominais abaixo de 50. Informar todos os denominadores por turno/UF, incluindo exterior.
- Para uma candidatura existente no turno, ausência de sua linha em uma seção corresponde a zero votos, depois de conferir as categorias e a cobertura dos arquivos. Campo numérico ausente não vira zero.
- Estrato primário: UF + município + zona eleitoral + faixa de aptos `floor(log(aptos)/log(1,25))`. Aptos na mesma faixa diferem por um fator inferior a 1,25. Turnos nunca são misturados.
- Exigir pelo menos **30 seções elegíveis por estrato**. Não recorrer automaticamente a outro município ou a uma faixa mais larga. Seções sem pares suficientes ficam fora da referência e têm sua cobertura publicada.

## Triagem e magnitude

Comparecimento é `comparecimento/aptos`; votação do candidato é `votos do candidato/nominais`. Para cada variável, uma seção pertence à cauda superior de 5% somente se `número de valores maiores ou iguais ao seu / n ≤ 1/20`. Empates são conservadores: não se escolhe arbitrariamente uma seção para completar a cauda. Grupo constante não tem cauda superior.

O inventário contém **todas as coincidências das duas caudas**. Uma classificação adicional de prioridade exige, simultaneamente, comparecimento pelo menos **5 pontos percentuais** acima da mediana do estrato e votação pelo menos **10 pontos** acima da mediana. Esses cortes são filtros descritivos de magnitude, sem valor-p individual. Medianas incluem a própria seção; não se apresentam como estimativas independentes dela. A aritmética em ponto flutuante admite tolerância de `1e-12` em fração apenas nas comparações dos cortes de magnitude; a validação usa razões exatas.

Para cada caso prioritário, consultar **outros** pares elegíveis no mesmo local de votação, município e zona, com aptos entre 0,8 e 1,25 vezes o valor da seção. Com pelo menos quatro pares, calcular medianas sem a seção e verificar os mesmos cortes de 5/10 pontos. Classificar como persistência dos dois cortes ou atenuação de pelo menos um; com menos pares, informar contexto insuficiente. Atenuação não encerra uma investigação nem demonstra origem natural.

## Referência estatística de associação

O teste formal é uma **referência de independência condicional entre as duas caudas**, não um teste de naturalidade da eleição. Em cada estrato, sejam `n` as seções, `a` as de comparecimento alto e `b` as de votação alta. A coincidência esperada é `a*b/n`. Sob a referência, a coincidência tem distribuição hipergeométrica; somam-se os resultados dos estratos.

- Estatística: total de coincidências `J`, testado na direção de excesso.
- Simular **19.999 realizações** por candidatura/turno, preservando `n`, `a` e `b` de cada estrato. Semente-base `20261028`, com fluxo independente `SeedSequence([semente, turno, número do candidato])`.
- Valor-p: `(1 + simulações com J_simulado ≥ J_observado)/(19.999 + 1)`, com resolução mínima `0,00005`. Guardar os vetores simulados no cache local para auditoria.
- Aplicar Holm a 5% à família fixa das **15 combinações candidato/turno**. Uma referência degenerada é não aplicável; recebe p=1 apenas no cálculo conservador da família, sem decisão formal própria.
- Informar observado, esperado, diferença, razão observado/esperado e faixa simulada. Essa faixa é uma referência para o total, não intervalo de confiança da eleição ou limite para cada seção.

## Sensibilidades definidas

Recalcular descritivamente, sem selecionar novos valores-p: caudas de 2,5% e 10%; mínimo de 20 pares; razão das faixas de aptos de 1,5; deslocamento de meia faixa (`floor(log(aptos)/log(1,25)+0,5)`); mínimo de 100 votos nominais. Alterar um parâmetro por vez. Mostrar cobertura, coincidências, prioridade e retenção dos casos primários entre as seções que continuam cobertas.

## Limites e validação

Mobilização, composição social e distribuição espacial legítimas podem associar comparecimento e votação mesmo dentro dos estratos. A precisão da proporção também varia com os votos nominais. Rejeitar independência não identifica manipulação; não rejeitá-la não demonstra naturalidade. Alterações que atinjam a maioria de um estrato podem permanecer invisíveis a uma comparação interna. A cobertura parcial impede generalizar às seções sem pares.

Uma implementação independente relerá os originais e verificará grupos, caudas, casos, totais, magnitudes, contexto local e cálculos dos valores-p/ajuste a partir dos vetores simulados. Testes artificiais devem verificar empates, zeros, limites, exclusão da própria seção dos pares locais, sinais inseridos e exemplos legítimos de heterogeneidade. Os arquivos originais e os resultados das etapas anteriores não serão alterados.
