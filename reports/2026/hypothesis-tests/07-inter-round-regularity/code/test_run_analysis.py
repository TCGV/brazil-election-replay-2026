"""H7 CLI verification using artificial original-format inputs only.

Temporary source/H1/Git scaffolding adapts H6 test_run_analysis.py at commit
cb32076a0eea70a35782fbabba7777a5e49c94fc. No observed H7 results are used.
"""
from __future__ import annotations

from collections import defaultdict
import csv
from fractions import Fraction
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import unittest

import numpy as np

import test_load_data as fixtures
import run_analysis as runner

SCRIPT = Path(__file__).with_name('run_analysis.py')
HERE = SCRIPT.parent.parent
CANDIDATES = {1:[13,14,16,21,22,27,28,29,30,35,55,70,80],2:[13,22]}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rows(path):
    opener=gzip.open if Path(path).suffix=='.gz' else open
    with opener(path,'rt',encoding='utf-8',newline='') as stream:
        return list(csv.DictReader(stream))


class AnalysisCliTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.LoaderTests('test_sorted_arrays_zero_vote_categories_and_uninstalled_rows_survive_cache')
        self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.root=self.fixture.root
        self.municipalities=(10,20,30)
        self.rebuild()
        subprocess.run(['git','init','--quiet',str(self.root)],check=True,capture_output=True)
        subprocess.run(['git','-c','user.name=H7 synthetic fixture','-c','user.email=h7-fixture@example.invalid',
            '-c','commit.gpgsign=false','-c','core.hooksPath=/dev/null','commit','--quiet','--allow-empty',
            '-m','Artificial H7 CLI fixture'],cwd=self.root,check=True,capture_output=True)

    def add_section(self,municipality,section,turn,*,uf='SP',aptos=400,place=1001,index=0,installed='Sim',small=False):
        if installed=='Não':
            turnout=nominal=lula=other=blank=null=0
        elif small:
            turnout=30;nominal=25;lula=11;other=3 if turn==1 else 0;blank=2;null=3
        else:
            turnout=300 if turn==1 else 310+2*index
            nominal=turnout-5;blank=2;null=3;other=25 if turn==1 else 0
            if turn==1:lula=135
            else:lula=int(round(nominal*(.50+{10:.06,20:-.025,30:.01}.get(municipality,.02)+(index%3-1)*.012)))
        detail=self.fixture.detail(section,turn,aptos=aptos,turnout=turnout,
            abstentions=aptos-turnout if installed=='Sim' else 0,
            nominal=nominal,blank=blank,null_votes=null,separate=0,installed=installed)
        detail.update(SG_UF=uf,CD_MUNICIPIO=str(municipality),NM_MUNICIPIO=f'ARTIFICIAL {uf} {municipality}',NR_LOCAL_VOTACAO=str(place))
        self.fixture.details.append(detail)
        if turnout:
            choices={13:lula,22:nominal-other-lula,14:other,95:blank,96:null,97:0}
            for candidate in [*CANDIDATES[turn],95,96,97]:
                self.fixture.votes.append({**{key:detail[key] for key in [*fixtures.LOADER.KEY_FIELDS,'ANO_ELEICAO','DS_CARGO','SG_UE']},
                    'NR_VOTAVEL':str(candidate),'NM_VOTAVEL':f'Artificial candidate {candidate}','QT_VOTOS':str(choices.get(candidate,0))})

    def rebuild(self):
        self.fixture.details=[];self.fixture.votes=[]
        for turn in (1,2):
            for municipality in self.municipalities:
                for index in range(6) if turn==1 else reversed(range(6)):
                    self.add_section(municipality,index+1,turn,index=index,place=1001+index//3)
            self.add_section(30341,1,turn,uf='ZZ')
            self.add_section(30342,1,turn,uf='ZZ',aptos=20,installed='Não')
            self.add_section(50,1,turn,aptos=40,small=True)
        self.add_section(40,99,1)
        self.pin()

    def pin(self):
        self.fixture.write_sources();self.fixture.pin_sources()
        self.original={kind:(self.root/relative).read_bytes() for kind,relative in fixtures.LOADER.SOURCE_PATHS.items()}

    def cli(self,name,*,workers=1,simulations=19,simulation_cache=None,expect=0):
        output=self.root/name
        cache=self.root/'simulation-cache' if simulation_cache is None else simulation_cache
        result=subprocess.run([sys.executable,str(SCRIPT),'--root',str(self.root),'--output',str(output),
            '--cache',str(self.root/'data-cache'),'--simulation-cache',str(cache),'--simulations',str(simulations),
            '--seed','20261029','--workers',str(workers)],capture_output=True,text=True,timeout=120,
            env=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1'))
        self.assertEqual(result.returncode,expect,msg=result.stdout+'\n'+result.stderr)
        return output,result

    def assert_sources_preserved(self):
        self.assertEqual(self.original,{kind:(self.root/relative).read_bytes() for kind,relative in fixtures.LOADER.SOURCE_PATHS.items()})

    @staticmethod
    def oracle_assignment(unit_rows,group_rows,model_id,rep):
        groups=defaultdict(list)
        for row in unit_rows:groups[int(row['group'])].append(int(row['unit']))
        movable={int(row['group']) for row in group_rows if row['movable']=='True'}
        result=np.arange(len(unit_rows),dtype=np.int32)
        rng=np.random.default_rng(np.random.SeedSequence([20261029,7,model_id],spawn_key=(rep,)))
        for size in sorted({len(groups[g]) for g in movable}):
            bucket=np.array([groups[g] for g in sorted(movable) if len(groups[g])==size],dtype=np.int32)
            result[bucket.ravel()]=rng.permuted(bucket,axis=1).ravel()
        return result

    @staticmethod
    def oracle_scores(unit_rows,group_rows,municipal_rows,edge_rows,section_rows,assigned):
        deltas={}
        for row in unit_rows:
            matching=[s for s in section_rows if all(s[f]==row[f] for f in ('uf','municipality','zone','place'))
                      and (row['model']=='place_block' or s['section']==row['section'])]
            deltas[int(row['unit'])]=sum((100*Fraction(int(s['delta_numerator']),int(s['delta_denominator'])) for s in matching),Fraction(0))
        means={}
        for group in group_rows:
            members=[r for r in unit_rows if r['group']==group['group']]
            means[int(group['group'])]=sum((deltas[int(r['unit'])] for r in members),Fraction(0))/sum(int(r['ns']) for r in members)
        residuals={int(r['unit']):deltas[int(r['unit'])]-means[int(r['group'])]*int(r['ns']) for r in unit_rows}
        counts={};rs={};ns={}
        for slot,donor_index in zip(unit_rows,assigned):
            donor=unit_rows[int(donor_index)];key=(slot['uf'],slot['municipality'])
            counts.setdefault(key,defaultdict(int));rs.setdefault(key,Fraction(0));ns.setdefault(key,0)
            for field in ('v13_1','v22_1','v13_2','v22_2','nominal_1','nominal_2'):counts[key][field]+=int(donor[field])
            rs[key]+=residuals[int(donor_index)];ns[key]+=int(donor['ns'])
        targets=[(r['uf'],r['municipality']) for r in municipal_rows if r['target']=='True']
        if not targets:return np.zeros(5),ns
        sign_sets=[[],[],[]]
        for key in targets:
            c=counts[key];a,b,x,y=(c[f] for f in ('v13_1','v22_1','v13_2','v22_2'))
            values=((x-a)-(y-b),(x-y)*c['nominal_1']-(a-b)*c['nominal_2'],x*(a+b)-a*(x+y))
            for signs,value in zip(sign_sets,values):signs.append((value>0)-(value<0))
        prevalence=[max(v.count(1),v.count(-1))/len(targets) for v in sign_sets]
        rms2=sum((rs[k]**2/ns[k] for k in targets),Fraction(0))/sum(ns[k] for k in targets)
        jumps=[]
        for edge in edge_rows:
            left=(edge['uf'],edge['left_municipality']);right=(edge['uf'],edge['right_municipality'])
            jumps.append((rs[left]/ns[left]-rs[right]/ns[right])**2/(Fraction(1,ns[left])+Fraction(1,ns[right])))
        return np.array([*prevalence,math.sqrt(float(rms2)),math.sqrt(float(max(jumps,default=Fraction(0))))]),ns

    def test_complete_census_exact_definitions_public_scores_and_ten_test_family(self):
        output,_=self.cli('analysis')
        manifest=json.loads((output/'manifest.json').read_text());summary=json.loads((output/'summary.json').read_text())
        self.assertEqual(manifest['status'],'completed');self.assertEqual(manifest['method_sha256'],digest(HERE/'METHOD.pt-BR.md'))
        self.assertEqual(manifest['parameters']['family_size'],10)
        self.assertEqual(summary['matched_pairs'],21);self.assertEqual(summary['cohort_pairs'],19);self.assertEqual(summary['domestic_cohort_pairs'],18)
        self.assertEqual(summary['domestic_municipalities'],5);self.assertEqual(summary['overseas_source_units'],2)
        self.assertEqual(manifest['git_base'],subprocess.check_output(['git','rev-parse','HEAD'],cwd=self.root,text=True).strip())
        self.assertEqual(len([p for p in output.iterdir() if '.csv' in p.name]),17)
        for name,entry in manifest['artifacts'].items():
            self.assertEqual(entry['sha256'],digest(output/name));self.assertEqual(entry['size_bytes'],(output/name).stat().st_size)
        for name,value in manifest['implementation_sha256'].items():self.assertEqual(value,digest(SCRIPT.parent/name))
        census=rows(output/'municipal-census.csv');self.assertEqual(len(census),14)
        for row in census:
            if row['nominal_identity_residual']:
                a,b,x,y=[int(row[f]) for f in ('v13_1','v22_1','v13_2','v22_2')]
                n1,n2=int(row['nominal_1']),int(row['nominal_2']);f1,f2=a+b,x+y
                q1,q2=Fraction(a,f1),Fraction(x,f2)
                self.assertEqual(200*(q2-q1)+100*(1-Fraction(f1,n1))*(2*q1-1),100*(Fraction(x-y,n2)-Fraction(a-b,n1)))
                self.assertEqual(2*f2*(q2-q1)+(f2-f1)*(2*q1-1),(x-a)-(y-b))
                self.assertEqual(row['nominal_identity_residual'],'0');self.assertEqual(row['count_identity_residual'],'0')
            if row['defined_relative']=='True' and row['defined_conditional']=='True':self.assertEqual(row['sign_relative'],row['sign_conditional'])
        candidates=rows(output/'candidate-totals.csv.gz')
        for row in census:
            for turn in (1,2):
                selected=[r for r in candidates if r['universe']==row['universe'] and r['uf']==row['uf'] and r['municipality']==row['municipality'] and r['turno']==str(turn)]
                self.assertEqual(sum(int(r['votes']) for r in selected),int(row[f'nominal_{turn}']))
                self.assertTrue(all(r['candidate_name'].startswith('Artificial candidate ') for r in selected))
        units=rows(output/'allocation-units.csv.gz');groups=rows(output/'allocation-groups.csv.gz')
        municipalities=rows(output/'municipality-results.csv');edges=rows(output/'adjacent-profiles.csv');sections=rows(output/'cohort-sections.csv.gz')
        tests=rows(output/'tests.csv');public=rows(output/'permutation-scores.csv.gz')
        self.assertEqual(len(tests),10);self.assertEqual(len(public),38)
        raw_ps=[]
        for test in tests:
            raw_ps.append(float(test['p_raw']) if test['p_raw'] else 1.)
        order=np.argsort(raw_ps,kind='stable');adjusted=np.minimum(1,np.maximum.accumulate(np.asarray(raw_ps)[order]*np.arange(10,0,-1)))
        for rank,index in enumerate(order):
            if tests[index]['p_raw']:self.assertEqual(float(tests[index]['p_holm']),adjusted[rank])
        for entry in manifest['simulation_caches']:
            metadata=entry['metadata'];model=metadata['model'];model_id=metadata['model_id'];directory=self.root/entry['path']
            cached=np.load(directory/'scores.npy',allow_pickle=False);self.assertEqual(cached.shape,(19,5))
            self.assertEqual(metadata['scores_sha256'],digest(directory/'scores.npy'))
            self.assertEqual(entry['metadata_sha256'],digest(directory/'metadata.json'))
            u=[r for r in units if r['model']==model];g=[r for r in groups if r['model']==model]
            m=[r for r in municipalities if r['model']==model];e=[r for r in edges if r['model']==model]
            for rep in (0,1):
                assigned=self.oracle_assignment(u,g,model_id,rep)
                self.assertEqual(metadata['assignment_prefix'][str(rep)],hashlib.sha256(assigned.astype('<i4').tobytes()).hexdigest())
                expected,_=self.oracle_scores(u,g,m,e,sections,assigned)
                np.testing.assert_allclose(cached[rep],expected,atol=1e-11,rtol=1e-11)
            identity=np.arange(len(u),dtype=np.int32);observed,_=self.oracle_scores(u,g,m,e,sections,identity)
            selected=[r for r in public if r['model']==model]
            np.testing.assert_array_equal([[float(r[s]) for s in runner.STATISTICS] for r in selected],cached)
            for j,stat in enumerate(runner.STATISTICS):
                test=next(t for t in tests if t['model']==model and t['statistic']==stat)
                self.assertAlmostEqual(float(test['observed']),observed[j],places=10)
                lower=stat=='Rlow';self.assertEqual(test['tail'],'lower' if lower else 'upper')
                expected_exceed=int(np.count_nonzero(cached[:,j]<=observed[j]+1e-12 if lower else cached[:,j]>=observed[j]-1e-12))
                self.assertEqual(int(test['exceedances']),expected_exceed)
                if test['p_raw']:self.assertEqual(float(test['p_raw']),(1+expected_exceed)/20)
        self.assertEqual(len(rows(output/'sensitivity.csv')),14)
        self.assert_sources_preserved()

    def test_workers_and_cache_reuse_preserve_all_numerical_evidence(self):
        first,_=self.cli('serial',simulations=53)
        second,_=self.cli('parallel',simulations=53,workers=2,simulation_cache=self.root/'parallel-cache')
        files=sorted(p.name for p in first.iterdir() if p.name!='manifest.json')
        for name in files:self.assertEqual((first/name).read_bytes(),(second/name).read_bytes(),name)
        caches=sorted((self.root/'simulation-cache').rglob('scores.npy'))
        before={str(p):(p.stat().st_mtime_ns,p.read_bytes()) for p in caches}
        third,result=self.cli('reused',simulations=53,workers=2)
        self.assertNotIn('53/53',result.stdout)
        self.assertEqual(before,{str(p):(p.stat().st_mtime_ns,p.read_bytes()) for p in caches})
        for name in files:self.assertEqual((first/name).read_bytes(),(third/name).read_bytes(),name)
        self.assert_sources_preserved()

    def test_missing_round_zero_cohort_and_overseas_units_have_explicit_denominators(self):
        output,_=self.cli('denominators')
        census=rows(output/'municipal-census.csv')
        missing=next(r for r in census if r['universe']=='raw' and r['municipality']=='40')
        self.assertEqual((missing['present_1'],missing['present_2']),('True','False'))
        self.assertEqual(missing['defined_count'],'False')
        for field in ('gain13','gain22','count_advantage','delta','sign_count'):self.assertEqual(missing[field],'')
        no_cohort=next(r for r in census if r['universe']=='cohort' and r['municipality']=='50')
        self.assertEqual(no_cohort['present_1'],'False');self.assertEqual(no_cohort['raw_sections_1'],'1')
        self.assertEqual(no_cohort['cohort_sections_1'],'0');self.assertEqual(no_cohort['gain13'],'')
        directions=rows(output/'gain-directions.csv')
        raw=next(r for r in directions if r['universe']=='raw' and r['scope_type']=='BR' and r['metric']=='count')
        cohort=next(r for r in directions if r['universe']=='cohort' and r['scope_type']=='BR' and r['metric']=='count')
        self.assertEqual((raw['units'],raw['defined_units'],raw['undefined_units']),('5','4','1'))
        self.assertEqual((cohort['units'],cohort['defined_units'],cohort['undefined_units']),('5','3','2'))
        overseas=next(r for r in directions if r['universe']=='raw' and r['scope_type']=='exterior' and r['metric']=='count')
        self.assertEqual(overseas['units'],'2')
        self.assertEqual({(r['present_in_round'],r['municipality'],r['section']) for r in rows(output/'unmatched.csv')},{('1','40','99')})
        self.assertTrue(all(r['uf']!='ZZ' for r in rows(output/'allocation-units.csv.gz')))
        self.assert_sources_preserved()

    def test_exact_99_percent_boundary_and_undefined_base_are_not_rounded(self):
        def sample(positive):
            records=[]
            for i in range(10000):
                record=dict(universe='raw',uf='SP',nominal_2=100,sign_count=1 if i<positive else -1,defined_count=True)
                for metric in ('nominal','relative','conditional'):record.update({f'sign_{metric}':'',f'defined_{metric}':False})
                records.append(record)
            return next(r for r in runner.direction_rows(records) if r['scope_type']=='BR' and r['universe']=='raw' and r['metric']=='count')
        below=sample(9899);exact=sample(9900)
        self.assertFalse(below['reaches99_13_all']);self.assertFalse(below['reaches99_13_defined'])
        self.assertTrue(exact['reaches99_13_all']);self.assertTrue(exact['reaches99_13_defined'])
        self.assertEqual(exact['fraction13_defined'],.99)
        self.municipalities=(10,);self.rebuild()
        output,_=self.cli('constant')
        summary=json.loads((output/'summary.json').read_text())
        self.assertEqual(summary['primary_not_applicable'],10)
        self.assertEqual(summary['primary_detected'],0);self.assertEqual(summary['primary_not_detected'],0)
        for row in rows(output/'tests.csv'):
            self.assertEqual(row['status'],'not_applicable');self.assertEqual(row['p_raw'],'');self.assertEqual(row['p_holm'],'')
        self.assert_sources_preserved()

    def test_whole_blocks_keep_fixed_targets_when_section_counts_change(self):
        self.fixture.details=[];self.fixture.votes=[]
        for turn in (1,2):
            for municipality in (10,20):
                section=0
                for place,(size,aptos) in enumerate(((2,360),(3,240)),1001):
                    for j in range(size):
                        section+=1;turnout=aptos*3//4+(0 if turn==1 else 6+j)
                        nominal=turnout-5;other=(25 if aptos==360 else 15) if turn==1 else 0
                        lula=(nominal-other)//2 if turn==1 else int(nominal*(.56 if (municipality==10)==(place==1001) else .47))
                        detail=self.fixture.detail(section,turn,aptos=aptos,turnout=turnout,abstentions=aptos-turnout,
                            nominal=nominal,blank=2,null_votes=3,separate=0)
                        detail.update(CD_MUNICIPIO=str(municipality),NM_MUNICIPIO=f'ARTIFICIAL {municipality}',NR_LOCAL_VOTACAO=str(place))
                        self.fixture.details.append(detail)
                        values={13:lula,22:nominal-other-lula,14:other,95:2,96:3,97:0}
                        for candidate in [*CANDIDATES[turn],95,96,97]:
                            self.fixture.votes.append({**{key:detail[key] for key in [*fixtures.LOADER.KEY_FIELDS,'ANO_ELEICAO','DS_CARGO','SG_UE']},
                                'NR_VOTAVEL':str(candidate),'NM_VOTAVEL':f'Artificial candidate {candidate}','QT_VOTOS':str(values.get(candidate,0))})
        self.pin();output,_=self.cli('blocks',simulations=53)
        units=[r for r in rows(output/'allocation-units.csv.gz') if r['model']=='place_block']
        groups=[r for r in rows(output/'allocation-groups.csv.gz') if r['model']=='place_block']
        municipalities=[r for r in rows(output/'municipality-results.csv') if r['model']=='place_block']
        edges=[r for r in rows(output/'adjacent-profiles.csv') if r['model']=='place_block']
        sections=rows(output/'cohort-sections.csv.gz')
        self.assertEqual({r['municipality'] for r in municipalities if r['target']=='True'},{'10','20'})
        self.assertEqual({r['ns'] for r in municipalities},{'5'})
        self.assertEqual({r['ns'] for r in units},{'2','3'})
        changed=False
        for rep in range(53):
            assigned=self.oracle_assignment(units,groups,1,rep)
            _,ns=self.oracle_scores(units,groups,municipalities,edges,sections,assigned)
            changed|=any(n!=5 for n in ns.values())
        self.assertTrue(changed,'Block reassignment should permit changing section counts while keeping original target codes')
        self.assert_sources_preserved()

    def test_output_cli_unknown_cache_fingerprint_and_tamper_guards_preserve_inputs(self):
        existing=self.root/'existing';existing.mkdir();marker=existing/'keep';marker.write_text('Preserve existing evidence.\n')
        _,result=self.cli('existing',expect=2);self.assertIn('Refusing a nonempty output directory',result.stderr)
        self.assertEqual(marker.read_text(),'Preserve existing evidence.\n')
        for name,kwargs in [('zero',dict(simulations=0)),('workers',dict(workers=5))]:
            _,result=self.cli(name,expect=2,**kwargs);self.assertIn('Use positive simulations and 1–4 workers',result.stderr)
            self.assertFalse((self.root/name).exists())
        unknown=self.root/'unknown-cache/section';unknown.mkdir(parents=True);mark=unknown/'keep';mark.write_text('unknown')
        _,result=self.cli('unknown',simulation_cache=unknown.parent,expect=1)
        self.assertIn('Unknown simulation cache',result.stderr);self.assertEqual(mark.read_text(),'unknown')
        self.cli('valid')
        metadata=self.root/'simulation-cache/section/metadata.json';payload=json.loads(metadata.read_text());original=metadata.read_bytes()
        payload['fingerprint']='wrong';metadata.write_text(json.dumps(payload));changed=metadata.read_bytes()
        _,result=self.cli('wrong-fingerprint',expect=1);self.assertIn('Incomplete, different or corrupted simulation cache',result.stderr)
        self.assertEqual(metadata.read_bytes(),changed);metadata.write_bytes(original)
        scores=self.root/'simulation-cache/section/scores.npy';changed=scores.read_bytes()+b'preserve tamper marker';scores.write_bytes(changed)
        _,result=self.cli('tamper',expect=1);self.assertIn('Incomplete, different or corrupted simulation cache',result.stderr)
        self.assertEqual(scores.read_bytes(),changed);self.assert_sources_preserved()


if __name__=='__main__':
    unittest.main()
