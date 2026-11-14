import csv
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch
import zipfile
import numpy as np
from astropy.wcs import WCS
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from prepare_triplets import eligible_triplet,shared_coverage,prepare_triplets
from run_real import make_handoff


def rows():
    return [dict(file=f'f{i}.fits',patch='ecliptic-ra90',detector='D6',t_mid_mjd=str(10+i),wl_um='2.',frame=str(i)) for i in range(3)]


def layers(wave=2.,hole=False):
    w=WCS(naxis=2);w.wcs.crpix=[25,25];w.wcs.crval=[120,0]
    w.wcs.cdelt=[-6.15/3600,6.15/3600];w.wcs.ctype=['RA---TAN','DEC--TAN']
    good=np.ones((50,50),bool)
    if hole:good[25,25]=False
    return np.full((50,50),wave),good,w,True


def test_joint_wavelength_gate_checks_all_three():
    good=shared_coverage([layers(),layers(2.005),layers(2.01)],stride=1)
    bad=shared_coverage([layers(),layers(2.1),layers()],stride=1)
    assert good['shared_compatible_fraction']>.5
    assert bad['shared_compatible_fraction']==0


def test_third_mask_neighborhood_reduces_coverage():
    a=shared_coverage([layers()]*3,stride=1)
    b=shared_coverage([layers(),layers(hole=True),layers()],stride=1)
    assert b['shared_compatible_fraction']<a['shared_compatible_fraction']
    assert b['shared_compatible_fraction']>0


def test_same_detector_distinct_time_and_model_limits():
    rr=rows();assert eligible_triplet(rr)
    rr[1]['detector']='D5';assert not eligible_triplet(rr)
    rr=rows();rr[1]['t_mid_mjd']=rr[0]['t_mid_mjd'];assert not eligible_triplet(rr)
    rr=rows();rr[2]['t_mid_mjd']='99';assert not eligible_triplet(rr)
    rr=rows();rr[1]['t_mid_mjd']='10.01';assert not eligible_triplet(rr)
    rr=rows();rr[1]['file']=rr[0]['file'];assert not eligible_triplet(rr)


def test_pre_eroded_cache_matches_uncached_comparison():
    from scipy.ndimage import binary_erosion
    original=[layers(),layers(hole=True),layers()]
    cached=[(w,binary_erosion(g,structure=np.ones((7,7),bool),border_value=0),c,p) for w,g,c,p in original]
    assert shared_coverage(original,stride=1)==shared_coverage(cached,stride=1,pre_eroded=True)


def test_triplet_pack_contains_middle_frame_and_exact_original_bytes():
    # Unit I/O fixture; no synthetic observations enter the real validation results.
    with TemporaryDirectory() as temp:
        root=Path(temp);(root/'tables').mkdir();(root/'data/aligned/ecliptic-ra90').mkdir(parents=True)
        rr=rows()
        for r in rr:(root/'data/aligned/ecliptic-ra90'/r['file']).write_bytes(('original '+r['file']).encode())
        for filename,records in [('frames_ecliptic-ra90.csv',rr),('psf_info.csv',[dict(patch=r['patch'],file=r['file']) for r in rr])]:
            with (root/'tables'/filename).open('w',newline='') as f:
                writer=csv.DictWriter(f,fieldnames=records[0]);writer.writeheader();writer.writerows(records)
        with patch('prepare_triplets.load_layers',return_value=layers()):
            audit=prepare_triplets(root,root/'selected.zip',triplets_per_patch=1)
        p=audit['patches'][0];assert len(p['selected_triplets'])==1
        assert p['selected_pairs'][0]['verification_files']==['f1.fits']
        assert p['selected_pairs'][0]['file1']=='f0.fits' and p['selected_pairs'][0]['file2']=='f2.fits'
        with zipfile.ZipFile(root/'selected.zip') as z:
            for r in rr:assert z.read('data/aligned/ecliptic-ra90/'+r['file'])==('original '+r['file']).encode()
            assert len(list(csv.DictReader(z.read('tables/frames_ecliptic-ra90.csv').decode().splitlines())))==3
        try:prepare_triplets(root,root/'selected.zip')
        except FileExistsError:pass
        else:raise AssertionError('Must not overwrite prior input package')


def test_handoff_does_not_confirm_or_hide_missing_verification():
    selection=dict(all_requested_patches_have_triplets=True,patches=[dict(selected_triplets=[{}])])
    results=[dict(status='completed',pairs_passing_gates=0,verification=dict(status_counts={'tested_no_support':5,'verification_unavailable':12}))]
    h=make_handoff(selection,results,{})
    assert h['confirmed_objects']==0 and not h['confirmation_performed']
    assert h['tested_without_support']==5 and h['verification_unavailable']==12


def test_empty_selection_handoff_is_explicit():
    selection=dict(all_requested_patches_have_triplets=False,patches=[dict(selected_triplets=[])])
    h=make_handoff(selection,[],{})
    assert h['status']=='no_suitable_triplet_found'
    assert h['comparisons_completed']==0 and h['reports']['comparisons'] is None
