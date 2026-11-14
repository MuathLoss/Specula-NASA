import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from pair_pipeline import gaussian_kernel,gaussian_matrix
from verify_tracks import prediction,resolve_records,wavelength_ok


def test_compact_kernel_mass_and_symmetry():
    for sigma in [.1,.7,.8,1.,2.]:
        k,info=gaussian_kernel(sigma,.001)
        assert info['removed_mass']<=.001
        assert np.isclose(k.sum(),1)
        assert np.allclose(k,k[::-1,:]) and np.allclose(k,k.T)


def test_mask_core_still_excluded_and_coverage_improves():
    valid=np.ones((21,21));valid[10,10]=0
    old=gaussian_matrix(valid.shape,.8)@valid.ravel()
    new=gaussian_matrix(valid.shape,.8,.001)@valid.ravel()
    assert new.reshape(valid.shape)[10,10]<1-1e-7
    assert np.count_nonzero(new>1-1e-7)>np.count_nonzero(old>1-1e-7)


def test_compact_operator_covariance():
    from pair_pipeline import aperture_variance
    op=gaussian_matrix((5,5),.8,.001);v=np.arange(1,26.)
    cov=op.toarray()@np.diag(v)@op.toarray().T
    ap=np.zeros((5,5),bool);ap[2,1:4]=True
    assert np.isclose(aperture_variance(op,v,ap),cov[np.ix_(ap.ravel(),ap.ravel())].sum())


def candidate(cid='a',end=1.):
    return dict(candidate_id=cid,epoch1=dict(file='old',mjd=10.,ra_deg=359.99,dec_deg=0.,reference_x=0,reference_y=0),
        epoch2=dict(file='new',mjd=12.,ra_deg=.01,dec_deg=0.,reference_x=end,reference_y=0))


def test_prediction_ra_wrap_and_time_limits():
    p,reason=prediction(candidate(),11.)
    assert reason is None and min(p.ra.deg,360-p.ra.deg)<1e-7
    for t in (10.,12.,9.,13.): assert prediction(candidate(),t)[0] is None
    c=candidate();c['epoch2']['mjd']=30.
    assert prediction(c,20.)[1]=='motion_model_window_exceeded'


def test_low_leverage_does_not_become_nondetection():
    c=candidate();c['epoch2']['ra_deg']=359.991
    assert prediction(c,11.)[1]=='insufficient_motion_leverage'


def record(cid,status,source=2):
    return dict(candidate_id=cid,status='pending',epochs=[dict(file='third',status=status,
        matches=[dict(source_index=source)] if status=='supported' else [])])


def test_missing_competitor_coverage_preserves_ambiguity():
    rr=[record('a','supported'),record('b','unavailable')]
    resolve_records(rr,[candidate(),candidate('b',2.)])
    assert rr[0]['status']=='supported_but_competitors_unchecked'
    assert rr[1]['status']=='verification_unavailable'


def test_unique_support_is_only_among_tested():
    rr=[record('a','supported'),record('b','tested_no_support')]
    resolve_records(rr,[candidate(),candidate('b',2.)])
    assert rr[0]['status']=='third_epoch_supported_unique_among_tested'
    assert rr[1]['status']=='tested_no_support'


def test_shared_third_detection_is_ambiguous():
    rr=[record('a','supported'),record('b','supported')]
    resolve_records(rr,[candidate(),candidate('b',2.)])
    assert all(r['status']=='ambiguous_after_verification' for r in rr)


def test_multiple_sources_are_not_greedily_selected():
    rr=[record('a','multiple_matches')]
    resolve_records(rr,[candidate()])
    assert rr[0]['status']=='ambiguous_after_verification'


def test_wavelength_gate():
    assert wavelength_ok(2.,[2.,2.001],.01)
    assert not wavelength_ok(2.1,[2.,2.001],.01)
    assert not wavelength_ok(None,[2.,2.],.01)
    assert not wavelength_ok(float('nan'),[2.,2.],.01)


def test_verification_io_registration_and_quality_branches():
    # Controlled numerical unit fixtures only; never reported as observational validation.
    from tempfile import TemporaryDirectory
    from types import SimpleNamespace
    from unittest.mock import patch
    import csv,json
    from astropy.wcs import WCS
    from verify_tracks import verify_pair
    w=WCS(naxis=2);w.wcs.crpix=[25,25];w.wcs.crval=[120,0]
    w.wcs.cdelt=[-6.15/3600,6.15/3600];w.wcs.ctype=['RA---TAN','DEC--TAN']
    with TemporaryDirectory() as temp:
        root=Path(temp);(root/'tables').mkdir()
        rows=[dict(file=f'f{i}',patch='ecliptic-ra90',detector='D6',t_mid_mjd=t) for i,t in [(1,10),(2,12),(3,11)]]
        with (root/'tables/frames_ecliptic-ra90.csv').open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=rows[0].keys());writer.writeheader();writer.writerows(rows)
        c=candidate();c['flags']=[];c['wavelength_um']=[2.,2.]
        for key,x,row in zip(('epoch1','epoch2'),(5,35),rows):
            co=w.pixel_to_world(x,25)
            c[key].update(file=row['file'],reference_x=x,reference_y=25,ra_deg=co.ra.deg,dec_deg=co.dec.deg)
        (root/'candidates.json').write_text(json.dumps([c]))
        (root/'native_sources.json').write_text(json.dumps(dict(epoch1=[],epoch2=[])))
        (root/'f3').write_bytes(b'unit fixture')
        co=w.pixel_to_world(20,25)
        source=dict(x=20.,y=25.,ra_deg=co.ra.deg,dec_deg=co.dec.deg,mask_bits=0,flags=[],wavelength_um=2.,snr=10.)
        frame=SimpleNamespace(wcs=w,wave=np.full((50,50),2.),data=np.ones((50,50)),
              err=np.ones((50,50)),mask=np.zeros((50,50),np.uint16),path=root/'f3')
        for case,expected in [('valid','third_epoch_supported_review'),('masked','no_usable_verification_epoch'),
                              ('bad_wave','no_usable_verification_epoch'),('poor_fit','tested_no_support'),
                              ('stationary','tested_no_support'),('registration','no_usable_verification_epoch')]:
            frame.mask[:]=0;frame.wave[:]=2.;source['flags']=[]
            if case=='masked': frame.mask[25,20]=16
            if case=='bad_wave': frame.wave[:]=3.
            if case=='poor_fit': source['flags']=['poor_gaussian_fit']
            matched=[(source,source)] if case=='stationary' else []
            with patch('verify_tracks.load_frame',return_value=frame),patch('verify_tracks.detect',return_value=[source]),\
                 patch('verify_tracks.reference_matches',return_value=(matched,np.zeros(2),{}),
                       side_effect=ValueError('alignment failed') if case=='registration' else None):
                result=verify_pair(root,root,root,rows[0],rows[1])
                assert result['result_status']==expected,(case,result)
                assert result['confirmation'] is False
