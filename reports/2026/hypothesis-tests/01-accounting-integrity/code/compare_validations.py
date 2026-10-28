#!/usr/bin/env python3
"""Compare separately implemented H1 scans and verify published evidence hashes."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[5]
EXPECTED_CHECKS = {
    'detail_quantities_complete','detail_quantities_nonnegative','turnout_le_electorate',
    'abstentions_le_electorate','electorate_identity','electorate_identity_installed',
    'electorate_identity_not_installed','installation_status_known','detail_votes_equal_turnout',
    'presidential_legend_zero','vote_quantities_complete','vote_quantities_nonnegative',
    'unique_detail_key','unique_vote_key','vote_section_has_unique_detail','positive_detail_has_votes',
    'source_votes_le_turnout','source_votes_equal_turnout','reconcile_nominal','reconcile_blank',
    'reconcile_null_votes','reconcile_separate',
}
UFS = 'AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO ZZ'.split()


def digest(path):
    sha = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(chunk)
    return sha.hexdigest()


def read_csv(path):
    with path.open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def key(row):
    return int(row['election_code']), int(row['turno']), row['uf']


def compare(evidence, output):
    if output.exists():
        raise ValueError('Output already exists; choose a new path')
    accounting = evidence/'accounting'
    manifest = json.loads((accounting/'manifest.json').read_text())
    independent = json.loads((evidence/'independent-validation.json').read_text())
    if manifest['status']!='completed' or independent['status']!='completed':
        raise ValueError('Both scans must be completed before comparing their evidence')
    baseline = json.loads((ROOT/'reports/2026/input-manifest.json').read_text())
    groups = {key(r):r for r in independent['group_totals']}
    secondary = {(*key(r),r['check']):r for r in independent['checks']}
    primary = read_csv(accounting/'checks.csv')
    coverage = read_csv(accounting/'coverage.csv')
    totals = read_csv(accounting/'totals.csv')
    failures, counts = [], {}

    def same(category, name, left, right):
        counts[category] = counts.get(category,0)+1
        if left != right:
            failures.append(dict(category=category, comparison=name, primary=left, independent=right))

    rounds = {(int(r['election_code']),int(r['turno'])) for r in baseline['inputs']['details']['observed_scopes']}
    expected_scopes = {(e,t,u) for e,t in rounds for u in [*UFS,'BR']}
    expected_check_keys = {(*scope,cid) for scope in expected_scopes for cid in EXPECTED_CHECKS}
    actual_check_keys = [(*key(r),r['check']) for r in primary]
    same('inventory','all primary checks present exactly once',sorted(actual_check_keys),sorted(expected_check_keys))
    same('inventory','totals scopes',sorted(key(r) for r in totals),sorted(expected_scopes))
    same('inventory','coverage scopes',sorted(key(r) for r in coverage),sorted(s for s in expected_scopes if s[2]!='BR'))
    same('inventory','independent scopes',sorted(groups),sorted(expected_scopes))
    same('inventory','independent check identifiers unique',len(secondary),len(independent['checks']))
    same('status','primary',manifest['status'],'completed')
    same('status','independent',independent['status'],'completed')
    same('code_hash','primary',manifest['code_sha256'],digest(HERE/'code/run_audit.py'))
    same('code_hash','independent',independent['script_sha256'],digest(HERE/'code/validate_independently.py'))
    for name,source in manifest['inputs'].items():
        same('source_hash',name,source['sha256'],independent['source_files'][name]['sha256'])
        same('source_hash',name+' vs stage 1',source['sha256'],baseline['inputs'][name]['sha256'])
        same('source_size',name,source['size_bytes'],independent['source_files'][name]['bytes'])
    for name,expected in manifest['artifact_sha256'].items():
        same('artifact_hash',name,digest(accounting/name),expected)
    mapping = {
        'turnout_le_electorate':'turnout_not_above_electorate',
        'abstentions_le_electorate':'abstentions_not_above_electorate',
        'electorate_identity':'electorate_equals_turnout_plus_abstentions',
        'electorate_identity_installed':'electorate_equals_turnout_plus_abstentions_installed',
        'electorate_identity_not_installed':'electorate_equals_turnout_plus_abstentions_not_installed',
        'detail_votes_equal_turnout':'detail_all_categories_equal_turnout',
        'presidential_legend_zero':'presidential_legend_votes_zero',
        'source_votes_equal_turnout':'vote_file_all_unique_categories_equal_turnout',
        **{f'reconcile_{p}':f'vote_detail_all_unique_{s}_equality' for p,s in
           [('nominal','nominal'),('blank','blank'),('null_votes','null'),('separate','separate')]},
    }
    for row in primary:
        scope = key(row)
        cid = row['check']
        if cid in mapping:
            other = secondary.get((*scope,mapping[cid]))
            # Empty strata have explicit zero opportunities in the primary scan.
            if other is None:
                other = dict(opportunities=0,evaluated=0,mismatches=0,non_comparable=0)
            for p,s in [('eligible','opportunities'),('compared','evaluated'),('violations','mismatches'),('not_comparable','non_comparable')]:
                same('section_check',f'{scope}:{cid}:{p}',int(row[p]),other[s])
        if cid in {'unique_detail_key','unique_vote_key'}:
            metric = 'duplicate_detail_key_groups' if cid=='unique_detail_key' else 'duplicate_vote_key_groups'
            same('duplicate_keys',f'{scope}:{cid}',int(row['violations']),groups[scope].get(metric,0))
    primary_index = {(*key(r),r['check']):r for r in primary}
    for scope in groups:
        for source,other_name in [('detail','detail_numeric_complete_nonnegative'),('vote','vote_count_complete_nonnegative')]:
            complete = primary_index[(*scope,f'{source}_quantities_complete')]
            nonnegative = primary_index[(*scope,f'{source}_quantities_nonnegative')]
            other = secondary[(*scope,other_name)]
            # Missing rows and complete-but-negative rows are disjoint.
            same('numeric_domain',f'{scope}:{source}:rows',int(complete['eligible']),other['opportunities'])
            same('numeric_domain',f'{scope}:{source}:invalid',int(complete['violations'])+int(nonnegative['violations']),other['mismatches'])
    coverage_map = {'detail_input_rows':'detail_rows','detail_section_keys':'detail_unique_keys',
                    'vote_section_keys':'vote_unique_section_keys','vote_input_rows':'vote_rows',
                    'matched_unique':'matched_unique_keys','votes_only':'vote_only_keys',
                    'duplicate_detail_keys':'duplicate_detail_key_groups','details_only':'detail_only_keys'}
    for row in coverage:
        for p,s in coverage_map.items():
            same('coverage',f'{key(row)}:{p}',int(row[p]),groups[key(row)].get(s,0))
    total_map = {'section_records':'detail_rows','aptos':'QT_APTOS','turnout':'QT_COMPARECIMENTO',
                 'abstentions':'QT_ABSTENCOES','nominal':'QT_VOTOS_NOMINAIS','blank':'QT_VOTOS_BRANCOS',
                 'null_votes':'QT_VOTOS_NULOS','legend':'QT_VOTOS_LEGENDA','separate':'QT_VOTOS_ANULADOS_APU_SEP',
                 'vote_sections':'vote_unique_section_keys','v_nominal':'votes_nominal','v_blank':'votes_blank',
                 'v_null_votes':'votes_null','v_separate':'votes_separate','v_total':'votes_total'}
    for row in totals:
        for p,s in total_map.items():
            same('totals',f'{key(row)}:{p}',int(row[p]),groups[key(row)].get(s,0))
    # Compare all identity exceptions, not just totals; subgroup checks overlap.
    exception_rows = [r for r in read_csv(accounting/'violations.csv') if r['check']=='electorate_identity']
    lhs = sorted((*key(r),int(r['municipality']),int(r['zone']),int(r['section']),int(r['difference'])) for r in exception_rows)
    rhs = sorted((*key(r),r['municipality'],r['zone'],r['section'],r['difference']) for r in independent['examples'].get('electorate_identity_mismatches',[]))
    # The independent sample is complete only if its declared count fits the cap.
    n_exceptions = sum(r['mismatches'] for r in independent['checks'] if r['uf']=='BR' and r['check']=='electorate_equals_turnout_plus_abstentions')
    same('exception_inventory','sample covers all raw exceptions',n_exceptions,len(rhs))
    same('exception_inventory','all exception keys and residuals',lhs,rhs)
    same('source_scope','group inventory',sorted(key(r) for r in totals),sorted(groups))
    result = dict(status='passed' if not failures else 'failed',
                  compared_at_utc=datetime.now(timezone.utc).isoformat(),
                  script_sha256=digest(Path(__file__)),comparisons=counts,
                  total_comparisons=sum(counts.values()),mismatches=len(failures),failures=failures,
                  scope='Exact comparisons between separate source parsers; primary SQLite vs independent dictionaries. Snapshot hashes also match stage 1.',
                  independent_validation_sha256=digest(evidence/'independent-validation.json'),
                  primary_manifest_sha256=digest(accounting/'manifest.json'))
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence',type=Path,default=HERE/'evidence')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=compare(args.evidence,args.output)
    print(json.dumps(result,ensure_ascii=False))
    raise SystemExit(0 if result['status']=='passed' else 1)
