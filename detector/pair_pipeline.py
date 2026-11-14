"""Two-epoch, wavelength-masked real-data subtraction for Specula aligned FITS.

Research MVP: approximate Gaussian PSF homogenization; no identity assignment.
Uncertainties propagate the complete added linear resampling/smoothing operator,
but upstream aligned-input covariance is unavailable. Scores are not probabilities.
"""
import argparse
import csv
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path

import numpy as np
from astropy.coordinates import SkyCoord
from astropy.io import fits
import astropy.units as u
from scipy.ndimage import maximum_filter, distance_transform_edt
from scipy.sparse import csr_matrix
from scipy.spatial import cKDTree
from sources import load_frame, detect, Config, robust_scale


@dataclass
class PairConfig:
    wavelength_tolerance: float = .01
    min_usable_fraction: float = .2
    min_reference_stars: int = 5
    max_alignment_rms_px: float = .25
    min_snr: float = 5.
    max_speed_arcsec_min: float = 3.1
    min_separation_px: float = 2.
    max_peaks_per_sign: int = 500
    max_sources_per_frame: int = 1000
    max_candidate_pairs: int = 1000
    local_alternative_radius_fwhm: float = 2.0
    local_alternative_min_relative_peak: float = .5
    extra_smoothing_sigma_px: float = .8
    kernel_tail_mass_budget: float = .001


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False))


def interpolation_matrix(shape_in, shape_out, x, y):
    """Bilinear linear operator. Out-of-image weights are absent, not renormalized."""
    h, w = shape_in
    x, y = np.asarray(x).ravel(), np.asarray(y).ravel()
    finite = np.isfinite(x) & np.isfinite(y)
    x = np.where(finite, x, -100)
    y = np.where(finite, y, -100)
    ix, iy = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x-ix, y-iy
    rr, cc, vv = [], [], []
    for dx, dy, weight in [(0,0,(1-fx)*(1-fy)),(1,0,fx*(1-fy)),
                            (0,1,(1-fx)*fy),(1,1,fx*fy)]:
        xx, yy = ix+dx, iy+dy
        good = finite & (xx>=0)&(xx<w)&(yy>=0)&(yy<h)&(weight>1e-12)
        rr.extend(np.flatnonzero(good)); cc.extend((yy[good]*w+xx[good]).tolist())
        vv.extend(weight[good].tolist())
    return csr_matrix((vv,(rr,cc)),shape=(int(np.prod(shape_out)),h*w))


def gaussian_kernel(sigma, tail_mass_budget=0.):
    """Drop complete symmetric shells, bounded by original normalized mass."""
    if not np.isfinite(sigma) or sigma <= 0:
        raise ValueError('Gaussian sigma must be positive and finite')
    if not 0 <= tail_mass_budget <= .001:
        raise ValueError('Tail budget must be between 0 and 0.001')
    radius=max(1,int(np.ceil(3*sigma)))
    gy,gx=np.mgrid[-radius:radius+1,-radius:radius+1]
    k=np.exp(-(gx*gx+gy*gy)/(2*sigma*sigma));k/=k.sum()
    omit=np.zeros(k.shape,dtype=bool)
    for level in np.unique(k):
        trial=k<=level
        if k[trial].sum() <= tail_mass_budget: omit=trial
        else: break
    removed=float(k[omit].sum())
    k[omit]=0; k/=k.sum()
    return k,dict(removed_mass=removed,retained_weights=int(np.count_nonzero(k)),
                  effective_sigma_px=float(np.sqrt((k*(gx*gx+gy*gy)).sum()/2)))


def gaussian_matrix(shape, sigma, tail_mass_budget=0.):
    h,w=shape; yy,xx=np.indices(shape); ids=np.arange(h*w).reshape(shape)
    k,_=gaussian_kernel(sigma,tail_mass_budget)
    radius=k.shape[0]//2
    gy,gx=np.mgrid[-radius:radius+1,-radius:radius+1]
    rr=[];cc=[];vv=[]
    for dy,dx,weight in zip(gy.ravel(),gx.ravel(),k.ravel()):
        if weight==0: continue
        cy,cx=yy+dy,xx+dx; good=(cy>=0)&(cy<h)&(cx>=0)&(cx<w)
        rr.append(ids[good]);cc.append(cy[good]*w+cx[good]);vv.append(np.full(good.sum(),weight))
    return csr_matrix((np.concatenate(vv),(np.concatenate(rr),np.concatenate(cc))),shape=(h*w,h*w))


def reference_matches(a,b,sa,sb,cfg):
    aa=[s for s in sa if not (s['mask_bits']&16) and s['snr']>=10]
    bb=[s for s in sb if not (s['mask_bits']&16) and s['snr']>=10]
    if len(aa)<cfg.min_reference_stars or len(bb)<cfg.min_reference_stars:
        raise ValueError('Insufficient unsaturated reference stars')
    xa=np.array([[s['x'],s['y']] for s in aa])
    bx,by=a.wcs.world_to_pixel_values([s['ra_deg'] for s in bb],[s['dec_deg'] for s in bb])
    xb=np.column_stack((bx,by))
    dist,idx=cKDTree(xb).query(xa);_,back=cKDTree(xa).query(xb)
    ii=np.array([i for i,j in enumerate(idx) if dist[i]<1.5 and back[j]==i],dtype=int)
    jj=idx[ii];delta=xb[jj]-xa[ii]
    if len(ii)<cfg.min_reference_stars:raise ValueError('Insufficient mutually matched reference stars')
    shift=np.median(delta,axis=0)
    good=np.linalg.norm(delta-shift,axis=1)<.5
    ii,jj,delta=ii[good],jj[good],delta[good]
    if len(ii)<cfg.min_reference_stars:raise ValueError('Insufficient reference stars after outlier rejection')
    shift=np.median(delta,axis=0)
    rms=float(np.sqrt(np.mean(np.sum((delta-shift)**2,axis=1))))
    if rms>cfg.max_alignment_rms_px:raise ValueError(f'Alignment RMS {rms:.3f} exceeds gate')
    return [(aa[i],bb[j]) for i,j in zip(ii,jj)],shift,dict(n_reference_stars=len(ii),
            median_shift_px=shift.tolist(),rms_after_translation_px=rms,
            reference_rms_arcsec=rms*6.15,absolute_astrometry_calibrated=False)


def inspect_psf(root,row):
    with (root/'tables/psf_info.csv').open(newline='') as f:
        matches=[r for r in csv.DictReader(f) if r['patch']==row['patch'] and r['file']==row['file']]
    if len(matches)!=1:raise ValueError('Exactly one PSF metadata row required')
    r=matches[0];zone=int(r['psf_zone'])
    with fits.open(root/'data/aligned'/row['patch']/row['file']) as h:
        layer=r['psf_layer'].upper()
        model=np.array(h[layer].data[zone] if layer=='PSF' else h[layer].data['EPSF'][zone],dtype=float)
        if model.ndim!=2 or not np.isfinite(model).all() or model.sum()<=0:
            raise ValueError('Invalid instrument PSF model')
    return dict(layer=layer,zone=zone,shape=list(model.shape),sum=float(model.sum()),
                metadata_fwhm_px=float(r['psf_fwhm_px']),
                model_sha256=hashlib.sha256(model.tobytes()).hexdigest())


def aperture(shape,x,y,radius):
    yy,xx=np.indices(shape);return (xx-x)**2+(yy-y)**2<=radius**2


def aperture_variance(op,var,mask):
    # Sum output rows first, then square: retains covariance introduced by this
    # pipeline, unlike summing only the diagonal output variances.
    weights=np.asarray(op[mask.ravel()].sum(axis=0)).ravel()
    return float(np.dot(weights*weights,var))


def signed_sources(diff,snr,good,sign,cfg):
    score=np.where(good,sign*snr,-np.inf)
    distance=distance_transform_edt(np.pad(good,1))[1:-1,1:-1]
    yy,xx=np.where((score==maximum_filter(score,size=3,mode='constant',cval=-np.inf))&
                   (score>=cfg.min_snr)&(distance>=2))
    if len(xx)>cfg.max_peaks_per_sign:raise ValueError('Residual peak cap exceeded; narrow input')
    result=[]
    for i in np.argsort(score[yy,xx])[::-1]:
        x,y=int(xx[i]),int(yy[i]); sl=np.s_[y-1:y+2,x-1:x+2]
        v=np.maximum(sign*diff[sl],0);norm=v.sum()
        if norm<=0:continue
        gy,gx=np.mgrid[y-1:y+2,x-1:x+2]
        cx=float((gx*v).sum()/norm);cy=float((gy*v).sum()/norm)
        if any(np.hypot(cx-s['x'],cy-s['y'])<2 for s in result):continue
        vx=float(((gx-cx)**2*v).sum()/norm);vy=float(((gy-cy)**2*v).sum()/norm)
        cov=float(((gx-cx)*(gy-cy)*v).sum()/norm)
        eig=np.linalg.eigvalsh([[vx,cov],[cov,vy]])
        ratio=float(np.sqrt(max(eig[0],0)/max(eig[1],1e-12)))
        result.append(dict(x=cx,y=cy,sign=sign,peak_significance=float(score[y,x]),
                           shape_axis_ratio=ratio,flags=[]))
    return result


def local_opposite_features(negative, positive, negatives, positives, target_sigma, cfg):
    """Flag local signed structure that makes a much longer pairing unsafe.

    A nearby feature need not itself pass an aperture/native-source gate to
    signal a PSF/registration residual or a different local association.
    This is a review flag, not a claim that the feature is certainly an artifact.
    """
    chosen=np.hypot(negative['x']-positive['x'],negative['y']-positive['y'])
    radius=cfg.local_alternative_radius_fwhm*2.35482*target_sigma
    result=[]
    for label,source,selected,others in [('old',negative,positive,positives),('new',positive,negative,negatives)]:
        for other in others:
            if other is selected:continue
            distance=float(np.hypot(source['x']-other['x'],source['y']-other['y']))
            if distance<=radius and distance<chosen/2 and other['peak_significance']>=cfg.local_alternative_min_relative_peak*source['peak_significance']:
                result.append(dict(endpoint=label,x=other['x'],y=other['y'],distance_px=distance,
                    peak_significance=other['peak_significance'],feature_flags=list(other['flags'])))
    return result


def flag_pair_ambiguity(candidates):
    """Only viable alternatives can make a viable association ambiguous."""
    plausible=[c for c in candidates if not c['flags']]
    for c in plausible:
        if any(d is not c and (d['_negative_index']==c['_negative_index'] or
               d['_positive_index']==c['_positive_index']) for d in plausible):
            c['flags'].append('ambiguous_residual_pairing')
            c['quality_score']*=.5


def diagnostics(out, candidate, arrays):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    a,b,d,s=arrays
    fig,axs=plt.subplots(2,4,figsize=(11,6))
    for row,ep in enumerate([candidate['epoch1'],candidate['epoch2']]):
        x,y=ep['reference_x'],ep['reference_y']
        lo_x=max(0,int(x)-8);hi_x=min(a.shape[1],int(x)+9)
        lo_y=max(0,int(y)-8);hi_y=min(a.shape[0],int(y)+9)
        sl=np.s_[lo_y:hi_y,lo_x:hi_x]
        lim=max(float(np.nanpercentile(np.abs(d[sl]),99)),1e-6)
        for ax,arr,title in zip(axs[row],arrays,['Epoch 1 (scaled)','Epoch 2 (aligned)','Difference: 2 - 1','Significance']):
            if title.startswith('Epoch'):
                ax.imshow(np.arcsinh(arr[sl]/.05),origin='lower',cmap='gray',vmin=-1,vmax=4)
            else:
                v=10 if title=='Significance' else lim
                ax.imshow(arr[sl],origin='lower',cmap='RdBu_r',vmin=-v,vmax=v)
            ax.plot(x-lo_x,y-lo_y,'+' if row else 'o',mfc='none',
                    color='#00b5d8' if row else '#ffb000',ms=9)
            ax.set_title(title,fontsize=10);ax.set_xticks([]);ax.set_yticks([])
        axs[row,0].set_ylabel('Proposed old position' if row==0 else 'Proposed new position',fontsize=10)
    fig.suptitle(candidate['candidate_id']+' | association unconfirmed',fontsize=10)
    fig.tight_layout();dest=out/(candidate['candidate_id']+'.png');fig.savefig(dest,dpi=150);plt.close(fig)
    return dest.name


def process_pair(root,out,row1,row2,cfg=None):
    cfg=cfg or PairConfig();root=Path(root);out=Path(out);out.mkdir(parents=True,exist_ok=False)
    report=dict(status='running',schema_version='2.0',configuration=asdict(cfg),
                input_files=[row1['file'],row2['file']],real_data_only=True,
                label_or_ephemeris_input=False,match_status='not_crossmatched')
    try:
        if row1['patch']!=row2['patch'] or row1['detector']!=row2['detector']:
            raise ValueError('Pair must share patch and detector')
        dt=(float(row2['t_mid_mjd'])-float(row1['t_mid_mjd']))*1440
        if dt<=0:raise ValueError('Epoch 2 must be later than epoch 1')
        a,b=load_frame(root,row1,forced_kind='aligned'),load_frame(root,row2,forced_kind='aligned')
        if a.wave is None or b.wave is None:raise ValueError('WAVE layers required')
        report['observation_times_mjd']=[float(row1['t_mid_mjd']),float(row2['t_mid_mjd'])]
        report['elapsed_minutes']=dt
        report['input_sha256']=[hashlib.sha256(f.path.read_bytes()).hexdigest() for f in (a,b)]
        report['psf']=[inspect_psf(root,r) for r in (row1,row2)]
        sa,sb=[detect(f,Config(max_sources_per_frame=cfg.max_sources_per_frame)) for f in (a,b)]
        write_json(out/'native_sources.json',dict(epoch1=sa,epoch2=sb))
        matched,shift,align=reference_matches(a,b,sa,sb,cfg);report['alignment']=align
        shape=a.data.shape;yy,xx=np.indices(shape)
        ra,dec=a.wcs.pixel_to_world_values(xx+shift[0],yy+shift[1])
        bx,by=b.wcs.world_to_pixel_values(ra,dec)
        R=interpolation_matrix(b.data.shape,shape,bx,by)
        good1=np.isfinite(a.data)&np.isfinite(a.err)&(a.err>0)&((a.mask&25)==0)
        good2=np.isfinite(b.data)&np.isfinite(b.err)&(b.err>0)&((b.mask&25)==0)
        wave2=(R@np.nan_to_num(b.wave).ravel()).reshape(shape)
        rel=np.abs(a.wave-wave2)/((a.wave+wave2)/2)
        waves=np.isfinite(rel)&(rel<=cfg.wavelength_tolerance)
        report['wavelength']=dict(tolerance_fraction=cfg.wavelength_tolerance,
                median_fractional_difference=float(np.nanmedian(rel[good1&(wave2>0)])))
        # Estimate effective widths from real aligned stars. The original PSF
        # cubes are in detector orientation; do not silently apply them north-up.
        widths=[]
        for epoch in (0,1):
            vals=[m[epoch]['gaussian_sigma_px'] for m in matched if m[epoch]['gaussian_sigma_px'] is not None]
            widths.append(float(np.median(vals)))
        if not all(.25<=s<=1.5 for s in widths):raise ValueError('Invalid empirical PSF widths')
        # Bilinear interpolation adds phase-dependent broadening. Account for
        # its mean variance in this approximate circular Gaussian model.
        fx=bx-np.floor(bx);fy=by-np.floor(by)
        interpolation_variance=float(np.nanmedian((fx*(1-fx)+fy*(1-fy))/2))
        effective=[widths[0],float(np.sqrt(widths[1]**2+interpolation_variance))]
        target=float(np.sqrt(max(effective)**2+cfg.extra_smoothing_sigma_px**2))
        sigmas=[float(np.sqrt(target**2-s*s)) for s in effective]
        K1=gaussian_matrix(shape,sigmas[0],cfg.kernel_tail_mass_budget);K2=gaussian_matrix(shape,sigmas[1],cfg.kernel_tail_mass_budget)
        report['smoothing_kernels']=[gaussian_kernel(s,cfg.kernel_tail_mass_budget)[1] for s in sigmas]
        O1=K1;O2=(K2@R).tocsr()
        report['psf_matching']=dict(method='empirical_circular_gaussian_approximation',
                native_sigma_px=widths,interpolation_variance_px2=interpolation_variance,
                target_sigma_px=target,kernel_sigma_px=sigmas,
                instrument_orientation_available=False,full_psf_kernel_applied=False)
        support1=np.asarray(O1@good1.ravel()).reshape(shape)
        support2=np.asarray(O2@good2.ravel()).reshape(shape)
        wave_support=np.asarray(K2@waves.ravel()).reshape(shape)
        wave_support1=np.asarray(K1@waves.ravel()).reshape(shape)
        good=(support1>1-1e-7)&(support2>1-1e-7)&(wave_support>1-1e-7)&(wave_support1>1-1e-7)
        report['usable_fraction_before_smoothing']=float((good1 & (np.asarray(R@good2.ravel()).reshape(shape)>1-1e-7) & waves).mean())
        report['usable_fraction_after_all_masks']=float(good.mean())
        if good.mean()<cfg.min_usable_fraction:raise ValueError('Insufficient valid wavelength-matched common support')
        v1=np.where(good1,(a.err*a.noise_scale)**2,0).ravel()
        v2=np.where(good2,(b.err*b.noise_scale)**2,0).ravel()
        A=np.asarray(O1@np.where(good1,a.data,0).ravel()).reshape(shape)
        B=np.asarray(O2@np.where(good2,b.data,0).ravel()).reshape(shape)
        refs=[];ratios=[];radius=max(2.,2.5*target)
        for s,t in matched:
            ap=aperture(shape,s['x'],s['y'],radius)
            if not good[ap].all():continue
            fa,fb=A[ap].sum(),B[ap].sum()
            if fa>0 and fb>0:
                ratios.append(float(fb/fa));refs.append([s['x'],s['y']])
        if len(ratios)<cfg.min_reference_stars:raise ValueError('Insufficient clean photometric reference apertures')
        ratios=np.array(ratios);med=np.median(ratios);mad=1.4826*np.median(np.abs(ratios-med))
        keep=np.abs(ratios-med)<=max(3*mad,.05)
        if keep.sum()<cfg.min_reference_stars:raise ValueError('Insufficient stable flux ratios')
        scale=float(np.median(ratios[keep]));scale_error=float(1.4826*np.median(np.abs(ratios[keep]-scale))/np.sqrt(keep.sum()))
        if not .5<scale<2:raise ValueError('Photometric scaling outside conservative range')
        report['photometry']=dict(epoch1_scale=scale,scale_error_heuristic=scale_error,
                                  reference_count=int(keep.sum()),ratio_scatter_mad=float(mad))
        # A robust residual constant addresses remaining background after upstream BKG_MED.
        diff=B-scale*A
        background=float(np.median(diff[good]));diff-=background
        var=(np.asarray(O2.multiply(O2)@v2)+scale*scale*np.asarray(O1.multiply(O1)@v1)).reshape(shape)
        var+=(A*scale_error)**2
        initial=diff/np.sqrt(np.maximum(var,1e-30))
        blank=good&(np.abs(A)<3*np.sqrt(np.maximum(np.asarray(O1.multiply(O1)@v1).reshape(shape),1e-30)))
        noise=robust_scale(initial[blank]);var*=noise*noise
        snr=np.where(good,diff/np.sqrt(np.maximum(var,1e-30)),np.nan)
        report['noise']=dict(empirical_scale=noise,residual_background=background,
             variance_method='square complete linear operator; aperture sums include added covariance',
             upstream_covariance_available=False,calibration_error_approximate=True)
        neg=signed_sources(diff,snr,good,-1,cfg);pos=signed_sources(diff,snr,good,1,cfg)
        fixed=np.array([[m[0]['x'],m[0]['y']] for m in matched])
        native1=np.array([[s['x'],s['y']] for s in sa]);bx0,by0=a.wcs.world_to_pixel_values([s['ra_deg'] for s in sb],[s['dec_deg'] for s in sb])
        native2=np.column_stack((bx0,by0))-shift
        for residuals,original,native in [(neg,sa,native1),(pos,sb,native2)]:
            for r in residuals:
                xy=np.array([r['x'],r['y']]);dd=np.linalg.norm(native-xy,axis=1);i=int(np.argmin(dd))
                r['native_detection']=original[i] if dd[i]<=2 else None
                if r['native_detection'] is None:r['flags'].append('no_native_source_within_2px')
                else:
                    native_flags=r['native_detection']['flags']
                    if r['native_detection']['mask_bits']&16:r['flags'].append('saturated_native_source')
                    for flag in ['sharp_or_undersampled','broad_or_blended','poor_gaussian_fit','star_residue']:
                        if flag in native_flags:r['flags'].append('native_'+flag)
                if np.min(np.linalg.norm(fixed-xy,axis=1))<2:r['flags'].append('stationary_variable_or_subtraction_residual')
                if r['shape_axis_ratio']<.35:r['flags'].append('elongated_residual')
                ap=aperture(shape,*xy,radius)
                if not good[ap].all():r['flags'].append('aperture_near_mask')
                r['aperture_flux_signed']=float(diff[ap].sum())
                av=aperture_variance(O2,v2,ap)+scale*scale*aperture_variance(O1,v1,ap)+(A[ap].sum()*scale_error)**2
                r['integrated_significance']=float(r['sign']*diff[ap].sum()/np.sqrt(max(av,1e-30))/noise)
                if r['integrated_significance']<cfg.min_snr:r['flags'].append('low_integrated_significance')
        candidates=[]
        report['eligible_negative_residuals']=sum(not s['flags'] for s in neg)
        report['eligible_positive_residuals']=sum(not s['flags'] for s in pos)
        for n in neg:
            if n['flags']:continue
            for p in pos:
                if p['flags']:continue
                displacement=float(np.hypot(p['x']-n['x'],p['y']-n['y']))
                if displacement<cfg.min_separation_px:continue
                coords=a.wcs.pixel_to_world([n['x'],p['x']],[n['y'],p['y']])
                sep=float(coords[0].separation(coords[1]).arcsec)
                if sep/dt>cfg.max_speed_arcsec_min:continue
                f1,f2=-n['aperture_flux_signed'],p['aperture_flux_signed']
                if f1<=0 or f2<=0 or not .25<f2/f1<4:continue
                flags=sorted(set(n['flags']+p['flags']))
                local_features=local_opposite_features(n,p,neg,pos,target,cfg)
                if local_features:flags.append('closer_opposite_residual_requires_review')
                if min(n['integrated_significance'],p['integrated_significance'])<cfg.min_snr:flags.append('low_integrated_significance')
                local1=float(a.wave[round(n['y']),round(n['x'])]);local2=float(wave2[round(p['y']),round(p['x'])])
                mismatch=abs(local1-local2)/((local1+local2)/2)
                if mismatch>cfg.wavelength_tolerance:flags.append('endpoint_wavelength_mismatch')
                epochs=[]
                for r,row,c in zip((n,p),(row1,row2),coords):
                    native=r['native_detection']
                    epochs.append(dict(file=row['file'],mjd=float(row['t_mid_mjd']),
                        ra_deg=float(c.ra.deg),dec_deg=float(c.dec.deg),
                        reference_x=r['x'],reference_y=r['y'],
                        native_x=None if native is None else native['x'],native_y=None if native is None else native['y'],
                        peak_significance=r['peak_significance'],integrated_significance=r['integrated_significance'],
                        shape_axis_ratio=r['shape_axis_ratio'],
                        native_mask_bits=None if native is None else native['mask_bits'],
                        native_quality_flags=[] if native is None else native['flags']))
                components=dict(signal=min(1,min(n['peak_significance'],p['peak_significance'])/10),
                        alignment=max(0,1-align['rms_after_translation_px']/cfg.max_alignment_rms_px),
                        flux_similarity=min(f1,f2)/max(f1,f2),shape=min(n['shape_axis_ratio'],p['shape_axis_ratio']))
                score=100*sum(components.values())/4
                if flags:score*=.25
                if len(candidates)>=cfg.max_candidate_pairs:raise ValueError('Candidate pair cap exceeded; narrow input scope')
                candidates.append(dict(candidate_id=f"{row1['patch']}_f{row1['frame']}_f{row2['frame']}_pair_{len(candidates)+1:04d}",epoch1=epochs[0],epoch2=epochs[1],
                    angular_separation_arcsec=sep,position_angle_deg=float(coords[0].position_angle(coords[1]).deg),
                    elapsed_minutes=dt,motion_arcsec_hour=sep/dt*60,
                    wavelength_um=[local1,local2],endpoint_wavelength_fraction=mismatch,
                    flux_ratio=f2/f1,flags=flags,local_opposite_features=local_features,quality_score=score,quality_components=components,
                    score_is_probability=False,match_status='not_crossmatched',status='review_candidate',
                    _negative_index=neg.index(n),_positive_index=pos.index(p)))
        # Preserve every alternative; no greedy forced pairing.
        flag_pair_ambiguity(candidates)
        for c in candidates:
            c['passes_configured_gates']=not c['flags']
            c['diagnostic_image']=diagnostics(out,c,[np.where(good,scale*A,np.nan),np.where(good,B,np.nan),np.where(good,diff,np.nan),snr])
        for c in candidates:c.pop('_negative_index');c.pop('_positive_index')
        candidates.sort(key=lambda c:-c['quality_score'])
        write_json(out/'candidates.json',candidates)
        write_json(out/'two_epoch_candidates.json',[c for c in candidates if c['passes_configured_gates']])
        with (out/'detections.csv').open('w',newline='') as export:
            writer=csv.DictWriter(export,fieldnames=['patch','frame','file','x','y','snr','track_id','is_target'])
            writer.writeheader()
            for c in candidates:
                if not c['passes_configured_gates']:continue
                for ep,row in zip([c['epoch1'],c['epoch2']],[row1,row2]):
                    writer.writerow(dict(patch=row['patch'],frame=int(row['frame']),file=row['file'],x=ep['native_x'],y=ep['native_y'],snr=ep['peak_significance'],track_id=c['candidate_id'],is_target=0))
        write_json(out/'residuals.json',dict(negative=neg,positive=pos))
        fields=['candidate_id','ra1_deg','dec1_deg','mjd1','ra2_deg','dec2_deg','mjd2','motion_arcsec_hour','quality_score','passes_configured_gates','match_status']
        with (out/'candidates.csv').open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
            for c in candidates:w.writerow(dict(candidate_id=c['candidate_id'],ra1_deg=c['epoch1']['ra_deg'],dec1_deg=c['epoch1']['dec_deg'],mjd1=c['epoch1']['mjd'],ra2_deg=c['epoch2']['ra_deg'],dec2_deg=c['epoch2']['dec_deg'],mjd2=c['epoch2']['mjd'],**{k:c[k] for k in fields[7:]}))
        header=a.wcs.to_header();header['BUNIT']='MJy / sr';header['DATAMODE']='REAL';header['MJD1']=float(row1['t_mid_mjd']);header['MJD2']=float(row2['t_mid_mjd'])
        hdus=[fits.PrimaryHDU()]
        for name,arr in [('EPOCH1',scale*A),('EPOCH2',B),('DIFF',diff),('DIFF_VAR',var),('SIGNIF',snr),('VALID',good.astype(np.uint8)),('WAVE1',a.wave),('WAVE2',wave2)]:
            hh=header.copy();hh['BUNIT']='' if name in ('SIGNIF','VALID') else 'um' if name.startswith('WAVE') else '(MJy/sr)^2' if name=='DIFF_VAR' else 'MJy / sr'
            value=arr if name=='VALID' else np.where(good,arr,np.nan).astype(np.float32)
            hdus.append(fits.ImageHDU(value,header=hh,name=name))
        fits.HDUList(hdus).writeto(out/'comparison.fits',checksum=True)
        report.update(status='completed',negative_residuals=len(neg),positive_residuals=len(pos),
                      candidate_pairs=len(candidates),pairs_passing_gates=sum(c['passes_configured_gates'] for c in candidates),
                      saturation_pixels=[int(np.count_nonzero(f.mask&16)) for f in (a,b)],
                      validation_status='real_pair_processed; identity_and_population_metrics_not_established')
        report['result_status'] = ('two_epoch_candidate_requires_verification' if report['pairs_passing_gates'] else
            'needs_third_epoch' if any(c['flags']==['ambiguous_residual_pairing'] for c in candidates) else
            'no_eligible_residuals' if not report['eligible_negative_residuals'] or not report['eligible_positive_residuals'] else
            'no_viable_pair')
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig,axs=plt.subplots(2,2,figsize=(9,8))
        for ax,arr,title in zip(axs.flat,[scale*A,B,diff,snr],
                                ['Real epoch 1, scaled','Real epoch 2, aligned','Difference (2 - 1)','Significance (approximate)']):
            shown=np.where(good,arr,np.nan)
            if title.startswith('Real'):
                ax.imshow(np.arcsinh(shown/.05),origin='lower',cmap='gray',vmin=-1,vmax=4)
            else:
                limit=10 if title.startswith('Significance') else .2
                ax.imshow(shown,origin='lower',cmap='RdBu_r',vmin=-limit,vmax=limit)
            ax.set_title(title);ax.set_xlabel('Reference-grid x (pixels)');ax.set_ylabel('Reference-grid y (pixels)')
        fig.suptitle(row1['patch']+' | real observations; masked regions shown white')
        fig.tight_layout();fig.savefig(out/'comparison_overview.png',dpi=150);plt.close(fig)
        # Keep saturated-source positional evidence separate from signed-residual
        # detections. Never promote it into an accepted difference candidate.
        saturated_review=[]
        for i,s in enumerate(sa):
            if not (s['mask_bits']&16):continue
            for j,t in enumerate(sb):
                if not (t['mask_bits']&16):continue
                sky1=SkyCoord(s['ra_deg']*u.deg,s['dec_deg']*u.deg)
                sky2=SkyCoord(t['ra_deg']*u.deg,t['dec_deg']*u.deg)
                sep=float(sky1.separation(sky2).arcsec)
                if not cfg.min_separation_px*6.15<=sep<=cfg.max_speed_arcsec_min*dt:continue
                item=dict(candidate_id=f"{row1['patch']}_f{row1['frame']}_f{row2['frame']}_saturated_{len(saturated_review)+1:04d}",
                     epoch1=s,epoch2=t,angular_separation_arcsec=sep,
                     motion_arcsec_hour=sep/dt*60,position_angle_deg=float(sky1.position_angle(sky2).deg),
                     flags=['saturated_centroids_approximate','two_epoch_association_not_confirmed',
                            'not_a_passing_difference_detection'],match_status='not_crossmatched')
                saturated_review.append(item)
        write_json(out/'saturated_positional_review.json',saturated_review)
        report['saturated_positional_review_pairs']=len(saturated_review)
        write_json(out/'run_report.json',report)
        return report
    except Exception as exc:
        report.update(status='failed',result_status='quality_rejected' if isinstance(exc,ValueError) else 'processing_error',error=f'{type(exc).__name__}: {exc}')
        write_json(out/'run_report.json',report)
        raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--patch',default='ceres');p.add_argument('--frames',nargs=2,type=int)
    p.add_argument('--max-sources-per-frame',type=int,default=1000)
    a=p.parse_args()
    with (a.root/'tables'/f'frames_{a.patch}.csv').open(newline='') as f:rows=list(csv.DictReader(f))
    if a.frames:rows=[next(r for r in rows if int(r['frame'])==i) for i in a.frames]
    if len(rows)!=2:p.error('Choose exactly two frames with --frames OLD NEW')
    rows.sort(key=lambda r:float(r['t_mid_mjd']))
    if a.max_sources_per_frame<1:p.error('Source cap must be positive')
    print(json.dumps(process_pair(a.root,a.out,*rows,cfg=PairConfig(max_sources_per_frame=a.max_sources_per_frame)),indent=2))
