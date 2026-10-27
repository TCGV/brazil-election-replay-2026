"""Descriptive geographic timing and composition analysis of the section replay.

Inputs are read-only. Percentages use 0..100 units. Time percentiles count
sections, not votes. Composition decompositions are exact arithmetic identities,
not causal estimates; all rates use nominal votes in the supplied extraction.
"""
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime, timedelta
import json
import math
from pathlib import Path
import sqlite3

SOURCES = {'first_partial_totalization': 'first_time', 'bu_received': 'bu_time'}
MILESTONES = (5, 10, 25, 50, 75, 90, 99, 100)
CLOCKS = ('17:30', '18:00', '18:30', '19:00', '20:00', '21:00')
DIMENSIONS = ('region', 'uf', 'capital_status', 'size_band', 'uf_capital_status', 'uf_size_band')
TOTAL_KEYS = ('sections', 'electorate', 'nominal', 'lula', 'flavio')
GROUP_SQL = {
    'region': 'region', 'uf': 'uf', 'size_band': 'size_band',
    'capital_status': "CASE WHEN is_capital IS NULL THEN 'exterior' WHEN is_capital=1 THEN 'capital' ELSE 'non_capital' END",
    'uf_capital_status': "uf||'|'||CASE WHEN is_capital IS NULL THEN 'exterior' WHEN is_capital=1 THEN 'capital' ELSE 'non_capital' END",
    'uf_size_band': "uf||'|'||size_band",
}


def percentage(numerator, denominator):
    return 100 * numerator / denominator if denominator else None


def _writer(path, fields):
    stream = path.open('w', encoding='utf-8', newline='')
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
    writer.writeheader()
    return stream, writer


def _row_totals(row):
    return {key: int(row[key] or 0) for key in TOTAL_KEYS}


def _add(destination, source):
    for key in TOTAL_KEYS:
        destination[key] += source[key]


def _blank():
    return {key: 0 for key in TOTAL_KEYS}


def _capital(value):
    return 'exterior' if value is None else ('capital' if value else 'non_capital')


def _group_value(row, dimension):
    if dimension == 'capital_status':
        return _capital(row['is_capital'])
    if dimension == 'uf_capital_status':
        return row['uf'] + '|' + _capital(row['is_capital'])
    if dimension == 'uf_size_band':
        return row['uf'] + '|' + row['size_band']
    if dimension == 'municipality':
        return row['uf'] + '|' + row['municipality']
    return row[dimension]


def _aggregate_municipalities(rows, dimension):
    result = defaultdict(_blank)
    for row in rows.values():
        _add(result[_group_value(row, dimension)], row)
    return dict(result)


def _municipalities(db, election, turn, column=None, cutoff=None, scope='BR'):
    where = 'election_code=? AND turno=?'
    params = [election, turn]
    if scope != 'BR':
        where += ' AND uf=?'
        params.append(scope)
    if column:
        where += f' AND {column} IS NOT NULL AND {column}<=?'
        params.append(cutoff)
    sql = f'''SELECT uf,municipality,MIN(municipality_name) AS municipality_name,
        MIN(region) AS region,MIN(is_capital) AS is_capital,MIN(size_band) AS size_band,
        COUNT(*) AS sections,SUM(COALESCE(aptos,0)) AS electorate,
        SUM(nominal_votes) AS nominal,SUM(lula_votes) AS lula,SUM(flavio_votes) AS flavio
        FROM section_events WHERE {where} GROUP BY uf,municipality'''
    return {(row['uf'], row['municipality']): dict(row) for row in db.execute(sql, params)}


def _sum_municipalities(rows):
    total = _blank()
    for row in rows.values():
        _add(total, row)
    return total


def _minutes(timestamp, origin):
    return (datetime.fromisoformat(timestamp) - origin).total_seconds() / 60 if timestamp else None


def _timing(db, election, turn, source, column, origin, final_municipalities, timing_writer, clock_writer):
    for dimension in DIMENSIONS:
        totals = _aggregate_municipalities(final_municipalities, dimension)
        expression = GROUP_SQL[dimension]
        sql = f'''SELECT {expression} AS group_label,{column} AS event,COUNT(*) AS sections,
            SUM(COALESCE(aptos,0)) AS electorate,SUM(nominal_votes) AS nominal,
            SUM(lula_votes) AS lula,SUM(flavio_votes) AS flavio FROM section_events
            WHERE election_code=? AND turno=? AND {column} IS NOT NULL
            GROUP BY group_label,event ORDER BY group_label,event'''
        events = iter(db.execute(sql, (election, turn)))
        event = next(events, None)
        for group, final in sorted(totals.items()):
            cumulative = _blank()
            quantiles = {}
            clocks = [(datetime.combine(origin.date(), datetime.strptime(clock, '%H:%M').time()).isoformat(sep=' ', timespec='microseconds'), clock) for clock in CLOCKS]
            clock_index = 0

            def emit_clock(index):
                cutoff, clock = clocks[index]
                clock_writer.writerow(dict(source_timestamp=source, election_code=election, turno=turn,
                    dimension=dimension, group=group, clock=clock, cutoff_timestamp=cutoff,
                    total_sections=final['sections'], cumulative_sections=cumulative['sections'],
                    section_completion_percentage=percentage(cumulative['sections'], final['sections']),
                    cumulative_nominal_votes=cumulative['nominal'], nominal_completion_percentage=percentage(cumulative['nominal'], final['nominal']),
                    lula_percentage=percentage(cumulative['lula'], cumulative['nominal']),
                    flavio_percentage=percentage(cumulative['flavio'], cumulative['nominal'])))

            while event and event['group_label'] == group:
                timestamp = event['event']
                while clock_index < len(clocks) and timestamp > clocks[clock_index][0]:
                    emit_clock(clock_index)
                    clock_index += 1
                _add(cumulative, _row_totals(event))
                for target in (10, 50, 90, 99):
                    if target not in quantiles and cumulative['sections'] >= math.ceil(final['sections'] * target / 100):
                        quantiles[target] = timestamp
                event = next(events, None)
            while clock_index < len(clocks):
                emit_clock(clock_index)
                clock_index += 1
            row = dict(source_timestamp=source, election_code=election, turno=turn,
                       dimension=dimension, group=group,total_sections=final['sections'],
                       total_electorate=final['electorate'],total_nominal_votes=final['nominal'],
                       lula_final_percentage=percentage(final['lula'], final['nominal']),
                       flavio_final_percentage=percentage(final['flavio'], final['nominal']))
            for target in (10, 50, 90, 99):
                row[f't{target}'] = quantiles.get(target)
                row[f't{target}_minutes'] = _minutes(quantiles.get(target), origin)
            timing_writer.writerow(row)


def _geographic_minutes(db, election, turn, source, column, origin, final_municipalities, writer):
    bounds = db.execute(f'SELECT MIN({column}),MAX({column}) FROM section_events WHERE election_code=? AND turno=? AND {column} IS NOT NULL', (election,turn)).fetchone()
    if not bounds[0]:
        return
    first = datetime.fromisoformat(bounds[0]).replace(second=0, microsecond=0)
    last = datetime.fromisoformat(bounds[1]).replace(second=0, microsecond=0)
    if (last-first).total_seconds() > 600000*60:
        raise ValueError('Unexpectedly long geographic timeline; inspect input timestamps')
    for dimension in ('region', 'uf'):
        final_groups = _aggregate_municipalities(final_municipalities, dimension)
        sql = f'''SELECT {GROUP_SQL[dimension]} AS group_label,substr({column},1,16)||':00' AS minute,
            COUNT(*) AS sections,SUM(COALESCE(aptos,0)) AS electorate,SUM(nominal_votes) AS nominal,
            SUM(lula_votes) AS lula,SUM(flavio_votes) AS flavio FROM section_events
            WHERE election_code=? AND turno=? AND {column} IS NOT NULL
            GROUP BY group_label,minute ORDER BY group_label,minute'''
        events = iter(db.execute(sql, (election,turn)))
        event = next(events, None)
        for group, final in sorted(final_groups.items()):
            cumulative = _blank()
            minute = first
            while minute <= last:
                label = minute.isoformat(sep=' ', timespec='seconds')
                incoming = _blank()
                if event and event['group_label'] == group and event['minute'] == label:
                    incoming = _row_totals(event)
                    _add(cumulative, incoming)
                    event = next(events, None)
                writer.writerow(dict(source_timestamp=source,election_code=election,turno=turn,
                    dimension=dimension,group=group,minute=label,
                    minutes_after_1700=(minute-origin).total_seconds()/60,
                    sections_in_minute=incoming['sections'],cumulative_sections=cumulative['sections'],
                    section_completion_percentage=percentage(cumulative['sections'],final['sections']),
                    nominal_votes_in_minute=incoming['nominal'],cumulative_nominal_votes=cumulative['nominal'],
                    nominal_completion_percentage=percentage(cumulative['nominal'],final['nominal']),
                    lula_votes_in_minute=incoming['lula'],cumulative_lula_votes=cumulative['lula'],
                    lula_percentage=percentage(cumulative['lula'],cumulative['nominal']),
                    incoming_lula_percentage=percentage(incoming['lula'],incoming['nominal']),
                    flavio_votes_in_minute=incoming['flavio'],cumulative_flavio_votes=cumulative['flavio'],
                    flavio_percentage=percentage(cumulative['flavio'],cumulative['nominal']),
                    incoming_flavio_percentage=percentage(incoming['flavio'],incoming['nominal'])))
                minute += timedelta(minutes=1)


def _milestone_cutoffs(db, election, turn, column, total_sections, scope='BR'):
    where = 'election_code=? AND turno=?'
    params = [election,turn]
    if scope != 'BR':
        where += ' AND uf=?'
        params.append(scope)
    sql = f'''SELECT {column} AS event,COUNT(*) AS n FROM section_events
        WHERE {where} AND {column} IS NOT NULL GROUP BY event ORDER BY event'''
    cumulative = 0
    result = {}
    last = None
    for event, count in db.execute(sql, params):
        cumulative += count
        last = event
        for target in MILESTONES:
            if target not in result and cumulative >= math.ceil(total_sections * target / 100):
                result[target] = (event,True)
    for target in MILESTONES:
        result.setdefault(target,(last,False))
    return result


def _uf_milestones(db, election, turn, source, column, final_municipalities, writer):
    """Stream each UF's timestamp groups once; thresholds use its own sections.

    Complete timestamp ties enter together. All source sections remain in the
    denominator, so missing timestamps cannot silently produce 100% coverage.
    ZZ is exported as its own scope, separate from the 27 domestic UFs.
    """
    totals = _aggregate_municipalities(final_municipalities, 'uf')
    sql = f'''SELECT uf,{column} AS event,COUNT(*) AS sections,
        SUM(COALESCE(aptos,0)) AS electorate,SUM(nominal_votes) AS nominal,
        SUM(lula_votes) AS lula,SUM(flavio_votes) AS flavio FROM section_events
        WHERE election_code=? AND turno=? AND {column} IS NOT NULL
        GROUP BY uf,event ORDER BY uf,event'''
    events = iter(db.execute(sql, (election,turn)))
    event = next(events,None)
    for uf,final in sorted(totals.items()):
        cumulative = _blank()
        pending = list(MILESTONES)
        last = None

        def emit(target,reached):
            writer.writerow(dict(source_timestamp=source,election_code=election,turno=turn,
                scope=uf,requested_sections_percentage=target,cutoff_timestamp=last,
                actual_sections_percentage=percentage(cumulative['sections'],final['sections']),
                target_reached=int(reached),total_sections=final['sections'],
                cumulative_sections=cumulative['sections'],total_nominal_votes=final['nominal'],
                cumulative_nominal_votes=cumulative['nominal'],
                nominal_completion_percentage=percentage(cumulative['nominal'],final['nominal']),
                lula_percentage=percentage(cumulative['lula'],cumulative['nominal']),
                flavio_percentage=percentage(cumulative['flavio'],cumulative['nominal']),
                lula_final_percentage=percentage(final['lula'],final['nominal']),
                flavio_final_percentage=percentage(final['flavio'],final['nominal'])))

        while event and event['uf']==uf:
            last = event['event']
            _add(cumulative,_row_totals(event))
            while pending and cumulative['sections']>=math.ceil(final['sections']*pending[0]/100):
                emit(pending.pop(0),True)
            event = next(events,None)
        for target in pending:
            emit(target,False)


def _decomposition(final, current, total_final, total_current):
    if not total_current['nominal'] or not total_final['nominal']:
        return None
    counterfactual = 0
    for group, observed in current.items():
        ref = final[group]
        if observed['nominal']:
            assert ref['nominal'] > 0
            counterfactual += observed['nominal']/total_current['nominal'] * ref['lula']/ref['nominal']
    current_share = total_current['lula']/total_current['nominal']
    final_share = total_final['lula']/total_final['nominal']
    composition = 100*(counterfactual-final_share)
    within = 100*(current_share-counterfactual)
    gap = 100*(current_share-final_share)
    assert abs(composition+within-gap)<1e-8
    return dict(current_lula_percentage=100*current_share,final_lula_percentage=100*final_share,
                counterfactual_lula_percentage=100*counterfactual,composition_effect_pp=composition,
                within_group_effect_pp=within,total_gap_pp=gap)


def _milestones(db, election, turn, source, column, final_municipalities, national_writer,
                composition_writer, decomposition_writer, municipal_writer):
    summaries = []
    for scope in ('BR','SP'):
        final_munis = {key:row for key,row in final_municipalities.items() if scope=='BR' or key[0]==scope}
        if not final_munis:
            continue
        total_final = _sum_municipalities(final_munis)
        final_groups = {dimension:_aggregate_municipalities(final_munis,dimension) for dimension in DIMENSIONS}
        final_regions = final_groups['region']
        ne_group = next((group for group in final_regions if group.casefold() in {'nordeste','northeast'}),None)
        cutoffs = _milestone_cutoffs(db,election,turn,column,total_final['sections'],scope)
        for target,(cutoff,reached) in cutoffs.items():
            if cutoff is None:
                continue
            current_munis = _municipalities(db,election,turn,column,cutoff,scope)
            current_total = _sum_municipalities(current_munis)
            current_groups = {dimension:_aggregate_municipalities(current_munis,dimension) for dimension in DIMENSIONS}
            observed_regions = current_groups['region']
            ne = observed_regions.get(ne_group,_blank())
            ne_final = final_regions.get(ne_group,_blank())
            common = dict(source_timestamp=source,election_code=election,turno=turn,scope=scope,
                          requested_sections_percentage=target,cutoff_timestamp=cutoff,
                          actual_sections_percentage=percentage(current_total['sections'],total_final['sections']))
            national = dict(common,target_reached=int(reached),cumulative_sections=current_total['sections'],
                            cumulative_nominal_votes=current_total['nominal'],nominal_completion_percentage=percentage(current_total['nominal'],total_final['nominal']),
                            lula_percentage=percentage(current_total['lula'],current_total['nominal']),
                            flavio_percentage=percentage(current_total['flavio'],current_total['nominal']),
                            lula_final_percentage=percentage(total_final['lula'],total_final['nominal']),
                            flavio_final_percentage=percentage(total_final['flavio'],total_final['nominal']),
                            ne_weight_percentage=percentage(ne['nominal'],current_total['nominal']) if ne_group else None,
                            ne_final_weight_percentage=percentage(ne_final['nominal'],total_final['nominal']) if ne_group else None,
                            ne_sections_completion_percentage=percentage(ne['sections'],ne_final['sections']) if ne_group else None)
            national_writer.writerow(national)
            summaries.append(national)
            if scope=='BR':
                for dimension in ('region','uf','capital_status','size_band'):
                    final_dimension,current_dimension = final_groups[dimension],current_groups[dimension]
                    for group,ref in sorted(final_dimension.items()):
                        observed=current_dimension.get(group,_blank())
                        composition_writer.writerow(dict(common,dimension=dimension,group=group,
                            total_sections=ref['sections'],cumulative_sections=observed['sections'],
                            section_completion_percentage=percentage(observed['sections'],ref['sections']),
                            current_section_weight_percentage=percentage(observed['sections'],current_total['sections']),
                            final_section_weight_percentage=percentage(ref['sections'],total_final['sections']),
                            cumulative_nominal_votes=observed['nominal'],total_nominal_votes=ref['nominal'],
                            current_nominal_weight_percentage=percentage(observed['nominal'],current_total['nominal']),
                            final_nominal_weight_percentage=percentage(ref['nominal'],total_final['nominal']),
                            lula_percentage=percentage(observed['lula'],observed['nominal']),
                            lula_final_percentage=percentage(ref['lula'],ref['nominal']),
                            flavio_percentage=percentage(observed['flavio'],observed['nominal']),
                            flavio_final_percentage=percentage(ref['flavio'],ref['nominal'])))
            decompositions = ('region','uf') if scope=='BR' else ('municipality',)
            for dimension in decompositions:
                final_dimension = _aggregate_municipalities(final_munis,dimension)
                current_dimension = _aggregate_municipalities(current_munis,dimension)
                decomposition = _decomposition(final_dimension,current_dimension,total_final,current_total)
                if decomposition:
                    decomposition_writer.writerow(dict(common,dimension=dimension,**decomposition))
            if scope=='SP' and current_total['nominal'] and total_final['nominal']:
                for key,ref in sorted(final_munis.items()):
                    observed = current_munis.get(key,_blank())
                    final_weight=ref['nominal']/total_final['nominal']
                    current_weight=observed['nominal']/current_total['nominal']
                    final_rate=ref['lula']/ref['nominal'] if ref['nominal'] else 0
                    current_rate=observed['lula']/observed['nominal'] if observed['nominal'] else 0
                    municipal_writer.writerow(dict(common,uf=key[0],municipality=key[1],municipality_name=ref['municipality_name'],
                        is_capital=ref['is_capital'],size_band=ref['size_band'],
                        section_completion_percentage=percentage(observed['sections'],ref['sections']),
                        current_nominal_weight_percentage=100*current_weight,final_nominal_weight_percentage=100*final_weight,
                        lula_percentage=percentage(observed['lula'],observed['nominal']),lula_final_percentage=100*final_rate,
                        composition_contribution_pp=100*(current_weight-final_weight)*final_rate,
                        within_contribution_pp=100*current_weight*(current_rate-final_rate),
                        centered_composition_contribution_pp=100*(current_weight-final_weight)*(final_rate-total_final['lula']/total_final['nominal'])))
    return summaries


def analyze(db_path:Path,output_dir:Path)->dict:
    """Write descriptive evidence CSVs from an existing section-level analytics DB."""
    db_path,output_dir=Path(db_path),Path(output_dir)
    output_dir.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(db_path.resolve().as_uri()+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA query_only=ON')
    handles=[]
    summary_path=output_dir/'summary.json'
    summary={'status':'running'}
    summary_path.write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    def writer(name,fields):
        stream,result=_writer(output_dir/name,fields)
        handles.append(stream)
        return result
    try:
        timing=writer('timing-summary.csv',['source_timestamp','election_code','turno','dimension','group','total_sections','total_electorate','total_nominal_votes','lula_final_percentage','t10','t50','t90','t99','t10_minutes','t50_minutes','t90_minutes','t99_minutes','flavio_final_percentage'])
        clock=writer('clock-completion.csv',['source_timestamp','election_code','turno','dimension','group','clock','cutoff_timestamp','total_sections','cumulative_sections','section_completion_percentage','cumulative_nominal_votes','nominal_completion_percentage','lula_percentage','flavio_percentage'])
        minute=writer('geographic-minute.csv',['source_timestamp','election_code','turno','dimension','group','minute','minutes_after_1700','sections_in_minute','cumulative_sections','section_completion_percentage','nominal_votes_in_minute','cumulative_nominal_votes','nominal_completion_percentage','lula_votes_in_minute','cumulative_lula_votes','lula_percentage','incoming_lula_percentage','flavio_votes_in_minute','cumulative_flavio_votes','flavio_percentage','incoming_flavio_percentage'])
        common=['source_timestamp','election_code','turno','scope','requested_sections_percentage','cutoff_timestamp','actual_sections_percentage']
        national=writer('national-milestones.csv',common+['target_reached','cumulative_sections','cumulative_nominal_votes','nominal_completion_percentage','lula_percentage','flavio_percentage','lula_final_percentage','flavio_final_percentage','ne_weight_percentage','ne_final_weight_percentage','ne_sections_completion_percentage'])
        composition=writer('milestone-composition.csv',common+['dimension','group','total_sections','cumulative_sections','section_completion_percentage','current_section_weight_percentage','final_section_weight_percentage','cumulative_nominal_votes','total_nominal_votes','current_nominal_weight_percentage','final_nominal_weight_percentage','lula_percentage','lula_final_percentage','flavio_percentage','flavio_final_percentage'])
        uf_milestones=writer('uf-milestones.csv',common+['target_reached','total_sections','cumulative_sections','total_nominal_votes','cumulative_nominal_votes','nominal_completion_percentage','lula_percentage','flavio_percentage','lula_final_percentage','flavio_final_percentage'])
        decomposition=writer('composition-decomposition.csv',common+['dimension','current_lula_percentage','final_lula_percentage','counterfactual_lula_percentage','composition_effect_pp','within_group_effect_pp','total_gap_pp'])
        municipal=writer('sp-municipality-contributions.csv',common+['uf','municipality','municipality_name','is_capital','size_band','section_completion_percentage','current_nominal_weight_percentage','final_nominal_weight_percentage','lula_percentage','lula_final_percentage','composition_contribution_pp','within_contribution_pp','centered_composition_contribution_pp'])
        summary={'method':'Descriptive census of recorded section arrivals; no causal or individual-demographic inference',
            'size_metric':'Registered electorate aggregated once per municipality, not resident population',
            'percentiles':'t10/t50/t90/t99 count sections using all simultaneous arrivals; not vote-weighted',
            'time_origin':'17:00 Hora TSE on earliest first-totalization date for the election; UTC offset unverified',
            'clock_cutoff':'Exact HH:MM:00, inclusive; minute curves accumulate through end of each minute',
            'milestones':'Requested fraction of all sections with vote records; include all tied arrivals and report actual attained fraction',
            'decomposition':'current share - final share = composition effect + within-group ordering effect; descriptive arithmetic identity',
            'sources':list(SOURCES),'origins':[],'national_milestones':[]}
        summary['coverage']=[dict(row) for row in db.execute('''SELECT election_code,turno,COUNT(*) AS sections,
            SUM(nominal_votes) AS nominal_votes,SUM(first_time IS NULL) AS first_time_missing_sections,
            SUM(bu_time IS NULL) AS bu_time_missing_sections FROM section_events GROUP BY election_code,turno''')]
        partitions=list(db.execute('SELECT DISTINCT election_code,turno FROM section_events ORDER BY election_code,turno'))
        for election,turn in partitions:
            final_municipalities=_municipalities(db,election,turn)
            first=db.execute('SELECT MIN(first_time),MIN(bu_time) FROM section_events WHERE election_code=? AND turno=?',(election,turn)).fetchone()
            earliest=first[0] or first[1]
            if not earliest:
                raise ValueError(f'No usable timestamps in election {election}, round {turn}')
            origin=datetime.combine(datetime.fromisoformat(earliest).date(),datetime.strptime('17:00','%H:%M').time())
            summary['origins'].append({'election_code':election,'turno':turn,'origin':origin.isoformat(sep=' ')})
            for source,column in SOURCES.items():
                _timing(db,election,turn,source,column,origin,final_municipalities,timing,clock)
                _geographic_minutes(db,election,turn,source,column,origin,final_municipalities,minute)
                summary['national_milestones'].extend(_milestones(db,election,turn,source,column,final_municipalities,national,composition,decomposition,municipal))
                _uf_milestones(db,election,turn,source,column,final_municipalities,uf_milestones)
        summary['status']='completed'
        (output_dir/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        return summary
    except Exception as error:
        summary['status']='failed'
        summary['error']=str(error)
        summary_path.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        raise
    finally:
        for handle in handles:
            handle.close()
        db.close()
