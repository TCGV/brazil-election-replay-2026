"""Independent H3 controls; all sections and permutations here are artificial."""
from collections import Counter
from fractions import Fraction
import csv
import hashlib
import gzip
import importlib.util
import itertools
import json
from pathlib import Path
import tempfile
import unittest

SPEC=importlib.util.spec_from_file_location('h3_independent',Path(__file__).with_name('validate_independently.py'))
INDEPENDENT=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INDEPENDENT)


class IndependentControls(unittest.TestCase):
    def assert_enumerated_moments(self,a,b):
        statistic=[]
        for shuffled in set(itertools.permutations(b)):
            statistic.append(sum(v*(v-1)//2 for v in Counter(zip(a,shuffled)).values()))
        e=sum(map(Fraction,statistic))/len(statistic)
        variance=sum((Fraction(x)-e)**2 for x in statistic)/len(statistic)
        actual=INDEPENDENT.exact_moments(list(Counter(a).values()),list(Counter(b).values()),
            list(Counter(zip(a,b)).values()))
        self.assertEqual(actual[1],e)
        self.assertEqual(actual[2],variance)
        return actual,statistic

    def test_exact_variance_including_shared_and_disjoint_pairs(self):
        for a,b in [([0,0,1,1],[0,0,1,1]),
                    ([0,0,0,1,1,2],[0,0,1,1,2,2]),
                    ([0,0,0,0,1,1],[0,0,0,1,2,2]),
                    ([0,0,1],[0,0,1]),([0,0],[0,1]),([0],[0])]:
            with self.subTest(a=a,b=b):
                self.assert_enumerated_moments(a,b)

    def test_cantelli_can_be_tight_but_is_not_an_exact_p_in_general(self):
        (x,e,v),statistics=self.assert_enumerated_moments([0,0,1,1],[0,0,1,1])
        upper=v/(v+(x-e)**2)
        exact=Fraction(sum(s>=x for s in statistics),len(statistics))
        self.assertEqual(upper,Fraction(1,3))
        self.assertEqual(upper,exact)
        (x,e,v),statistics=self.assert_enumerated_moments([0,0,0,1,1,2],[0,0,0,1,2,2])
        if x>e:
            self.assertGreaterEqual(v/(v+(x-e)**2),Fraction(sum(s>=x for s in statistics),len(statistics)))

    def test_constant_block_conditions_away_repetition(self):
        for a,b in [([0]*4,[0,0,1,1]),([0]*4,[0]*4),([0,1,2,3],[0,0,1,1])]:
            (x,e,v),_=self.assert_enumerated_moments(a,b)
            self.assertEqual(v,0)
            self.assertEqual(x,e)

    def test_fixed_two_member_holm_family_including_nonapplicable_as_one(self):
        self.assertEqual(INDEPENDENT.holm_reference({1:Fraction(1,100),2:Fraction(3,100)}),
            {1:Fraction(1,50),2:Fraction(3,100)})
        self.assertEqual(INDEPENDENT.holm_reference({1:Fraction(1,100),2:Fraction(1)}),
            {1:Fraction(1,50),2:Fraction(1)})

    def test_all_integer_vector_components_matter_not_percentages(self):
        result=INDEPENDENT.summarize_vectors([(20,20,0,0,0,0,40),(30,30,0,0,0,0,60)])
        self.assertEqual(result['repeated_clusters'],0)
        result=INDEPENDENT.summarize_vectors([(10,20,0,0,0,0,30)]*3+[(9,20,1,0,0,0,30)])
        self.assertEqual(result,dict(sections=4,unique_vectors=2,repeated_clusters=1,
            repeated_sections=3,collision_pairs=3,max_multiplicity=3))

    def test_population_views_keep_zero_rows_and_separate_small_positive(self):
        zero=INDEPENDENT.view_members((100,0,0,0,0,0,0,0),False,False)
        small=INDEPENDENT.view_members((100,40,60,35,2,3,0,0),True,False)
        eligible=INDEPENDENT.view_members((100,80,20,75,2,3,0,0),True,False)
        cancelled=INDEPENDENT.view_members((100,80,20,75,2,3,0,0),True,True)
        self.assertEqual([v for v,n in zero.items() if n],['all_details','zero_activity'])
        self.assertEqual([v for v,n in small.items() if n],['all_details','small_positive'])
        self.assertEqual([v for v,n in eligible.items() if n],['all_details','eligible'])
        self.assertEqual([v for v,n in cancelled.items() if n],['all_details','other_excluded_positive'])

    def test_repeated_values_on_distinct_keys_are_inventory_not_key_duplicates(self):
        records=[]
        vectors={(6257,1,13):[25,25,20,20],(6257,1,22):[25,25,30,30]}
        for section in range(1,5):
            blank=0 if section in (1,2) else 1
            q=(100,50+blank,50-blank,50,blank,0,0,0)
            records.append(((6257,1,'SP',71072,1,section),1,q,True,False,section+1))
        result=INDEPENDENT.reference_from_records(records,vectors,{(6257,1):[13,22]},Counter(),{})
        eligible=next(r for r in result['inventory'] if r['view']=='eligible' and r['signature_type']=='full')
        self.assertEqual(eligible['repeated_clusters'],2)
        self.assertEqual(eligible['collision_pairs'],2)
        self.assertEqual(len(result['strata']),1)
        self.assertEqual(result['strata'][0]['observed_pairs'],2)
        self.assertEqual(result['strata'][0]['expected_pairs'],2/3)


class ComparatorControls(unittest.TestCase):
    def fixture(self,folder):
        records=[];vectors={};candidates={}
        for turn in (1,2):
            election=6256+turn;candidates[election,turn]=[13,22]
            vectors[election,turn,13]=[25,25,20,20]*2
            vectors[election,turn,22]=[25,25,30,30]*2
            for section in range(1,5):
                blank=0 if section<3 else 1
                records.append(((election,turn,'SP',71072,1,section),1,
                    (100,50+blank,50-blank,50,blank,0,0,0),True,False,len(records)+2))
        # Vectors have one entry for every global record index, as in the raw parser.
        totals={(6257,1,'SP'):Counter(records=4),(6258,2,'SP'):Counter(records=4)}
        reference=INDEPENDENT.reference_from_records(records,vectors,candidates,Counter(),totals)
        tables={
            'inventory.csv':reference['inventory'],
            'clusters.csv.gz':reference['clusters'],
            'cluster-members.csv.gz':reference['cluster_members'],
            'turnout-distribution.csv':reference['turnout_distribution'],
            'strata.csv.gz':reference['strata'],
        }
        adjusted=INDEPENDENT.holm_reference({(r['election_code'],r['turno']):
            Fraction(int(r['p_numerator']),int(r['p_denominator'])) for r in reference['rounds']})
        tables['conditional-tests.csv']=[dict(r,p_holm=float(adjusted[r['election_code'],r['turno']]),
            status='excess_detected' if adjusted[r['election_code'],r['turno']]<=Fraction(1,20) else 'not_detected')
            for r in reference['rounds']]
        coverage=[]
        for r in reference['rounds']:
            for uf in ('SP','BR'):
                coverage.append(dict(election_code=r['election_code'],turno=r['turno'],uf=uf,
                    raw_details=4,eligible=4,small_positive=0,zero_activity=0,other_excluded_positive=0,
                    **{f:r[f] for f in ('groups','sections','nonsingleton_groups','nonsingleton_sections','informative_groups','informative_sections')}))
        tables['coverage.csv']=coverage
        tables['sensitivity.csv']=[dict(scenario='primary',**r) for r in reference['rounds']]
        for name,rows in tables.items():
            rows=[dict(r) for r in rows]
            for r in rows:
                if 'signature' in r:
                    r['vector_json']=json.dumps(r.pop('signature'))
            opener=gzip.open if name.endswith('.gz') else open
            with opener(folder/name,'wt',newline='') as f:
                writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n')
                writer.writeheader();writer.writerows(rows)
        summary=dict(inventory=reference['inventory'],conditional_tests=tables['conditional-tests.csv'],
            coverage=[r for r in coverage if r['uf']=='BR'],candidates=reference['candidates'],sensitivity=tables['sensitivity.csv'])
        (folder/'summary.json').write_text(json.dumps(summary))
        manifest=dict(status='completed',source_inputs={},primary_family_size=2,
            method_sha256=INDEPENDENT.digest_file(INDEPENDENT.HERE/'METHOD.pt-BR.md'),
            implementation_sha256={},artifact_sha256={name:INDEPENDENT.digest_file(folder/name) for name in [*tables,'summary.json']})
        (folder/'manifest.json').write_text(json.dumps(manifest))
        return reference,dict(source_inputs={},implementation_fingerprint='synthetic-fixture')

    def test_complete_synthetic_primary_tables_pass_independent_comparison(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);reference,metadata=self.fixture(folder)
            result=INDEPENDENT.validate_analysis(folder,reference,metadata)
            self.assertEqual(result['status'],'passed',result['failures'])
            self.assertEqual(result['mismatches'],0)

    def test_missing_stratum_is_detected_even_after_updating_its_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);reference,metadata=self.fixture(folder)
            path=folder/'strata.csv.gz'
            with gzip.open(path,'rt') as f:rows=f.read().splitlines()
            with gzip.open(path,'wt') as f:f.write('\n'.join(rows[:-1])+'\n')
            manifest=json.loads((folder/'manifest.json').read_text())
            manifest['artifact_sha256']['strata.csv.gz']=INDEPENDENT.digest_file(path)
            (folder/'manifest.json').write_text(json.dumps(manifest))
            result=INDEPENDENT.validate_analysis(folder,reference,metadata)
            self.assertEqual(result['status'],'failed')
            self.assertTrue(any(r['category']=='inventory' for r in result['failures']))


if __name__=='__main__':
    unittest.main()
