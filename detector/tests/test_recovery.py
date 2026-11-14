import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from astropy.wcs import WCS
from audit_recovery import match_reference,source_status,export_source


def fixture():
    w=WCS(naxis=2);w.wcs.crpix=[25,25];w.wcs.crval=[120,0]
    w.wcs.cdelt=[-6.15/3600,6.15/3600];w.wcs.ctype=['RA---TAN','DEC--TAN']
    c=w.pixel_to_world(20,20)
    row=dict(patch='ceres',frame='1',detector='D2',t_mid_mjd='61000')
    l=dict(row,object='Ceres',file='one.fits',x='20',y='20',ra_deg=str(c.ra.deg),dec_deg=str(c.dec.deg),mask='0',in_data='1')
    s=dict(source_id='one',x=20.1,y=20.1,ra_deg=c.ra.deg,dec_deg=c.dec.deg,mask_bits=0,flags=[])
    return l,s,row,dict(shape=[50,50],wcs_header=dict(w.to_header()))


def test_unique_reference_match_remains_unconfirmed():
    l,s,row,meta=fixture();r=match_reference(l,[s],row,meta,2.)
    assert r['status']=='unsaturated_positional_match' and r['confirmed'] is False
    assert r['source_id']=='one' and np.isclose(r['offset_px'],np.sqrt(.02))


def test_saturation_in_either_source_or_reference_is_separate():
    l,s,row,meta=fixture();l['mask']='18'
    assert match_reference(l,[s],row,meta,2.)['status']=='saturated_positional_match'
    l['mask']='0';s['mask_bits']=16
    assert match_reference(l,[s],row,meta,2.)['status']=='saturated_positional_match'


def test_misses_and_ambiguity_not_promoted():
    l,s,row,meta=fixture()
    assert match_reference(l,[],row,meta,2.)['status']=='no_source_match_unsaturated_reference'
    assert match_reference(l,[s,dict(s,source_id='two')],row,meta,2.)['status']=='ambiguous_multiple_sources'


def test_invalid_reference_not_counted_as_a_miss():
    l,s,row,meta=fixture();l['t_mid_mjd']='61001'
    assert match_reference(l,[s],row,meta,2.)['status']=='reference_time_mismatch'
    l,s,row,meta=fixture();l['x']='30'
    assert match_reference(l,[s],row,meta,2.)['status']=='reference_wcs_mismatch'
    l,s,row,meta=fixture();l['in_data']='0'
    assert match_reference(l,[s],row,meta,2.)['status']=='reference_outside_or_bad_pixel'


def test_source_export_has_no_reference_identity():
    _,s,_,_=fixture();s['flags']=['poor_gaussian_fit']
    out=export_source(s,'one')
    assert out['identity_status']=='unidentified_source'
    assert out['measurement_status']=='quality_flagged_measurement'
    assert 'object' not in out and 'confirmed' not in out
