"""Process the real pairs listed in INPUT_SELECTION_REPORT.json; never read labels."""
import argparse
import csv
import json
from pathlib import Path
from pair_pipeline import process_pair, PairConfig
from verify_tracks import verify_pair


def run_selected(root, out, cfg=None, verification_root=None):
    root, out = Path(root), Path(out)
    cfg = cfg or PairConfig()
    selection = json.loads((root/'INPUT_SELECTION_REPORT.json').read_text())
    out.mkdir(parents=True, exist_ok=False)
    results=[]
    for patch in selection['patches']:
        name=patch['patch']
        if name not in ['ceres','ecliptic-virgo','ecliptic-ra90','nep-cats-eye','3i-atlas']:
            raise ValueError('Unknown patch')
        pairs=patch.get('selected_pairs',[])
        if not pairs:
            results.append(dict(patch=name,status='no_input_pair',selection_errors=patch.get('errors',[])))
            continue
        with (root/'tables'/f'frames_{name}.csv').open(newline='') as f:
            rows={r['file']:r for r in csv.DictReader(f)}
        for pair in pairs:
            rr=sorted([rows[pair['file1']],rows[pair['file2']]],key=lambda r:float(r['t_mid_mjd']))
            run_name=f'{name}_{int(rr[0]["frame"])}_{int(rr[1]["frame"])}'
            print(f'Starting {run_name}',flush=True)
            try:
                report=process_pair(root,out/run_name,*rr,cfg=cfg)
                try:
                    report['verification']=verify_pair(root,verification_root or root,out/run_name,*rr,cfg=cfg)
                except Exception as exc:
                    report['verification']=dict(result_status='verification_error',error=f'{type(exc).__name__}: {exc}')
                (out/run_name/'run_report.json').write_text(json.dumps(report,indent=2,allow_nan=False))
            except Exception:
                path=out/run_name/'run_report.json'
                if not path.exists():raise
                report=json.loads(path.read_text())
            report['selected_verification_files']=pair.get('verification_files',[])
            report['selection_mode']=pair.get('selection_mode','pair')
            (out/run_name/'run_report.json').write_text(json.dumps(report,indent=2,allow_nan=False))
            results.append(dict(run_name=run_name,patch=name,**report))
            (out/'summary.json').write_text(json.dumps(results,indent=2,allow_nan=False))
            print(f'{run_name}: {report.get("result_status",report["status"])}; verification = {report.get("verification",{}).get("result_status","not evaluated")}',flush=True)
    (out/'summary.json').write_text(json.dumps(results,indent=2,allow_nan=False))
    print('Finished. Review every status in summary.json, including rejected or failed comparisons.',flush=True)
    return results


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--verification-root',type=Path,help='Full extracted dataset with tables and aligned FITS; defaults to --root')
    p.add_argument('--max-sources-per-frame',type=int,default=1000)
    a=p.parse_args()
    if a.max_sources_per_frame<1:p.error('Source cap must be positive')
    results=run_selected(a.root,a.out,PairConfig(max_sources_per_frame=a.max_sources_per_frame),a.verification_root)

    if any(r.get('result_status')=='processing_error' or r.get('verification',{}).get('result_status')=='verification_error' for r in results):
        raise SystemExit(1)
