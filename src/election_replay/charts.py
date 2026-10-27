"""Dependency-free SVG exports and a self-contained interactive replay report.

CSV files remain authoritative. Only chart points may be reduced, with bucket
extrema and the first/last point preserved; no vote counts are interpolated.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re


SOURCES = {
    "replay-first-totalization-minute.csv": (
        "first_partial_totalization", "Primeira totalização"
    ),
    "replay-bu-received-minute.csv": ("bu_received", "Recebimento do BU"),
}
# Explicit candidate numbers keep the requested colors stable across rounds,
# timestamp sources, metrics, and changes to the remaining candidate list.
CANDIDATE_COLORS = {"13": "#c62828", "22": "#1565c0"}
COLORS = ["#2e7d32", "#7b1fa2", "#ef6c00", "#00838f", "#ad1457", "#5d4037",
          "#455a64", "#6a6f00", "#3150a2", "#9c5800", "#607d8b"]
CAUTION = (
    "Reconstrução retrospectiva aproximada; não representa o histórico certificado "
    "de publicações do TSE. Hora TSE conforme o arquivo; fuso/offset não confirmado."
)
PERCENTAGE_CAVEAT = (
    "Percentuais: apenas votos nominais com horário nesta série; votos excluídos "
    "podem existir. Não é percentual sobre todos os votos finais."
)
SYNTHETIC_HEADING = "DEMONSTRAÇÃO SINTÉTICA — não são resultados eleitorais"


def _reduce(points: list[list], budget: int = 2400) -> list[list]:
    """Preserve endpoints and percentage/count extrema in chronological buckets."""
    if len(points) <= budget:
        return points
    selected = {0, len(points) - 1}
    width = max(1, (len(points) + budget // 6 - 1) // (budget // 6))
    for start in range(0, len(points), width):
        end = min(len(points), start + width)
        selected.update((start, end - 1))
        for column in (2, 3):
            usable = [i for i in range(start, end) if points[i][column] is not None]
            if usable:
                selected.add(min(usable, key=lambda i: points[i][column]))
                selected.add(max(usable, key=lambda i: points[i][column]))
    return [points[i] for i in sorted(selected)]


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", value)


def _read(output_dir: Path) -> list[dict]:
    """Two-pass sampling: memory is bounded by 2,400 points per series.

    The pipeline writes each series chronologically, including minute rows
    interleaved with other candidates. Reject nonchronological input rather than
    silently drawing incorrect paths or sorting an unbounded number of rows.
    """
    grouped: dict[tuple, dict] = {}
    epoch = datetime(1970, 1, 1)

    def rows():
        for filename, (source, label) in SOURCES.items():
            path = output_dir / filename
            if not path.exists():
                continue
            with path.open(encoding="utf-8-sig", newline="") as stream:
                for row in csv.DictReader(stream):
                    if row.get("vote_class", "nominal") not in {
                        "nominal", "candidate", "candidato"
                    }:
                        continue
                    if row.get("uf_scope", "BR") != "BR" or not row.get("minute"):
                        continue
                    key = row["election_code"], row["turno"], source, row["nr_votavel"]
                    yield key, label, row

    # Pass one counts without retaining unreduced minute points.
    for key, label, row in rows():
        election, turn, source, candidate = key
        series = grouped.setdefault(key, {
            "election": election, "turn": turn, "source": source,
            "source_label": label, "candidate": candidate,
            "name": row.get("nm_votavel") or candidate, "points": [],
            "original_count": 0,
        })
        series["original_count"] += 1

    states = {}
    for key, series in grouped.items():
        count = series["original_count"]
        width = 1 if count <= 2400 else (count + 399) // 400
        states[key] = {"index": 0, "width": width, "bucket": {}, "last_tick": None}

    def flush(key):
        bucket = states[key]["bucket"]
        selected = {index: point for index, point in bucket.values()}
        grouped[key]["points"].extend(selected[index] for index in sorted(selected))
        bucket.clear()

    # Pass two retains only first/last and min/max percentage/count per bucket.
    for key, _, row in rows():
        state = states[key]
        index = state["index"]
        if index and index % state["width"] == 0:
            flush(key)
        moment = datetime.fromisoformat(row["minute"])
        # Coordinate only: do not assert that Hora TSE is UTC.
        if moment.tzinfo is not None:
            moment = moment.replace(tzinfo=None)
        tick = int((moment - epoch).total_seconds() * 1000)
        if state["last_tick"] is not None and tick < state["last_tick"]:
            raise ValueError(f"Chart CSV must be chronological within each series: {key}")
        state["last_tick"] = tick
        pct = row.get("percentage_valid_votes", "")
        point = [tick, row["minute"], float(pct) if pct else None,
                 int(row["cumulative_votes"]), int(row["cumulative_sections"])]
        bucket = state["bucket"]
        bucket.setdefault("first", (index, point))
        bucket["last"] = index, point
        for column in (2, 3):
            if point[column] is None:
                continue
            for operation in ("min", "max"):
                label = operation, column
                old = bucket.get(label)
                better = old is None or (point[column] < old[1][column] if operation == "min"
                                         else point[column] > old[1][column])
                if better:
                    bucket[label] = index, point
        state["index"] += 1
    for key in states:
        flush(key)
    series_list = sorted(grouped.values(), key=lambda s: (
        s["election"], s["turn"], s["candidate"], s["source"]
    ))
    return series_list


def _svg(series_list: list[dict], title: str, colors: dict[str, str], synthetic=False) -> str:
    width, height = 1200, 780 + 24 * ((len(series_list) + 1) // 2)
    left, right, top, bottom = 82, 1140, 105, 615
    valid = [p for s in series_list for p in s["points"] if p[2] is not None]
    x_min = min((p[0] for p in valid), default=0)
    x_max = max((p[0] for p in valid), default=x_min + 60000)
    span = max(x_max - x_min, 60000)

    def x(value: float) -> float:
        return left + (value - x_min) / span * (right - left)

    def y(value: float) -> float:
        return bottom - value / 100 * (bottom - top)

    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
             f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">',
             f'<title id="title">{html.escape((SYNTHETIC_HEADING + " · " if synthetic else "") + title)}</title>',
             f'<desc id="desc">{html.escape(CAUTION)}</desc>',
             '<rect width="100%" height="100%" fill="#fff"/>',
             '<g font-family="Arial,sans-serif" fill="#182538">']
    if synthetic:
        parts.extend([
            f'<text x="30" y="30" font-size="23" font-weight="bold" fill="#b71c1c">{SYNTHETIC_HEADING}</text>',
            f'<text x="30" y="58" font-size="21" font-weight="bold">{html.escape(title)}</text>',
            '<text x="30" y="85" font-size="15">Votos nominais acumulados (%) · total ao fim de cada minuto</text>',
        ])
    else:
        parts.extend([
            f'<text x="30" y="35" font-size="24" font-weight="bold">{html.escape(title)}</text>',
            '<text x="30" y="65" font-size="15">Votos nominais acumulados (%) · total ao fim de cada minuto</text>',
        ])
    for percent in range(0, 101, 20):
        parts.extend([
            f'<line x1="{left}" x2="{right}" y1="{y(percent):.2f}" y2="{y(percent):.2f}" stroke="#dce3eb"/>',
            f'<text x="{left-12}" y="{y(percent)+5:.2f}" text-anchor="end" font-size="14">{percent}%</text>',
        ])
    if valid:
        for n in range(5):
            moment = x_min + (x_max - x_min) * n / 4
            label = datetime.fromtimestamp(moment / 1000, timezone.utc).strftime("%d/%m/%Y %H:%M")
            parts.append(f'<text x="{x(moment):.2f}" y="{bottom+25}" text-anchor="middle" font-size="12">{label}</text>')
    else:
        parts.append('<text x="600" y="350" text-anchor="middle" font-size="20">Sem votos nominais com horário válido</text>')
    for index, series in enumerate(series_list):
        color = colors[series["candidate"]]
        segments, segment = [], []
        for point in series["points"]:
            if point[2] is None:
                if segment:
                    segments.append(segment)
                segment = []
            else:
                segment.append(f'{x(point[0]):.2f},{y(point[2]):.2f}')
        if segment:
            segments.append(segment)
        for segment in segments:
            if len(segment) == 1:
                cx, cy = segment[0].split(",")
                parts.append(f'<circle cx="{cx}" cy="{cy}" r="3" fill="{color}"/>')
            else:
                parts.append(f'<polyline fill="none" stroke="{color}" stroke-width="2.5" points="{" ".join(segment)}"/>')
        lx, ly = 40 + (index % 2) * 570, 690 + (index // 2) * 24
        parts.extend([
            f'<line x1="{lx}" x2="{lx+22}" y1="{ly-5}" y2="{ly-5}" stroke="{color}" stroke-width="3"/>',
            f'<text x="{lx+30}" y="{ly}" font-size="14">{html.escape(series["candidate"] + " — " + series["name"])}</text>',
        ])
    parts.append(f'<text x="30" y="{height-45}" font-size="11">{html.escape(PERCENTAGE_CAVEAT)}</text>')
    parts.append(f'<text x="30" y="{height-26}" font-size="11">{html.escape(CAUTION)}</text>')
    parts.append('</g></svg>')
    return "\n".join(parts)


def generate_charts(output_dir: Path) -> list[str]:
    """Read national minute CSVs and write self-contained HTML and SVG reports."""
    output_dir = Path(output_dir)
    manifest_path = output_dir / "input-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    synthetic = manifest.get("synthetic") is True
    series_list = _read(output_dir)
    charts_dir = output_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)
    candidates = sorted({s["candidate"] for s in series_list})
    remaining = [candidate for candidate in candidates if candidate not in CANDIDATE_COLORS]
    colors = {candidate: COLORS[i % len(COLORS)] for i, candidate in enumerate(remaining)}
    colors.update({candidate: CANDIDATE_COLORS[candidate] for candidate in candidates
                   if candidate in CANDIDATE_COLORS})
    artifacts = []
    groups: dict[tuple, list[dict]] = {}
    for series in series_list:
        groups.setdefault((series["election"], series["turn"], series["source"]), []).append(series)
    for (election, turn, source), group in sorted(groups.items()):
        filename = f"charts/election-{_safe_name(election)}-turn-{_safe_name(turn)}-{source}.svg"
        title = f"Eleição {election} · {turn}º turno · {group[0]['source_label']}"
        (output_dir / filename).write_text(_svg(group, title, colors, synthetic), encoding="utf-8")
        artifacts.append(filename)
    payload = json.dumps({"series": series_list, "colors": colors}, ensure_ascii=False,
                         separators=(",", ":")).replace("<", "\\u003c")
    heading = SYNTHETIC_HEADING if synthetic else "Replay da apuração presidencial"
    page = (_HTML.replace("__PAYLOAD__", payload).replace("__CAUTION__", html.escape(CAUTION))
            .replace("__HEADING__", html.escape(heading))
            .replace("__HEADING_CLASS__", "synthetic" if synthetic else ""))
    (output_dir / "replay-report.html").write_text(page, encoding="utf-8")
    artifacts.append("replay-report.html")
    return artifacts


_HTML = r'''<!doctype html>
<html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__HEADING__</title>
<style>
:root{font-family:system-ui,sans-serif;color:#17263c;background:#f3f6fa}body{max-width:1300px;margin:auto;padding:24px}
h1{font-size:30px;margin-bottom:8px}.synthetic{color:#b71c1c;background:#ffe9e5;padding:18px;border:3px solid #b71c1c;border-radius:8px}p{line-height:1.5}.note{background:#fff4d7;padding:14px;border-radius:8px}
.controls{display:flex;gap:18px;flex-wrap:wrap;margin:24px 0}label{display:grid;gap:6px;font-size:14px}select{font:inherit;padding:8px;border:1px solid #aebdce;border-radius:6px;background:white}
.panel{background:white;padding:18px;border-radius:12px;box-shadow:0 2px 12px #17263c0a}svg{width:100%;height:auto;display:block;touch-action:pan-y}.legend{display:flex;gap:10px 20px;flex-wrap:wrap;font-size:13px}.legend span{display:flex;gap:7px;align-items:center}.swatch{width:22px;height:3px;display:inline-block}.meta{font-size:13px;color:#496078}#tooltip{white-space:pre-line;min-height:60px;font-size:14px;line-height:1.5;padding:12px;background:#f6f8fb;margin-top:12px}a{color:#1565c0}.visually-hidden{position:absolute;width:1px;height:1px;overflow:hidden}
</style>
<h1 class="__HEADING_CLASS__">__HEADING__</h1>
<p>Votos finais associados retrospectivamente ao horário da seção. Explore os turnos e compare as duas referências temporais.</p>
<p class="note">__CAUTION__</p>
<div class="controls">
<label>Eleição e turno<select id="election"></select></label>
<label>Referência temporal<select id="source"><option value="both">Comparar as duas referências</option><option value="first_partial_totalization">Primeira totalização</option><option value="bu_received">Recebimento do BU</option></select></label>
<label>Medida<select id="metric"><option value="percentage">Votos nominais acumulados (%)</option><option value="votes">Votos nominais acumulados</option></select></label>
</div>
<div class="panel"><p id="summary" class="meta"></p><svg id="plot" viewBox="0 0 1200 610" role="img" aria-labelledby="chart-title"><title id="chart-title">Evolução acumulada da votação nominal</title></svg><div id="legend" class="legend"></div><div id="tooltip" aria-live="polite">Passe o cursor ou toque no gráfico para consultar os valores.</div></div>
<p class="note">O denominador dos percentuais inclui apenas votos nominais com horário válido nesta referência temporal, acumulados até aquele minuto. Podem existir votos excluídos da série por falta de horário ou pareamento: os percentuais não representam a participação sobre todos os votos finais. Consulte os votos sem horário e a qualidade dos dados.</p>
<p class="meta">Cada ponto representa o acumulado ao fim do minuto identificado. Brancos, nulos e anulados constam nos CSVs. Trecho contínuo: primeira totalização; tracejado: recebimento do BU. Minutos sem percentual definido não são tratados como zero.</p>
<p class="meta">A visualização pode reduzir séries extensas, preservando início, fim e extremos de porcentagem/votos por bloco. Os CSVs mantêm todos os minutos e devem ser usados para análise exata. No gráfico, segmentos unem os pontos retidos; o cursor consulta o ponto retido mais próximo, sem interpolar votos. As datas são rótulos de Hora TSE, sem conversão de fuso.</p>
<p><a href="replay-first-totalization-minute.csv">CSV · primeira totalização</a> · <a href="replay-bu-received-minute.csv">CSV · recebimento do BU</a> · <a href="final-results.csv">Resultados finais</a> · <a href="untimed-votes.csv">Votos excluídos da série temporal</a> · <a href="data-quality.csv">Qualidade dos dados</a> · <a href="input-manifest.json">Manifesto e rastreabilidade</a></p>
<script type="application/json" id="chart-data">__PAYLOAD__</script>
<script>
'use strict';
const data=JSON.parse(document.getElementById('chart-data').textContent),sel=document.getElementById('election'),source=document.getElementById('source'),metric=document.getElementById('metric'),plot=document.getElementById('plot'),tooltip=document.getElementById('tooltip');
const keys=[...new Set(data.series.map(s=>JSON.stringify([s.election,s.turn])))];
for(const key of keys){const [e,t]=JSON.parse(key),o=document.createElement('option');o.value=key;o.textContent=`Eleição ${e} · ${t}º turno`;sel.append(o)}
const NS='http://www.w3.org/2000/svg';function el(tag,attrs={},text){const n=document.createElementNS(NS,tag);for(const[k,v]of Object.entries(attrs))n.setAttribute(k,v);if(text!==undefined)n.textContent=text;plot.append(n);return n}
const fmt=new Intl.NumberFormat('pt-BR'),pct=new Intl.NumberFormat('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2});
function dateLabel(t){const d=new Date(t);return `${String(d.getUTCDate()).padStart(2,'0')}/${String(d.getUTCMonth()+1).padStart(2,'0')}/${d.getUTCFullYear()} ${String(d.getUTCHours()).padStart(2,'0')}:${String(d.getUTCMinutes()).padStart(2,'0')}`}
let state=null;
function render(){plot.replaceChildren();el('title',{id:'chart-title'},'Evolução acumulada da votação nominal');document.getElementById('legend').replaceChildren();if(!sel.value){el('text',{x:600,y:300,'text-anchor':'middle'},'Sem votos nominais com horário válido');document.getElementById('summary').textContent='Não há séries temporais nominais disponíveis.';state=null;return}
const[e,t]=JSON.parse(sel.value),series=data.series.filter(s=>s.election===e&&s.turn===t&&(source.value==='both'||s.source===source.value)),column=metric.value==='percentage'?2:3;
let xmin=Infinity,xmax=-Infinity,max=0,count=0,original=0;for(const s of series){count+=s.points.length;original+=s.original_count;for(const p of s.points)if(p[column]!==null){xmin=Math.min(xmin,p[0]);xmax=Math.max(xmax,p[0]);max=Math.max(max,p[column])}}
if(!Number.isFinite(xmin)){el('text',{x:600,y:300,'text-anchor':'middle'},'Sem valores para esta seleção');state=null;return}
const left=85,right=1150,top=35,bottom=540,span=Math.max(60000,xmax-xmin),ymax=column===2?100:Math.max(1,max*1.05),x=v=>left+(v-xmin)/span*(right-left),y=v=>bottom-v/ymax*(bottom-top);
for(let i=0;i<=5;i++){const value=ymax*i/5;el('line',{x1:left,x2:right,y1:y(value),y2:y(value),stroke:'#dce3eb'});el('text',{x:left-12,y:y(value)+5,'text-anchor':'end','font-size':13,fill:'#496078'},column===2?`${Math.round(value)}%`:fmt.format(Math.round(value)))}
for(let i=0;i<5;i++){const tick=xmin+(xmax-xmin)*i/4;el('text',{x:x(tick),y:bottom+28,'text-anchor':'middle','font-size':12,fill:'#496078'},dateLabel(tick))}
for(const s of series){let path='',start=true;for(const p of s.points){if(p[column]===null){start=true;continue}path+=`${start?'M':'L'}${x(p[0]).toFixed(2)},${y(p[column]).toFixed(2)} `;start=false}el('path',{d:path,fill:'none',stroke:data.colors[s.candidate],'stroke-width':2.3,'stroke-dasharray':s.source==='bu_received'?'7 4':'none'});if(s.points.length===1&&s.points[0][column]!==null)el('circle',{cx:x(s.points[0][0]),cy:y(s.points[0][column]),r:3,fill:data.colors[s.candidate]})}
for(const s of series.filter((s,i,a)=>a.findIndex(q=>q.candidate===s.candidate)===i)){const item=document.createElement('span'),swatch=document.createElement('i');swatch.className='swatch';swatch.style.background=data.colors[s.candidate];item.append(swatch,document.createTextNode(`${s.candidate} — ${s.name}`));document.getElementById('legend').append(item)}
const cursor=el('line',{x1:left,x2:left,y1:top,y2:bottom,stroke:'#496078','stroke-dasharray':'3 4',visibility:'hidden'});el('rect',{x:left,y:top,width:right-left,height:bottom-top,fill:'transparent',id:'hit-area'});state={series,xmin,span,left,right,top,bottom,cursor};document.getElementById('summary').textContent=`Eleição ${e} · ${t}º turno · ${dateLabel(xmin)} a ${dateLabel(xmax)} · Brasil, incluindo exterior quando presente · ${fmt.format(count)} pontos visuais de ${fmt.format(original)} registros nominais.`;tooltip.textContent='Passe o cursor ou toque no gráfico para consultar os pontos retidos.'}
function inspect(event){if(!state)return;const box=plot.getBoundingClientRect(),px=(event.clientX-box.left)/box.width*1200;if(px<state.left||px>state.right)return;const tick=state.xmin+(px-state.left)/(state.right-state.left)*state.span;state.cursor.setAttribute('x1',px);state.cursor.setAttribute('x2',px);state.cursor.setAttribute('visibility','visible');const lines=[];for(const s of state.series){const a=s.points;let lo=0,hi=a.length;while(lo<hi){const mid=(lo+hi)>>1;if(a[mid][0]<tick)lo=mid+1;else hi=mid}let index=Math.min(lo,a.length-1);if(index>0&&Math.abs(a[index-1][0]-tick)<=Math.abs(a[index][0]-tick))index--;const p=a[index];if(!p)continue;lines.push(`${s.candidate} — ${s.name} · ${s.source_label}\n${p[1]} · ${fmt.format(p[3])} votos · ${p[2]===null?'percentual indefinido':pct.format(p[2])+'%'} · ${fmt.format(p[4])} seções`)}tooltip.textContent=lines.join('\n\n')}
plot.addEventListener('pointermove',inspect);plot.addEventListener('pointerdown',inspect);for(const control of [sel,source,metric])control.addEventListener('change',render);render();
</script></html>
'''
