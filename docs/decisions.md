# Decisões do experimento

## Prioridade e escopo

As orientações do chat prevalecem sobre o documento anexado `Election-replay-instructions.md`, usado como referência de requisitos e metodologia, não como comprovação de conteúdo dos CSVs. O primeiro objetivo é o replay com CSV e gráficos; foram mantidos os diagnósticos necessários para interpretá-lo. Bash/Python substituem os exemplos PowerShell. Processam-se somente os turnos encontrados, sem exigir os dois.

## Entradas e rastreabilidade

- Somente `votacao_secao_2026_BR.csv` e `detalhe_votacao_secao_2026_BR.csv` compõem o fluxo principal. Nada é concatenado com `BRASIL` ou UFs.
- Originais são abertos somente para leitura. A execução registra SHA-256, tamanho, cabeçalhos e datas de extração presentes; data de coleta fica desconhecida quando não fornecida. Mtime não é tratado como coleta.
- `ANO_ELEICAO` é filtro explícito (2026 por padrão); `CD_CARGO=1`, `DS_CARGO=Presidente` e `SG_UE=BR` são conferidos. Inconsistências de código/nome presidencial causam falha, não descarte silencioso. Escopos observados e descartes ficam no manifesto.
- Ponteiros Git LFS são recusados. Não se calculam eleições sobre ponteiros nem se usam dados sintéticos como substitutos dos resultados reais.

## Modelo e duplicidades

- Chave: eleição + turno + UF + município + zona + seção + cargo. Apenas um ano é selecionado por execução. Códigos numéricos perdem zeros à esquerda para pareamento consistente.
- Votos repetidos na mesma seção/votável são somados, conforme o documento. Esses grupos são reportados; o programa não presume se a repetição significa erro na fonte.
- Nomes não participam da chave. Todas as variantes brutas são inventariadas. O nome de apresentação é o mínimo lexicográfico por votável; o número/código identifica a candidatura.
- **Todas** as chaves com mais de uma linha no detalhe são excluídas das curvas, mesmo que as linhas pareçam idênticas. A regra conservadora evita escolher um timestamp arbitrário e preserva os votos no resultado final e nos diagnósticos.
- Seções apenas na votação continuam nos totais finais e ficam fora das curvas. Seções apenas no detalhe entram no relatório de cobertura, sem inventar votos.

## Horários e curvas

- Referência principal: `DT_PRIM_TOT_PARCIAL_HOR_TSE`; alternativa: `DT_RECEBIMENTO_BU_HOR_TSE`. `DT_GERACAO`/`HH_GERACAO` são proveniência, nunca eventos.
- Formato observado inicialmente no detalhe: `DD/MM/AAAA HH:MM:SS`. O leitor aceita também frações de segundo e formatos locais ISO documentados no código. Valores com offset explícito ou formatos desconhecidos são inválidos, sem conversão adivinhada.
- Os PDFs descrevem “Hora TSE” sem fixar offset nos campos. Preserva-se o relógio local registrado, sem afirmar UTC ou converter para America/Sao_Paulo. A data completa evita fundir dias distintos.
- Timestamp ausente e inválido são motivos distintos. Detalhe faltante/duplicado também é contabilizado. São verificados votos temporais + não temporais = votos finais em cada candidato/turno/fonte.
- Minuto M representa `[M, M+1min)`; acumulado ao fim de M. Todos os minutos entre o primeiro e o último evento utilizável são escritos, com incrementos zero nos intervalos vazios.
- Não há interpolação ou distribuição artificial dos votos dentro da seção. O conjunto completo dos votos da seção entra no minuto de seu horário.
- Branco=95, nulo=96, separado=97. Outros números positivos são tratados operacionalmente como nominais no cargo presidencial. Esses arquivos não permitem certificar a validade jurídica individual por candidato; o percentual deve ser interpretado com essa limitação.
- Percentuais usam apenas nominais temporalmente atribuídos até o minuto. Classes especiais não entram no denominador e recebem percentual vazio.

## Qualidade e visualização

- Reconciliação por seção compara nominal/branco/nulo/separado onde o campo do detalhe está disponível; campos ausentes não viram zero. Quantidades de comparações possíveis e de métricas faltantes também são reportadas.
- Condições anulada/não instalada e origens diferentes da urna eletrônica são reportadas, sem exclusão automática de votos. No detalhe real foram observados `Sim`, `Não` e `Urna Eletrônica`, embora o PDF exemplifique códigos S/N/U; ambos são reconhecidos.
- Diferença recebimento→totalização é um intervalo entre registros, não latência da divulgação pública. Valores negativos são mantidos para diagnóstico.
- CSVs têm todos os minutos. Gráficos podem reduzir pontos, conservando início, fim e extremos por bloco; isso fica indicado no próprio relatório visual. HTML autônomo facilita exploração; SVGs são exportáveis e não exigem serviço externo.
- SQLite em disco, ingestão em lotes e gráficos com leitura em duas passagens evitam carregar arquivos grandes completos em RAM. Somente metadados de escopo e séries reduzidas ficam em memória.
- Pastas de saída não vazias são recusadas. O manifesto distingue execução concluída de falha com saídas parciais. As execuções completas em `output/` são ignoradas pelo Git por serem artefatos reproduzíveis. Uma seleção de CSVs compactos, manifesto, relatório e gráficos da execução validada é copiada para `reports/2026/` e versionada para facilitar o consumo no GitHub, sem incluir o SQLite ou grandes recortes por seção.

## Histórico operacional

O acesso Git inicial funcionou, mas o Git LFS retornou `Resource not accessible by integration`. Após o usuário conceder acesso do App Codex ao repositório no GitHub, o download dos dois CSVs nacionais foi concluído. Os hashes coincidiram com os ponteiros LFS e o processamento integral dos dois turnos terminou com conservação de votos verificada. Veja `docs/results-2026.md`. A implementação não altera autenticação, não usa novos tokens e não baixa outros datasets.

## Apresentação e idiomas

Por solicitação do usuário, o candidato 13 (Lula) usa vermelho `#c62828` e o candidato 22 (Flávio Bolsonaro) usa azul `#1565c0`. O mapeamento é explícito por número e vale para HTML, SVG, turnos, referências temporais e medidas. Os demais candidatos recebem cores de uma paleta separada; não há inferência automática de orientação política.

`README.md` é a versão principal em inglês dos EUA; `README.pt-BR.md` contém a versão em português do Brasil. Links no topo permitem alternar entre elas, pois o GitHub exibe o README principal sem selecionar automaticamente uma tradução.
