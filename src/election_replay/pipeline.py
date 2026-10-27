"""Streaming CSV ingestion, disk-backed joins, and auditable minute replays."""
from __future__ import annotations

import csv
import hashlib
import json
import logging
import re
import sqlite3
import subprocess
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOG = logging.getLogger(__name__)
KEY = ['election_code', 'turno', 'uf', 'municipality', 'zone', 'section', 'cargo']
INPUT_KEY = ['CD_ELEICAO', 'NR_TURNO', 'SG_UF', 'CD_MUNICIPIO', 'NR_ZONA', 'NR_SECAO', 'CD_CARGO']
COMMON = ['ANO_ELEICAO', 'DS_CARGO', 'SG_UE', *INPUT_KEY]
SOURCES = {
    'first_partial_totalization': ('DT_PRIM_TOT_PARCIAL_HOR_TSE', 'first_time', 'replay-first-totalization-minute.csv'),
    'bu_received': ('DT_RECEBIMENTO_BU_HOR_TSE', 'bu_time', 'replay-bu-received-minute.csv'),
}
METRICS = ['QT_VOTOS_NOMINAIS', 'QT_VOTOS_BRANCOS', 'QT_VOTOS_NULOS', 'QT_VOTOS_ANULADOS_APU_SEP']
OPTIONAL = [*METRICS, 'QT_APTOS', 'QT_COMPARECIMENTO', 'QT_ABSTENCOES', 'ST_SECAO_INSTALADA', 'ST_SECAO_ANULADA', 'DS_ORIGEM_VOTO']
MISSING = {'', '#NULO', '#NE', '-1', '-3'}


def timestamp(value):
    """Keep Hora TSE wall-clock values; no undocumented UTC offset is inferred."""
    value = value.strip()
    if value.upper() in MISSING:
        return None, 'timestamp_missing'
    for fmt in ('%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M:%S.%f', '%d/%m/%Y %H:%M',
                '%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f'):
        try:
            return datetime.strptime(value, fmt).isoformat(sep=' ', timespec='microseconds'), None
        except ValueError:
            pass
    return None, 'timestamp_invalid'


def integer(value, field, allow_missing=False):
    value = value.strip()
    if allow_missing and value.upper() in MISSING:
        return None
    if not re.fullmatch(r'\d+', value):
        raise ValueError(f'{field}: expected nonnegative integer, got {value!r}')
    return int(value)


def vote_class(number):
    return {95: 'blank', 96: 'null', 97: 'separate'}.get(number, 'nominal')


def inspect_input(path):
    if not path.is_file():
        raise ValueError(f'Input not found: {path}')
    with path.open('rb') as stream:
        first = stream.read(512)
        if first.startswith(b'version https://git-lfs.github.com/spec/v1'):
            pointer = first.decode('ascii')
            raise ValueError(f'{path}: Git LFS pointer, not a CSV. Recover the original payload with git lfs pull. {pointer.strip()}')
        digest = hashlib.sha256()
        digest.update(first)
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    with path.open(encoding='latin1', newline='') as stream:
        header = next(csv.reader(stream, delimiter=';'), [])
    if len(header) != len(set(header)):
        raise ValueError(f'{path}: duplicate header columns')
    return {'path': str(path), 'size_bytes': path.stat().st_size, 'sha256': digest.hexdigest(),
            'collection_date': None, 'columns': header}


def write_csv(path, columns, rows):
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(columns)
        writer.writerows(rows)


def query_csv(db, out, name, sql, params=()):
    cursor = db.execute(sql, params)
    write_csv(out / name, [c[0] for c in cursor.description], cursor)


def ingest(db, path, kind, year, manifest):
    required = COMMON + (['NR_VOTAVEL', 'NM_VOTAVEL', 'QT_VOTOS'] if kind == 'votes' else [v[0] for v in SOURCES.values()])
    missing = sorted(set(required) - set(manifest['columns']))
    if missing:
        raise ValueError(f'{path}: missing required columns: {", ".join(missing)}')
    manifest['optional_columns_missing'] = sorted(set(OPTIONAL) - set(manifest['columns'])) if kind == 'details' else []
    stats = Counter()
    observed = Counter()
    generation = set()
    timestamp_formats = Counter()
    batch = []
    table = 'raw_votes' if kind == 'votes' else 'raw_details'
    ncols = 11 if kind == 'votes' else 24
    insert = f'INSERT INTO {table} VALUES ({",".join("?" for _ in range(ncols))})'
    with path.open(encoding='latin1', newline='') as stream:
        reader = csv.DictReader(stream, delimiter=';', restkey='__extra__')
        for line, row in enumerate(reader, 2):
            try:
                if None in row.values() or '__extra__' in row:
                    raise ValueError('inconsistent number of CSV fields')
                stats['rows_read'] += 1
                observed[(row['ANO_ELEICAO'], row['CD_ELEICAO'], row['NR_TURNO'], row['CD_CARGO'], row['DS_CARGO'], row['SG_UE'])] += 1
                if row.get('DT_GERACAO') or row.get('HH_GERACAO'):
                    generation.add((row.get('DT_GERACAO'), row.get('HH_GERACAO')))
                if integer(row['ANO_ELEICAO'], 'ANO_ELEICAO') != year:
                    stats['other_year_rows'] += 1
                    continue
                cargo = integer(row['CD_CARGO'], 'CD_CARGO')
                if cargo != 1:
                    if row['DS_CARGO'].strip().casefold() == 'presidente':
                        raise ValueError('DS_CARGO=Presidente with CD_CARGO other than 1')
                    stats['other_office_rows'] += 1
                    continue
                if row['DS_CARGO'].strip().casefold() != 'presidente':
                    raise ValueError('CD_CARGO=1 with unexpected DS_CARGO')
                if row['SG_UE'].strip().upper() != 'BR':
                    raise ValueError('presidential row with SG_UE other than BR')
                key = [str(integer(row[c], c)) if c != 'SG_UF' else row[c].strip().upper() for c in INPUT_KEY]
                if not re.fullmatch('[A-Z]{2}', key[2]):
                    raise ValueError('invalid SG_UF')
                if key[1] not in {'1', '2'}:
                    raise ValueError('presidential NR_TURNO must be 1 or 2')
                if kind == 'votes':
                    number = integer(row['NR_VOTAVEL'], 'NR_VOTAVEL')
                    if number == 0:
                        raise ValueError('NR_VOTAVEL=0 is unsupported')
                    name = row['NM_VOTAVEL'].strip()
                    if name.upper() in MISSING:
                        raise ValueError('missing NM_VOTAVEL')
                    batch.append((*key, number, name, vote_class(number), integer(row['QT_VOTOS'], 'QT_VOTOS')))
                else:
                    first_raw, bu_raw = row['DT_PRIM_TOT_PARCIAL_HOR_TSE'], row['DT_RECEBIMENTO_BU_HOR_TSE']
                    first, first_reason = timestamp(first_raw)
                    bu, bu_reason = timestamp(bu_raw)
                    for source, raw, parsed, reason in [('first_partial_totalization', first_raw, first, first_reason), ('bu_received', bu_raw, bu, bu_reason)]:
                        timestamp_formats[(source, reason or ('day_first' if '/' in raw else 'iso_local'))] += 1
                    values = [integer(row.get(c, ''), c, allow_missing=True) for c in OPTIONAL[:7]]
                    flags = [row.get(c, '').strip() for c in OPTIONAL[7:]]
                    batch.append((*key, first, first_reason, bu, bu_reason, *values, *flags, first_raw, bu_raw, line))
                stats['selected_rows'] += 1
                if len(batch) >= 10000:
                    db.executemany(insert, batch)
                    batch.clear()
                    if stats['selected_rows'] % 500000 == 0:
                        LOG.info('%s: %s selected rows', kind, stats['selected_rows'])
            except ValueError as error:
                raise ValueError(f'{path}:{line}: {error}') from error
        if batch:
            db.executemany(insert, batch)
    manifest['ingestion'] = dict(stats)
    manifest['observed_scopes'] = [dict(zip(['year', 'election_code', 'turno', 'cargo', 'office', 'sg_ue', 'rows'], (*key, count))) for key, count in sorted(observed.items())]
    manifest['extraction_values'] = sorted(generation)
    manifest['timestamp_formats'] = [{'source': s, 'format_or_status': f, 'rows': n} for (s, f), n in sorted(timestamp_formats.items())]
    if not stats['selected_rows']:
        raise ValueError(f'{path}: no presidential records selected for {year}')
    db.commit()


def create_database(path):
    db = sqlite3.connect(path)
    db.execute('PRAGMA journal_mode=DELETE')
    db.execute('PRAGMA temp_store=FILE')
    db.execute('PRAGMA cache_size=-65536')
    common = ','.join(f'{key} TEXT NOT NULL' for key in KEY)
    db.execute(f'CREATE TABLE raw_votes ({common}, nr_votavel INTEGER, nm_votavel TEXT, vote_class TEXT, votes INTEGER)')
    db.execute(f'''CREATE TABLE raw_details ({common}, first_time TEXT, first_reason TEXT, bu_time TEXT, bu_reason TEXT,
        nominal INTEGER, blank INTEGER, null_votes INTEGER, separate INTEGER, aptos INTEGER, turnout INTEGER, abstentions INTEGER,
        installed TEXT, cancelled TEXT, origin TEXT, first_raw TEXT, bu_raw TEXT, input_line INTEGER)''')
    return db


def aggregate(db):
    key = ','.join(KEY)
    # Keep all raw name variants before collapsing section/candidate rows.
    db.execute('''CREATE TABLE candidate_names AS SELECT election_code,turno,nr_votavel,nm_votavel,
        COUNT(*) AS input_rows,SUM(votes) AS votes FROM raw_votes GROUP BY election_code,turno,nr_votavel,nm_votavel''')
    db.execute(f'''CREATE TABLE votes AS SELECT {key}, nr_votavel, MIN(nm_votavel) AS nm_votavel,
        vote_class, SUM(votes) AS votes, COUNT(*) AS input_rows FROM raw_votes GROUP BY {key},nr_votavel''')
    db.execute(f'CREATE INDEX votes_key ON votes ({key})')
    db.execute(f'CREATE TABLE detail_counts AS SELECT {key}, COUNT(*) AS detail_rows FROM raw_details GROUP BY {key}')
    db.execute(f'CREATE UNIQUE INDEX detail_counts_key ON detail_counts ({key})')
    db.execute(f'''CREATE TABLE details AS SELECT d.* FROM raw_details d JOIN detail_counts USING ({key}) WHERE detail_rows=1''')
    db.execute(f'CREATE UNIQUE INDEX details_key ON details ({key})')
    db.execute(f'''CREATE TABLE sections AS SELECT {key},
        SUM(CASE WHEN vote_class='nominal' THEN votes ELSE 0 END) AS nominal_votes,
        SUM(CASE WHEN vote_class='blank' THEN votes ELSE 0 END) AS blank_votes,
        SUM(CASE WHEN vote_class='null' THEN votes ELSE 0 END) AS null_votes,
        SUM(CASE WHEN vote_class='separate' THEN votes ELSE 0 END) AS separate_votes,
        SUM(votes) AS total_votes FROM votes GROUP BY {key}''')
    db.execute(f'CREATE UNIQUE INDEX sections_key ON sections ({key})')
    db.execute('''CREATE TABLE candidates AS SELECT election_code,turno,nr_votavel,MIN(nm_votavel) AS nm_votavel,
        vote_class,SUM(votes) AS votes,COUNT(*) AS sections FROM votes GROUP BY election_code,turno,nr_votavel''')
    # Remove staging votes to reduce the retained database size; detail rows are kept for auditing.
    db.execute('DROP TABLE raw_votes')
    db.commit()


def diagnostics(db, out):
    key = ','.join(KEY)
    query_csv(db, out, 'section-coverage.csv', f'''SELECT {key},
        CASE WHEN s.section IS NULL THEN 'detail_only' WHEN c.section IS NULL THEN 'votes_only'
        WHEN c.detail_rows>1 THEN 'detail_duplicate' ELSE 'matched' END AS status,
        COALESCE(c.detail_rows,0) AS detail_rows,COALESCE(s.total_votes,0) AS votes
        FROM sections s FULL OUTER JOIN detail_counts c USING ({key}) ORDER BY election_code,turno,uf,municipality,zone,section''')
    query_csv(db, out, 'duplicate-details.csv', f'''SELECT * FROM raw_details JOIN detail_counts USING ({key})
        WHERE detail_rows>1 ORDER BY election_code,turno,uf,municipality,zone,section,input_line''')
    query_csv(db, out, 'vote-aggregation.csv', f'SELECT * FROM votes WHERE input_rows>1')
    query_csv(db, out, 'candidate-names.csv', 'SELECT * FROM candidate_names ORDER BY election_code,turno,nr_votavel,nm_votavel')
    comparisons = [('nominal_votes', 'nominal'), ('blank_votes', 'blank'), ('null_votes', 'null_votes'), ('separate_votes', 'separate')]
    parts = [f'''SELECT {','.join('s.'+k for k in KEY)},'{label}' AS category,s.{left} AS votes_total,d.{right} AS detail_total,
        s.{left}-d.{right} AS difference FROM sections s JOIN details d USING ({key})
        WHERE d.{right} IS NOT NULL AND s.{left}<>d.{right}''' for label, (left, right) in zip(['nominal','blank','null','separate'], comparisons)]
    query_csv(db, out, 'reconciliation.csv', ' UNION ALL '.join(parts))
    query_csv(db, out, 'section-exceptions.csv', f'''SELECT * FROM raw_details WHERE
        installed NOT IN ('S','Sim','SIM') OR cancelled NOT IN ('N','Não','NÃO','NAO','Nao') OR origin NOT IN ('U','URNA ELETRÔNICA','URNA ELETRONICA','Urna eletrônica','Urna Eletrônica') OR first_reason IS NOT NULL OR bu_reason IS NOT NULL
        OR (aptos IS NOT NULL AND turnout IS NOT NULL AND abstentions IS NOT NULL AND aptos<>turnout+abstentions)''')
    query_csv(db, out, 'timestamp-latency.csv', f'''SELECT {key},first_time,bu_time,
        ROUND((julianday(first_time)-julianday(bu_time))*86400,3) AS seconds_receipt_to_first_totalization
        FROM details WHERE first_time IS NOT NULL AND bu_time IS NOT NULL''')
    comparable = {}
    for label, (left, right) in zip(['nominal','blank','null','separate'], comparisons):
        ncomp, nmissing = db.execute(f'''SELECT COUNT(d.{right}),SUM(CASE WHEN d.{right} IS NULL THEN 1 ELSE 0 END)
            FROM sections s JOIN details d USING ({key})''').fetchone()
        comparable[label] = {'compared_sections':ncomp, 'missing_metric_sections':nmissing or 0}
    quality = []
    def collect(category, sql):
        for election, turn, uf, metric, value in db.execute(sql):
            quality.append((category, election, turn, uf, metric, value))
    collect('coverage', f'''SELECT election_code,turno,uf,'vote_sections',COUNT(*) FROM sections GROUP BY election_code,turno,uf
        UNION ALL SELECT election_code,turno,uf,'detail_sections',COUNT(*) FROM detail_counts GROUP BY election_code,turno,uf
        UNION ALL SELECT election_code,turno,uf,'matched_unique_sections',COUNT(*) FROM sections JOIN details USING ({key}) GROUP BY election_code,turno,uf
        UNION ALL SELECT election_code,turno,uf,'votes_only_sections',COUNT(*) FROM sections LEFT JOIN detail_counts USING ({key}) WHERE detail_rows IS NULL GROUP BY election_code,turno,uf
        UNION ALL SELECT election_code,turno,uf,'detail_only_sections',COUNT(*) FROM detail_counts LEFT JOIN sections USING ({key}) WHERE total_votes IS NULL GROUP BY election_code,turno,uf
        UNION ALL SELECT election_code,turno,uf,'duplicate_detail_sections',COUNT(*) FROM detail_counts WHERE detail_rows>1 GROUP BY election_code,turno,uf''')
    for source, (_, col, _) in SOURCES.items():
        reason_col = 'first_reason' if col == 'first_time' else 'bu_reason'
        collect(source, f'''SELECT election_code,turno,uf,COALESCE({reason_col},'timestamp_valid'),COUNT(*) FROM raw_details GROUP BY election_code,turno,uf,{reason_col}''')
    collect('consistency', '''SELECT election_code,turno,uf,'aptos_turnout_abstentions_mismatch',COUNT(*) FROM raw_details
        WHERE aptos IS NOT NULL AND turnout IS NOT NULL AND abstentions IS NOT NULL AND aptos<>turnout+abstentions GROUP BY election_code,turno,uf''')
    for field in ['installed','cancelled','origin']:
        collect('section_flags', f"SELECT election_code,turno,uf,'{field}='||{field},COUNT(*) FROM raw_details GROUP BY election_code,turno,uf,{field}")
    for category, values in comparable.items():
        for metric, value in values.items():
            quality.append(('reconciliation', '', '', '', category+'_'+metric, value))
    write_csv(out / 'data-quality.csv', ['category','election_code','turno','uf','metric','value'], quality)
    return {'reconciliation_comparability':comparable, 'vote_sections': db.execute('SELECT COUNT(*) FROM sections').fetchone()[0],
            'detail_sections': db.execute('SELECT COUNT(*) FROM detail_counts').fetchone()[0],
            'duplicate_detail_sections': db.execute('SELECT COUNT(*) FROM detail_counts WHERE detail_rows>1').fetchone()[0],
            'matched_unique_sections': db.execute(f'SELECT COUNT(*) FROM sections JOIN details USING ({key})').fetchone()[0],
            'reconciliation_mismatches': sum(1 for _ in db.execute(' UNION ALL '.join(parts))),
            'coverage_by_uf': [dict(zip(['election_code','turno','uf','sections','votes'], r)) for r in db.execute('SELECT election_code,turno,uf,COUNT(*),SUM(total_votes) FROM sections GROUP BY election_code,turno,uf')]}


def final_results(db, out):
    query_csv(db, out, 'final-results.csv', 'SELECT * FROM candidates ORDER BY election_code,turno,votes DESC,nr_votavel')
    for name, geo in [('uf', ['uf']), ('municipality', ['uf', 'municipality'])]:
        cols = ','.join(['election_code','turno',*geo,'nr_votavel'])
        query_csv(db, out, f'final-results-{name}.csv', f'''SELECT {cols},MIN(nm_votavel) AS nm_votavel,vote_class,SUM(votes) AS votes,COUNT(*) AS sections
            FROM votes GROUP BY {cols} ORDER BY {cols}''')
    query_csv(db, out, 'final-results-section.csv', f'SELECT {",".join(KEY)},nr_votavel,nm_votavel,vote_class,votes FROM votes ORDER BY {",".join(KEY)},nr_votavel')


def replay(db, out, max_minutes):
    key = ','.join(KEY)
    untimed = []
    summary = []
    fields = ['election_code','turno','minute','source_timestamp','uf_scope','nr_votavel','nm_votavel','vote_class',
              'votes_in_minute','cumulative_votes','sections_in_minute','cumulative_sections','percentage_valid_votes']
    elections = list(db.execute('SELECT DISTINCT election_code,turno FROM candidates ORDER BY election_code,turno'))
    for source, (_, column, filename) in SOURCES.items():
        reason = 'first_reason' if column == 'first_time' else 'bu_reason'
        reason_sql = f"CASE WHEN c.detail_rows IS NULL THEN 'detail_missing' WHEN c.detail_rows>1 THEN 'detail_duplicate' ELSE d.{reason} END"
        missing_sql = f'''SELECT v.election_code,v.turno,v.nr_votavel,MIN(v.nm_votavel),v.vote_class,{reason_sql} AS reason,
            SUM(v.votes),COUNT(*) FROM votes v LEFT JOIN detail_counts c USING ({key}) LEFT JOIN details d USING ({key})
            WHERE c.detail_rows IS NULL OR c.detail_rows>1 OR d.{column} IS NULL GROUP BY v.election_code,v.turno,v.nr_votavel,reason'''
        missing = list(db.execute(missing_sql))
        untimed.extend((source, *row) for row in missing)
        missing_totals = Counter()
        for e, t, number, _, _, _, total, _ in missing:
            missing_totals[(e,t,number)] += total
        db.execute('DROP TABLE IF EXISTS minute_votes')
        db.execute(f'''CREATE TABLE minute_votes AS SELECT v.election_code,v.turno,substr(d.{column},1,16)||':00' AS minute,
            v.nr_votavel,SUM(v.votes) AS votes FROM votes v JOIN details d USING ({key}) WHERE d.{column} IS NOT NULL
            GROUP BY v.election_code,v.turno,minute,v.nr_votavel''')
        db.execute('CREATE INDEX minute_votes_idx ON minute_votes(election_code,turno,minute,nr_votavel)')
        db.execute('DROP TABLE IF EXISTS minute_sections')
        db.execute(f'''CREATE TABLE minute_sections AS SELECT s.election_code,s.turno,substr(d.{column},1,16)||':00' AS minute,
            COUNT(*) AS sections FROM sections s JOIN details d USING ({key}) WHERE d.{column} IS NOT NULL
            GROUP BY s.election_code,s.turno,minute''')
        db.execute('CREATE INDEX minute_sections_idx ON minute_sections(election_code,turno,minute)')
        with (out / filename).open('w', encoding='utf-8', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(fields)
            for election, turn in elections:
                candidates = list(db.execute('SELECT nr_votavel,nm_votavel,vote_class,votes FROM candidates WHERE election_code=? AND turno=? ORDER BY nr_votavel', (election,turn)))
                start, end = db.execute('SELECT MIN(minute),MAX(minute) FROM minute_sections WHERE election_code=? AND turno=?', (election,turn)).fetchone()
                cumulative = Counter()
                cumulative_sections = 0
                if start:
                    current, last = datetime.fromisoformat(start), datetime.fromisoformat(end)
                    minutes = int((last-current).total_seconds() // 60) + 1
                    if minutes > max_minutes:
                        raise ValueError(f'{source}, election {election}, turn {turn}: {minutes} minutes exceeds --max-minutes {max_minutes}; inspect timestamps or raise the explicit limit')
                    events = iter(db.execute('SELECT minute,nr_votavel,votes FROM minute_votes WHERE election_code=? AND turno=? ORDER BY minute,nr_votavel', (election,turn)))
                    sections = iter(db.execute('SELECT minute,sections FROM minute_sections WHERE election_code=? AND turno=? ORDER BY minute', (election,turn)))
                    event, section_event = next(events, None), next(sections, None)
                    while current <= last:
                        minute = current.isoformat(sep=' ', timespec='seconds')
                        increment = Counter()
                        while event and event[0] == minute:
                            increment[event[1]] += event[2]
                            cumulative[event[1]] += event[2]
                            event = next(events, None)
                        nsections = 0
                        if section_event and section_event[0] == minute:
                            nsections = section_event[1]
                            section_event = next(sections, None)
                        cumulative_sections += nsections
                        nominal = sum(cumulative[n] for n, _, cls, _ in candidates if cls == 'nominal')
                        for number, name, cls, _ in candidates:
                            percentage = f'{100*cumulative[number]/nominal:.10f}' if cls == 'nominal' and nominal else ''
                            writer.writerow([election,turn,minute,source,'BR',number,name,cls,increment[number],cumulative[number],nsections,cumulative_sections,percentage])
                        current += timedelta(minutes=1)
                for number, _, _, total in candidates:
                    if cumulative[number] + missing_totals[(election,turn,number)] != total:
                        raise AssertionError('Vote conservation failed')
                summary.append({'source':source,'election_code':election,'turno':turn,'first_minute':start,'last_minute':end,
                                'timed_votes':sum(cumulative.values()),'untimed_votes':sum(missing_totals[(election,turn,n)] for n,_,_,_ in candidates),
                                'timed_sections':cumulative_sections,'vote_conservation':'passed'})
    write_csv(out / 'untimed-votes.csv', ['source_timestamp','election_code','turno','nr_votavel','nm_votavel','vote_class','reason','votes','sections'], untimed)
    db.commit()
    return summary


def run(votes_path: Path, details_path: Path, output_dir: Path, year=2026, max_minutes=600000, synthetic=False):
    votes_path, details_path, output_dir = map(Path, (votes_path, details_path, output_dir))
    if max_minutes < 1:
        raise ValueError('max_minutes must be positive')
    # Preflight before creating outputs: never turn an LFS pointer into a plausible result.
    manifests = {'votes':inspect_input(votes_path), 'details':inspect_input(details_path)}
    for path in (votes_path, details_path):
        if path.resolve().is_relative_to(output_dir.resolve()):
            raise ValueError('Output directory must not contain input files')
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f'Output directory must be empty (preserve previous runs): {output_dir}')
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = {'status':'running', 'year':year, 'synthetic':synthetic, 'started_at_utc':datetime.now(timezone.utc).isoformat(),
               'time_convention':'Hora TSE, local wall clock; UTC offset unverified; no conversion',
               'nature':'Retrospective approximate reconstruction, not the official publication history',
               'inputs':manifests}
    try:
        summary['git_commit'] = subprocess.check_output(['git','rev-parse','HEAD'], text=True, stderr=subprocess.DEVNULL).strip()
        summary['git_dirty'] = bool(subprocess.check_output(['git','status','--porcelain'], text=True))
    except (OSError, subprocess.CalledProcessError):
        summary['git_commit'] = None
    manifest_path = output_dir / 'input-manifest.json'
    manifest_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    db = None
    try:
        db = create_database(output_dir / 'replay.sqlite')
        ingest(db, votes_path, 'votes', year, manifests['votes'])
        ingest(db, details_path, 'details', year, manifests['details'])
        LOG.info('Aggregating sections and building unique joins')
        aggregate(db)
        summary['quality'] = diagnostics(db, output_dir)
        final_results(db, output_dir)
        summary['replays'] = replay(db, output_dir, max_minutes)
        from .charts import generate_charts
        summary['charts'] = generate_charts(output_dir)
        write_report(output_dir, summary)
        summary['status'] = 'completed'
        summary['completed_at_utc'] = datetime.now(timezone.utc).isoformat()
        summary['artifacts'] = sorted(str(p.relative_to(output_dir)) for p in output_dir.rglob('*') if p.is_file())
        LOG.info('Completed: %s', output_dir)
        return summary
    except Exception as error:
        summary['status'] = 'failed'
        summary['error'] = str(error)
        raise
    finally:
        if db is not None:
            db.close()
        manifest_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def write_report(out, summary):
    """Human-readable findings tied to this run, without implying external certification."""
    title = 'DEMONSTRAÇÃO SINTÉTICA — não são resultados eleitorais' if summary['synthetic'] else 'Replay retrospectivo da apuração presidencial'
    lines = [f'# {title}', '',
             'Reconstrução aproximada: os votos finais de cada seção são associados retrospectivamente ao horário registrado. '
             'Não é um histórico certificado das atualizações públicas do TSE.', '',
             'Horários preservados em **Hora TSE**, sem inferência de offset UTC. Cada linha representa o acumulado ao fim do minuto; '
             'por exemplo, 17:00 inclui eventos de 17:00:00 até antes de 17:01:00.', '',
             '## Entradas', '', '| Fonte | Bytes | SHA-256 |', '|---|---:|---|']
    for name, entry in summary['inputs'].items():
        lines.append(f"| {name} | {entry['size_bytes']} | `{entry['sha256']}` |")
    lines += ['', 'A data de coleta é desconhecida; datas de extração observadas estão no manifesto. Os originais não são modificados.', '',
              '## Evolução temporal', '', '| Eleição | Turno | Referência | Primeiro minuto | Último minuto | Votos com horário | Votos fora da curva | Seções com horário |',
              '|---|---|---|---|---|---:|---:|---:|']
    for entry in summary['replays']:
        lines.append('| ' + ' | '.join(str(entry.get(k) if entry.get(k) is not None else 'ausente') for k in
                     ['election_code','turno','source','first_minute','last_minute','timed_votes','untimed_votes','timed_sections']) + ' |')
    turns = sorted({r['turno'] for r in summary['replays']})
    lines += ['', f"Turnos efetivamente encontrados na votação: {', '.join(turns)}. Não foram criados turnos ausentes.", '',
              '## Resultado final recontado', '', '| Eleição | Turno | Número | Nome/classe | Classe | Votos |', '|---|---|---|---|---|---:|']
    with (out / 'final-results.csv').open(encoding='utf-8', newline='') as stream:
        for entry in csv.DictReader(stream):
            lines.append('| ' + ' | '.join(entry[k].replace('|', '\\|') for k in ['election_code','turno','nr_votavel','nm_votavel','vote_class','votes']) + ' |')
    q = summary['quality']
    lines += ['', '## Qualidade e cobertura', '',
              f"- Seções na votação: {q['vote_sections']}; no detalhe: {q['detail_sections']}; pareadas sem duplicidade: {q['matched_unique_sections']}.",
              f"- Chaves duplicadas no detalhe: {q['duplicate_detail_sections']}; todas ficam fora das curvas, preservadas nos totais finais.",
              f"- Divergências de categoria/seção na reconciliação interna: {q['reconciliation_mismatches']} (consulte `reconciliation.csv`).",
              '- Reconciliação compara apenas métricas presentes em seções com detalhe único; zero divergências não comprova concordância quando métricas faltam. A contagem de comparações por classe está em `data-quality.csv` e no manifesto.',
              '- Conservação verificada por eleição/turno/votável e por referência: votos na curva + votos sem horário utilizável = total final.',
              '- O percentual divide apenas votos nominais acumulados com horário utilizável. Brancos, nulos e anulados/apurados em separado não entram no denominador.',
              '- Sem detalhe, detalhe duplicado, timestamp ausente e timestamp inválido são contabilizados separadamente em `untimed-votes.csv`.', '',
              '| Eleição | Turno | UF | Seções na votação | Votos |', '|---|---|---|---:|---:|']
    for entry in q['coverage_by_uf']:
        lines.append('| ' + ' | '.join(str(entry[k]) for k in ['election_code','turno','uf','sections','votes']) + ' |')
    lines += ['', 'A UF ZZ representa exterior e é incluída quando presente, sem inferir ausência pelo tamanho de outros arquivos.', '',
              '## Artefatos', '',
              '- `replay-report.html`: visualização interativa autônoma; `charts/*.svg`: gráficos exportáveis.',
              '- `replay-*-minute.csv`: séries integrais, inclusive minutos sem novos eventos.',
              '- `final-results*.csv`: votos por Brasil, UF, município e seção.',
              '- `section-coverage.csv`, `duplicate-details.csv`, `section-exceptions.csv`: diagnóstico do pareamento e das exceções.',
              '- `timestamp-latency.csv`: diferença recebimento → primeira totalização para detalhes únicos com ambos os horários; não é latência de publicação.',
              '- `candidate-names.csv` e `vote-aggregation.csv`: variações de nome e agregação de linhas repetidas.',
              '- `replay.sqlite`: base intermediária auditável em disco; `input-manifest.json`: proveniência, escopo, formatos, verificações e status.', '',
              '## Limitações', '',
              'A verificação é interna aos dois arquivos selecionados; não há comparação independente com um resultado oficial externo. '
              'Horários e quantidades podem refletir extrações, retotalizações e situações jurídicas diferentes. '
              'Seções anuladas/não instaladas e origens incomuns são listadas, mas seus votos não são descartados automaticamente. '
              'Na ausência de dado nominal detalhado de situação jurídica por candidato, os nominais são classificados operacionalmente '
              'como números diferentes de 95/96/97. Esta classificação não certifica a validade jurídica de cada voto.', '']
    (out / 'report.md').write_text('\n'.join(lines), encoding='utf-8')
