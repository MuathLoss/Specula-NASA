"""Export independent real-frame source measurements, then audit reference positions.

Detection finishes and writes catalogs BEFORE the label table is opened. Reference
matches are positional associations, never independent identity or orbit confirmation.
"""
import argparse
import csv
from collections import Counter
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

import numpy as np
from astropy.coordinates import SkyCoord
import astropy.units as u
from astropy.wcs import WCS
from data_io import Images
from sources import load_frame,detect,Config
from pair_pipeline import write_json

SOURCE_FIELDS=['source_id','patch','frame','file','detector','t_mid_mjd','ra_deg','dec_deg',
    'x','y','snr','centroid_error_px','centroid_method','wavelength_um','mask_bits',
    'gaussian_sigma_px','fit_reduced_chi2','quality_flags','measurement_status','identity_status']
BAD_FLAGS={'poor_gaussian_fit','broad_or_blended','sharp_or_undersampled','star_residue'}


def source_status(s):
    if s['mask_bits']&16:return 'saturated_positional_measurement'
    if s['mask_bits']&9 or BAD_FLAGS&set(s['flags']):return 'quality_flagged_measurement'
    return 'unsaturated_measurement'


def export_source(s,source_id):
    row={k:s.get(k) for k in SOURCE_FIELDS}
    row.update(source_id=source_id,quality_flags=';'.join(s['flags']),
               measurement_status=source_status(s),identity_status='unidentified_source')
    return row


def match_reference(label,sources,row,metadata,radius_px):
    result=dict(object=label['object'],file=label['file'],frame=label['frame'],
                status='unavailable',reference_mask=int(label['mask']),
                reference_in_data=label['in_data']=='1',match_count=0,source_id=None,
                offset_px=None,offset_arcsec=None,source_flags=None,source_mask=None,
                confirmed=False)
    if label['patch']!=row['patch'] or label['detector']!=row['detector'] or int(label['frame'])!=int(row['frame']):
        result['status']='reference_metadata_mismatch';return result
    time=float(label['t_mid_mjd'])
    if not np.isfinite(time) or abs(time-float(row['t_mid_mjd']))*86400>2:
        result['status']='reference_time_mismatch';return result
    x,y=float(label['x']),float(label['y'])
    ra,dec=float(label['ra_deg']),float(label['dec_deg'])
    if not np.isfinite([x,y,ra,dec]).all():result['status']='invalid_reference_coordinates';return result
    w=WCS(metadata['wcs_header']).celestial
    wx,wy=w.world_to_pixel_values(ra,dec)
    if not np.isfinite([wx,wy]).all() or np.hypot(wx-x,wy-y)>1.:
        result['status']='reference_wcs_mismatch';return result
    h,width=metadata['shape']
    if not result['reference_in_data'] or not(0<=x<width and 0<=y<h) or int(label['mask'])&9:
        result['status']='reference_outside_or_bad_pixel';return result
    distances=np.array([np.hypot(s['x']-x,s['y']-y) for s in sources])
    indices=np.flatnonzero(distances<=radius_px)
    result['match_count']=len(indices)
    if not len(indices):
        result['status']='no_source_match_saturated_reference' if int(label['mask'])&16 else 'no_source_match_unsaturated_reference'
        return result
    if len(indices)>1:
        result['status']='ambiguous_multiple_sources';return result
    s=sources[int(indices[0])]
    result.update(source_id=s['source_id'],offset_px=float(distances[indices[0]]),
        offset_arcsec=float(SkyCoord(ra*u.deg,dec*u.deg).separation(SkyCoord(s['ra_deg']*u.deg,s['dec_deg']*u.deg)).arcsec),
        source_flags=';'.join(s['flags']),source_mask=s['mask_bits'])
    if (int(label['mask'])|s['mask_bits'])&16:result['status']='saturated_positional_match'
    elif source_status(s)=='quality_flagged_measurement':result['status']='quality_flagged_positional_match'
    else:result['status']='unsaturated_positional_match'
    return result


def run(root,out,patch='ceres',object_name='1 Ceres (A801 AA)',max_sources_per_frame=5000,match_radius_px=2.,skip_reference_audit=False):
    root,out=Path(root),Path(out)
    if patch not in {'ceres','3i-atlas','nep-cats-eye','ecliptic-ra90','ecliptic-virgo'}:raise ValueError('Unknown patch')
    if max_sources_per_frame<1 or not 0<match_radius_px<=3:raise ValueError('Invalid source cap or match radius')
    with (root/'tables'/f'frames_{patch}.csv').open(newline='',encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
    if not rows or len({r['file'] for r in rows})!=len(rows):raise ValueError('Empty frame table or duplicate filenames')
    if any(r['patch']!=patch for r in rows):raise ValueError('Frame table patch mismatch')
    rows.sort(key=lambda r:(float(r['t_mid_mjd']),r['file']))
    out.mkdir(parents=True,exist_ok=False);(out/'catalogs').mkdir()
    cfg=Config(max_sources_per_frame=max_sources_per_frame)
    frames=[];total=0;counts=Counter()
    report=dict(schema_version='1.0',mode='independent_frame_source_export_then_reference_audit',
        status='detecting',labels_used_for_detection=False,confirmed_objects=0,confirmation_performed=False,
        detection_configuration=asdict(cfg),match_radius_px=match_radius_px,
        target_reference_object=None if skip_reference_audit else object_name,frames_requested=len(rows),frames_completed=0,frames_failed=0,
        measured_sources=0,limitations=[
            'A positional reference match is not independent identity or motion confirmation.',
            'Label masks describe reference positions; masks across the full PSF may differ.',
            'No population completeness or false-positive calibration is provided.',
            'Saturated measurements have approximate centroids and unreliable photometry.'])
    write_json(out/'recovery_summary.json',report)
    images=Images(root,patch)
    try:
        with tempfile.TemporaryDirectory(prefix='reverse_most_audit_') as temp, (out/'measured_sources.csv').open('w',newline='') as csvfile:
            writer=csv.DictWriter(csvfile,fieldnames=SOURCE_FIELDS);writer.writeheader()
            for index,row in enumerate(rows):
                entry=dict(file=row['file'],frame=row['frame'],status='processing')
                dest=None
                try:
                    located=images.locate(row)
                    if located is None:raise FileNotFoundError(row['file'])
                    local_root=root
                    if not isinstance(located,Path):
                        local_root=Path(temp)
                        dest=local_root/'data/aligned'/patch/row['file'];dest.parent.mkdir(parents=True,exist_ok=True)
                        with images.open(row) as src,dest.open('wb') as dst:shutil.copyfileobj(src,dst)
                    frame=load_frame(local_root,row,forced_kind='aligned')
                    detections=detect(frame,cfg)
                    for i,s in enumerate(detections):s['source_id']=f'{patch}_{int(row["frame"]):04d}_{i+1:05d}'
                    catalog=f'catalogs/frame_{int(row["frame"]):04d}.json'
                    metadata=dict(shape=list(frame.data.shape),wcs_header=dict(frame.wcs.to_header()))
                    write_json(out/catalog,dict(frame=row,metadata=metadata,sources=detections))
                    for s in detections:
                        writer.writerow(export_source(s,s['source_id']));counts[source_status(s)]+=1
                    total+=len(detections)
                    entry.update(status='completed',sources=len(detections),catalog=catalog,
                        sha256=hashlib.sha256(frame.path.read_bytes()).hexdigest())
                except Exception as exc:
                    entry.update(status='failed',error=f'{type(exc).__name__}: {exc}')
                finally:
                    if dest is not None:dest.unlink(missing_ok=True)
                frames.append(entry);csvfile.flush()
                write_json(out/'frame_report.json',frames)
                print(f'{index+1}/{len(rows)} {row["file"]}: {entry["status"]}; sources={entry.get("sources",0)}',flush=True)
    finally:images.close()
    report.update(status='source_export_complete',frames_completed=sum(f['status']=='completed' for f in frames),
        frames_failed=sum(f['status']=='failed' for f in frames),measured_sources=total,measurement_status_counts=dict(counts))
    write_json(out/'recovery_summary.json',report)
    if skip_reference_audit:
        report.update(status='completed_with_frame_errors' if report['frames_failed'] else 'completed',
            audit_status='not_requested',teammate_catalog='measured_sources.csv',catalog_contains_motion_tracks=False)
        write_json(out/'recovery_summary.json',report)
        print(json.dumps(report,indent=2))
        return report
    # Label access is intentionally separated from source detection and catalog export.
    label_path=root/'tables'/f'labels_{patch}.csv'
    try:
        with label_path.open(newline='',encoding='utf-8-sig') as f:
            labels=[l for l in csv.DictReader(f) if l['object']==object_name]
        report['reference_table_sha256']=hashlib.sha256(label_path.read_bytes()).hexdigest()
        by_file={f['file']:f for f in frames};by_row={r['file']:r for r in rows};audits=[];cache_key=None;catalog=None
        for l in labels:
            if l['file'] not in by_file or by_file[l['file']]['status']!='completed':
                audits.append(dict(object=l['object'],file=l['file'],frame=l['frame'],status='frame_unavailable',confirmed=False));continue
            if l['file']!=cache_key:
                catalog=json.loads((out/by_file[l['file']]['catalog']).read_text());cache_key=l['file']
            try:audits.append(match_reference(l,catalog['sources'],by_row[l['file']],catalog['metadata'],match_radius_px))
            except (ValueError,KeyError,TypeError) as exc:
                audits.append(dict(object=l['object'],file=l['file'],frame=l['frame'],status='invalid_reference_row',error=str(exc),confirmed=False))
        # A source cannot uniquely establish two reference associations in the same frame.
        used=Counter(a.get('source_id') for a in audits if a.get('source_id'))
        for a in audits:
            if a.get('source_id') and used[a['source_id']]>1:a['status']='ambiguous_shared_source'
        write_json(out/'recovery_matches.json',audits)
        fields=['object','file','frame','status','reference_mask','reference_in_data','match_count','source_id',
                'offset_px','offset_arcsec','source_flags','source_mask','confirmed','error']
        with (out/'recovery_matches.csv').open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(audits)
        report.update(status='completed_with_frame_errors' if report['frames_failed'] else 'completed',
            reference_rows=len(labels),reference_outcomes=dict(Counter(a['status'] for a in audits)),
            audit_status='completed' if labels else 'no_matching_reference_rows')
    except Exception as exc:
        report.update(status='source_export_complete_audit_failed',audit_error=f'{type(exc).__name__}: {exc}')
    report['teammate_catalog']='measured_sources.csv'
    report['catalog_contains_motion_tracks']=False
    write_json(out/'recovery_summary.json',report)
    print(json.dumps(report,indent=2))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--patch',default='ceres');p.add_argument('--object-name',default='1 Ceres (A801 AA)')
    p.add_argument('--max-sources-per-frame',type=int,default=5000)
    p.add_argument('--match-radius-px',type=float,default=2.)
    p.add_argument('--skip-reference-audit',action='store_true',help='Export every frame without reading labels')
    a=p.parse_args();result=run(**vars(a))
    raise SystemExit(1 if result['frames_failed'] or 'audit_error' in result else 0)
