#!/usr/bin/env python3
"""Rebuild H2 publication aggregates from the independently audited primary tables.

This is a transitive consistency check, not another source scan, model fit, or
independent recomputation of sensitivity scenarios. No primary module is imported.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

HERE=Path(__file__).resolve().parents[1]
ARTIFACTS={'coverage.csv','strata.csv','cases.csv','uf-summary.csv','association-tests.csv','sensitivity.csv','summary.json'}
UF_FIELDS=('covered','n_strata','joint_count','priority_count','local_persists','local_attenuated','local_insufficient')
STATUSES=('persists_both','attenuated_one_or_both','insufficient_peers','not_priority_not_assessed')
ASSOCIATION_INTS={'election_code','turno','candidate','n_strata','n_sections','observed_joint','priority_count','simulations','seed','exceedances'}


def digest(path):
    sha=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            sha.update(block)
    return sha.hexdigest()


def read_csv(path):
    with Path(path).open(encoding='utf-8',newline='') as stream:
        return list(csv.DictReader(stream))


def identity(row,with_uf=False):
    values=(int(row['election_code']),int(row['turno']),int(row['candidate']))
    return (*values,row['uf']) if with_uf else values


def section_round(row):
    return (int(row['election_code']),int(row['turno']),row['uf'],int(row['municipality']),int(row['zone']),int(row['section']))


def validate(analysis,figures=None):
    analysis=Path(analysis)
    manifest=json.loads((analysis/'manifest.json').read_text())
    independent_path=analysis.parent/'independent-validation.json'
    independent=json.loads(independent_path.read_text())
    if manifest.get('status')!='completed' or independent.get('status')!='passed' or independent.get('mismatches')!=0:
        raise ValueError('Completed primary analysis and passed independent validation required')
    counts=Counter();failures=[]

    def same(category,label,actual,expected,tolerance=None):
        counts[category]+=1
        if tolerance is None:
            passed=actual==expected
        else:
            passed=math.isfinite(float(actual)) and math.isfinite(float(expected)) and abs(float(actual)-float(expected))<=tolerance
        if not passed:
            counts['mismatches']+=1
            if len(failures)<100:
                failures.append(dict(category=category,comparison=label,actual=actual,expected=expected))

    def unique(rows,key,category):
        indexed={key(row):row for row in rows}
        same('inventory',category+' unique keys',len(indexed),len(rows))
        return indexed

    same('inventory','required primary artifacts in manifest',sorted(manifest['artifact_sha256']),sorted(ARTIFACTS))
    same('inventory','published primary files',sorted(p.name for p in analysis.iterdir() if p.is_file() and p.name!='manifest.json'),sorted(ARTIFACTS))
    for name in sorted(ARTIFACTS):
        same('artifact_integrity',name,digest(analysis/name),manifest['artifact_sha256'].get(name))
    for name,source in independent['source_inputs'].items():
        for field in ('sha256','size_bytes'):
            same('source_link',name+':'+field,manifest['source_inputs'][name][field],source[field])

    strata=read_csv(analysis/'strata.csv');cases=read_csv(analysis/'cases.csv')
    coverage=read_csv(analysis/'coverage.csv');tests=read_csv(analysis/'association-tests.csv')
    summaries=read_csv(analysis/'uf-summary.csv');summary=json.loads((analysis/'summary.json').read_text())
    coverage_index=unique(coverage,lambda r:(int(r['election_code']),int(r['turno']),r['uf']),'coverage')
    test_index=unique(tests,identity,'association family')
    frozen_family={(6257,1,c) for c in (13,14,16,21,22,27,28,29,30,35,55,70,80)}|{(6258,2,13),(6258,2,22)}
    same('inventory','fifteen predeclared candidate-round identities',sorted(test_index),sorted(frozen_family))
    expected_uf_keys={(*key,uf) for key in test_index for e,t,uf in coverage_index if (e,t)==key[:2] and uf!='BR'}
    uf_index=unique(summaries,lambda r:identity(r,True),'UF summaries')
    same('inventory','complete UF summary inventory',sorted(uf_index),sorted(expected_uf_keys))

    groups=defaultdict(Counter);expected_terms=defaultdict(list);variance_terms=defaultdict(list)
    group_counts=Counter()
    for row in strata:
        key=identity(row,True)
        groups[key].update(covered=int(row['n']),n_strata=1,strata_joint=int(row['joint_count']),strata_priority=int(row['priority_count']))
        expected_terms[key].append(float(row['expected_joint']))
        variance_terms[key].append(float(row['variance']))
        group_counts[(*key,int(row['municipality']),int(row['zone']),int(row['size_band']))]+=1
    same('inventory','stratum keys unique',max(group_counts.values(),default=0),1 if strata else 0)
    same('inventory','all stratum UF identities represented',sorted(set(groups)-expected_uf_keys),[])

    case_counts=Counter();local_counts=Counter();priority_sections=set();all_sections=set()
    for row in cases:
        key=identity(row,True);priority=int(row['priority'])
        status=row['local_status'];all_sections.add(section_round(row))
        case_counts[(*key,int(row['municipality']),int(row['zone']),int(row['section']))]+=1
        groups[key].update(joint_count=1,priority_count=priority)
        if priority:
            priority_sections.add(section_round(row))
        local_counts[status]+=1
        mapped={'persists_both':'local_persists','attenuated_one_or_both':'local_attenuated','insufficient_peers':'local_insufficient'}.get(status)
        if mapped:
            groups[key][mapped]+=1
    same('inventory','case keys unique',max(case_counts.values(),default=0),1 if cases else 0)
    same('inventory','all case UF identities represented',sorted(set(groups)-expected_uf_keys),[])
    same('inventory','only declared local statuses',sorted(set(local_counts)-set(STATUSES)),[])
    for key in sorted(expected_uf_keys&set(uf_index)):
        row=uf_index[key];expected=groups[key]
        for field in UF_FIELDS:
            same('uf_summary',f'{key}:{field}',int(row[field]),expected[field])
        same('uf_summary',f'{key}:expected_joint',float(row['expected_joint']),math.fsum(expected_terms[key]),1e-9)
        same('aggregate_link',f'{key}:strata/cases joint',expected['strata_joint'],expected['joint_count'])
        same('aggregate_link',f'{key}:strata/cases priority',expected['strata_priority'],expected['priority_count'])
    for key,row in test_index.items():
        keys=[k for k in expected_uf_keys if k[:3]==key]
        for field,source in [('n_strata','n_strata'),('n_sections','covered'),('observed_joint','joint_count'),('priority_count','priority_count')]:
            same('association_link',f'{key}:{field}',int(row[field]),sum(groups[k][source] for k in keys))
        same('association_link',f'{key}:expected_joint',float(row['expected_joint']),math.fsum(v for k in keys for v in expected_terms[k]),1e-9)
        same('association_link',f'{key}:variance',float(row['variance']),math.fsum(v for k in keys for v in variance_terms[k]),1e-9)

    national=[{k:(v if k=='uf' else int(v)) for k,v in row.items()} for row in coverage if row['uf']=='BR']
    same('summary_coverage','national coverage',sorted(summary['coverage'],key=lambda r:r['turno']),sorted(national,key=lambda r:r['turno']))
    def typed_test(row):
        return {field:(int(value) if field in ASSOCIATION_INTS else value if field=='status' or value=='' else float(value)) for field,value in row.items()}
    same('summary_tests','all formal test fields',sorted(summary['association_tests'],key=identity),sorted(map(typed_test,tests),key=identity))
    same('summary_counts','all joint cases',summary['total_joint_cases'],len(cases))
    same('summary_counts','priority cases',summary['total_priority_cases'],sum(groups[k]['priority_count'] for k in expected_uf_keys))
    same('summary_counts','local statuses',summary['local_context'],{status:local_counts[status] for status in STATUSES})
    same('summary_configuration','descriptive scenarios',summary['scenarios'],manifest['scenarios'])
    sensitivity=read_csv(analysis/'sensitivity.csv')
    sensitivity_keys=unique(sensitivity,lambda r:(*identity(r),r['scenario']),'sensitivity inventory')
    expected_sensitivity={(*key,scenario['name']) for key in frozen_family for scenario in manifest['scenarios']}
    same('inventory','descriptive scenario row inventory',sorted(sensitivity_keys),sorted(expected_sensitivity))

    if figures is not None:
        figures=Path(figures);fig_manifest=json.loads((figures/'manifest.json').read_text())
        same('figure_integrity','completed',fig_manifest['status'],'completed')
        same('figure_integrity','generator code',fig_manifest['code_sha256'],digest(HERE/'code/generate_figures.py'))
        expected_names={f'{base}.{extension}' for base in ('coverage-by-uf','association-reference','joint-tail-magnitudes','priority-local-context') for extension in ('png','svg')}
        records=unique(fig_manifest['figures'],lambda r:r['path'],'figure inventory')
        same('inventory','all eight figure files',sorted(records),sorted(expected_names))
        same('inventory','figure inputs',sorted(fig_manifest['input_sha256']),['association-tests.csv','cases.csv','coverage.csv'])
        for name,sha in fig_manifest['input_sha256'].items():
            same('figure_integrity','input '+name,sha,digest(analysis/name))
        for name,row in records.items():
            same('figure_integrity',name+' sha256',row['sha256'],digest(figures/name))
            same('figure_integrity',name+' size',row['size_bytes'],(figures/name).stat().st_size)
    mismatches=counts.pop('mismatches',0)
    return dict(status='passed' if mismatches==0 else 'failed',completed_at_utc=datetime.now(timezone.utc).isoformat(),
                script_sha256=digest(Path(__file__)),comparisons=dict(counts),mismatches=mismatches,failures=failures,
                independently_audited_input_sha256={name:digest(analysis/name) for name in ('strata.csv','cases.csv','coverage.csv','association-tests.csv')},
                independent_validation_sha256=digest(independent_path),
                derived_counts=dict(joint_cases=len(cases),distinct_joint_section_rounds=len(all_sections),
                                    priority_cases=sum(groups[k]['priority_count'] for k in expected_uf_keys),
                                    distinct_priority_section_rounds=len(priority_sections),uf_summary_rows=len(summaries),
                                    local_context={status:local_counts[status] for status in STATUSES}),
                scope='Transitive consistency checks from independently audited primary tables; no new original-source scan, Monte Carlo regeneration, sensitivity-model recomputation, or external authentication.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analysis-dir',type=Path,default=HERE/'evidence/analysis')
    parser.add_argument('--figures',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():
        parser.error('Output already exists; choose a new path')
    result=validate(args.analysis_dir,args.figures)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
    raise SystemExit(0 if result['status']=='passed' else 1)


if __name__=='__main__':
    main()
