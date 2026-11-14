"""One-command selection, real-data processing and portable team handoff."""
import argparse
import json
from pathlib import Path
import platform
import zipfile
from importlib.metadata import version

from prepare_triplets import prepare_triplets, PATCHES
from run_selected_pairs import run_selected
from pair_pipeline import PairConfig, write_json


def make_handoff(selection,results,configuration):
    """Summarize partial coverage explicitly; absence of evidence is not absence."""
    verification=[r.get('verification',{}) for r in results]
    return dict(schema_version='1.0',data_mode='real_observations',confirmed_objects=0,
        confirmation_performed=False,configuration=configuration,
        selection_complete=selection['all_requested_patches_have_triplets'] and all(p.get('requested_triplet_count_met',True) for p in selection['patches']),
        every_patch_has_a_triplet=selection['all_requested_patches_have_triplets'],
        selected_triplets=sum(len(p['selected_triplets']) for p in selection['patches']),
        comparisons_completed=sum(r.get('status')=='completed' for r in results),
        comparisons_quality_rejected=sum(r.get('result_status')=='quality_rejected' for r in results),
        processing_errors=sum(r.get('result_status')=='processing_error' or
                              r.get('verification',{}).get('result_status')=='verification_error' for r in results),
        two_epoch_candidates=sum(r.get('pairs_passing_gates',0) for r in results),
        third_epoch_supported_review=sum(v.get('status_counts',{}).get('third_epoch_supported_unique_among_tested',0) for v in verification),
        tested_without_support=sum(v.get('status_counts',{}).get('tested_no_support',0) for v in verification),
        verification_unavailable=sum(v.get('status_counts',{}).get('verification_unavailable',0) for v in verification),
        status='review_outputs' if results else 'no_suitable_triplet_found',
        limits=['No identity or orbit confirmation.',
                'Shared sky coverage does not guarantee coverage along every motion trajectory.',
                'Upstream covariance, false-positive rate and completeness remain uncalibrated.'],
        reports=dict(selection='selection.json',comparisons='results/summary.json' if results else None),
        runtime=dict(python=platform.python_version(),dependencies={p:version(p) for p in ['numpy','scipy','astropy','matplotlib']}))


def run(root,out,patches=('ecliptic-ra90',),max_triplets=2000,triplets_per_patch=3,max_sources_per_frame=5000,min_overlap=.10):
    root,out=Path(root),Path(out)
    out.mkdir(parents=True,exist_ok=False)
    configuration=dict(patches=list(patches),max_triplets=max_triplets,
                       triplets_per_patch=triplets_per_patch,max_sources_per_frame=max_sources_per_frame,
                       minimum_shared_coverage=min_overlap)
    try:
        selection=prepare_triplets(root,out/'selected_inputs.zip',patches=patches,max_triplets=max_triplets,
            triplets_per_patch=triplets_per_patch,min_overlap=min_overlap)
        write_json(out/'selection.json',selection)
        results=[]
        if any(p['selected_triplets'] for p in selection['patches']):
            with zipfile.ZipFile(out/'selected_inputs.zip') as z:
                # This archive was just written by the selector, using validated basenames.
                z.extractall(out/'inputs')
            results=run_selected(out/'inputs',out/'results',PairConfig(max_sources_per_frame=max_sources_per_frame))
        handoff=make_handoff(selection,results,configuration)
        write_json(out/'handoff.json',handoff)
        print(json.dumps(handoff,indent=2))
        return 1 if handoff['processing_errors'] else 0 if results else 2
    except Exception as exc:
        write_json(out/'failure.json',dict(status='processing_error',error=f'{type(exc).__name__}: {exc}',configuration=configuration))
        raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--patches',nargs='+',choices=PATCHES,default=['ecliptic-ra90'])
    p.add_argument('--max-triplets',type=int,default=2000)
    p.add_argument('--triplets-per-patch',type=int,default=3)
    p.add_argument('--max-sources-per-frame',type=int,default=5000)
    p.add_argument('--min-overlap',type=float,default=.10)
    a=p.parse_args()
    if a.max_sources_per_frame<1:p.error('Source cap must be positive')
    raise SystemExit(run(**vars(a)))
