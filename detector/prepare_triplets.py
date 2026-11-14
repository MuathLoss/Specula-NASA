"""Select three real observations jointly, without labels or source detections.

Shared sky coverage is a selection proxy, not a guarantee of coverage along every
moving-source trajectory. Actual candidate positions are checked by verify_tracks.
"""
import argparse
import csv
import itertools
import json
from pathlib import Path
import zipfile
from collections import OrderedDict

import numpy as np
from scipy.ndimage import binary_erosion, map_coordinates, label
from data_io import Images, load_layers, csv_text
from verify_tracks import MAX_BASELINE_DAYS, MIN_TIME_FRACTION

PATCHES=['ceres','ecliptic-virgo','ecliptic-ra90','nep-cats-eye','3i-atlas']


def eligible_triplet(rows,min_hours=1.,max_days=MAX_BASELINE_DAYS):
    times=np.array([float(r['t_mid_mjd']) for r in rows])
    if not np.isfinite(times).all() or len({r['file'] for r in rows})!=3: return False
    if len({r['detector'] for r in rows})!=1: return False
    gaps=np.diff(times)
    if not np.all(gaps*24>=min_hours): return False
    span=times[-1]-times[0]
    return 0<span<=max_days and MIN_TIME_FRACTION <= gaps[0]/span <= 1-MIN_TIME_FRACTION


def shared_coverage(layers,tolerance=.01,stride=4,pre_eroded=False):
    """Require complete search neighborhoods and pairwise local wavelength agreement."""
    wa,_,aw,_=layers[0]
    yy,xx=np.mgrid[0:wa.shape[0]:stride,0:wa.shape[1]:stride]
    ra,dec=aw.pixel_to_world_values(xx,yy)
    waves=[];valid=np.ones(xx.shape,bool)
    for wave,good,wcs,_ in layers:
        x,y=wcs.world_to_pixel_values(ra,dec)
        # Matches the verifier's 7x7 neighborhood; full bilinear footprint valid.
        safe=good if pre_eroded else binary_erosion(good,structure=np.ones((7,7),bool),border_value=0)
        mapped=map_coordinates(wave,[y,x],order=1,mode='constant',cval=np.nan,prefilter=False)
        support=map_coordinates(safe.astype(float),[y,x],order=1,mode='constant',cval=0,prefilter=False)
        valid &= (support>1-1e-7)&np.isfinite(mapped)&(mapped>0)
        waves.append(mapped)
    low=np.minimum.reduce(waves);high=np.maximum.reduce(waves)
    with np.errstate(invalid='ignore',divide='ignore'):
        compatible=valid&((high-low)/((high+low)/2)<=tolerance)
    labels,count=label(compatible)
    largest=int(np.bincount(labels.ravel())[1:].max()) if count else 0
    return dict(shared_valid_fraction=float(valid.mean()),
                shared_compatible_fraction=float(compatible.mean()),
                largest_connected_sample_pixels=largest,sampling_stride_px=stride,
                full_psf_layers_present=all(l[3] for l in layers))


def prepare_triplets(root,out,patches=('ecliptic-ra90',),min_overlap=.10,
                     max_triplets=2000,triplets_per_patch=3,min_hours=1.,wave_tolerance=.01):
    root,out=Path(root),Path(out)
    if out.exists(): raise FileExistsError(f'Choose a new output path: {out}')
    if not (0<min_overlap<=1 and 0<wave_tolerance<=.01 and max_triplets>=1 and triplets_per_patch>=1 and min_hours>0):
        raise ValueError('Invalid triplet selection settings')
    if not patches or any(p not in PATCHES for p in patches):raise ValueError('Unknown or empty patch selection')
    audit=dict(schema_version='3.0',selection_mode='joint_triplet',real_data_only=True,
        labels_used_for_selection=False,source_detections_used_for_selection=False,
        purpose='Geometric and wavelength input selection; not detection confirmation',
        configuration=dict(min_overlap=min_overlap,max_triplets=max_triplets,
             triplets_per_patch=triplets_per_patch,min_hours=min_hours,wave_tolerance=wave_tolerance,
             max_baseline_days=MAX_BASELINE_DAYS,neighborhood_pixels=7),patches=[])
    psf_path=root/'tables/psf_info.csv'
    with psf_path.open(newline='',encoding='utf-8-sig') as f:
        reader=csv.DictReader(f);psf_fields=reader.fieldnames;psfs=list(reader)
    psf_counts={}
    for r in psfs:
        key=(r['patch'],r['file']);psf_counts[key]=psf_counts.get(key,0)+1
    selected={};readers={}
    try:
        for patch in patches:
            record=dict(patch=patch,selected_pairs=[],selected_triplets=[],comparisons=[],errors=[])
            audit['patches'].append(record)
            with (root/'tables'/f'frames_{patch}.csv').open(newline='',encoding='utf-8-sig') as f:
                rows=list(csv.DictReader(f))
            if len({r['file'] for r in rows})!=len(rows):raise ValueError(f'{patch}: duplicate frame filenames')
            images=readers[patch]=Images(root,patch)
            available=[]
            for r in rows:
                if images.locate(r) is None:
                    record['errors'].append(dict(file=r['file'],reason='missing_image'));continue
                if psf_counts.get((patch,r['file']))!=1:
                    record['errors'].append(dict(file=r['file'],reason='missing_or_duplicate_psf_metadata'));continue
                if r['patch']!=patch:raise ValueError('Frame table patch mismatch')
                available.append(r)
            record.update(table_frames=len(rows),available_frames=len(available))
            ranked=[]
            for detector in sorted({r['detector'] for r in available}):
                group=sorted([r for r in available if r['detector']==detector],key=lambda r:(float(r['t_mid_mjd']),r['file']))
                for trio in itertools.combinations(group,3):
                    if not eligible_triplet(trio,min_hours):continue
                    waves=np.array([float(r['wl_um']) for r in trio])
                    if not np.isfinite(waves).all() or min(waves)<=0:continue
                    spread=float(np.ptp(waves)/np.mean(waves))
                    # Metadata only orders the budget; no metadata wavelength veto.
                    ranked.append((spread,tuple(r['file'] for r in trio),trio))
            ranked.sort(key=lambda item:(item[0],item[1]))
            record['potential_triplets']=len(ranked)
            record['search_budget_exhausted']=len(ranked)>max_triplets
            cache=OrderedDict();shortlist=[]
            def get(row):
                key=row['file']
                if key not in cache:
                    if len(cache)>=8:cache.popitem(last=False)
                    wave,good,wcs,psf=load_layers(images,row)
                    cache[key]=(wave,binary_erosion(good,structure=np.ones((7,7),bool),border_value=0),wcs,psf)
                cache.move_to_end(key)
                return cache[key]
            for index,(_,_,trio) in enumerate(ranked[:max_triplets]):
                if index%50==0:print(f'{patch}: checking triplet {index+1}/{min(len(ranked),max_triplets)}',flush=True)
                item=dict(files=[r['file'] for r in trio],detector=trio[0]['detector'])
                try:
                    layers=[get(r) for r in trio]
                    stats=shared_coverage(layers,wave_tolerance,stride=4,pre_eroded=True)
                    # Coarse screening has a margin; exact full-resolution gate decides.
                    if stats['shared_compatible_fraction']>=min_overlap*.8 and stats['full_psf_layers_present']:
                        stats=shared_coverage(layers,wave_tolerance,stride=1,pre_eroded=True)
                    item.update(stats)
                    item['qualified']=bool(stats['sampling_stride_px']==1 and
                        stats['shared_compatible_fraction']>=min_overlap and
                        stats['largest_connected_sample_pixels']>=25 and stats['full_psf_layers_present'])
                    record['comparisons'].append(item)
                    if item['qualified']:shortlist.append((item,trio))
                except (ValueError,KeyError,OSError) as exc:
                    item['error']=f'{type(exc).__name__}: {exc}';record['comparisons'].append(item)
            shortlist.sort(key=lambda x:(-x[0]['shared_compatible_fraction'],-x[0]['largest_connected_sample_pixels'],x[0]['files']))
            used=set()
            for item,trio in shortlist:
                # Avoid spending all requested tests on nearly identical frame combinations.
                if used&set(item['files']):continue
                a,m,b=trio
                chosen=dict(item,selected=True,middle_file=m['file'],file1=a['file'],file2=b['file'],
                            times_mjd=[float(r['t_mid_mjd']) for r in trio])
                record['selected_triplets'].append(chosen)
                record['selected_pairs'].append(dict(file1=a['file'],file2=b['file'],
                      verification_files=[m['file']],detector=a['detector'],selection_mode='joint_triplet'))
                selected.setdefault(patch,[]).extend(trio);used.update(item['files'])
                if len(record['selected_triplets'])>=triplets_per_patch:break
            record['status']='selected' if record['selected_triplets'] else 'no_suitable_triplet_found'
            record['requested_triplet_count_met']=len(record['selected_triplets'])==triplets_per_patch
            print(f"{patch}: {len(record['selected_triplets'])} triplets selected",flush=True)
        audit['all_requested_patches_have_triplets']=all(r['selected_triplets'] for r in audit['patches'])
        out.parent.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(out,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for patch,rows in selected.items():
                for r in rows:readers[patch].copy(r,z)
                z.writestr(f'tables/frames_{patch}.csv',csv_text(rows))
            wanted={(p,r['file']) for p,rr in selected.items() for r in rr}
            z.writestr('tables/psf_info.csv',csv_text([r for r in psfs if (r['patch'],r['file']) in wanted],psf_fields))
            z.writestr('INPUT_SELECTION_REPORT.json',json.dumps(audit,indent=2,allow_nan=False))
        return audit
    finally:
        for reader in readers.values():reader.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--patches',nargs='+',choices=PATCHES,default=['ecliptic-ra90'])
    p.add_argument('--min-overlap',type=float,default=.10)
    p.add_argument('--max-triplets',type=int,default=2000)
    p.add_argument('--triplets-per-patch',type=int,default=3)
    a=p.parse_args()
    report=prepare_triplets(**vars(a))
    print(json.dumps(dict(output=str(a.out.resolve()),all_requested_patches_have_triplets=report['all_requested_patches_have_triplets']),indent=2))
    raise SystemExit(0 if report['all_requested_patches_have_triplets'] else 2)
