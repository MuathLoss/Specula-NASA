"""Conservative third-epoch corroboration, not an orbit or identity confirmation.

Only interpolated epochs within a 14-day baseline are used. All hypotheses and
missing-data reasons survive. No label, ephemeris, or injected source is read.
"""
import csv
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import numpy as np
from astropy.coordinates import SkyCoord
import astropy.units as u
from sources import load_frame, detect, Config
from pair_pipeline import reference_matches, write_json, PairConfig

SEARCH_RADIUS_ARCSEC = 5.0
MAX_BASELINE_DAYS = 14.0
MIN_TIME_FRACTION = .15
BAD_FLAGS = {'sharp_or_undersampled','broad_or_blended','poor_gaussian_fit',
             'star_residue','saturated_centroid_uncertain','local_wavelength_unavailable'}


def sky(epoch):
    return SkyCoord(epoch['ra_deg']*u.deg,epoch['dec_deg']*u.deg)


def prediction(candidate, time):
    """Short-arc constant-angular-speed hypothesis, with explicit domain limits."""
    a,b=candidate['epoch1'],candidate['epoch2']
    span=b['mjd']-a['mjd']
    if not 0 < span <= MAX_BASELINE_DAYS: return None,'motion_model_window_exceeded'
    f=(time-a['mjd'])/span
    if not MIN_TIME_FRACTION <= f <= 1-MIN_TIME_FRACTION:
        return None,'outside_interpolation_window'
    first,last=sky(a),sky(b)
    predicted=first.directional_offset_by(first.position_angle(last),first.separation(last)*f)
    if min(predicted.separation(first).arcsec,predicted.separation(last).arcsec) <= 2*SEARCH_RADIUS_ARCSEC:
        return None,'insufficient_motion_leverage'
    return predicted,None


def endpoint_keys(c):
    return {(key,c[key]['file'],round(c[key]['reference_x'],4),round(c[key]['reference_y'],4))
            for key in ('epoch1','epoch2')}


def resolve_records(records,candidates):
    """Do not resolve alternatives when their coverage is missing or supports conflict."""
    by_id={c['candidate_id']:c for c in candidates}
    for r in records:
        if r.get('status')=='excluded_by_pair_gates': continue
        tested=[e for e in r['epochs'] if e['status'] in ('supported','multiple_matches','tested_no_support')]
        support=[e for e in tested if e['status']=='supported']
        r['tested_epochs']=len(tested)
        r['supporting_epochs']=len(support)
        if any(e['status']=='multiple_matches' for e in tested):
            r['status']='ambiguous_after_verification'
        elif support: r['status']='third_epoch_supported_review'
        elif tested: r['status']='tested_no_support'
        else: r['status']='verification_unavailable'
    for r in records:
        if r['status']!='third_epoch_supported_review': continue
        c=by_id[r['candidate_id']]
        competitors=[other for other in records if other is not r and
                     other['status']!='excluded_by_pair_gates' and
                     endpoint_keys(c)&endpoint_keys(by_id[other['candidate_id']])]
        supported_files={e['file'] for e in r['epochs'] if e['status']=='supported'}
        third_keys={(e['file'],e['matches'][0]['source_index']) for e in r['epochs'] if e['status']=='supported'}
        shared_third=any(third_keys & {(e['file'],m['source_index']) for e in other['epochs']
                        for m in e.get('matches',[])} for other in records if other is not r)
        if shared_third or any(o.get('supporting_epochs',0) or any(e['status']=='multiple_matches' for e in o['epochs']) for o in competitors):
            r['status']='ambiguous_after_verification'
        elif any(not supported_files <= {e['file'] for e in o['epochs'] if e['status']=='tested_no_support'} for o in competitors):
            r['status']='supported_but_competitors_unchecked'
        else: r['status']='third_epoch_supported_unique_among_tested'
    return records


def verify_pair(pair_root,verification_root,out,row1,row2,cfg=None):
    pair_root,verification_root,out=map(Path,(pair_root,verification_root,out))
    cfg=cfg or PairConfig()
    candidates=json.loads((out/'candidates.json').read_text())
    records=[dict(candidate_id=c['candidate_id'],original_flags=c['flags'],epochs=[],
                  status='pending' if not(set(c['flags'])-{'ambiguous_residual_pairing'}) else 'excluded_by_pair_gates')
             for c in candidates]
    active=[(c,r) for c,r in zip(candidates,records) if r['status']=='pending']
    report=dict(pair_configuration=asdict(cfg),model='short_arc_constant_angular_speed_interpolation',max_baseline_days=MAX_BASELINE_DAYS,
                search_radius_arcsec=SEARCH_RADIUS_ARCSEC,minimum_time_fraction=MIN_TIME_FRACTION,
                confirmation=False,identity_assigned=False,frames_considered=[],
                limitations=['No orbital curvature fit; absence of support does not rule out an object.',
                             'Association false-positive rate and completeness are not calibrated.',
                             'Registration and circular PSF models remain approximate.'])
    if active:
        table=verification_root/'tables'/f"frames_{row1['patch']}.csv"
        with table.open(newline='') as f: rows=list(csv.DictReader(f))
        rows=[r for r in rows if r['patch']==row1['patch'] and r['detector']==row1['detector'] and
              r['file'] not in (row1['file'],row2['file'])]
        # Deduplicate repeated metadata rows; distinct observation times required.
        rows=list({r['file']:r for r in rows}.values())
        a=load_frame(pair_root,row1,forced_kind='aligned')
        native=json.loads((out/'native_sources.json').read_text())
        for row in sorted(rows,key=lambda r:(float(r['t_mid_mjd']),r['file'])):
            time=float(row['t_mid_mjd'])
            predictions=[prediction(c,time) for c,r in active]
            if not any(p is not None for p,reason in predictions):
                report['frames_considered'].append(dict(file=row['file'],status='outside_model_or_leverage_limits'))
                continue
            print('Checking third epoch '+row['file'],flush=True)
            try:
                third=load_frame(verification_root,row,forced_kind='aligned')
                if third.wave is None: raise ValueError('WAVE layer missing')
                sources=detect(third,Config(max_sources_per_frame=cfg.max_sources_per_frame))
                matches,shift,align=reference_matches(a,third,native['epoch1'],sources,cfg)
                stationary={(m[1]['x'],m[1]['y']) for m in matches}
                x,y=a.wcs.world_to_pixel_values([s['ra_deg'] for s in sources],[s['dec_deg'] for s in sources])
                coords=a.wcs.pixel_to_world(np.asarray(x)-shift[0],np.asarray(y)-shift[1])
                frame_entry=dict(file=row['file'],status='registered',alignment=align,
                    sha256=hashlib.sha256(third.path.read_bytes()).hexdigest())
                report['frames_considered'].append(frame_entry)
                for (c,r),(pred,reason) in zip(active,predictions):
                    e=dict(file=row['file'],mjd=time,status='unavailable',reason=reason,matches=[])
                    r['epochs'].append(e)
                    if pred is None: continue
                    px,py=a.wcs.world_to_pixel(pred)
                    world=a.wcs.pixel_to_world(float(px)+shift[0],float(py)+shift[1])
                    tx,ty=third.wcs.world_to_pixel(world)
                    if not np.isfinite([tx,ty]).all(): e['reason']='outside_image';continue
                    ix,iy=int(round(float(tx))),int(round(float(ty)))
                    h,w=third.data.shape
                    # Full 7x7 neighborhood covers search radius and source fit margins.
                    if not (3<=ix<w-3 and 3<=iy<h-3): e['reason']='outside_image';continue
                    sl=np.s_[iy-3:iy+4,ix-3:ix+4]
                    valid=np.isfinite(third.data[sl])&np.isfinite(third.err[sl])&(third.err[sl]>0)&((third.mask[sl]&25)==0)
                    if not valid.all(): e['reason']='masked_search_neighborhood';continue
                    wave=float(third.wave[iy,ix])
                    if not wavelength_ok(wave,c['wavelength_um'],cfg.wavelength_tolerance):
                        e['reason']='prediction_wavelength_mismatch';continue
                    separations=coords.separation(pred).arcsec
                    for i in np.flatnonzero(separations<=SEARCH_RADIUS_ARCSEC):
                        s=sources[int(i)]
                        if s['mask_bits']&25 or BAD_FLAGS&set(s['flags']): continue
                        if (s['x'],s['y']) in stationary: continue
                        if not wavelength_ok(s['wavelength_um'],c['wavelength_um'],cfg.wavelength_tolerance): continue
                        e['matches'].append(dict(source_index=int(i),ra_deg=float(coords[i].ra.deg),
                            dec_deg=float(coords[i].dec.deg),residual_arcsec=float(separations[i]),
                            snr=s['snr'],native_x=s['x'],native_y=s['y'],wavelength_um=s['wavelength_um']))
                    e['status']='supported' if len(e['matches'])==1 else 'multiple_matches' if e['matches'] else 'tested_no_support'
                    e['reason']=None
                    e['predicted_ra_deg']=float(pred.ra.deg);e['predicted_dec_deg']=float(pred.dec.deg)
            except (ValueError,OSError,KeyError) as exc:
                reason=f'{type(exc).__name__}: {exc}'
                report['frames_considered'].append(dict(file=row['file'],status='unusable',reason=reason))
                for c,r in active:
                    r['epochs'].append(dict(file=row['file'],status='unavailable',reason=reason,matches=[]))
    resolve_records(records,candidates)
    report['candidates']=records
    report['status_counts']={s:sum(r['status']==s for r in records) for s in sorted({r['status'] for r in records})}
    if not active: report['result_status']='no_eligible_two_epoch_hypotheses'
    elif any(r['status']=='third_epoch_supported_unique_among_tested' for r in records): report['result_status']='third_epoch_supported_review'
    elif any('ambiguous' in r['status'] or r['status']=='supported_but_competitors_unchecked' for r in records): report['result_status']='ambiguous_after_verification'
    elif any(r['status']=='tested_no_support' for r in records):
        report['result_status']='partial_verification_no_support' if any(r['status']=='verification_unavailable' for r in records) else 'tested_no_support'
    else: report['result_status']='no_usable_verification_epoch'
    write_json(out/'verification_report.json',report)
    write_json(out/'third_epoch_supported_review.json',[dict(candidate=c,verification=r) for c,r in zip(candidates,records)
        if r['status']=='third_epoch_supported_unique_among_tested'])
    return {k:report[k] for k in ('result_status','status_counts','confirmation')}


def wavelength_ok(value,endpoints,tolerance):
    if value is None or not np.isfinite(value) or value<=0: return False
    return all(np.isfinite(v) and v>0 and abs(value-v)/((value+v)/2)<=tolerance for v in endpoints)
