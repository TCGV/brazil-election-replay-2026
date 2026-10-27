"""Prepare a reproducible section-level geographic analysis without changing inputs."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import sqlite3
import unicodedata

REGIONS = {
    **dict.fromkeys(['AC','AP','AM','PA','RO','RR','TO'], 'Norte'),
    **dict.fromkeys(['AL','BA','CE','MA','PB','PE','PI','RN','SE'], 'Nordeste'),
    **dict.fromkeys(['ES','MG','RJ','SP'], 'Sudeste'),
    **dict.fromkeys(['PR','RS','SC'], 'Sul'),
    **dict.fromkeys(['DF','GO','MT','MS'], 'Centro-Oeste'), 'ZZ':'Exterior',
}
CAPITALS = {
    'AC':'RIO BRANCO','AL':'MACEIÓ','AP':'MACAPÁ','AM':'MANAUS','BA':'SALVADOR',
    'CE':'FORTALEZA','DF':'BRASÍLIA','ES':'VITÓRIA','GO':'GOIÂNIA','MA':'SÃO LUÍS',
    'MT':'CUIABÁ','MS':'CAMPO GRANDE','MG':'BELO HORIZONTE','PA':'BELÉM',
    'PB':'JOÃO PESSOA','PR':'CURITIBA','PE':'RECIFE','PI':'TERESINA',
    'RJ':'RIO DE JANEIRO','RN':'NATAL','RS':'PORTO ALEGRE','RO':'PORTO VELHO',
    'RR':'BOA VISTA','SC':'FLORIANÓPOLIS','SP':'SÃO PAULO','SE':'ARACAJU','TO':'PALMAS',
}
KEY = 'election_code,turno,uf,municipality,zone,section,cargo'


def normalize_name(value):
    return ''.join(c for c in unicodedata.normalize('NFD', value.upper().strip())
                   if not unicodedata.combining(c))


def size_band(electorate):
    if electorate <= 10000:
        return '<=10k'
    if electorate <= 50000:
        return '10k-50k'
    if electorate <= 200000:
        return '50k-200k'
    if electorate <= 1000000:
        return '200k-1m'
    return '>1m'


def file_hash(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        while chunk:=stream.read(1024*1024):
            digest.update(chunk)
    return digest.hexdigest()


def build_analysis_database(replay_database: Path, details_csv: Path, output_dir: Path):
    replay_database, details_csv, output_dir=map(Path,(replay_database,details_csv,output_dir))
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f'Preserve previous analysis: output must be empty: {output_dir}')
    replay_manifest=json.loads((replay_database.parent/'input-manifest.json').read_text())
    if replay_manifest['status']!='completed':
        raise ValueError('A completed replay is required')
    for entry in replay_manifest['inputs'].values():
        path=Path(entry['path'])
        if path.stat().st_size!=entry['size_bytes'] or file_hash(path)!=entry['sha256']:
            raise ValueError(f'Source changed since replay: {path}')
    names={}
    year=replay_manifest['year']
    with details_csv.open(encoding='latin1',newline='') as stream:
        for row in csv.DictReader(stream,delimiter=';'):
            if int(row['ANO_ELEICAO'])!=year or int(row['CD_CARGO'])!=1:
                continue
            key=(str(int(row['CD_ELEICAO'])),str(int(row['NR_TURNO'])),row['SG_UF'],str(int(row['CD_MUNICIPIO'])))
            name=row['NM_MUNICIPIO'].strip()
            if key in names and names[key]!=name:
                raise ValueError(f'Ambiguous municipality name: {key}')
            names[key]=name
    output_dir.mkdir(parents=True,exist_ok=True)
    db_path=output_dir/'analysis.sqlite'
    db=sqlite3.connect(str(db_path),uri=True)
    try:
        db.execute('PRAGMA cache_size=-65536')
        db.execute('PRAGMA temp_store=FILE')
        db.execute('ATTACH DATABASE ? AS replay',(replay_database.resolve().as_uri()+'?mode=ro',))
        db.execute('''CREATE TABLE municipality_metadata(election_code TEXT,turno TEXT,uf TEXT,municipality TEXT,
            municipality_name TEXT,region TEXT,is_capital INTEGER,municipality_electorate INTEGER,size_band TEXT,
            round_electorate INTEGER,PRIMARY KEY(election_code,turno,uf,municipality))''')
        totals=list(db.execute('''SELECT election_code,turno,uf,municipality,SUM(aptos) FROM replay.details
            GROUP BY election_code,turno,uf,municipality ORDER BY CAST(turno AS INTEGER),election_code,uf,municipality'''))
        baseline={}
        for _,_,uf,municipality,total in totals:
            if total is None:
                raise ValueError('Missing electorate: cannot assign municipality size')
            baseline.setdefault((uf,municipality),total)
        records=[]
        capitals={}
        for election,turn,uf,municipality,total in totals:
            if uf not in REGIONS:
                raise ValueError(f'Unknown UF: {uf}')
            name=names[(election,turn,uf,municipality)]
            capital=None if uf=='ZZ' else int(normalize_name(name)==normalize_name(CAPITALS[uf]))
            if capital:
                capitals.setdefault((election,turn),set()).add(uf)
            electorate=baseline[(uf,municipality)]
            records.append((election,turn,uf,municipality,name,REGIONS[uf],capital,electorate,
                            'exterior' if uf=='ZZ' else size_band(electorate),total))
        for election,turn in {(r[0],r[1]) for r in totals}:
            if capitals.get((election,turn))!=set(CAPITALS):
                raise ValueError(f'Capital classification incomplete: {election}/{turn}')
        db.executemany('INSERT INTO municipality_metadata VALUES (?,?,?,?,?,?,?,?,?,?)',records)
        db.execute(f'''CREATE TABLE candidate_sections AS SELECT {KEY},
            SUM(CASE WHEN nr_votavel=13 THEN votes ELSE 0 END) AS lula_votes,
            SUM(CASE WHEN nr_votavel=22 THEN votes ELSE 0 END) AS flavio_votes
            FROM replay.votes GROUP BY {KEY}''')
        db.execute(f'CREATE UNIQUE INDEX candidate_sections_key ON candidate_sections({KEY})')
        db.execute(f'''CREATE TABLE section_events AS SELECT s.election_code,s.turno,s.uf,s.municipality,
            m.municipality_name,s.zone,s.section,m.region,m.is_capital,m.size_band,m.municipality_electorate,
            d.aptos,s.nominal_votes,c.lula_votes,c.flavio_votes,d.first_time,d.bu_time
            FROM replay.sections s JOIN replay.details d USING({KEY}) JOIN candidate_sections c USING({KEY})
            JOIN municipality_metadata m USING(election_code,turno,uf,municipality)''')
        db.execute('CREATE UNIQUE INDEX event_key ON section_events(election_code,turno,uf,municipality,zone,section)')
        db.execute('CREATE INDEX event_first ON section_events(election_code,turno,first_time)')
        db.execute('CREATE INDEX event_bu ON section_events(election_code,turno,bu_time)')
        db.execute('DROP TABLE candidate_sections')
        section_count=db.execute('SELECT COUNT(*) FROM section_events').fetchone()[0]
        expected=db.execute('SELECT COUNT(*) FROM replay.sections').fetchone()[0]
        if section_count!=expected:
            raise ValueError('Analysis join lost or multiplied sections')
        source_totals=list(db.execute('SELECT election_code,turno,SUM(nominal_votes),SUM(lula_votes),SUM(flavio_votes) FROM section_events GROUP BY election_code,turno'))
        missing=list(db.execute('SELECT election_code,turno,SUM(first_time IS NULL),SUM(bu_time IS NULL) FROM section_events GROUP BY election_code,turno'))
        if any(first or bu for _,_,first,bu in missing):
            raise ValueError('Timing coverage incomplete: analysis must explicitly handle missing timestamps')
        db.commit()
        manifest={'status':'completed','year':year,'source_replay':str(replay_database),'source_inputs':replay_manifest['inputs'],
                  'analysis_sections':section_count,'totals':source_totals,'capital_mapping':CAPITALS,
                  'size_proxy':'registered electorate, not resident population',
                  'size_baseline':'first available round for each municipality; held fixed across rounds',
                  'country_scope':'BR includes ZZ; municipal/capital/size comparisons exclude ZZ',
                  'time_convention':replay_manifest['time_convention'],'geographic_fields_source':str(details_csv),
                  'municipalities':len(records),'database':str(db_path)}
        (output_dir/'analysis-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
        return db_path
    finally:
        db.close()
