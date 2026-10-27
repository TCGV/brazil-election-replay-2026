"""Municipality-level descriptive checks for geographic confounding (not causal)."""
from __future__ import annotations

import csv
from datetime import datetime
from itertools import groupby
import json
import math
from pathlib import Path
import sqlite3
import statistics


def _ranks(values):
    ranks=[0.0]*len(values)
    ordered=sorted(range(len(values)),key=values.__getitem__)
    start=0
    while start<len(ordered):
        end=start+1
        while end<len(ordered) and values[ordered[end]]==values[ordered[start]]:
            end+=1
        average=(start+1+end)/2
        for i in ordered[start:end]:ranks[i]=average
        start=end
    return ranks


def _correlation(x,y):
    if len(x)<2:return None
    mx,my=statistics.mean(x),statistics.mean(y)
    sx=sum((a-mx)**2 for a in x);sy=sum((a-my)**2 for a in y)
    return sum((a-mx)*(b-my) for a,b in zip(x,y))/math.sqrt(sx*sy) if sx and sy else None


def controls(db_path:Path,output_dir:Path):
    import numpy as np
    db=sqlite3.connect(Path(db_path).resolve().as_uri()+'?mode=ro',uri=True)
    rows=db.execute('''SELECT election_code,turno,uf,municipality,municipality_name,region,is_capital,
        municipality_electorate,size_band,first_time,bu_time FROM section_events WHERE uf<>'ZZ'
        ORDER BY election_code,turno,uf,municipality''')
    municipalities=[]
    for key,group in groupby(rows,key=lambda r:r[:4]):
        batch=list(group)
        base=datetime.fromisoformat(batch[0][9]).replace(hour=17,minute=0,second=0,microsecond=0)
        for source,col in [('first_partial_totalization',9),('bu_received',10)]:
            times=sorted((datetime.fromisoformat(row[col])-base).total_seconds()/60 for row in batch)
            first=batch[0]
            municipalities.append(dict(zip(['election_code','turno','uf','municipality','municipality_name','region','is_capital','electorate','size_band'],first[:9]))|
                                  {'source':source,'sections':len(times),'t50_minutes':times[(len(times)-1)//2]})
    db.close()
    fields=list(municipalities[0])
    with (output_dir/'municipality-timing.csv').open('w',encoding='utf8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(municipalities)
    results=[]
    for source in ['first_partial_totalization','bu_received']:
        for election,turn in sorted({(r['election_code'],r['turno']) for r in municipalities}):
            selected=[r for r in municipalities if r['source']==source and r['election_code']==election and r['turno']==turn and r['electorate']>0]
            x=[math.log10(r['electorate']) for r in selected];y=[r['t50_minutes'] for r in selected]
            rx,ry=_ranks(x),_ranks(y)
            ufs=sorted({r['uf'] for r in selected})
            groups={uf:[i for i,r in enumerate(selected) if r['uf']==uf] for uf in ufs}
            cx,cy=rx[:],ry[:]
            for indices in groups.values():
                mx=statistics.mean(rx[i] for i in indices);my=statistics.mean(ry[i] for i in indices)
                for i in indices:cx[i]-=mx;cy[i]-=my
            # Equal municipality weights, UF fixed intercepts. Coefficients describe associations.
            matrix=np.array([[1,math.log10(r['electorate']),int(r['is_capital']),*[int(r['uf']==uf) for uf in ufs[1:]]] for r in selected],dtype=float)
            beta,_,rank,_=np.linalg.lstsq(matrix,np.array(y),rcond=None)
            results.append({'source':source,'election_code':election,'turno':turn,'municipalities':len(selected),
                            'spearman_size_vs_t50':_correlation(rx,ry),'within_uf_rank_correlation':_correlation(cx,cy),
                            'ols_minutes_per_10x_electorate':float(beta[1]),'ols_capital_minutes_vs_noncapital':float(beta[2]),
                            'ols_rank':int(rank),'ols_columns':matrix.shape[1],
                            'model':'municipality t50 = intercept + log10(electorate) + capital indicator + UF intercepts; equal municipality weights; descriptive, not causal'})
    (output_dir/'municipality-controls.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    return results
