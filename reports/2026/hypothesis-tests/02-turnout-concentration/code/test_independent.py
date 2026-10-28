"""Small exact-ratio fixtures for the separate H2 validator; no election claims."""
from array import array
from collections import Counter
from fractions import Fraction
import importlib.util
from pathlib import Path
import unittest

SPEC=importlib.util.spec_from_file_location('h2_independent',Path(__file__).with_name('validate_independently.py'))
MODULE=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class IndependentReferenceTests(unittest.TestCase):
    def test_ties_are_not_broken_to_fill_tail(self):
        values=[Fraction(1,10)]*37+[Fraction(1,2),Fraction(2,4),Fraction(3,6)]
        flags,upper=MODULE.upper_tail(values)
        self.assertEqual(sum(flags),0)
        self.assertEqual(upper[-3:],[3,3,3])

    def test_tail_and_even_median_are_exact(self):
        values=[Fraction(i,100) for i in range(40)]
        flags,upper=MODULE.upper_tail(values)
        self.assertEqual(sum(flags),2)
        self.assertEqual(flags[-2:],[True,True])
        self.assertEqual(MODULE.exact_median(values),Fraction(39,200))
        self.assertEqual(MODULE.exact_median([Fraction(1,3)]*30),Fraction(1,3))

    def fixture(self,other_local_peers=4):
        records=[]
        for i in range(30):
            turnout=150+i if i<29 else 200
            place=1 if i<other_local_peers or i==29 else 2
            quantities=(200,turnout,200-turnout,150,turnout-150,0,0,0)
            records.append(((6257,1,'SP',71072,1,i+1),place,quantities,True,False,i+2))
        first=array('q',[50+i for i in range(29)]+[140])
        zero=array('q',[0])*30
        vectors={(6257,1,13):first,(6257,1,22):zero}
        candidates={(6257,1):[13,22]}
        stats=Counter(detail_rows_selected=30,vote_rows_selected=30)
        totals={(6257,1,'SP'):Counter(records=30)}
        return records,vectors,candidates,stats,totals

    def test_priority_and_local_context_use_other_sections_only(self):
        result=MODULE.reference_from_records(*self.fixture())
        cases=result['cases']
        self.assertEqual(len(cases),1)
        case=cases[0]
        self.assertEqual(case['candidate'],13)
        self.assertTrue(case['priority'])
        self.assertEqual(case['place_peers'],4)
        self.assertEqual(case['local_status'],'persists_both')
        self.assertEqual(case['local_median_turnout'],float(Fraction(303,400)))
        absent=next(r for r in result['strata'] if r['candidate']==22)
        self.assertEqual(absent['candidate_tail'],0)
        self.assertEqual(absent['joint_count'],0)

    def test_too_few_local_peers_are_insufficient_not_attenuated(self):
        result=MODULE.reference_from_records(*self.fixture(other_local_peers=3))
        case=result['cases'][0]
        self.assertEqual(case['place_peers'],3)
        self.assertEqual(case['local_status'],'insufficient_peers')
        self.assertIsNone(case['place_persistent'])

    def test_eligibility_hierarchy_places_small_electorate_before_no_turnout(self):
        records,vectors,candidates,stats,totals=self.fixture()
        scope,place,_,installed,cancelled,line=records[0]
        records[0]=(scope,place,(30,0,30,0,0,0,0,0),installed,cancelled,line)
        result=MODULE.reference_from_records(records,vectors,candidates,stats,totals)
        coverage=result['coverage'][0]
        self.assertEqual(coverage['excluded_electorate'],1)
        self.assertEqual(coverage.get('excluded_turnout',0),0)
        self.assertEqual(coverage['eligible'],29)
        self.assertEqual(coverage['no_peer_support'],29)
        self.assertEqual(result['strata'],[])

    def test_independent_holm_keeps_the_whole_family_and_monotonicity(self):
        adjusted=MODULE.holm_reference({'first':.01,'second':.04,'third':.03,'degenerate':1.0})
        self.assertEqual(adjusted['first'],.04)
        self.assertEqual(adjusted['second'],.09)
        self.assertEqual(adjusted['third'],.09)
        self.assertEqual(adjusted['degenerate'],1.0)

    def test_reference_quantile_interpolates_without_normal_approximation(self):
        self.assertEqual(MODULE.linear_quantile(range(40),Fraction(1,40)),float(Fraction(39,40)))
        self.assertEqual(MODULE.linear_quantile(range(40),Fraction(39,40)),float(Fraction(1521,40)))


if __name__=='__main__':
    unittest.main()
