#!/usr/bin/env python3
"""H1: exact, source-level accounting checks. Python standard library only."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

KEY = ('election_code', 'turno', 'uf', 'municipality', 'zone', 'section', 'cargo')
SOURCE_KEY = ('CD_ELEICAO', 'NR_TURNO', 'SG_UF', 'CD_MUNICIPIO', 'NR_ZONA', 'NR_SECAO', 'CD_CARGO')
FIELDS = {
    'aptos': 'QT_APTOS', 'turnout': 'QT_COMPARECIMENTO', 'abstentions': 'QT_ABSTENCOES',
    'nominal': 'QT_VOTOS_NOMINAIS', 'blank': 'QT_VOTOS_BRANCOS', 'null_votes': 'QT_VOTOS_NULOS',
    'legend': 'QT_VOTOS_LEGENDA', 'separate': 'QT_VOTOS_ANULADOS_APU_SEP',
}
FLAGS = ('installed', 'cancelled', 'origin')
MISSING = {'', '-1', '-3', '#NULO', '#NE'}
ROOT = Path(__file__).resolve().parents[5]
H1 = Path(__file__).resolve().parents[1]
VOTES = Path('data/votacao_secao_2026_BR/votacao_secao_2026_BR.csv')
DETAILS = Path('data/detalhe_votacao_secao_2026/detalhe_votacao_secao_2026_BR.csv')


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def write_csv(path, columns, rows):
    with Path(path).open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream, lineterminator='\n')
        writer.writerow(columns)
        writer.writerows(rows)


def quantity(raw):
    """Missing/malformed counts remain unavailable, never zero; negatives are retained."""
    raw = raw.strip()
    if raw.upper() in MISSING:
        return None, 'missing'
    if not re.fullmatch(r'[+-]?[0-9]+', raw):
        return None, 'invalid'
    value = int(raw)
    if abs(value) >= 2 ** 63:
        return None, 'outside_sqlite_integer_range'
    return value, 'negative' if value < 0 else None


def normalized_key(row):
    values = []
    for field in SOURCE_KEY:
        raw = row[field].strip()
        if field == 'SG_UF':
            if not re.fullmatch('[A-Za-z]{2}', raw):
                raise ValueError(f'Invalid UF: {raw!r}')
            values.append(raw.upper())
        else:
            if not re.fullmatch('[0-9]+', raw):
                raise ValueError(f'Invalid key {field}: {raw!r}')
            values.append(int(raw))
    if values[1] not in (1, 2):
        raise ValueError('Expected first or second round')
    return tuple(values)


def ingest(db, path, kind, year, issues):
    names = [*SOURCE_KEY, 'ANO_ELEICAO', 'DS_CARGO', 'SG_UE']
    names += list(FIELDS.values()) + ['ST_SECAO_INSTALADA', 'ST_SECAO_ANULADA', 'DS_ORIGEM_VOTO'] if kind == 'details' else ['NR_VOTAVEL', 'QT_VOTOS']
    table = 'details' if kind == 'details' else 'raw_votes'
    batch, stats, extraction = [], Counter(), set()
    with path.open('rb') as stream:
        if stream.read(100).startswith(b'version https://git-lfs.github.com/spec/v1'):
            raise ValueError(f'{path}: Git LFS pointer, not source data')
    with path.open(encoding='latin1', newline='') as stream:
        reader = csv.DictReader(stream, delimiter=';', restkey='__extra__')
        if len(reader.fieldnames or []) != len(set(reader.fieldnames or [])):
            raise ValueError(f'{path}: duplicate header fields')
        missing = set(names) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f'{path}: missing columns {sorted(missing)}')
        for line, row in enumerate(reader, 2):
            stats['rows_read'] += 1
            if None in row.values() or '__extra__' in row:
                raise ValueError(f'{path}:{line}: malformed CSV row')
            extraction.add((row.get('DT_GERACAO', ''), row.get('HH_GERACAO', '')))
            if int(row['ANO_ELEICAO']) != year or int(row['CD_CARGO']) != 1:
                stats['excluded_scope_rows'] += 1
                continue
            if row['DS_CARGO'].strip().casefold() != 'presidente' or row['SG_UE'].strip().upper() != 'BR':
                raise ValueError(f'{path}:{line}: inconsistent presidential scope')
            key = normalized_key(row)
            vals = []
            for field in FIELDS.values() if kind == 'details' else ['QT_VOTOS']:
                value, reason = quantity(row[field])
                vals.append(value)
                if reason:
                    issues.writerow((kind, line, *key, field, row[field], reason))
                    stats[f'quantity_{reason}_cells'] += 1
            # The fingerprint distinguishes identical raw records from key collisions.
            fingerprint = hashlib.sha256(json.dumps(list(row.values()), ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
            if kind == 'details':
                installed = row['ST_SECAO_INSTALADA'].strip()
                norm = 'yes' if installed.casefold() in {'sim', 's'} else 'no' if installed.casefold() in {'não', 'nao', 'n'} else 'unknown'
                batch.append((line, *key, *vals, installed, row['ST_SECAO_ANULADA'].strip(), row['DS_ORIGEM_VOTO'].strip(), norm, fingerprint))
            else:
                number = row['NR_VOTAVEL'].strip()
                if not re.fullmatch('[0-9]+', number) or int(number) == 0:
                    raise ValueError(f'{path}:{line}: unsupported NR_VOTAVEL {number!r}')
                batch.append((line, *key, int(number), *vals, fingerprint))
            stats['selected_rows'] += 1
            if len(batch) == 10000:
                db.executemany(f'INSERT INTO {table} VALUES ({",".join("?" for _ in batch[0])})', batch)
                batch.clear()
            if stats['selected_rows'] % 1000000 == 0:
                print(f'{kind}: {stats["selected_rows"]:,} rows', file=sys.stderr, flush=True)
        if batch:
            db.executemany(f'INSERT INTO {table} VALUES ({",".join("?" for _ in batch[0])})', batch)
    if not stats['selected_rows']:
        raise ValueError(f'{path}: no presidential records selected for {year}')
    db.commit()
    return {'counts': dict(stats), 'extraction_values': sorted(extraction)}


def build(db):
    key = ','.join(KEY)
    db.execute(f'''CREATE TABLE detail_keys AS SELECT {key}, COUNT(*) AS detail_rows,
        COUNT(DISTINCT fingerprint) AS variants FROM details GROUP BY {key}''')
    db.execute(f'CREATE UNIQUE INDEX detail_keys_ix ON detail_keys ({key})')
    db.execute(f'CREATE INDEX details_ix ON details ({key})')
    db.execute(f'''CREATE TABLE vote_groups AS SELECT {key},number,COUNT(*) AS input_rows,
        COUNT(DISTINCT fingerprint) AS variants, SUM(votes) AS votes,
        SUM(votes IS NULL OR votes<0) AS bad_rows FROM raw_votes GROUP BY {key},number''')
    db.execute(f'CREATE INDEX vote_groups_ix ON vote_groups ({key})')
    db.execute(f'''CREATE TABLE vote_sections AS SELECT {key},COUNT(*) AS votable_groups,
        SUM(input_rows) AS input_rows, SUM(bad_rows) AS bad_rows,
        SUM(CASE WHEN number NOT IN (95,96,97) THEN votes ELSE 0 END) AS nominal,
        SUM(CASE WHEN number=95 THEN votes ELSE 0 END) AS blank,
        SUM(CASE WHEN number=96 THEN votes ELSE 0 END) AS null_votes,
        SUM(CASE WHEN number=97 THEN votes ELSE 0 END) AS separate,
        SUM(votes) AS total_votes FROM vote_groups GROUP BY {key}''')
    db.execute(f'CREATE UNIQUE INDEX vote_sections_ix ON vote_sections ({key})')
    selected = ','.join(f'd.{f}' for f in [*FIELDS, *FLAGS, 'installed_norm', 'line'])
    db.execute(f'''CREATE TABLE joined AS SELECT k.*,COALESCE(c.detail_rows,0) AS detail_rows,
        {selected}, COALESCE(v.input_rows,0) AS vote_rows, COALESCE(v.bad_rows,0) AS bad_vote_rows,
        COALESCE(v.nominal,0) AS v_nominal, COALESCE(v.blank,0) AS v_blank,
        COALESCE(v.null_votes,0) AS v_null_votes, COALESCE(v.separate,0) AS v_separate,
        COALESCE(v.total_votes,0) AS v_total FROM
        (SELECT {key} FROM detail_keys UNION SELECT {key} FROM vote_sections) k
        LEFT JOIN detail_keys c USING ({key})
        LEFT JOIN details d ON {" AND ".join("d."+x+"=k."+x for x in KEY)} AND c.detail_rows=1
        LEFT JOIN vote_sections v USING ({key})''')
    db.commit()


def checks():
    complete = ' AND '.join(f'{f} IS NOT NULL' for f in FIELDS)
    nonnegative = ' AND '.join(f'{f}>=0' for f in FIELDS)
    categories = 'nominal+blank+null_votes+legend+separate'
    category_available = ' AND '.join(f'{f} IS NOT NULL' for f in ['nominal', 'blank', 'null_votes', 'legend', 'separate', 'turnout'])
    # id, table, eligible predicate, available predicate, passing predicate, residual, meaning
    result = [
        ('detail_quantities_complete', 'details', '1', '1', complete, 'NULL', 'All eight detail quantities present and parseable'),
        ('detail_quantities_nonnegative', 'details', '1', complete, nonnegative, 'NULL', 'Detail quantities >= 0'),
        ('turnout_le_electorate', 'details', '1', 'aptos IS NOT NULL AND turnout IS NOT NULL', 'turnout<=aptos', 'turnout-aptos', 'Turnout <= electorate'),
        ('abstentions_le_electorate', 'details', '1', 'aptos IS NOT NULL AND abstentions IS NOT NULL', 'abstentions<=aptos', 'abstentions-aptos', 'Abstentions <= electorate'),
        ('electorate_identity', 'details', '1', 'aptos IS NOT NULL AND turnout IS NOT NULL AND abstentions IS NOT NULL', 'aptos=turnout+abstentions', 'aptos-turnout-abstentions', 'Electorate = turnout + abstentions'),
        ('electorate_identity_installed', 'details', "installed_norm='yes'", 'aptos IS NOT NULL AND turnout IS NOT NULL AND abstentions IS NOT NULL', 'aptos=turnout+abstentions', 'aptos-turnout-abstentions', 'Same identity, installed sections only'),
        ('electorate_identity_not_installed', 'details', "installed_norm='no'", 'aptos IS NOT NULL AND turnout IS NOT NULL AND abstentions IS NOT NULL', 'aptos=turnout+abstentions', 'aptos-turnout-abstentions', 'Same identity, uninstalled sections only'),
        ('installation_status_known', 'details', '1', '1', "installed_norm IN ('yes','no')", 'NULL', 'Installation flag recognized; context check'),
        ('detail_votes_equal_turnout', 'details', '1', category_available, f'{categories}=turnout', f'{categories}-turnout', 'Five detail vote categories = turnout'),
        ('presidential_legend_zero', 'details', '1', 'legend IS NOT NULL', 'legend=0', 'legend', 'No party-list vote in presidential office'),
        ('vote_quantities_complete', 'raw_votes', '1', '1', 'votes IS NOT NULL', 'NULL', 'Vote quantities present and parseable'),
        ('vote_quantities_nonnegative', 'raw_votes', '1', 'votes IS NOT NULL', 'votes>=0', 'votes', 'Vote quantities >= 0'),
        ('unique_detail_key', 'detail_keys', '1', '1', 'detail_rows=1', 'detail_rows-1', 'One raw detail record per section key'),
        ('unique_vote_key', 'vote_groups', '1', '1', 'input_rows=1', 'input_rows-1', 'One raw vote record per section/votable key'),
        ('vote_section_has_unique_detail', 'joined', 'vote_rows>0', '1', 'detail_rows=1', 'NULL', 'Every vote section has exactly one detail record'),
        ('positive_detail_has_votes', 'joined', 'detail_rows=1 AND (turnout>0 OR nominal+blank+null_votes+legend+separate>0)', '1', 'vote_rows>0', 'NULL', 'No positive-turnout/vote detail without vote rows'),
        ('source_votes_le_turnout', 'joined', 'detail_rows=1', 'turnout IS NOT NULL AND bad_vote_rows=0', 'v_total<=turnout', 'v_total-turnout', 'Sum of source vote rows <= turnout'),
        ('source_votes_equal_turnout', 'joined', 'detail_rows=1', 'turnout IS NOT NULL AND bad_vote_rows=0', 'v_total=turnout', 'v_total-turnout', 'Sum of source vote rows = turnout'),
    ]
    for field in ('nominal', 'blank', 'null_votes', 'separate'):
        result.append((f'reconcile_{field}', 'joined', 'detail_rows=1', f'{field} IS NOT NULL AND bad_vote_rows=0', f'v_{field}={field}', f'v_{field}-{field}', f'Source vote rows agree with detail {field}'))
    return result


def evaluate(db, out):
    results = []
    with (out / 'violations.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream, lineterminator='\n')
        writer.writerow(['check', *KEY, 'difference', 'record_json'])
        for cid, table, eligible, available, passing, difference, meaning in checks():
            by_round = {}
            sql = f'''SELECT election_code,turno,uf, COUNT(*) AS universe,
                SUM(CASE WHEN {eligible} THEN 1 ELSE 0 END) AS eligible,
                SUM(CASE WHEN ({eligible}) AND ({available}) THEN 1 ELSE 0 END) AS compared,
                SUM(CASE WHEN ({eligible}) AND ({available}) AND NOT ({passing}) THEN 1 ELSE 0 END) AS violations
                FROM {table} GROUP BY election_code,turno,uf ORDER BY election_code,turno,uf'''
            for row in db.execute(sql):
                row = dict(row)
                totals = by_round.setdefault((row['election_code'], row['turno']), Counter())
                totals.update({f: row[f] for f in ('universe', 'eligible', 'compared', 'violations')})
                row['check'] = cid
                row['not_comparable'] = row['eligible'] - row['compared']
                row['definition'] = meaning
                results.append(row)
            for (election, turn), counts in by_round.items():
                results.append(dict(check=cid, election_code=election, turno=turn, uf='BR', **counts,
                                    not_comparable=counts['eligible']-counts['compared'], definition=meaning))
            for row in db.execute(f'SELECT *,{difference} AS difference FROM {table} WHERE ({eligible}) AND ({available}) AND NOT ({passing})'):
                record = dict(row)
                writer.writerow([cid, *(record[k] for k in KEY), record['difference'], json.dumps(record, ensure_ascii=False, separators=(',', ':'))])
    columns = ['check', 'election_code', 'turno', 'uf', 'universe', 'eligible', 'compared', 'violations', 'not_comparable', 'definition']
    results.sort(key=lambda r: (r['election_code'], r['turno'], r['uf'], r['check']))
    write_csv(out / 'checks.csv', columns, ([r[c] for c in columns] for r in results))
    return results


def export_query(db, out, filename, sql):
    cursor = db.execute(sql)
    write_csv(out / filename, [d[0] for d in cursor.description], cursor)


def summarize(db, out, results):
    key = ','.join(KEY)
    category_sum = 'nominal+blank+null_votes+legend+separate'
    export_query(db, out, 'zero-vote-details-only.csv', f'''SELECT {key},line,aptos,turnout,abstentions,
        nominal,blank,null_votes,legend,separate,installed,cancelled,origin
        FROM joined WHERE detail_rows=1 AND vote_rows=0 AND {category_sum}=0 AND turnout=0
        ORDER BY election_code,turno,uf,municipality,zone,section''')
    export_query(db, out, 'coverage.csv', '''SELECT election_code,turno,uf,
        COUNT(*) AS union_section_keys, SUM(detail_rows>0) AS detail_section_keys,
        SUM(detail_rows) AS detail_input_rows, SUM(vote_rows>0) AS vote_section_keys,
        SUM(vote_rows) AS vote_input_rows,
        SUM(detail_rows=1 AND vote_rows>0) AS matched_unique,
        SUM(detail_rows=0 AND vote_rows>0) AS votes_only,
        SUM(detail_rows>1) AS duplicate_detail_keys,
        SUM(detail_rows=1 AND vote_rows=0) AS details_only,
        SUM(detail_rows=1 AND vote_rows=0 AND nominal+blank+null_votes+legend+separate=0 AND turnout=0) AS zero_details_only
        FROM joined GROUP BY election_code,turno,uf ORDER BY election_code,turno,uf''')
    export_query(db, out, 'detail-context.csv', f'''SELECT election_code,turno,uf,installed,cancelled,origin,
        COUNT(*) AS section_records,SUM(aptos) AS electorate,SUM(turnout) AS turnout,
        SUM(abstentions) AS abstentions,SUM({category_sum}) AS votes,
        SUM(aptos-turnout-abstentions) AS electorate_identity_residual
        FROM details GROUP BY election_code,turno,uf,installed,cancelled,origin
        ORDER BY election_code,turno,uf,installed,cancelled,origin''')
    export_query(db, out, 'duplicate-details.csv', f'''SELECT d.*,c.detail_rows,c.variants FROM details d JOIN detail_keys c USING ({key})
        WHERE c.detail_rows>1 ORDER BY {key},line''')
    export_query(db, out, 'duplicate-votes.csv', f'''SELECT r.*,g.input_rows,g.variants FROM raw_votes r JOIN vote_groups g USING ({key},number)
        WHERE g.input_rows>1 ORDER BY {key},number,line''')
    totals = []
    for row in db.execute(f'''SELECT election_code,turno,uf,COUNT(*) AS section_records,
            {','.join(f'SUM({f}) AS {f}' for f in FIELDS)} FROM details
            GROUP BY election_code,turno,uf ORDER BY election_code,turno,uf'''):
        totals.append(dict(row))
    for election, turn in sorted({(r['election_code'], r['turno']) for r in totals}):
        rows = [r for r in totals if r['election_code']==election and r['turno']==turn]
        totals.append(dict(election_code=election, turno=turn, uf='BR',
                           **{f: sum(r[f] or 0 for r in rows) for f in ['section_records', *FIELDS]}))
    vote_totals = {(r['election_code'],r['turno'],r['uf']):dict(r) for r in db.execute('''SELECT election_code,turno,uf,
        COUNT(*) AS vote_sections,SUM(nominal) AS v_nominal,SUM(blank) AS v_blank,
        SUM(null_votes) AS v_null_votes,SUM(separate) AS v_separate,SUM(total_votes) AS v_total
        FROM vote_sections GROUP BY election_code,turno,uf''')}
    for election, turn in sorted({(k[0],k[1]) for k in vote_totals}):
        rows = [r for k,r in vote_totals.items() if k[:2]==(election,turn)]
        vote_totals[(election,turn,'BR')] = {f:sum(r[f] or 0 for r in rows) for f in ['vote_sections','v_nominal','v_blank','v_null_votes','v_separate','v_total']}
    extra = ['vote_sections','v_nominal','v_blank','v_null_votes','v_separate','v_total']
    for row in totals:
        row.update({f:vote_totals.get((row['election_code'],row['turno'],row['uf']),{}).get(f,0) for f in extra})
        # Summary sums are descriptive; completeness is explicitly checked separately.
        row['electorate_identity_residual'] = row['aptos']-row['turnout']-row['abstentions'] if all(row[f] is not None for f in ['aptos','turnout','abstentions']) else None
    columns = ['election_code','turno','uf','section_records',*FIELDS,*extra,'electorate_identity_residual']
    write_csv(out / 'totals.csv', columns, ([r[c] for c in columns] for r in sorted(totals,key=lambda r:(r['election_code'],r['turno'],r['uf']))))
    return {'national_checks':[r for r in results if r['uf']=='BR'],
            'national_totals':[r for r in totals if r['uf']=='BR'],
            'violations_are_overlapping':True,
            'conclusion_rule':'Report every violated identity and every unavailable comparison; do not equate accounting consistency with authenticity.'}


def run(votes, details, out, year=2026):
    out = Path(out).resolve()
    if out.exists() and any(out.iterdir()):
        raise ValueError(f'Refusing nonempty output directory: {out}')
    out.mkdir(parents=True, exist_ok=True)
    manifest = {'status':'running','hypothesis':'H1','year':year,
                'started_at_utc':datetime.now(timezone.utc).isoformat(),
                'method':'Exhaustive exact integer checks; no sampling, p-values or statistical null model.',
                'python':sys.version,'sqlite':sqlite3.sqlite_version,
                'code_sha256':sha256(__file__), 'inputs':{}}
    for name,path in [('votes',Path(votes)),('details',Path(details))]:
        manifest['inputs'][name] = {'path':str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
                                  'size_bytes':path.stat().st_size,'sha256':sha256(path)}
    base = subprocess.run(['git','rev-parse','HEAD'], cwd=ROOT, text=True, capture_output=True)
    manifest['git_base_commit'] = base.stdout.strip() if base.returncode==0 else None
    write_json(out/'manifest.json',manifest)
    try:
        # Scratch files belong to this hypothesis and are removed after the run.
        scratch = H1 / '.work'
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='primary-', dir=scratch) as temporary:
            with sqlite3.connect(str(Path(temporary)/'audit.sqlite')) as db:
                db.row_factory = sqlite3.Row
                db.execute('PRAGMA journal_mode=OFF')
                db.execute('PRAGMA synchronous=OFF')
                db.execute('PRAGMA temp_store=FILE')
                db.execute('PRAGMA cache_size=-131072')
                keydef = ','.join(k+(' TEXT' if k=='uf' else ' INTEGER') for k in KEY)
                db.execute(f'''CREATE TABLE details (line INTEGER,{keydef},
                    {','.join(f+' INTEGER' for f in FIELDS)},installed TEXT,cancelled TEXT,origin TEXT,
                    installed_norm TEXT,fingerprint TEXT)''')
                db.execute(f'CREATE TABLE raw_votes (line INTEGER,{keydef},number INTEGER,votes INTEGER,fingerprint TEXT)')
                with (out/'input-issues.csv').open('w',encoding='utf-8',newline='') as stream:
                    writer = csv.writer(stream,lineterminator='\n')
                    writer.writerow(['source','line',*KEY,'field','raw_value','reason'])
                    manifest['ingestion'] = {
                        'details':ingest(db,Path(details),'details',year,writer),
                        'votes':ingest(db,Path(votes),'votes',year,writer)}
                print('Building section-level joins and duplicate inventories',file=sys.stderr,flush=True)
                build(db)
                results = evaluate(db,out)
                summary = summarize(db,out,results)
                write_json(out/'summary.json',summary)
        # Catch source changes during the scan as well as identify the snapshot.
        for name,path in [('votes',Path(votes)),('details',Path(details))]:
            if sha256(path)!=manifest['inputs'][name]['sha256']:
                raise ValueError(f'Source changed during analysis: {path}')
        manifest['status']='completed'
        manifest['completed_at_utc']=datetime.now(timezone.utc).isoformat()
        manifest['artifact_sha256']={p.name:sha256(p) for p in sorted(out.iterdir()) if p.is_file() and p.name!='manifest.json'}
        manifest['scratch_database_retained']=False
        write_json(out/'manifest.json',manifest)
        return summary
    except Exception as error:
        manifest['status']='failed'
        manifest['error']=str(error)
        write_json(out/'manifest.json',manifest)
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--votes',type=Path,default=ROOT/VOTES)
    parser.add_argument('--details',type=Path,default=ROOT/DETAILS)
    parser.add_argument('--output',type=Path,required=True,help='New/empty evidence directory')
    parser.add_argument('--year',type=int,default=2026)
    args=parser.parse_args()
    summary=run(args.votes.resolve(),args.details.resolve(),args.output,args.year)
    print(json.dumps({'status':'completed','national_totals':summary['national_totals']},ensure_ascii=False))


if __name__=='__main__':
    main()
