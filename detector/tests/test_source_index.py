from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from math import floor
import numpy as np
from sources import _nearby_accepted

def test_spatial_duplicate_rule_matches_full_scan():
    rng=np.random.default_rng(192)
    points=list(map(tuple,rng.uniform(-5,5,(1000,2))))
    points += [(0.,0.),(1.,0.),(np.nextafter(1.,0.),0.),(-1.,0.),(0.,1.)]
    accepted=[];cells={}
    for x,y in points:
        expected=any(np.hypot(px-x,py-y)<1 for px,py in accepted)
        assert _nearby_accepted(cells,x,y)==expected
        if not expected:
            accepted.append((x,y));cells.setdefault((floor(x),floor(y)),[]).append((x,y))

def test_spatial_duplicate_boundary_and_diagonal():
    cells={(0,0):[(0.,0.)]}
    assert not _nearby_accepted(cells,1.,0.)
    assert _nearby_accepted(cells,np.nextafter(1.,0.),0.)
    assert not _nearby_accepted(cells,.8,.8)
    assert _nearby_accepted(cells,-.6,-.6)
