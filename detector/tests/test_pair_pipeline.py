import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from pair_pipeline import interpolation_matrix,gaussian_matrix,aperture_variance


def test_bilinear_operator_constant_and_boundary():
    r=interpolation_matrix((3,3),(1,2),np.array([[.5,-.5]]),np.array([[.5,.5]]))
    assert np.allclose(r@np.ones(9),[1,.5])
    assert np.allclose(r.multiply(r)@np.ones(9),[.25,.125])


def test_variance_of_composed_operator_not_sequential_diagonal():
    r=interpolation_matrix((3,3),(3,3),*np.meshgrid(np.arange(3)+.25,np.arange(3)+.25))
    k=gaussian_matrix((3,3),.7)
    o=k@r
    v=np.arange(1,10,dtype=float)
    full=o.toarray()@np.diag(v)@o.toarray().T
    assert np.allclose(o.multiply(o)@v,np.diag(full))
    mask=np.zeros((3,3),bool);mask[1,:]=True
    expected=full[np.ix_(mask.ravel(),mask.ravel())].sum()
    assert np.isclose(aperture_variance(o,v,mask),expected)
    # Aperture error must include positive correlations created by smoothing.
    assert expected>np.diag(full)[mask.ravel()].sum()


def test_gaussian_operator_preserves_interior_constant():
    k=gaussian_matrix((15,15),.8)
    image=(k@np.ones(225)).reshape(15,15)
    assert np.allclose(image[4:-4,4:-4],1)
    assert image[0,0]<1


def test_rejected_alternative_does_not_veto_good_pair():
    from pair_pipeline import flag_pair_ambiguity
    good=dict(_negative_index=0,_positive_index=1,flags=[],quality_score=80.)
    bad=dict(_negative_index=0,_positive_index=2,flags=['endpoint_wavelength_mismatch'],quality_score=10.)
    flag_pair_ambiguity([good,bad])
    assert good['flags']==[] and good['quality_score']==80.


def test_viable_competing_pairs_remain_ambiguous():
    from pair_pipeline import flag_pair_ambiguity
    pairs=[dict(_negative_index=0,_positive_index=i,flags=[],quality_score=80.) for i in [1,2]]
    flag_pair_ambiguity(pairs)
    assert all(p['flags']==['ambiguous_residual_pairing'] and p['quality_score']==40 for p in pairs)


def test_far_pair_with_local_signed_structure_requires_review():
    from pair_pipeline import local_opposite_features,PairConfig
    n=dict(x=0.,y=0.,peak_significance=10.,flags=[])
    p=dict(x=100.,y=0.,peak_significance=10.,flags=[])
    local=dict(x=3.,y=0.,peak_significance=8.,flags=['low_integrated_significance'])
    result=local_opposite_features(n,p,[n],[p,local],1.,PairConfig())
    assert len(result)==1 and result[0]['endpoint']=='old'


def test_local_pair_itself_is_not_an_alternative():
    from pair_pipeline import local_opposite_features,PairConfig
    n=dict(x=0.,y=0.,peak_significance=10.,flags=[])
    p=dict(x=3.,y=0.,peak_significance=10.,flags=[])
    assert local_opposite_features(n,p,[n],[p],1.,PairConfig())==[]
