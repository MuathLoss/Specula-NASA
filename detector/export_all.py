"""Process every listed frame of each requested patch; build a bounded-file Git export.

This exports measured sources, not motion tracks. It does not run the separate
triplet/subtraction search. Raw observations and per-frame catalogs stay in --out.
"""
import argparse
import csv
import hashlib
from importlib.metadata import version
import io
import json
from pathlib import Path
import platform
import shutil
from datetime import datetime,timezone
from audit_recovery import run as export_patch
from data_io import Images
from pair_pipeline import write_json

PATCHES=['ceres','3i-atlas','ecliptic-ra90','ecliptic-virgo','nep-cats-eye']


def split_csv(source,destination,max_bytes=10*1024*1024):
    """Bound individual UTF-8 CSV files, repeat headers, preserve every data row."""
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    chunks=[];handle=None;size=0;rows=0
    def encoded(row):
        buf=io.StringIO(newline='');csv.writer(buf,lineterminator='\n').writerow(row)
        return buf.getvalue().encode('utf-8')
    try:
        with Path(source).open(newline='',encoding='utf-8-sig') as f:
            reader=csv.reader(f);header=encoded(next(reader))
            if len(header)>=max_bytes:raise ValueError('CSV header exceeds chunk limit')
            for row in reader:
                data=encoded(row)
                if len(header)+len(data)>max_bytes:raise ValueError('CSV row exceeds chunk limit')
                if handle is None or size+len(data)>max_bytes:
                    if handle is not None:handle.close();chunks[-1]['rows']=rows
                    path=destination/f'measured_sources_{len(chunks)+1:04d}.csv'
                    handle=path.open('xb');handle.write(header);size=len(header);rows=0
                    chunks.append(dict(file=path.name,rows=0))
                handle.write(data);size+=len(data);rows+=1
            if handle is None:
                path=destination/'measured_sources_0001.csv';handle=path.open('xb');handle.write(header)
                chunks.append(dict(file=path.name,rows=0))
            chunks[-1]['rows']=rows
    finally:
        if handle is not None:handle.close()
    for chunk in chunks:
        path=destination/chunk['file'];chunk.update(bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    return chunks


def preflight(root,patches,audit_ceres):
    problems=[];inventory=[]
    for patch in patches:
        table=root/'tables'/f'frames_{patch}.csv'
        try:
            with table.open(newline='',encoding='utf-8-sig') as f:rows=list(csv.DictReader(f))
            if not rows:raise ValueError('Frame table is empty')
            images=Images(root,patch)
            try:missing=[r['file'] for r in rows if images.locate(r) is None]
            finally:images.close()
            if missing:problems.append(dict(patch=patch,error='Missing images',files=missing))
            inventory.append(dict(patch=patch,frames=len(rows),frame_table_sha256=hashlib.sha256(table.read_bytes()).hexdigest()))
        except (OSError,ValueError,KeyError) as exc:problems.append(dict(patch=patch,error=f'{type(exc).__name__}: {exc}'))
    if audit_ceres and 'ceres' in patches and not (root/'tables/labels_ceres.csv').is_file():
        problems.append(dict(patch='ceres',error='--audit-ceres requires tables/labels_ceres.csv'))
    return inventory,problems


def run(root,out,bundle,patches=PATCHES,max_sources_per_frame=5000,audit_ceres=False):
    root,out,bundle=map(Path,(root,out,bundle))
    if len(set(patches))!=len(patches) or not patches or any(p not in PATCHES for p in patches):raise ValueError('Invalid patches')
    if max_sources_per_frame<1:raise ValueError('Source cap must be positive')
    if out.exists() or bundle.exists():raise FileExistsError('Choose new --out and --bundle directories; existing results are preserved')
    if out.resolve() in bundle.resolve().parents or bundle.resolve() in out.resolve().parents or out.resolve()==bundle.resolve():
        raise ValueError('Keep raw run output and commit bundle in separate directory trees')
    inventory,problems=preflight(root,patches,audit_ceres)
    if problems:
        print(json.dumps(dict(status='input_check_failed',problems=problems),indent=2))
        return 2
    out.mkdir(parents=True);bundle.mkdir(parents=True)
    report=dict(schema_version='1.0',created_utc=datetime.now(timezone.utc).isoformat(),
        mode='all_listed_frames_source_export',contains_motion_tracks=False,confirmation_performed=False,
        inventory=inventory,patches=[],max_sources_per_frame=max_sources_per_frame,
        runtime=dict(python=platform.python_version(),dependencies={p:version(p) for p in ['numpy','scipy','astropy','matplotlib']}),
        code_sha256={name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in ['export_all.py','audit_recovery.py','sources.py','data_io.py']})
    for patch in patches:
        print(f'=== Exporting ALL frames: {patch} ===',flush=True)
        entry=dict(patch=patch,status='processing')
        report['patches'].append(entry)
        try:
            result=export_patch(root,out/patch,patch=patch,max_sources_per_frame=max_sources_per_frame,
                               skip_reference_audit=not(audit_ceres and patch=='ceres'))
            chunks=split_csv(out/patch/'measured_sources.csv',bundle/patch)
            if sum(c['rows'] for c in chunks)!=result['measured_sources']:raise ValueError('CSV export count differs from source report')
            for name in ['recovery_summary.json','frame_report.json','recovery_matches.csv']:
                src=out/patch/name
                if src.is_file():shutil.copyfile(src,bundle/patch/name)
            entry.update(status=result['status'],frames_completed=result['frames_completed'],
                frames_failed=result['frames_failed'],measured_sources=result['measured_sources'],
                audit_status=result.get('audit_status'),chunks=chunks)
        except Exception as exc:entry.update(status='failed',error=f'{type(exc).__name__}: {exc}')
        write_json(out/'batch_summary.json',report);write_json(bundle/'batch_summary.json',report)
    report['complete']=all(p['status']=='completed' for p in report['patches'])
    report['measured_sources']=sum(p.get('measured_sources',0) for p in report['patches'])
    report['frames_completed']=sum(p.get('frames_completed',0) for p in report['patches'])
    report['catalog_chunk_bytes']=sum(c['bytes'] for p in report['patches'] for c in p.get('chunks',[]))
    (bundle/'README.md').write_text('''# Real source catalog export

Every row is one source measurement, not a distinct object or confirmed moving track.
Read batch_summary.json first: complete=false means at least one patch was incomplete.
Each patch has measured_sources_0001.csv and further numbered parts when needed.
Read ALL parts; each has the same header. CSV chunks are at most 10 MiB each.
Join records within this batch using source_id; use a run ID as well across batches.
Preserve quality_flags and measurement_status, including saturated measurements.
Times are MJD days, sky positions degrees, wavelengths micrometres, and x/y are
zero-based FITS pixel coordinates. Signal-to-noise is not probability or photometry.
Optional recovery_matches.csv is a separate positional reference audit, not identity
confirmation. Its confirmed field remains false. Frame reports preserve input hashes.
Raw FITS, archive inputs, per-frame catalogs and environments are intentionally absent.
Source extraction does not perform the separate triplet/subtraction or track search.
''',encoding='utf-8')
    write_json(out/'batch_summary.json',report);write_json(bundle/'batch_summary.json',report)
    print(json.dumps(report,indent=2))
    return 0 if report['complete'] else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--bundle',type=Path,required=True)
    p.add_argument('--patches',nargs='+',choices=PATCHES,default=PATCHES)
    p.add_argument('--max-sources-per-frame',type=int,default=5000)
    p.add_argument('--audit-ceres',action='store_true')
    raise SystemExit(run(**vars(p.parse_args())))
