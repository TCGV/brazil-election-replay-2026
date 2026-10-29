"""H5 paired-section screening and conditional allocation between polling places."""
from __future__ import annotations

from itertools import permutations, product
import numpy as np

MODELS = {'zone_size': 0, 'zone_size_baseline': 1}
STATISTICS = ('RMS', 'MAX')
EPS = 1e-12
PRIORITY_PP = 10.0
MIN_PEERS = 4
KEY_FIELDS = ('uf','municipality','zone','section')


def physical_keys(data):
    keys=np.empty(len(data['uf']),dtype=[('uf','U2'),('municipality','i4'),('zone','i4'),('section','i4')])
    for field in KEY_FIELDS:
        keys[field]=data[field]
    if len(np.unique(keys))!=len(keys):
        raise ValueError('Ambiguous physical section key within one round')
    return keys


def pair_sections(rounds):
    first=[rd for rd in rounds if int(rd['turno'])==1]
    second=[rd for rd in rounds if int(rd['turno'])==2]
    if len(first)!=1 or len(second)!=1:
        raise ValueError('Require exactly one presidential election per round')
    a,b=first[0],second[0]
    if not {13,22}<=set(a['candidate_numbers']) or set(b['candidate_numbers'])!={13,22}:
        raise ValueError('Finalists must exist in both rounds and exhaust round 2 nominal votes')
    ka,kb=physical_keys(a),physical_keys(b)
    keys,ia,ib=np.intersect1d(ka,kb,assume_unique=True,return_indices=True)
    pairs={field:keys[field] for field in KEY_FIELDS}
    fields=('place','source_line','aptos','turnout','abstentions','nominal','installed','cancelled')
    for turn,rd,indices in ((1,a,ia),(2,b,ib)):
        for field in fields:
            pairs[f'{field}_{turn}']=rd[field][indices]
        for candidate in (13,22):
            pairs[f'v{candidate}_{turn}']=rd['candidate_votes'][indices,rd['candidate_numbers'].index(candidate)].astype(np.int64)
        pairs[f'f_{turn}']=pairs[f'v13_{turn}']+pairs[f'v22_{turn}']
    only_a=np.setdiff1d(np.arange(len(ka)),ia,assume_unique=True)
    only_b=np.setdiff1d(np.arange(len(kb)),ib,assume_unique=True)
    pairs.update(election_1=int(a['election_code']),election_2=int(b['election_code']))
    return dict(pairs=pairs,unmatched=[(1,a,only_a),(2,b,only_b)],rounds=(a,b),matched_indices=(ia,ib))


def eligibility(pairs,finalist_floor=50,unchanged_aptos=False):
    n=len(pairs['uf']);remaining=np.ones(n,dtype=bool)
    reasons=np.full(n,'eligible',dtype='U24')
    a1,a2=pairs['aptos_1'].astype(np.int64),pairs['aptos_2'].astype(np.int64)
    criteria=[('section_status',~pairs['installed_1']|~pairs['installed_2']|pairs['cancelled_1']|pairs['cancelled_2']),
        ('aptos_below_50',(a1<50)|(a2<50)),
        ('nonpositive_turnout',(pairs['turnout_1']<=0)|(pairs['turnout_2']<=0)),
        ('nominal_below_50',(pairs['nominal_1']<50)|(pairs['nominal_2']<50)),
        ('finalists_below_floor',pairs['f_1']<finalist_floor),
        ('missing_place',(pairs['place_1']<0)|(pairs['place_2']<0)),
        ('changed_place',pairs['place_1']!=pairs['place_2']),
        ('aptos_ratio',4*np.maximum(a1,a2)>5*np.minimum(a1,a2))]
    basic=None
    if unchanged_aptos:
        criteria.append(('changed_aptos',a1!=a2))
    for name,excluded in criteria:
        take=remaining&excluded
        reasons[take]=name;remaining[take]=False
        if name=='nominal_below_50':
            basic=remaining.copy()
    return remaining,reasons,basic


def preference_band(votes,finalists,bins=20):
    if bins<=0 or np.any(finalists<=0):
        raise ValueError('Positive denominator and bin count required')
    return np.minimum(bins-1,bins*votes.astype(np.int64)//finalists).astype(np.int32)


def changes(pairs,ids):
    f1,f2=pairs['f_1'][ids].astype(np.int64),pairs['f_2'][ids].astype(np.int64)
    if np.any((f1<=0)|(f2<=0)):
        raise ValueError('Undefined conditional finalist share')
    if int(f1.max())*int(f2.max())>np.iinfo(np.int64).max:
        raise ValueError('Ratio cross-products would overflow int64')
    numerator=pairs['v13_2'][ids]*f1-pairs['v13_1'][ids]*f2
    denominator=f1*f2
    divisor=np.gcd(np.abs(numerator),denominator)
    return dict(delta=100.0*numerator/denominator,numerator=numerator//divisor,denominator=denominator//divisor,
        q1=100*pairs['v13_1'][ids]/f1,q2=100*pairs['v13_2'][ids]/f2,
        dp13=100*(pairs['v13_2'][ids]/pairs['nominal_2'][ids]-pairs['v13_1'][ids]/pairs['nominal_1'][ids]),
        dp22=100*(pairs['v22_2'][ids]/pairs['nominal_2'][ids]-pairs['v22_1'][ids]/pairs['nominal_1'][ids]))


def grouping(columns):
    keys,first,labels,sizes=np.unique(np.column_stack(columns),axis=0,return_index=True,return_inverse=True,return_counts=True)
    order=np.argsort(labels,kind='stable');starts=np.r_[0,np.cumsum(sizes)]
    return dict(keys=keys,first=first,labels=labels,sizes=sizes,order=order,starts=starts)


def median_without_self(values):
    values=np.asarray(values,dtype=float);n=len(values)
    if n<2:
        raise ValueError('At least two sections required')
    order=np.argsort(values,kind='stable');sorted_values=values[order]
    rank=np.empty(n,dtype=np.int64);rank[order]=np.arange(n)
    low=(n-2)//2;high=(n-1)//2
    return (sorted_values[low+(rank<=low)]+sorted_values[high+(rank<=high)])/2


def screening(pairs,ids,bins=20):
    change=changes(pairs,ids)
    _,uf_id=np.unique(pairs['uf'][ids],return_inverse=True)
    band=np.floor(np.log(pairs['aptos_1'][ids])/np.log(1.25)).astype(np.int32)
    initial=preference_band(pairs['v13_1'][ids],pairs['f_1'][ids],bins)
    columns=[uf_id,pairs['municipality'][ids],pairs['zone'][ids],pairs['place_1'][ids],band]
    result=dict(change)
    for name,cols in [('broad',columns),('strict',[*columns,initial])]:
        group=grouping(cols);n=len(ids)
        count=group['sizes'][group['labels']]-1
        median=np.full(n,np.nan)
        for g,size in enumerate(group['sizes']):
            if size-1>=MIN_PEERS:
                members=group['order'][group['starts'][g]:group['starts'][g+1]]
                median[members]=median_without_self(change['delta'][members])
        contrast=change['delta']-median
        priority=(count>=MIN_PEERS)&(np.abs(contrast)>=PRIORITY_PP-EPS)
        result.update({f'{name}_peer_count':count,f'{name}_median':median,
                       f'{name}_contrast':contrast,f'{name}_priority':priority})
    return result


def prepare(pairs,model,bins=20,finalist_floor=50,unchanged_aptos=False,min_target=5):
    if model not in MODELS or min_target<1:
        raise ValueError('Invalid reference model or target size')
    mask,reasons,basic=eligibility(pairs,finalist_floor,unchanged_aptos)
    ids=np.flatnonzero(mask)
    if not len(ids):
        raise ValueError('Empty paired cohort')
    change=changes(pairs,ids)
    _,uf_id=np.unique(pairs['uf'][ids],return_inverse=True)
    band=np.floor(np.log(pairs['aptos_1'][ids])/np.log(1.25)).astype(np.int32)
    initial=preference_band(pairs['v13_1'][ids],pairs['f_1'][ids],bins)
    cols=[uf_id,pairs['municipality'][ids],pairs['zone'][ids],band]
    if model=='zone_size_baseline':
        cols.append(initial)
    groups=grouping(cols)
    places=grouping([uf_id,pairs['municipality'][ids],pairs['zone'][ids],pairs['place_1'][ids]])
    labels,sizes=groups['labels'],groups['sizes']
    means=np.bincount(labels,weights=change['delta'])/sizes
    rational_unique=np.unique(np.column_stack([labels,change['numerator'],change['denominator']]),axis=0)
    variable=np.bincount(rational_unique[:,0],minlength=len(sizes))>1
    residual=change['delta']-means[labels]
    residual[~variable[labels]]=0.0
    closure=np.bincount(labels,weights=residual,minlength=len(sizes))
    if np.max(np.abs(closure))>1e-6 or abs(residual.sum())>1e-6:
        raise ArithmeticError('Paired residuals fail group closure')
    targets=places['sizes']>=min_target
    group_place=np.unique(np.column_stack([labels,places['labels']]),axis=0)
    place_count=np.bincount(group_place[:,0],minlength=len(sizes))
    target_slots=np.bincount(labels,weights=targets[places['labels']],minlength=len(sizes)).astype(np.int64)
    potential=variable&(place_count>=2)&(target_slots>0)
    buckets=[]
    for size in sorted(set(sizes.tolist())-{1}):
        selected=np.flatnonzero(sizes==size)
        buckets.append(np.asarray([groups['order'][groups['starts'][g]:groups['starts'][g+1]] for g in selected],dtype=np.int32))
    return dict(pairs=pairs,ids=ids,reasons=reasons,basic=basic,model=model,bins=bins,min_target=min_target,
        group=groups,place=places,band=band,initial_band=initial,change=change,mean=means,
        variable=variable,residual=residual,targets=targets,group_place_count=place_count,
        group_target_slots=target_slots,potential=potential,buckets=buckets)


def concentration(prepared,residual=None):
    if residual is None:
        residual=prepared['residual']
    sums=np.bincount(prepared['place']['labels'],weights=residual,minlength=len(prepared['place']['sizes']))
    target=prepared['targets'];sizes=prepared['place']['sizes']
    if not np.any(target):
        return np.zeros(2),sums
    rms=np.sqrt(np.sum(sums[target]**2/sizes[target])/sizes[target].sum())
    maximum=np.max(np.abs(sums[target])/np.sqrt(sizes[target]))
    return np.array([rms,maximum]),sums


def assignment(prepared,seed,model_id,repetition):
    rng=np.random.default_rng(np.random.SeedSequence([seed,model_id],spawn_key=(repetition,)))
    result=np.arange(len(prepared['ids']),dtype=np.int32)
    for bucket in prepared['buckets']:
        result[bucket.ravel()]=rng.permuted(bucket,axis=1).ravel()
    return result


def score_variability(prepared,sampled,observed,max_exact=40320):
    sampled=np.asarray(sampled,dtype=float);observed=np.asarray(observed,dtype=float)
    if sampled.ndim!=2 or sampled.shape[1]!=2 or observed.shape!=(2,) or not np.all(np.isfinite(sampled)) or not np.all(np.isfinite(observed)) or max_exact<0:
        raise ValueError('Expected finite B-by-two scores')
    if not np.any(prepared['targets']):
        return np.zeros(2,dtype=bool),['no_targets']*2
    if not np.any(prepared['potential']):
        return np.zeros(2,dtype=bool),['no_movable_variable_groups']*2
    flags=np.ptp(np.vstack([observed,sampled]),axis=0)>EPS
    reasons=['sampled_distinct_scores' if flag else '' for flag in flags]
    if np.all(flags):
        return flags,reasons
    groups=[];orbit=1;group=prepared['group']
    for g in np.flatnonzero(prepared['potential']):
        members=group['order'][group['starts'][g]:group['starts'][g+1]]
        groups.append(members)
        for factor in range(2,len(members)+1):
            orbit*=factor
            if orbit>max_exact:
                raise ArithmeticError('Unresolved concentration-score variability; exact orbit too large')
    lower=np.full(2,np.inf);upper=np.full(2,-np.inf)
    for draw in product(*(permutations(m.tolist()) for m in groups)):
        r=prepared['residual'].copy()
        for members,source in zip(groups,draw):
            r[members]=prepared['residual'][list(source)]
        values,_=concentration(prepared,r)
        lower=np.minimum(lower,values);upper=np.maximum(upper,values)
        if np.all(flags|(upper-lower>EPS)):
            break
    for k in np.flatnonzero(~flags):
        flags[k]=upper[k]-lower[k]>EPS
        reasons[k]='exact_enumeration_variable' if flags[k] else 'exact_enumeration_constant'
    return flags,reasons


def holm(pvalues):
    p=np.asarray(pvalues,dtype=float)
    if np.any(~np.isfinite(p)) or np.any((p<0)|(p>1)):
        raise ValueError('Invalid p-values')
    order=np.argsort(p,kind='stable')
    adjusted=np.minimum(1,np.maximum.accumulate(p[order]*np.arange(len(p),0,-1)))
    result=np.empty_like(p);result[order]=adjusted
    return result
