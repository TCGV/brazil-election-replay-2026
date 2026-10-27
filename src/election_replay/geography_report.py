"""Stage 2: geographic/electoral composition, rendered as Markdown and HTML."""
from __future__ import annotations

import base64
from collections import Counter
import csv
from datetime import datetime
import html
import json
from pathlib import Path
import re
import unicodedata

PRIMARY = 'first_partial_totalization'
ALTERNATIVE = 'bu_received'
PROGRESS = (10, 25, 50, 75, 90, 99, 100)
REGIONS = ('Norte', 'Nordeste', 'Centro-Oeste', 'Sudeste', 'Sul', 'Exterior')
SIZE_BANDS = (('<=10k', 'Até 10 mil'), ('10k-50k', 'Mais de 10 a 50 mil'),
              ('50k-200k', 'Mais de 50 a 200 mil'), ('200k-1m', 'Mais de 200 mil a 1 milhão'),
              ('>1m', 'Mais de 1 milhão'))
CANDIDATES = (('13', 'Lula', 'lula'), ('22', 'Flávio Bolsonaro', 'flavio'))
NULL_LABELS = {'global': 'nacional', 'within_uf': 'dentro da UF'}
DIMENSION_LABELS = {'region': 'avanço regional', 'uf': 'avanço da UF',
                    'capital_status': 'capital versus demais municípios',
                    'size_band': 'porte municipal', 'candidate': 'percentual do candidato'}
UF_NAMES = {'AC':'Acre','AL':'Alagoas','AM':'Amazonas','AP':'Amapá','BA':'Bahia',
            'CE':'Ceará','DF':'Distrito Federal','ES':'Espírito Santo','GO':'Goiás',
            'MA':'Maranhão','MG':'Minas Gerais','MS':'Mato Grosso do Sul','MT':'Mato Grosso',
            'PA':'Pará','PB':'Paraíba','PE':'Pernambuco','PI':'Piauí','PR':'Paraná',
            'RJ':'Rio de Janeiro','RN':'Rio Grande do Norte','RO':'Rondônia','RR':'Roraima',
            'RS':'Rio Grande do Sul','SC':'Santa Catarina','SE':'Sergipe','SP':'São Paulo',
            'TO':'Tocantins'}


def _number(value, digits=2):
    if value in (None, ''):
        return '—'
    return f'{float(value):,.{digits}f}'.replace(',', '_').replace('.', ',').replace('_', '.')


def _pct(value, digits=2):
    return _number(value, digits)+'%' if value not in (None, '') else '—'


def _clock(value):
    return datetime.fromisoformat(value).strftime('%H:%M:%S') if value else '—'


def _place(value):
    if value == 'BR':
        return 'Brasil'
    if value == 'ZZ':
        return 'Exterior (ZZ)'
    return UF_NAMES[value]+' ('+value+')' if value in UF_NAMES else value


def _group_label(row):
    dimension,name = row['dimension'],row['group']
    if dimension in {'candidate','uf'}:
        return _place(name)
    if dimension == 'capital_status':
        return {'capital':'capitais','non_capital':'demais municípios','exterior':'exterior'}.get(name,name)
    if dimension == 'size_band':
        return dict(SIZE_BANDS).get(name,name)
    return name


def _inline(value):
    text = html.escape(str(value))
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
    return re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)


def _slug(value):
    value = ''.join(c for c in unicodedata.normalize('NFD', value.lower()) if not unicodedata.combining(c))
    return re.sub(r'[^a-z0-9]+', '-', value).strip('-')


class _Document:
    def __init__(self, directory):
        self.directory = directory
        self.markdown = []
        self.body = []
        self.title = 'Etapa 2 — Composição das seções contabilizadas e evolução da apuração'

    def heading(self, text, level=2, anchor=None):
        if level == 1:
            self.title = text
        if anchor:
            self.markdown.extend([f'<a id="{anchor}"></a>', ''])
        self.markdown.extend([f'{"#"*level} {text}', ''])
        self.body.append(f'<h{level} id="{anchor or _slug(text)}">{html.escape(text)}</h{level}>')

    def paragraph(self, text):
        self.markdown.extend([text, ''])
        self.body.append(f'<p>{_inline(text)}</p>')

    def bullets(self, items):
        items = list(items)
        self.markdown.extend([f'- {item}' for item in items]+[''])
        self.body.append('<ul>'+''.join(f'<li>{_inline(item)}</li>' for item in items)+'</ul>')

    def table(self, columns, rows):
        rows = list(rows)
        def cell(value):
            return str(value).replace('|', '\\|').replace('\n', ' ')
        self.markdown.extend(['| '+' | '.join(map(cell, columns))+' |', '|'+'|'.join(['---']*len(columns))+'|'])
        self.markdown.extend('| '+' | '.join(cell(value) for value in row)+' |' for row in rows)
        self.markdown.append('')
        self.body.append('<div class="table-wrap"><table><thead><tr>'+''.join(f'<th>{_inline(c)}</th>' for c in columns)+
                         '</tr></thead><tbody>'+''.join('<tr>'+''.join(f'<td>{_inline(c)}</td>' for c in row)+'</tr>' for row in rows)+'</tbody></table></div>')

    def figure(self, name, caption):
        path = self.directory/'figures'/f'{name}.png'
        if not path.exists():
            raise ValueError(f'Report figure missing: {path}')
        self.markdown.extend([f'![{caption}](figures/{name}.png)', '', f'*{caption}*', ''])
        payload = base64.b64encode(path.read_bytes()).decode('ascii')
        self.body.append(f'<figure><img src="data:image/png;base64,{payload}" alt="{html.escape(caption)}"><figcaption>{html.escape(caption)}</figcaption></figure>')

    def code(self, text):
        self.markdown.extend(['```bash', text, '```', ''])
        self.body.append('<pre><code>'+html.escape(text)+'</code></pre>')

    def save(self):
        (self.directory/'REPORT.pt-BR.md').write_text('\n'.join(self.markdown), encoding='utf8')
        css = '''body{font-family:system-ui,Arial,sans-serif;color:#182a3b;max-width:1200px;margin:40px auto;padding:0 25px;font-size:16px;line-height:1.55}h1{line-height:1.2;font-size:36px}h2{margin-top:2em;border-bottom:2px solid #d7e2eb;padding-bottom:.3em}h3{margin-top:1.5em}a{color:#145b94}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:8px 10px;border-bottom:1px solid #d7e2eb;text-align:left}th{background:#edf3f8}.table-wrap{overflow-x:auto}figure{margin:30px 0;break-inside:avoid}img{width:100%;height:auto}figcaption{color:#496078;font-size:13px}code{background:#eff3f6;padding:1px 4px}pre{padding:15px;background:#eff3f6;white-space:pre-wrap}li{margin:.4em 0}@page{size:A4;margin:15mm 13mm}@media print{body{font-size:10pt;line-height:1.4;max-width:none;margin:0;padding:0}h1{font-size:22pt}h2{font-size:15pt;break-after:avoid}h3{break-after:avoid}table{font-size:8pt}thead{display:table-header-group}tr{break-inside:avoid}th,td{padding:4px}img{max-height:190mm;object-fit:contain}figure{margin:15px 0}a{text-decoration:none;color:inherit}pre{font-size:8pt}}'''
        page = '<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(self.title)+'</title><style>'+css+'</style><body>'+''.join(self.body)+'</body></html>'
        (self.directory/'report.html').write_text(page, encoding='utf8')
        return ['REPORT.pt-BR.md', 'report.html']


def _status(row):
    if row is None:
        return 'não executado'
    return {'detected': 'desvio detectado', 'not_detected': 'desvio não detectado',
            'NA': 'não aplicável', 'not_applicable': 'não aplicável',
            'sensitivity_only': 'sensibilidade BU', 'descriptive_only': 'descritivo'}.get(row.get('status'), row.get('status', '—'))


def generate_report(output_dir: Path):
    """Generate the canonical Stage 2 MD and its supplemental standalone HTML."""
    output_dir = Path(output_dir)
    def read(name, optional=False):
        path = output_dir/name
        if optional and not path.exists():
            return []
        with path.open(encoding='utf8', newline='') as stream:
            return list(csv.DictReader(stream))
    def load(name, optional=False):
        path = output_dir/name
        return json.loads(path.read_text()) if path.exists() else (None if optional else {})

    timing = read('timing-summary.csv')
    milestones = read('national-milestones.csv')
    composition = read('milestone-composition.csv')
    decomposition = read('composition-decomposition.csv')
    municipality = read('sp-municipality-contributions.csv')
    clocks = read('clock-completion.csv')
    uf_milestones = read('uf-milestones.csv', optional=True)
    controls = load('municipality-controls.json')
    manifest = load('analysis-manifest.json')
    summary = load('summary.json')
    validation = load('independent-validation.json', optional=True)
    random_validation = load('randomization-validation.json', optional=True)
    random_manifest = load('randomization-manifest.json', optional=True)
    random_complete = bool(random_manifest and random_manifest.get('status') == 'completed')
    random_results = read('randomization-results.csv', optional=True) if random_complete else []
    primary_tests = [r for r in random_results if r.get('source_timestamp') == PRIMARY and str(r.get('primary_test')) in {'1', 'True', 'true'}]
    if summary.get('status') != 'completed':
        raise ValueError('Cannot report an incomplete analysis')

    def one(rows, **criteria):
        selected = [r for r in rows if all(str(r.get(key)) == str(value) for key, value in criteria.items())]
        if len(selected) != 1:
            raise ValueError(f'Expected unique report fact: {criteria}, found {len(selected)}')
        return selected[0]
    def marker(turn, progress, scope='BR', source=PRIMARY):
        return one(milestones, source_timestamp=source, turno=turn, scope=scope, requested_sections_percentage=progress)
    def group(turn, dimension, name, source=PRIMARY):
        return one(timing, source_timestamp=source, turno=turn, dimension=dimension, group=name)
    def comp(turn, progress, dimension, name, source=PRIMARY):
        return one(composition, source_timestamp=source, turno=turn, scope='BR', requested_sections_percentage=progress, dimension=dimension, group=name)
    def decomp(turn, progress, scope, dimension, source=PRIMARY):
        return one(decomposition, source_timestamp=source, turno=turn, scope=scope, dimension=dimension, requested_sections_percentage=progress)
    def test(turn, null, dimension, name, candidate='', metric=None):
        found = [r for r in primary_tests if r['turno'] == str(turn) and r['null_model'] == null and r['dimension'] == dimension and r['group'] == name
                 and (not candidate or r.get('candidate') == candidate) and (metric is None or r['metric'] == metric)]
        if len(found) > 1:
            raise ValueError(f'Ambiguous randomization test: {turn}/{null}/{dimension}/{name}/{candidate}')
        return found[0] if found else None
    def test_cells(row):
        return [_status(row), _number(row.get('observed_statistic_pp'), 3) if row else '—']
    def candidate_pair(row):
        return _pct(row.get('lula_percentage'))+' / '+_pct(row.get('flavio_percentage'))
    def national_at_clock(turn, clock):
        rows = [r for r in clocks if r['source_timestamp'] == PRIMARY and r['turno'] == str(turn) and r['dimension'] == 'region' and r['clock'] == clock]
        return 100*sum(int(r['cumulative_sections']) for r in rows)/sum(int(r['total_sections']) for r in rows)
    def capital_contrasts(turn):
        rows = {r['group']: r for r in timing if r['source_timestamp'] == PRIMARY and r['turno'] == str(turn) and r['dimension'] == 'uf_capital_status'}
        paired = [float(rows[uf+'|capital']['t50_minutes'])-float(rows[uf+'|non_capital']['t50_minutes'])
                  for uf in sorted({key.split('|')[0] for key in rows}) if uf+'|capital' in rows and uf+'|non_capital' in rows]
        return sum(value < 0 for value in paired), len(paired)
    def pattern(turn, dimension, name):
        differences = [float(comp(turn, p, dimension, name)['section_completion_percentage'])-float(comp(turn, p, dimension, name)['actual_sections_percentage']) for p in (10,25,50,75,90)]
        if all(value > 1e-9 for value in differences):
            return 'adiantado em todos os marcos'
        if all(value < -1e-9 for value in differences):
            return 'atrasado em todos os marcos'
        return 'posição heterogênea entre marcos'
    def uf_point(turn, uf, progress):
        return one(uf_milestones, source_timestamp=PRIMARY, turno=turn, scope=uf, requested_sections_percentage=progress)
    def sp_cities(turn, progress=10, source=PRIMARY):
        return [r for r in municipality if r['source_timestamp'] == source and r['turno'] == str(turn) and r['requested_sections_percentage'] == str(progress)]
    def city_mix(turn):
        rows = sp_cities(turn)
        capital = one(rows, is_capital=1)
        rest = [r for r in rows if r['is_capital'] == '0']
        wc = sum(float(r['current_nominal_weight_percentage']) for r in rest)
        wf = sum(float(r['final_nominal_weight_percentage']) for r in rest)
        current = sum(float(r['current_nominal_weight_percentage'])*float(r['lula_percentage'] or 0) for r in rest)/wc
        final = sum(float(r['final_nominal_weight_percentage'])*float(r['lula_final_percentage']) for r in rest)/wf
        return capital, current, final

    turns = sorted({r['turno'] for r in milestones if r['scope'] == 'BR'}, key=int)
    ufs = sorted({r['group'] for r in composition if r['dimension'] == 'uf' and r['group'] != 'ZZ'})
    regions = [region for region in REGIONS if any(r['dimension'] == 'region' and r['group'] == region for r in composition)]
    bands = [(code,label) for code,label in SIZE_BANDS if any(r['dimension'] == 'size_band' and r['group'] == code for r in composition)]
    doc = _Document(output_dir)
    doc.heading('Etapa 2 — Composição das seções contabilizadas e evolução da apuração', 1)
    doc.paragraph('[Índice do estudo](../README.md) · [Etapa 1 — Reconstrução minuto a minuto](../report.md)')
    doc.paragraph('**Registro principal em Markdown do segundo passo do estudo.** A etapa 1 reconstruiu os votos minuto a minuto. Esta etapa examina **quem estava representado no acumulado em cada momento** — regiões, UFs, capitais e porte dos municípios — e como essa combinação se relacionou aos percentuais dos candidatos nos dois turnos. PDF e HTML são formatos complementares.')
    doc.paragraph('Neste documento, “demografia da apuração” significa **composição territorial e porte eleitoral das seções contabilizadas**. Não significa renda, idade, escolaridade ou população residente. A referência principal é a primeira totalização parcial; o recebimento do BU é uma sensibilidade. Todos os horários permanecem em Hora TSE, sem offset UTC confirmado.')
    doc.heading('Leitura do estudo', 2, 'leitura')
    doc.bullets([f'[{label}](#{anchor})' for label,anchor in [
        ('1. Síntese dos padrões e da evidência', 'sintese'), ('2. Participação de todas as regiões', 'regioes'),
        ('3. Ritmo e percentuais por UF', 'ufs'), ('4. Capitais e porte dos municípios', 'cidades'),
        ('5. Composição territorial e mudança dos percentuais', 'percentuais'), ('6. Referência formal de aleatoriedade', 'aleatoriedade'),
        ('7. Sensibilidade e limites de interpretação', 'limites'), ('8. Evidências, método e reprodução', 'reproducao')]])

    doc.heading('1. Síntese dos padrões e da evidência', 2, 'sintese')
    matrix = []
    for turn in turns:
        ne = marker(turn,50)
        cap = group(turn,'capital_status','capital')
        interior = group(turn,'capital_status','non_capital')
        control = one(controls,source=PRIMARY,turno=turn)
        sp0,spf = marker(turn,10,'SP'),marker(turn,100,'SP')
        matrix.extend([
            [turn+'º','Nordeste no marco nacional de 50%',_pct(ne['ne_sections_completion_percentage'])+' das próprias seções; peso nominal '+_pct(ne['ne_weight_percentage']),_status(test(turn,'global','region','Nordeste'))],
            [turn+'º','Capitais versus demais municípios','t50 '+_clock(cap['t50'])+' / '+_clock(interior['t50']),_status(test(turn,'within_uf','capital_status','capital'))],
            [turn+'º','Porte versus mediana municipal','Spearman '+_number(control['spearman_size_vs_t50'],3)+'; ranks ajustados por UF '+_number(control['within_uf_rank_correlation'],3),'associação descritiva; testes por faixa na seção 4'],
            [turn+'º','Lula em SP, de 10% ao final',_pct(sp0['lula_percentage'])+' → '+_pct(spf['lula_percentage'])+' ('+_number(float(spf['lula_percentage'])-float(sp0['lula_percentage']))+' pp)',_status(test(turn,'within_uf','candidate','SP','13'))],
        ])
    doc.table(['Turno','Recorte','Magnitude / evidência observada','Referência aleatória'],matrix)
    if random_complete:
        statuses=Counter(row['status'] for row in primary_tests)
        doc.paragraph('**Resultado formal em uma leitura:** '+str(len(primary_tests))+' curvas primárias; '+str(statuses.get('detected',0))+' com desvio detectado e '+str(statuses.get('not_detected',0))+' sem desvio detectado após Holm a 5%. As exceções abaixo identificam exatamente os recortes que não se afastaram de forma detectável da referência, em vez de atribuir aleatoriedade a todo um estado ou a uma faixa de cidades.')
        exceptions={}
        for row in primary_tests:
            if row['status']=='not_detected':
                exceptions.setdefault((row['turno'],row['null_model'],row['dimension'],row['group']),[]).append(row)
        if exceptions:
            descriptions=[]
            for (turn,null,dimension,name),rows in sorted(exceptions.items()):
                candidate_names=[dict((number,label) for number,label,_ in CANDIDATES).get(row.get('candidate'),row.get('candidate','')) for row in rows if row.get('candidate')]
                recorte=(('percentuais de ' if len(candidate_names)>1 else 'percentual de ')+' e '.join(candidate_names)) if candidate_names else DIMENSION_LABELS.get(dimension,dimension)
                scores=[float(row['observed_statistic_pp']) for row in rows]
                magnitude=_number(min(scores),3)+(('–'+_number(max(scores),3)) if max(scores)-min(scores)>1e-9 else '')
                descriptions.append('**'+_place(name)+', '+turn+'º turno:** '+recorte+', referência '+NULL_LABELS.get(null,null)+'; S '+magnitude+' pp.')
            doc.bullets(descriptions)
        doc.paragraph('**Desvio não detectado não é prova de aleatoriedade.** As classificações são específicas da curva, dos marcos e da referência usados; não se transferem automaticamente para outras características do mesmo território. Magnitude em pontos percentuais e significância são leituras separadas.')
    doc.paragraph('As tabelas distinguem **ordenamento observado**, **tamanho da variação** e **evidência contra uma referência aleatória específica**. Um resultado estatisticamente detectado pode ter magnitude pequena; uma correlação fraca não demonstra aleatoriedade. A falta de rejeição também não prova que a sequência seja aleatória.')
    doc.paragraph('As conclusões se referem aos arquivos desta execução. As comparações completas abaixo incluem todas as regiões e UFs; Nordeste e SP funcionam como exemplos concretos, e não como substitutos da análise nacional.')
    doc.table(['Turno','Código da eleição','Seções/turno com votos','Votos nominais'],[(turn,marker(turn,100)['election_code'],_number(marker(turn,100)['cumulative_sections'],0),_number(marker(turn,100)['cumulative_nominal_votes'],0)) for turn in turns])
    doc.paragraph('O universo contém '+_number(manifest['analysis_sections'],0)+' registros seção/turno. O mesmo local físico pode aparecer nos dois turnos. O progresso é contado por **seções**, mas percentuais dos candidatos e pesos territoriais usam **votos nominais**. Todos os empates de horário entram juntos, portanto o progresso efetivo pode exceder ligeiramente o marco solicitado. O denominador de cada tabela é indicado explicitamente.')

    doc.heading('2. Participação de todas as regiões', 2, 'regioes')
    doc.paragraph('Peso regional = votos nominais daquela região já contabilizados / votos nominais nacionais já contabilizados. Compará-lo ao peso final mostra a **representação territorial da amostra acumulada**, não quantos por cento da própria região já foram concluídos. São medidas diferentes.')
    for turn in turns:
        doc.heading(turn+'º turno — participação nos votos nominais nacionais (%)',3)
        doc.table(['Região','10%','25%','50%','75%','90%','99%','Final'],[
            [region,*[_number(comp(turn,p,'region',region)['current_nominal_weight_percentage']) for p in PROGRESS]] for region in regions])
        if all('flavio_percentage' in comp(turn,10,'region',region) for region in regions):
            doc.table(['Região','BR=10%: Lula / Flávio','BR=50%','BR=90%','Final'],[
                [region,*[candidate_pair(comp(turn,p,'region',region)) for p in (10,50,90,100)]] for region in regions])
            doc.paragraph('Na tabela de candidaturas, o denominador é o voto nominal já contado **dentro da própria região**, observado no marco nacional indicado. Essa fração não deve ser confundida com o peso da região no total brasileiro.')
        doc.heading(turn+'º turno — avanço próprio e perfil da região',3)
        doc.table(['Região','Seções concluídas quando BR=50%','t50 da região','Peso em BR=50% / final','Perfil em BR=10–90%','Teste global; S (pp)'],[
            [region,_pct(comp(turn,50,'region',region)['section_completion_percentage']),_clock(group(turn,'region',region)['t50']),
             _pct(comp(turn,50,'region',region)['current_nominal_weight_percentage'])+' / '+_pct(comp(turn,100,'region',region)['current_nominal_weight_percentage']),
             pattern(turn,'region',region),_status(test(turn,'global','region',region))+'; '+(test_cells(test(turn,'global','region',region))[1])]
            for region in regions])
    if '1' in turns and '2' in turns and 'Nordeste' in regions:
        a,b=marker(1,50),marker(2,50)
        doc.paragraph('**Nordeste como exemplo:** no marco nacional de 50%, sua conclusão própria foi '+_pct(a['ne_sections_completion_percentage'])+' no primeiro turno e '+_pct(b['ne_sections_completion_percentage'])+' no segundo; o peso nominal foi '+_pct(a['ne_weight_percentage'])+' / '+_pct(b['ne_weight_percentage'])+'. O avanço relativo foi diferente do relógio: o t50 regional ocorreu às '+_clock(group(1,'region','Nordeste')['t50'])+' / '+_clock(group(2,'region','Nordeste')['t50'])+'. As tabelas por UF impedem generalizar essa trajetória para todos os estados nordestinos.')
    doc.figure('northeast-composition','Figura 1 — Peso do Nordeste no mesmo progresso nacional; as demais regiões constam integralmente nas tabelas. A linha pontilhada indica seu peso final.')
    doc.figure('regional-completion','Figura 2 — Todas as regiões no relógio registrado, com a mesma escala temporal nos dois turnos.')

    doc.heading('3. Ritmo e percentuais por UF',2,'ufs')
    doc.paragraph('A primeira comparação fixa o **progresso do Brasil** e pergunta quão concluída estava cada UF. As tabelas seguintes fixam o **progresso da própria UF** e acompanham Lula e Flávio. Misturar essas réguas produziria comparações enganosas. Exterior (`ZZ`) permanece na composição nacional e é apresentado separadamente dos 27 recortes domésticos.')
    for turn in turns:
        doc.heading(turn+'º turno — avanço relativo das 27 UFs',3)
        doc.table(['UF','Conclusão própria: BR=10%','BR=50%','BR=90%','Peso nominal: BR=50% / final','Teste global','S (pp)'],[
            [uf,*[_pct(comp(turn,p,'uf',uf)['section_completion_percentage']) for p in (10,50,90)],
             _pct(comp(turn,50,'uf',uf)['current_nominal_weight_percentage'])+' / '+_pct(comp(turn,100,'uf',uf)['current_nominal_weight_percentage']),
             *test_cells(test(turn,'global','uf',uf))] for uf in ufs])
        adelantados=[uf for uf in ufs if pattern(turn,'uf',uf)=='adiantado em todos os marcos']
        atrasados=[uf for uf in ufs if pattern(turn,'uf',uf)=='atrasado em todos os marcos']
        heterogeneous=[uf for uf in ufs if uf not in adelantados and uf not in atrasados]
        doc.paragraph('Nos marcos nacionais de 10%, 25%, 50%, 75% e 90%, ficaram sempre relativamente adiantadas: '+(', '.join(adelantados) or 'nenhuma')+'. Sempre relativamente atrasadas: '+(', '.join(atrasados) or 'nenhuma')+'. Alternaram posição ao longo dos marcos: '+(', '.join(heterogeneous) or 'nenhuma')+'. Esta é uma descrição da trajetória, não um teste de monotonicidade ou de causalidade.')
        if uf_milestones:
            for number,name,key in CANDIDATES:
                doc.heading(turn+'º turno — '+name+' conforme o avanço da própria UF',3)
                doc.table(['UF','10%','50%','90%','Final','Variação 10% → final (pp)','Teste dentro da UF','S (pp)'],[
                    [uf,*[_pct(uf_point(turn,uf,p)[key+'_percentage']) for p in (10,50,90,100)],
                     _number(float(uf_point(turn,uf,100)[key+'_percentage'])-float(uf_point(turn,uf,10)[key+'_percentage'])),
                     *test_cells(test(turn,'within_uf','candidate',uf,number))] for uf in ufs])
        else:
            doc.paragraph('**Marcos próprios de todas as UFs não disponíveis nesta execução.** Gere `uf-milestones.csv` com a implementação atual para obter as duas candidaturas diretamente; o relatório não preenche lacunas nem infere Flávio como complemento de Lula no primeiro turno.')
    if any(r['dimension']=='uf' and r['group']=='ZZ' for r in composition):
        doc.heading('Exterior — registro separado',3)
        doc.table(['Turno','Conclusão ZZ quando BR=10%','BR=50%','BR=90%','Peso nominal em BR=50% / final'],[
            [turn+'º',*[_pct(comp(turn,p,'uf','ZZ')['section_completion_percentage']) for p in (10,50,90)],
             _pct(comp(turn,50,'uf','ZZ')['current_nominal_weight_percentage'])+' / '+_pct(comp(turn,100,'uf','ZZ')['current_nominal_weight_percentage'])] for turn in turns])
    doc.paragraph('Os percentuais de Flávio são calculados a partir dos votos do candidato 22. **No primeiro turno não se usa 100% − Lula**, pois outros candidatos fazem parte dos votos nominais.')
    doc.figure('state-timing','Figura 3 — t50 e avanço até 90% por UF; o agrupamento regional não elimina a heterogeneidade estadual.')

    doc.heading('4. Capitais e porte dos municípios',2,'cidades')
    doc.paragraph('Capital e porte são atributos territoriais das seções, não perfis individuais dos eleitores. Brasília é classificada como capital; DF não tem contraparte de interior. Porte utiliza eleitores aptos agregados no primeiro turno disponível e mantém a mesma faixa entre turnos; não utiliza população residente. Os pesos nominais abaixo têm denominador nacional; exterior fica fora das classes domésticas.')
    for turn in turns:
        doc.heading(turn+'º turno — como os tipos de cidade estavam representados',3)
        cohorts=[('capital_status','capital','Capitais'),('capital_status','non_capital','Demais municípios'),*[('size_band',code,label) for code,label in bands]]
        doc.table(['Recorte','Conclusão própria: BR=10%','BR=50%','BR=90%','Peso nominal: BR=50% / final','Teste dentro de UF','S (pp)'],[
            [label,*[_pct(comp(turn,p,dimension,name)['section_completion_percentage']) for p in (10,50,90)],
             _pct(comp(turn,50,dimension,name)['current_nominal_weight_percentage'])+' / '+_pct(comp(turn,100,dimension,name)['current_nominal_weight_percentage']),
             *test_cells(test(turn,'within_uf',dimension,name))] for dimension,name,label in cohorts])
        if all('flavio_percentage' in comp(turn,10,dimension,name) for dimension,name,_ in cohorts):
            doc.table(['Recorte','BR=10%: Lula / Flávio','BR=50%','BR=90%','Final'],[
                [label,*[candidate_pair(comp(turn,p,dimension,name)) for p in (10,50,90,100)]] for dimension,name,label in cohorts])
            doc.paragraph('Os pares Lula / Flávio usam os votos nominais já contados do próprio grupo de cidade. Mudança na fração interna e mudança no peso do grupo são mecanismos contábeis diferentes; ambos aparecem separadamente nas tabelas.')
        doc.table(['Recorte','t10','t50','t90'],[[label,*[_clock(group(turn,dimension,name)['t'+str(p)]) for p in (10,50,90)]] for dimension,name,label in cohorts])
        cap,rest=group(turn,'capital_status','capital'),group(turn,'capital_status','non_capital')
        faster,paired=capital_contrasts(turn)
        delta=float(rest['t50_minutes'])-float(cap['t50_minutes'])
        doc.paragraph('No '+turn+'º turno, o t50 agregado das capitais ocorreu '+_number(abs(delta))+' minutos '+('antes' if delta>=0 else 'depois')+' dos demais municípios. Na comparação dentro de cada UF, a capital chegou ao t50 antes do restante em '+str(faster)+' de '+str(paired)+' pares. A agregação depende da composição regional e da quantidade de seções; não é um efeito isolado de ser capital.')
    doc.figure('capital-size-timing','Figura 4 — Distribuição do horário das seções por capital e faixa eleitoral; ponto=t50 e intervalo=t10–t90.')
    doc.table(['Correlação entre porte e t50 municipal — municípios com pesos iguais',*[turn+'º turno' for turn in turns]],[
        ['Spearman global',*[_number(one(controls,source=PRIMARY,turno=turn)['spearman_size_vs_t50'],3) for turn in turns]],
        ['Relação entre ranks globais após retirar médias de UF',*[_number(one(controls,source=PRIMARY,turno=turn)['within_uf_rank_correlation'],3) for turn in turns]],
    ])
    doc.paragraph('Os valores acima medem associação entre tamanho e mediana de cada município, dando peso igual aos municípios. Eles não são a média de correlações estaduais e não têm a ponderação por seções das tabelas anteriores. Uma relação global reduzida, faixas não monotônicas ou trajetórias que mudam entre turnos são evidências contra uma regra simples de porte; **não equivalem a uma demonstração de aleatoriedade**. O teste condicionado por UF responde à pergunta adicional de quanto cada curva se afasta de um embaralhamento dentro dos estados.')

    doc.heading('5. Composição territorial e mudança dos percentuais',2,'percentuais')
    doc.paragraph('A porcentagem acumulada pode variar sem que ninguém tenha mudado de preferência: entram seções com resultados finais diferentes. Uma região pode ganhar peso e, simultaneamente, mudar a composição das seções já contadas dentro dela. A decomposição abaixo distingue essas duas contribuições contábeis.')
    doc.table(['Turno e progresso BR','Lula corrente','Flávio corrente','Lula final','Flávio final','Desvio de Lula (pp)'],[
        [turn+'º, '+str(p)+'%',_pct(marker(turn,p)['lula_percentage']),_pct(marker(turn,p)['flavio_percentage']),_pct(marker(turn,100)['lula_percentage']),_pct(marker(turn,100)['flavio_percentage']),_number(float(marker(turn,p)['lula_percentage'])-float(marker(turn,100)['lula_percentage']),3)]
        for turn in turns for p in (10,50,90)])
    doc.table(['Turno e marco BR','Desvio de Lula frente ao próprio final (pp)','Composição entre regiões (pp)','Ordenação dentro das regiões (pp)'],[
        [turn+'º, '+str(p)+'%',*[_number(decomp(turn,p,'BR','region')[field],3) for field in ('total_gap_pp','composition_effect_pp','within_group_effect_pp')]] for turn in turns for p in (10,50)])
    doc.paragraph('Os componentes variam com a granularidade geográfica: regiões, UFs e municípios produzem referências diferentes. São identidades sobre os dados fornecidos, não estimativas causais. Níveis brutos do primeiro e segundo turnos não isolam ordenação, porque o primeiro turno possui outras candidaturas; por isso a comparação utiliza o resultado final do próprio turno como referência.')
    doc.figure('composition-decomposition','Figura 5 — Composição entre territórios e ordenação interna; o agrupamento de SP utiliza municípios.')
    doc.heading('São Paulo como estudo de caso: a capital não explica tudo',3)
    doc.table(['Progresso próprio de SP',*[turn+'º: Lula / Flávio' for turn in turns]],[
        [str(p)+'%',*[_pct(marker(turn,p,'SP')['lula_percentage'])+' / '+_pct(marker(turn,p,'SP')['flavio_percentage']) for turn in turns]] for p in PROGRESS])
    caprows=[]
    for turn in turns:
        city,current_rest,final_rest=city_mix(turn)
        caprows.append([turn+'º',_pct(city['current_nominal_weight_percentage']),_pct(city['final_nominal_weight_percentage']),_pct(city['lula_final_percentage']),_pct(current_rest)+' → '+_pct(final_rest)])
    doc.table(['Turno','Capital: peso em SP=10%','Capital: peso final','Lula final na capital','Lula no restante: SP=10% → final'],caprows)
    doc.paragraph('A capital paulista foi sub-representada no início desta execução e tem uma participação final de Lula acima da média estadual. Sua entrada ajuda a descrever a subida, mas o restante do estado também muda. Isso é compatível com diferenças entre municípios e com ordenação interna, em vez de uma única oposição capital/interior. Crescimento global da curva não significa monotonicidade em todos os eventos.')
    doc.table(['Turno e progresso SP','Desvio de Lula (pp)','Composição municipal (pp)','Ordenação interna (pp)'],[
        [turn+'º, '+str(p)+'%',*[_number(decomp(turn,p,'SP','municipality')[field],3) for field in ('total_gap_pp','composition_effect_pp','within_group_effect_pp')]] for turn in turns for p in (10,50)])
    top=[]
    for turn in turns:
        for row in sorted(sp_cities(turn),key=lambda r:float(r['centered_composition_contribution_pp']))[:3]:
            top.append([turn+'º',row['municipality_name'],_pct(row['current_nominal_weight_percentage']),_pct(row['final_nominal_weight_percentage']),_number(row['centered_composition_contribution_pp'],3)])
    doc.table(['SP=10%','Município','Peso corrente','Peso final','Contribuição centrada (pp)'],top)
    doc.paragraph('A contribuição individual usa o percentual municipal centrado no resultado estadual final. Um termo negativo pode representar um município mais favorável a Lula ainda sub-representado ou um município menos favorável já super-representado. Os termos não centrados, preservados no CSV, não são interpretados isoladamente porque podem se cancelar.')
    doc.figure('candidate-shares','Figura 6 — Percentuais de ambos os candidatos no Brasil e em SP em marcos de progresso; as tabelas da seção 3 estendem a leitura às demais UFs.')

    doc.heading('6. Referência formal de aleatoriedade',2,'aleatoriedade')
    if not random_complete:
        state=random_manifest.get('status') if random_manifest else None
        doc.paragraph('**Teste de aleatoriedade '+('não concluído (status: '+str(state)+')' if state else 'não executado nesta reprodução')+'.** As conclusões descritivas anteriores não substituem esse teste. Nenhum grupo é declarado aleatório por ausência de correlação. Para executar a referência formal, utilize `--randomizations 4999 --seed 20261027`.')
    else:
        usable=[r for r in primary_tests if r['status'] not in {'NA','not_applicable'}]
        counts=Counter(r['status'] for r in usable)
        nperms=int(primary_tests[0]['permutations']) if primary_tests else int(random_manifest.get('permutations',0))
        seed=primary_tests[0].get('seed',random_manifest.get('seed')) if primary_tests else random_manifest.get('seed')
        doc.paragraph('Foram realizadas '+_number(nperms,0)+' permutações por configuração, com semente '+str(seed)+'. Na referência principal, '+str(counts.get('detected',0))+' curvas tiveram desvio detectado e '+str(counts.get('not_detected',0))+' não tiveram desvio detectado após o ajuste de Holm a 5%; '+str(len(primary_tests)-len(usable))+' hipóteses ficaram não aplicáveis. As hipóteses dos dois turnos integram a mesma família de testes primários.')
        doc.paragraph('A resolução mínima do p-valor Monte Carlo é '+_number(1/(nperms+1),6)+'. Resultados no piso não fornecem precisão adicional sobre quão pequeno seria o p-valor com mais permutações. A coluna S mede o afastamento máximo em pontos percentuais da referência média conjunta, não a variação do candidato entre o começo e o fim da contagem.')
        table=[]
        families=sorted({(r['turno'],r['null_model'],r['dimension']) for r in primary_tests})
        for turn,null,dimension in families:
            rows=[r for r in primary_tests if (r['turno'],r['null_model'],r['dimension'])==(turn,null,dimension)]
            statuses=Counter(r['status'] for r in rows)
            table.append([turn+'º',NULL_LABELS.get(null,null),DIMENSION_LABELS.get(dimension,dimension),statuses.get('detected',0),statuses.get('not_detected',0),sum(statuses.get(key,0) for key in ('NA','not_applicable'))])
        doc.table(['Turno','Referência','Família de curvas','Desvio detectado','Não detectado','Não aplicável'],table)
        doc.heading('Percentuais nacionais: desvio além da composição estadual preservada?',3)
        country=[r for r in primary_tests if r['dimension']=='candidate' and r['group']=='BR']
        doc.table(['Turno','Candidato','Referência','Máximo desvio S (pp)','p ajustado (Holm)','Resultado'],[
            [r['turno']+'º',dict((n,name) for n,name,_ in CANDIDATES).get(r.get('candidate'),r.get('candidate','—')),NULL_LABELS.get(r['null_model'],r['null_model']),_number(r['observed_statistic_pp'],3),_number(r.get('p_adjusted'),4),_status(r)]
            for r in sorted(country,key=lambda r:(int(r['turno']),r.get('candidate',''),r['null_model']))])
        not_detected=[r for r in primary_tests if r['status']=='not_detected']
        doc.heading('Onde não foi detectado afastamento da referência',3)
        if not_detected:
            doc.table(['Turno','Referência','Dimensão / recorte','Candidato','S observado (pp)','p ajustado'],[
                [r['turno']+'º',NULL_LABELS.get(r['null_model'],r['null_model']),DIMENSION_LABELS.get(r['dimension'],r['dimension'])+' / '+_group_label(r),dict((number,name) for number,name,_ in CANDIDATES).get(r.get('candidate'),'—'),_number(r['observed_statistic_pp'],3),_number(r.get('p_adjusted'),4)]
                for r in sorted(not_detected,key=lambda r:(int(r['turno']),r['null_model'],r['dimension'],r['group'],r.get('candidate','')))])
        else:
            doc.paragraph('Nenhuma das curvas primárias aplicáveis ficou na categoria “desvio não detectado” nesta execução. Isso não transforma todas as magnitudes em grandes: os desvios em pontos percentuais e as associações descritivas continuam necessários para julgar relevância prática.')
        na=[r for r in primary_tests if r['status'] in {'NA','not_applicable'}]
        if na:
            doc.paragraph('Não aplicáveis: '+'; '.join(r['turno']+'º / '+NULL_LABELS.get(r['null_model'],r['null_model'])+' / '+DIMENSION_LABELS.get(r['dimension'],r['dimension'])+' / '+_group_label(r)+(' / '+r.get('candidate','') if r.get('candidate') else '') for r in na)+'. Uma curva invariável sob o embaralhamento não fornece um teste informativo e não deve receber o rótulo “aleatória”.')
        for name,caption in [
            ('randomization-candidate-reference','Referência aleatória dos percentuais nacionais dos candidatos nos dois turnos. Envelopes de 95% ponto a ponto; não são intervalos populacionais nem bandas simultâneas. A decisão formal utiliza o teste da curva com Holm.'),
            ('randomization-city-reference','Capital e faixas de porte diante do embaralhamento dentro de UF. Os desvios são relativos à referência condicionada, não necessariamente a uma linha horizontal final. Os envelopes são ponto a ponto.'),
        ]:
            if (output_dir/'figures'/f'{name}.png').exists():
                doc.figure(name,caption)
    doc.heading('O que os dois embaralhamentos preservam',3)
    doc.paragraph('Os rótulos legíveis “nacional” e “dentro da UF” correspondem aos identificadores `null_model=global` e `null_model=within_uf` nos CSVs. As famílias de curvas usam `dimension=region`, `uf`, `capital_status`, `size_band` ou `candidate`; os identificadores são mantidos nas evidências para reprodução.')
    doc.bullets([
        '**Global:** a seção completa troca de slot de horário com qualquer outra seção; examina ordenação entre regiões e UFs. Votos, município, capital e porte permanecem juntos.',
        '**Dentro de UF:** troca de slots apenas entre seções da mesma UF. O avanço estadual observado é preservado; capital/porte e percentuais dos candidatos são comparados à sua referência condicionada. A referência não precisa ser uma linha horizontal no percentual final.',
        'Os horários disponíveis e seus empates permanecem: os tamanhos dos lotes temporais são preservados. O embaralhamento de seções não preserva os agrupamentos geográficos e operacionais originalmente presentes dentro desses lotes.',
        'Marcos formais: 10%, 25%, 50%, 75%, 90% e 99%. Brasil utiliza progresso nacional; cada UF utiliza o próprio progresso. Recebimento do BU reaproveita os mesmos índices aleatórios como sensibilidade, sem constituir amostra independente ou oportunidade de selecionar o menor p-valor.',
        'Cada curva é centrada pela média ponto a ponto das B+1 realizações, incluindo a observada. Para todas as realizações aplica-se simetricamente S = máximo desvio absoluto dessa média. O p-valor Monte Carlo usa (1 + número de estatísticas permutadas ao menos tão extremas) / (B+1).',
        'Os envelopes 2,5–97,5% das permutações são referências aleatórias ponto a ponto; não são bandas simultâneas nem intervalos de confiança de uma população. A decisão é o teste da curva com ajuste múltiplo, não a inspeção de um ponto fora do envelope.',
        'Um p ajustado acima de 0,05 significa que não foi detectado desvio desta referência com este desenho e resolução. Não prova aleatoriedade ou equivalência. Diferença entre os resultados de rejeição dos turnos não demonstra diferença estatisticamente significativa entre turnos.',
    ])

    doc.heading('7. Sensibilidade e limites de interpretação',2,'limites')
    doc.table(['Indicador','1º: totalização / recebimento','2º: totalização / recebimento'],[
        ['Peso NE quando BR=50%',_pct(marker(1,50)['ne_weight_percentage'])+' / '+_pct(marker(1,50,source=ALTERNATIVE)['ne_weight_percentage']),_pct(marker(2,50)['ne_weight_percentage'])+' / '+_pct(marker(2,50,source=ALTERNATIVE)['ne_weight_percentage'])],
        ['Composição municipal SP quando SP=10% (pp)',_number(decomp(1,10,'SP','municipality')['composition_effect_pp'],3)+' / '+_number(decomp(1,10,'SP','municipality',source=ALTERNATIVE)['composition_effect_pp'],3),_number(decomp(2,10,'SP','municipality')['composition_effect_pp'],3)+' / '+_number(decomp(2,10,'SP','municipality',source=ALTERNATIVE)['composition_effect_pp'],3)],
    ])
    if random_complete:
        sensitivity=[r for r in random_results if r['source_timestamp']==ALTERNATIVE and r['status']=='sensitivity_only']
        doc.paragraph('Os resultados de BU da referência aleatória estão identificados como sensibilidade em `randomization-results.csv` ('+str(len(sensitivity))+' curvas), sem uma segunda decisão primária por Holm. Não se escolhe o horário pelo p-valor mais favorável.')
    doc.table(['Indicador temporal','1º turno','2º turno'],[
        ['Seções nacionais contabilizadas às 19:00:00',_pct(national_at_clock(1,'19:00'),3),_pct(national_at_clock(2,'19:00'),3)],
        ['Brasil: horário de 10% / 90%',_clock(marker(1,10)['cutoff_timestamp'])+' / '+_clock(marker(1,90)['cutoff_timestamp']),_clock(marker(2,10)['cutoff_timestamp'])+' / '+_clock(marker(2,90)['cutoff_timestamp'])],
    ])
    doc.paragraph('O trecho inicial horizontal do segundo turno cobre pouquíssimas seções nos horários registrados. Estabilidade visual nesse trecho não significa representatividade ampla. Os arquivos mostram o desenho temporal, mas não identificam a causa operacional. “Mais cedo” relativo ao progresso nacional não é sinônimo de mais cedo no relógio.')
    doc.bullets([
        'Os votos finais da extração são atribuídos retrospectivamente ao horário da seção. O replay não reconstrói integralmente substituições de BUs, retotalizações ou publicações sucessivas do painel público.',
        'As diferenças geográficas não identificam renda, idade, escolaridade, perfil urbano/rural ou mecanismos individuais; não foram acrescentadas essas fontes. Também não mostram eleitores mudando de preferência durante a apuração.',
        'Os resultados são descritivos e os testes usam uma referência explícita de troca livre de seções, não uma amostra probabilística da população. Detectar ordenação não identifica sua causa.',
        'A decomposição depende da granularidade do agrupamento; seus componentes não são percentuais causais de explicação. Significância e magnitude prática são apresentadas separadamente.',
    ])

    doc.heading('8. Evidências, método e reprodução',2,'reproducao')
    doc.heading('Identidade da decomposição',3)
    doc.paragraph('Se w_g(t) é o peso do grupo g nos votos nominais já contados, p_g(t) a fração de Lula dentro dele e p_g(F) sua fração final, o contrafactual contábil é C(t) = Σ_g w_g(t) p_g(F). Composição = C(t) − P(F); ordenação interna = P(t) − C(t); desvio total = P(t) − P(F). A soma dos dois componentes é verificada numericamente. As tabelas expressam as diferenças em pontos percentuais.')
    doc.paragraph('A contribuição municipal centrada é [w_g(t) − w_g(F)] × [p_g(F) − P(F)], com a mesma soma total da composição. O t50 é o primeiro instante em que ao menos metade das seções do grupo entrou; empates são incluídos integralmente. Horários fixos incluem até HH:MM:00 e as curvas por minuto incluem o minuto completo. Percentuais nominais não incluem brancos, nulos e separados no denominador.')
    doc.heading('Controle municipal adicional',3)
    doc.table(['Modelo com pesos iguais por município',*[turn+'º turno' for turn in turns]],[
        ['Minutos por eleitorado 10 vezes maior, ajustando UF e capital',*[_number(one(controls,source=PRIMARY,turno=turn)['ols_minutes_per_10x_electorate']) for turn in turns]],
        ['Indicador de capital: diferença em minutos, ajustando UF e log10 do eleitorado',*[_number(one(controls,source=PRIMARY,turno=turn)['ols_capital_minutes_vs_noncapital']) for turn in turns]],
    ])
    doc.paragraph('Esse ajuste linear da mediana municipal usa log10 do eleitorado, indicador de capital e interceptos de UF. Dá igual peso a cada município; não tem a ponderação por seções das tabelas agregadas. O suporte de comparações entre capitais e demais municípios de porte semelhante é limitado. Os coeficientes são associações condicionais, não efeitos causais.')
    evidence=[
        ('analysis-manifest.json','Proveniência, hashes das fontes e da implementação, cobertura, capitais e porte'),
        ('independent-validation.json','Conferência independente dos marcos, horários e ajustes contra o replay original'),
        ('uf-milestones.csv','Marcos próprios de cada UF: percentuais reais de Lula e Flávio, denominadores e cobertura'),
        ('national-milestones.csv','Brasil/SP: progresso próprio, percentuais e representação do Nordeste'),
        ('milestone-composition.csv','Participação e avanço por região, UF, capital e porte em marcos nacionais'),
        ('timing-summary.csv','t10/t50/t90/t99 e totais por grupo, inclusive comparações dentro de UF'),
        ('clock-completion.csv','Cobertura em horários fixos e percentuais dos dois candidatos'),
        ('geographic-minute.csv','Séries completas de regiões e UFs, percentuais acumulados e entrantes'),
        ('composition-decomposition.csv','Componentes entre grupos e de ordenação interna'),
        ('sp-municipality-contributions.csv','Pesos municipais de SP e contribuições centradas'),
        ('municipality-controls.json','Correlações e coeficientes com e sem ajuste por UF'),
        ('municipality-timing.csv','Mediana, eleitorado, porte e capital de cada município'),
        ('randomization-manifest.json','Definições dos nulos, configurações, semente, permutações e status'),
        ('randomization-validation.json','Auditoria independente das curvas observadas, estatísticas, p-valores e ajuste múltiplo'),
        ('randomization-results.csv','Estatísticas por curva, p-valores, Holm e classificação'),
        ('randomization-bands.csv','Observado e envelopes aleatórios ponto a ponto; pesos nominais descritivos'),
    ]
    doc.table(['Arquivo','Onde conferir'],[(f'[{name}]({name})',description) for name,description in evidence if (output_dir/name).exists()])
    if validation:
        checks=validation['checks']
        doc.paragraph('A conferência independente comparou '+_number(checks.get('core'),0)+' valores dos marcos e '+_number(checks.get('fixed_clock'),0)+' de horários fixos; divergências: '+_number(validation.get('mismatches'),0)+'. O ajuste municipal foi resolvido por outro método numérico. Os testes da implementação também cobrem empates, ponderação nominal, preservação das fontes e denominadores do primeiro turno. Essas verificações não autenticam externamente as fontes.')
    if random_validation:
        checks=random_validation.get('checks',{})
        doc.paragraph('A auditoria independente das permutações confrontou '+_number(checks.get('observed_curve_values'),0)+' valores observados e '+_number(checks.get('observed_progress'),0)+' progressos com o replay original; verificou '+_number(checks.get('plus_one_p'),0)+' p-valores Monte Carlo, '+_number(checks.get('observed_score'),0)+' estatísticas observadas e '+_number(checks.get('holm_adjusted_p'),0)+' ajustes de Holm, além dos centros e contagens dos '+_number(checks.get('simulation_cache_files'),0)+' arquivos de curvas simuladas. Divergências: '+_number(random_validation.get('mismatches'),0)+', com tolerância numérica '+str(random_validation.get('absolute_numeric_tolerance'))+'. Essa auditoria recalcula os resultados a partir das curvas simuladas retidas; não gera uma segunda sequência independente de atribuições aleatórias.')
    doc.paragraph('Para reproduzir as tabelas, figuras e este registro com os testes formais, use uma pasta nova, com o replay original concluído e as dependências de análise instaladas:')
    doc.code('PYTHONPATH=src python3 -m election_replay.geography_run --output output/geography-step2 --randomizations 4999 --seed 20261027')
    doc.paragraph('Sem `--randomizations`, o fluxo mantém a análise descritiva e identifica explicitamente que a referência aleatória não foi executada. As fontes originais são abertas somente para leitura; hashes, semente e parâmetros permitem rastrear a execução. Em novas extrações, refaça os cálculos e revise as conclusões, sem transportar automaticamente as interpretações desta fotografia de dados.')
    return doc.save()
