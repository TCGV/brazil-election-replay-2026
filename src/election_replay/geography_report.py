"""Consolidated Portuguese geographic findings, rendered as Markdown and HTML."""
from __future__ import annotations

import base64
import csv
from datetime import datetime
import html
import json
from pathlib import Path
import re

PRIMARY = 'first_partial_totalization'
ALTERNATIVE = 'bu_received'


def _number(value, digits=2):
    if value in (None, ''):
        return '—'
    return f'{float(value):,.{digits}f}'.replace(',', '_').replace('.', ',').replace('_', '.')


def _clock(value):
    return datetime.fromisoformat(value).strftime('%H:%M:%S') if value else '—'


def _inline(value):
    text=html.escape(str(value))
    text=re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    text=re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
    return re.sub(r'\[([^\]]+)\]\(([^)]+)\)',r'<a href="\2">\1</a>',text)


class _Document:
    def __init__(self, directory):
        self.directory=directory
        self.markdown=[]
        self.body=[]

    def heading(self,text,level=2):
        self.markdown.extend([f'{"#"*level} {text}',''])
        self.body.append(f'<h{level}>{html.escape(text)}</h{level}>')

    def paragraph(self,text):
        self.markdown.extend([text,''])
        self.body.append(f'<p>{_inline(text)}</p>')

    def bullets(self,items):
        self.markdown.extend([f'- {item}' for item in items]+[''])
        self.body.append('<ul>'+''.join(f'<li>{_inline(item)}</li>' for item in items)+'</ul>')

    def table(self,columns,rows):
        rows=list(rows)
        self.markdown.extend(['| '+' | '.join(columns)+' |','|'+'|'.join(['---']*len(columns))+'|'])
        self.markdown.extend('| '+' | '.join(str(cell) for cell in row)+' |' for row in rows)
        self.markdown.append('')
        self.body.append('<div class="table-wrap"><table><thead><tr>'+''.join(f'<th>{_inline(c)}</th>' for c in columns)+
                         '</tr></thead><tbody>'+''.join('<tr>'+''.join(f'<td>{_inline(c)}</td>' for c in row)+'</tr>' for row in rows)+'</tbody></table></div>')

    def figure(self,name,caption):
        path=self.directory/'figures'/f'{name}.png'
        if not path.exists():
            raise ValueError(f'Report figure missing: {path}')
        self.markdown.extend([f'![{caption}](figures/{name}.png)','',f'*{caption}*',''])
        payload=base64.b64encode(path.read_bytes()).decode('ascii')
        self.body.append(f'<figure><img src="data:image/png;base64,{payload}" alt="{html.escape(caption)}"><figcaption>{html.escape(caption)}</figcaption></figure>')

    def code(self,text):
        self.markdown.extend(['```bash',text,'```',''])
        self.body.append('<pre><code>'+html.escape(text)+'</code></pre>')

    def save(self):
        (self.directory/'REPORT.pt-BR.md').write_text('\n'.join(self.markdown),encoding='utf8')
        css='''body{font-family:system-ui,Arial,sans-serif;color:#182a3b;max-width:1100px;margin:40px auto;padding:0 25px;font-size:16px;line-height:1.55}h1{line-height:1.2;font-size:36px}h2{margin-top:2em;border-bottom:2px solid #d7e2eb;padding-bottom:.3em}h3{margin-top:1.5em}a{color:#145b94}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:8px 10px;border-bottom:1px solid #d7e2eb;text-align:left}th{background:#edf3f8}.table-wrap{overflow-x:auto}figure{margin:30px 0;break-inside:avoid}img{width:100%;height:auto}figcaption{color:#496078;font-size:13px}code{background:#eff3f6;padding:1px 4px}pre{padding:15px;background:#eff3f6;white-space:pre-wrap}li{margin:.4em 0}@page{size:A4;margin:15mm 13mm}@media print{body{font-size:10.5pt;line-height:1.4;max-width:none;margin:0;padding:0}h1{font-size:23pt}h2{font-size:16pt;break-after:avoid}h3{break-after:avoid}table{font-size:8.5pt}thead{display:table-header-group}tr{break-inside:avoid}th,td{padding:5px}img{max-height:190mm;object-fit:contain}figure{margin:15px 0}a{text-decoration:none;color:inherit}pre{font-size:8pt}}'''
        page='<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Geografia da apuração presidencial de 2026</title><style>'+css+'</style><body>'+''.join(self.body)+'</body></html>'
        (self.directory/'report.html').write_text(page,encoding='utf8')
        return ['REPORT.pt-BR.md','report.html']


def generate_report(output_dir:Path):
    output_dir=Path(output_dir)
    def read(name):
        with (output_dir/name).open(encoding='utf8',newline='') as stream:return list(csv.DictReader(stream))
    timing=read('timing-summary.csv');milestones=read('national-milestones.csv')
    composition=read('milestone-composition.csv');decomposition=read('composition-decomposition.csv')
    municipality=read('sp-municipality-contributions.csv');clocks=read('clock-completion.csv')
    controls=json.loads((output_dir/'municipality-controls.json').read_text())
    manifest=json.loads((output_dir/'analysis-manifest.json').read_text())
    summary=json.loads((output_dir/'summary.json').read_text())
    validation_path=output_dir/'independent-validation.json'
    validation=json.loads(validation_path.read_text()) if validation_path.exists() else None
    if summary['status']!='completed':raise ValueError('Cannot report an incomplete analysis')

    def one(rows,**criteria):
        selected=[r for r in rows if all(str(r.get(key))==str(value) for key,value in criteria.items())]
        if len(selected)!=1:raise ValueError(f'Expected unique report fact: {criteria}, found {len(selected)}')
        return selected[0]
    def marker(turn,progress,scope='BR',source=PRIMARY):
        return one(milestones,source_timestamp=source,turno=turn,scope=scope,requested_sections_percentage=progress)
    def group(turn,dimension,name,source=PRIMARY):
        return one(timing,source_timestamp=source,turno=turn,dimension=dimension,group=name)
    def decomp(turn,progress,scope,dimension,source=PRIMARY):
        return one(decomposition,source_timestamp=source,turno=turn,scope=scope,dimension=dimension,requested_sections_percentage=progress)
    def national_at_clock(turn,clock):
        rows=[r for r in clocks if r['source_timestamp']==PRIMARY and r['turno']==str(turn) and r['dimension']=='region' and r['clock']==clock]
        return 100*sum(int(r['cumulative_sections']) for r in rows)/sum(int(r['total_sections']) for r in rows)
    def capital_contrasts(turn):
        rows={r['group']:r for r in timing if r['source_timestamp']==PRIMARY and r['turno']==str(turn) and r['dimension']=='uf_capital_status'}
        paired=[]
        for uf in sorted({key.split('|')[0] for key in rows}):
            if uf+'|capital' in rows and uf+'|non_capital' in rows:
                paired.append(float(rows[uf+'|capital']['t50_minutes'])-float(rows[uf+'|non_capital']['t50_minutes']))
        return sum(x<0 for x in paired),len(paired)
    def sp_cities(turn,progress=10,source=PRIMARY):
        return [r for r in municipality if r['source_timestamp']==source and r['turno']==str(turn) and r['requested_sections_percentage']==str(progress)]
    def city_mix(turn):
        rows=sp_cities(turn);capital=one(rows,is_capital=1);rest=[r for r in rows if r['is_capital']=='0']
        rest_current_weight=sum(float(r['current_nominal_weight_percentage']) for r in rest)
        rest_final_weight=sum(float(r['final_nominal_weight_percentage']) for r in rest)
        current_rest=sum(float(r['current_nominal_weight_percentage'])*float(r['lula_percentage'] or 0) for r in rest)/rest_current_weight
        final_rest=sum(float(r['final_nominal_weight_percentage'])*float(r['lula_final_percentage']) for r in rest)/rest_final_weight
        return capital,current_rest,final_rest

    doc=_Document(output_dir)
    doc.heading('Geografia da apuração presidencial de 2026',1)
    doc.paragraph('**Primeiro e segundo turnos — conclusões e evidências.** Análise dos arquivos fornecidos no repositório; referência principal: primeira totalização parcial de cada seção. A referência alternativa de recebimento do BU é usada como teste de sensibilidade. Horários preservados em Hora TSE, sem offset UTC confirmado.')
    doc.heading('Conclusões principais')
    ne1,ne2=marker(1,50),marker(2,50)
    doc.bullets([
        '**Há um padrão geográfico claro na ordem de entrada.** O Nordeste ficou mais sub-representado no primeiro turno. No marco de 50% das seções nacionais, tinha '+_number(ne1['ne_sections_completion_percentage'])+'% de suas seções contabilizadas, contra '+_number(ne2['ne_sections_completion_percentage'])+'% no segundo.',
        '**“Mais cedo” no segundo turno significa mais cedo em relação ao avanço nacional.** Em horário absoluto, o Nordeste atingiu 50% mais tarde: '+_clock(group(1,'region','Nordeste')['t50'])+' no primeiro turno e '+_clock(group(2,'region','Nordeste')['t50'])+' no segundo.',
        '**Capitais tenderam a avançar antes, mas isso não é uma regra universal.** A vantagem agregada foi maior no primeiro turno; a relação com porte municipal foi fraca e variou entre turnos e UFs.',
        '**A subida de Lula em São Paulo é confirmada.** A combinação de municípios que entravam no acumulado explica boa parte do desvio inicial frente ao resultado final, e há também ordenação dentro dos municípios. A capital ajuda, mas não explica sozinha o movimento.',
        '**Os arquivos mostram geografia e porte eleitoral, não o perfil individual dos eleitores.** Não permitem atribuir os padrões a renda, escolaridade, idade ou mudança de preferência durante a apuração.'
    ])
    doc.heading('1. Como a comparação foi feita')
    totals=manifest['totals']
    doc.table(['Turno','Código da eleição','Seções com votos','Votos nominais'],[(r[1],r[0],_number(next(c['sections'] for c in summary['coverage'] if str(c['turno'])==str(r[1])),0) if isinstance(summary['coverage'],list) and summary['coverage'] and 'sections' in summary['coverage'][0] else _number(marker(r[1],100)['cumulative_sections'],0),_number(r[2],0)) for r in totals])
    doc.paragraph('São '+_number(manifest['analysis_sections'],0)+' chaves de seção/turno analisadas, todas pareadas sem multiplicação de votos e sem horários ausentes nas duas referências. Uma mesma seção física pode aparecer em ambos os turnos; a contagem acima é de registros seção/turno. As 85 chaves presentes apenas no detalhe, todas sem votos, não geram eventos nesta análise.')
    doc.paragraph('Foram usadas duas réguas: **horário fixo** e **mesmo percentual de seções contabilizadas**. O primeiro responde quando os dados entraram; o segundo mede quais territórios estavam adiantados ou atrasados em relação ao restante do país. Os marcos de progresso incluem todos os eventos empatados no instante em que o limiar é alcançado; por isso o percentual efetivamente atingido pode superar ligeiramente 10%, 50% etc.')
    doc.paragraph('O progresso é medido por **número de seções**, enquanto os percentuais dos candidatos e os pesos geográficos usam **votos nominais**. Seções não têm o mesmo número de votos. Exterior (`ZZ`) é mantido na agregação nacional e separado dos grupos domésticos de capital e porte. Brasília é tratada como capital; o DF não tem contraparte de interior nesta classificação.')
    doc.heading('2. Nordeste: a hipótese é confirmada em termos relativos')
    doc.table(['Marco nacional de seções','NE concluído — 1º','NE concluído — 2º','Peso NE nos nominais — 1º','Peso NE — 2º'],[(f'{p}%',_number(marker(1,p)['ne_sections_completion_percentage'])+'%',_number(marker(2,p)['ne_sections_completion_percentage'])+'%',_number(marker(1,p)['ne_weight_percentage'])+'%',_number(marker(2,p)['ne_weight_percentage'])+'%') for p in [10,50,90,100]])
    doc.paragraph('No marco de 50%, o peso do Nordeste entre os votos nominais contados era '+_number(ne1['ne_weight_percentage'])+'%, frente a '+_number(ne1['ne_final_weight_percentage'])+'% no resultado final do primeiro turno. No segundo, esses pesos eram '+_number(ne2['ne_weight_percentage'])+'% e '+_number(ne2['ne_final_weight_percentage'])+'%. A composição já se parecia muito mais com a final no segundo turno, nesse estágio.')
    doc.figure('northeast-composition','Figura 1 — Representação do Nordeste comparando o mesmo progresso nacional. A linha de referência mostra o peso final, e a referência alternativa usa recebimento do BU.')
    doc.heading('Nem todos os estados do Nordeste avançaram mais no segundo turno',3)
    def uf_stage(turn,uf):return one(composition,source_timestamp=PRIMARY,turno=turn,scope='BR',requested_sections_percentage=50,dimension='uf',group=uf)
    doc.table(['UF','Seções da UF concluídas no marco nacional de 50% — 1º','2º','Diferença (pp)'],[(uf,_number(uf_stage(1,uf)['section_completion_percentage'])+'%',_number(uf_stage(2,uf)['section_completion_percentage'])+'%',_number(float(uf_stage(2,uf)['section_completion_percentage'])-float(uf_stage(1,uf)['section_completion_percentage']))) for uf in ['AL','BA','CE','MA','PB','PE','PI','RN','SE']])
    doc.paragraph('O avanço relativo maior foi observado em AL, MA, RN, CE, PE e PB. BA ficou ligeiramente menos avançada, e PI e SE ficaram substancialmente mais atrasados nesse marco. Portanto, a formulação correta é **“alguns estados do Nordeste entraram relativamente antes”**, sem generalizar o comportamento da região a todas as suas UFs.')
    doc.heading('O relógio e o platô inicial do segundo turno',3)
    doc.table(['Indicador','1º turno','2º turno'],[
        ['Nordeste: horário em que alcançou 50% das próprias seções',_clock(group(1,'region','Nordeste')['t50']),_clock(group(2,'region','Nordeste')['t50'])],
        ['Brasil: seções contabilizadas às 19:00:00',_number(national_at_clock(1,'19:00'),3)+'%',_number(national_at_clock(2,'19:00'),3)+'%'],
        ['Brasil: horário de 10% das seções',_clock(marker(1,10)['cutoff_timestamp']),_clock(marker(2,10)['cutoff_timestamp'])],
        ['Brasil: horário de 90% das seções',_clock(marker(1,90)['cutoff_timestamp']),_clock(marker(2,90)['cutoff_timestamp'])],
    ])
    doc.paragraph('O longo trecho horizontal inicial do segundo turno se apoia em pouquíssimas seções: às 19h havia apenas '+_number(national_at_clock(2,'19:00'),3)+'% do total nacional. Ele não deve ser lido como evidência de representatividade ampla ou de estabilidade do eleitorado. O avanço de 10% a 90% foi mais comprimido no segundo turno. Os arquivos permitem observar esse desenho temporal, mas não identificar sua causa operacional.')
    doc.figure('regional-completion','Figura 2 — Ritmo das regiões no relógio registrado, com a mesma escala temporal nos dois turnos. A cobertura nacional às 19h explicita o tamanho reduzido da base inicial do segundo turno.')
    doc.figure('state-timing','Figura 3 — Mediana e avanço até 90% por UF. Diferenças entre estados impedem interpretar o Nordeste ou qualquer região como bloco uniforme.')
    doc.heading('3. Capitais e municípios menores: tendência, não regra')
    caprows=[]
    for turn in [1,2]:
        cap=group(turn,'capital_status','capital');other=group(turn,'capital_status','non_capital')
        faster,paired=capital_contrasts(turn)
        caprows.append([f'{turn}º',_clock(cap['t50']),_clock(other['t50']),_number(float(other['t50_minutes'])-float(cap['t50_minutes']))+' min',f'{faster}/{paired}'])
    doc.table(['Turno','Capitais: 50%','Demais municípios: 50%','Antecedência agregada das capitais','UFs com capital antes do restante'],caprows)
    doc.paragraph('As capitais chegaram à metade das seções antes no agregado, mas a vantagem foi pequena no segundo turno. As comparações dentro de UF mostram exceções relevantes. A comparação agregada é ponderada por seções e depende da distribuição regional; não mede um efeito isolado de “ser capital”.')
    bands=[('<=10k','Até 10 mil'),('10k-50k','Mais de 10 a 50 mil'),('50k-200k','Mais de 50 a 200 mil'),('200k-1m','Mais de 200 mil a 1 milhão'),('>1m','Mais de 1 milhão')]
    doc.table(['Porte: eleitorado municipal registrado','50% das seções — 1º','50% das seções — 2º'],[(label,_clock(group(1,'size_band',code)['t50']),_clock(group(2,'size_band',code)['t50'])) for code,label in bands])
    doc.paragraph('Porte foi definido pelo total de eleitores aptos do município no primeiro turno disponível, mantido fixo entre os turnos. **Não é população residente.** As faixas não formam uma escada uniforme: municípios com mais de um milhão de eleitores chegaram à metade antes dos de até 10 mil no primeiro turno, mas depois deles no segundo. Região, UF e heterogeneidade dentro das faixas importam.')
    doc.figure('capital-size-timing','Figura 4 — Capitais e faixas de eleitorado municipal. As medianas são de eventos de seção; o porte é eleitoral, não populacional.')
    doc.heading('Controle por UF e unidade de comparação',3)
    c1=one(controls,source=PRIMARY,turno='1');c2=one(controls,source=PRIMARY,turno='2')
    doc.table(['Associação entre porte e horário mediano municipal','1º turno','2º turno'],[
        ['Correlação de Spearman, municípios com mesmo peso',_number(c1['spearman_size_vs_t50'],3),_number(c2['spearman_size_vs_t50'],3)],
        ['Correlação entre ranks após retirar médias de UF',_number(c1['within_uf_rank_correlation'],3),_number(c2['within_uf_rank_correlation'],3)],
    ])
    doc.paragraph('A associação global é positiva, mas fraca: municípios maiores tenderam a ter mediana um pouco mais tardia. Ao retirar diferenças médias de UF, a relação praticamente desaparece no primeiro turno e permanece pequena no segundo. Isso enfraquece uma explicação geral baseada apenas em tamanho. Esses cálculos dão o mesmo peso a cada município, ao contrário das medianas nacionais de seção da tabela anterior.')
    doc.heading('4. São Paulo: a subida de Lula é real, mas tem mais de um componente')
    doc.table(['Progresso das seções de SP','Lula — 1º turno','Lula — 2º turno'],[(f'{p}%',_number(marker(1,p,'SP')['lula_percentage'])+'%',_number(marker(2,p,'SP')['lula_percentage'])+'%') for p in [10,25,50,75,90,99,100]])
    doc.paragraph('O crescimento é geral, não estritamente monotônico. Por exemplo, no primeiro turno o percentual em SP cai ligeiramente entre o marco de 99% ('+_number(marker(1,99,'SP')['lula_percentage'],4)+'%) e o resultado final ('+_number(marker(1,100,'SP')['lula_percentage'],4)+'%). Pequenas oscilações não contradizem a tendência de conjunto.')
    doc.figure('candidate-shares','Figura 5 — Percentuais acumulados dos candidatos em marcos de progresso do Brasil e de São Paulo. Os pontos começam em 5% e usam os votos nominais do próprio turno; não são uma linha contínua de todos os eventos.')
    captable=[]
    for turn in [1,2]:
        city,current_rest,final_rest=city_mix(turn)
        captable.append([f'{turn}º',_number(city['current_nominal_weight_percentage'])+'%',_number(city['final_nominal_weight_percentage'])+'%',_number(city['lula_final_percentage'])+'%',_number(current_rest)+'% → '+_number(final_rest)+'%'])
    doc.table(['Turno','Capital: peso nos nominais no marco de 10% de SP','Capital: peso final','Lula: resultado final na capital','Lula no restante: marco de 10% → final'],captable)
    doc.paragraph('A capital começou sub-representada nos dois turnos e termina mais favorável a Lula do que o restante do estado. Sua entrada ajuda a elevar o percentual estadual. Porém, Lula também sobe no conjunto dos demais municípios: a explicação não se reduz a “capital tardia versus interior precoce”.')
    doc.heading('Separando combinação de municípios e ordenação interna',3)
    doc.table(['Turno e marco de SP','Desvio de Lula frente ao próprio final (pp)','Composição entre municípios (pp)','Ordenação dentro dos municípios (pp)'],[(f'{turn}º, {p}%',_number(decomp(turn,p,'SP','municipality')['total_gap_pp'],3),_number(decomp(turn,p,'SP','municipality')['composition_effect_pp'],3),_number(decomp(turn,p,'SP','municipality')['within_group_effect_pp'],3)) for turn in [1,2] for p in [10,50]])
    doc.paragraph('No marco de 10% de SP, a mistura de municípios responde por um componente de '+_number(decomp(1,10,'SP','municipality')['composition_effect_pp'],3)+' pp no primeiro turno e '+_number(decomp(2,10,'SP','municipality')['composition_effect_pp'],3)+' pp no segundo, relativamente ao resultado final. O restante é a diferença entre a votação já contada dentro de cada município e sua votação final. É uma identidade descritiva; não é prova de causalidade.')
    top_rows=[]
    for turn in [1,2]:
        rows=sorted(sp_cities(turn),key=lambda r:float(r['centered_composition_contribution_pp']))[:3]
        top_rows.extend([f'{turn}º',r['municipality_name'],_number(r['current_nominal_weight_percentage'])+'%',_number(r['final_nominal_weight_percentage'])+'%',_number(r['centered_composition_contribution_pp'],3)] for r in rows)
    doc.table(['Turno, marco de 10% de SP','Município','Peso corrente','Peso final','Contribuição centrada (pp)'],top_rows)
    doc.paragraph('As contribuições acima são centradas na votação final estadual. Um termo negativo pode surgir tanto de um município mais favorável a Lula ainda sub-representado quanto de um município menos favorável já super-representado. Não significa que todos os municípios listados foram tardios. Os termos individuais não centrados, também disponíveis no CSV para auditoria, não devem ser interpretados isoladamente porque valores grandes se cancelam.')
    doc.heading('5. O mecanismo nacional: mudança na composição geográfica')
    doc.table(['Turno e marco nacional','Desvio de Lula frente ao final (pp)','Composição entre regiões (pp)','Ordenação dentro das regiões (pp)'],[(f'{turn}º, {p}%',_number(decomp(turn,p,'BR','region')['total_gap_pp'],3),_number(decomp(turn,p,'BR','region')['composition_effect_pp'],3),_number(decomp(turn,p,'BR','region')['within_group_effect_pp'],3)) for turn in [1,2] for p in [10,50]])
    doc.paragraph('No primeiro turno, a composição regional inicial é bastante menos favorável a Lula que a composição final. No segundo, esse componente continua presente, mas é menor nos mesmos marcos. No marco de 10% do segundo turno, a ordenação interna às regiões o compensa parcialmente. Assim, não basta olhar somente para o peso do Nordeste: também importa quais seções de cada região já tinham entrado.')
    doc.paragraph('Os níveis brutos dos candidatos não são diretamente comparáveis entre turnos: o primeiro contém outros candidatos, e o segundo apenas dois. Por isso, a tabela usa o desvio de cada turno frente ao **próprio resultado final**. O “mais estável” do segundo turno é compatível com menor desvio geográfico nesses marcos, mas o platô inicial com cobertura minúscula não deve fundamentar essa conclusão.')
    doc.figure('composition-decomposition','Figura 6 — Identidade descritiva: composição entre regiões/UFs e ordenação interna. A decomposição de SP usa municípios. Os componentes variam com a granularidade geográfica e não são efeitos causais.')
    doc.heading('6. Sensibilidade ao horário escolhido')
    doc.table(['Indicador','1º: totalização / recebimento','2º: totalização / recebimento'],[
        ['Peso NE nos nominais no marco nacional de 50%',_number(marker(1,50)['ne_weight_percentage'])+'% / '+_number(marker(1,50,source=ALTERNATIVE)['ne_weight_percentage'])+'%',_number(marker(2,50)['ne_weight_percentage'])+'% / '+_number(marker(2,50,source=ALTERNATIVE)['ne_weight_percentage'])+'%'],
        ['Composição municipal de SP no marco estadual de 10% (pp)',_number(decomp(1,10,'SP','municipality')['composition_effect_pp'],3)+' / '+_number(decomp(1,10,'SP','municipality',source=ALTERNATIVE)['composition_effect_pp'],3),_number(decomp(2,10,'SP','municipality')['composition_effect_pp'],3)+' / '+_number(decomp(2,10,'SP','municipality',source=ALTERNATIVE)['composition_effect_pp'],3)],
    ])
    doc.paragraph('As conclusões centrais se mantêm usando recebimento do BU. Isso mostra robustez à escolha entre os dois horários disponíveis, sem transformar o replay em histórico certificado das atualizações públicas.')
    doc.heading('Método, limites e rastreabilidade')
    doc.heading('Identidade da decomposição',3)
    doc.paragraph('Para cada grupo geográfico g, seja w_g(t) seu peso nos votos nominais já contados, p_g(t) a fração de Lula dentro desses votos e p_g(F) sua fração final. O contrafactual descritivo é C(t) = Σ_g w_g(t) p_g(F). Não altera votos nem simula uma eleição; apenas substitui a composição interna corrente de cada grupo pela sua composição final.')
    doc.bullets([
        'Composição entre grupos = C(t) − P(F).',
        'Ordenação dentro dos grupos = P(t) − C(t).',
        'Desvio total = P(t) − P(F) = composição + ordenação interna.',
        'As tabelas expressam essas diferenças em pontos percentuais. Para contribuição municipal centrada, usa-se [w_g(t) − w_g(F)] × [p_g(F) − P(F)]; a soma continua igual ao componente de composição.'
    ])
    doc.paragraph('O t50 é o primeiro instante em que pelo menos metade das seções de um grupo foi contabilizada; o mesmo vale para t10/t90/t99. Seções simultâneas entram juntas. Horários fixos incluem eventos até HH:MM:00; curvas por minuto incluem o intervalo inteiro do minuto. O horizonte temporal mantém datas completas. Percentuais de candidato excluem brancos, nulos e votos em separado do denominador nominal.')
    doc.heading('Controle descritivo adicional por UF',3)
    doc.table(['Modelo municipal, pesos iguais','1º turno','2º turno'],[
        ['Minutos por multiplicar o eleitorado por 10, controlando UF e indicador de capital',_number(c1['ols_minutes_per_10x_electorate']),_number(c2['ols_minutes_per_10x_electorate'])],
        ['Indicador de capital: diferença em minutos, controlando UF e log10 do eleitorado',_number(c1['ols_capital_minutes_vs_noncapital']),_number(c2['ols_capital_minutes_vs_noncapital'])],
    ])
    doc.paragraph('A regressão é um ajuste linear descritivo da mediana municipal por log10 do eleitorado, indicador de capital e interceptos de UF. Usa '+_number(c1['municipalities'],0)+' municípios domésticos com igual peso por turno. Difere da ponderação por seções das tabelas agregadas; coeficientes não são efeitos causais. A comparação capital/interior tem suporte limitado em faixas de tamanho semelhantes, e características não observadas podem explicar associações. Não foram usados testes de significância como substitutos de magnitude: o universo observado é censitário, condicionado à cobertura dos arquivos.')
    doc.bullets([
        'Os quantitativos são finais na extração, associados retrospectivamente ao horário da seção. Substituições de BUs, retotalizações e publicações sucessivas não são reconstruídas integralmente.',
        'Geografia e porte eleitoral não equivalem a renda, idade, escolaridade, perfil urbano/rural ou comportamento individual. Nenhuma dessas características foi adicionada de outra fonte.',
        'Diferenças no ritmo registrado não identificam, por si só, causas técnicas ou administrativas. Tampouco demonstram que eleitores mudaram de preferência enquanto a apuração avançava.',
        'A decomposição depende de usar regiões, UFs ou municípios. Os componentes são contábeis, não percentuais causais de explicação.',
        'Os hashes das duas entradas foram conferidos contra o replay antes desta análise; o banco derivado é lido sem modificar as fontes.'
    ])
    doc.heading('Arquivos de evidência e reprodução',3)
    doc.table(['Arquivo','Onde conferir'],[
        ['[analysis-manifest.json](analysis-manifest.json)','Proveniência, hashes, cobertura, capitais e definição de porte'],
        *([['[independent-validation.json](independent-validation.json)','Conferência independente dos marcos e horários contra o banco do replay original']] if validation else []),
        ['[national-milestones.csv](national-milestones.csv)','Progresso nacional/estadual e percentuais de Lula/Flávio; colunas scope e requested_sections_percentage'],
        ['[milestone-composition.csv](milestone-composition.csv)','Pesos geográficos corrente/final e conclusão própria de cada grupo'],
        ['[timing-summary.csv](timing-summary.csv)','t10/t50/t90/t99 por região, UF, capital e faixa; comparações dentro de UF'],
        ['[clock-completion.csv](clock-completion.csv)','Cobertura em HH:MM:00; referência temporal explícita'],
        ['[composition-decomposition.csv](composition-decomposition.csv)','componentes composition_effect_pp e within_group_effect_pp'],
        ['[sp-municipality-contributions.csv](sp-municipality-contributions.csv)','Pesos de municípios de SP e centered_composition_contribution_pp'],
        ['[municipality-controls.json](municipality-controls.json)','Correlações e coeficientes municipais com e sem controle por UF'],
        ['[municipality-timing.csv](municipality-timing.csv)','Mediana, faixa, eleitorado e indicador de capital de cada município'],
        ['[geographic-minute.csv](geographic-minute.csv)','Séries completas por minuto de regiões e UFs'],
    ])
    doc.paragraph('A suíte de validação da implementação cobre cálculos do replay e da análise geográfica, inclusive empates temporais, ponderação nominal, decomposição e preservação dos dados. Essas verificações não são certificação externa das fontes.')
    if validation:
        checks=validation['checks']
        doc.paragraph('Nesta execução, a conferência independente comparou '+_number(checks['core'],0)+' valores dos marcos e '+_number(checks['fixed_clock'],0)+' valores de horários fixos ao banco do replay; divergências: '+_number(validation['mismatches'],0)+'. Também verificou os coeficientes do ajuste municipal por outro método numérico. O resultado completo está em `independent-validation.json`.')
    doc.paragraph('Na raiz do repositório, com o replay original concluído e as dependências de análise instaladas:')
    doc.code('PYTHONPATH=src python3 -m election_replay.geography_run --output output/geography-new')
    doc.paragraph('A pasta de saída deve ser nova. A reprodução gera tabelas, gráficos e este relatório a partir das mesmas regras. Em novas extrações ou alterações de cobertura, as conclusões devem ser reavaliadas junto com os valores recalculados.')
    return doc.save()
