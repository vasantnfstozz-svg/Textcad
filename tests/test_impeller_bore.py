"""impeller.py's shaft bore is a hole, not a promise.

`impeller._hub` drills the bore with `blocks.with_center_hole` and
`impeller.build` fuses the blades on AFTERWARDS — the exact ordering that was
round one's P0 in `meanline.py`: blade material reaching inside the bore fills
the hole back in, and the spec `impeller.build` verifies against (symmetry,
n_solids, require_manifold) passes every line with the bore full.

The shipped defaults clear it (the blade starts at `hub_top_radius` 9.0 against
a 6.0 bore), so nothing was wrong today — the module's whole point is that
"change BLADE_COUNT (or any parameter) and the whole thing re-runs and
re-verifies", and two of those parameters walk straight into it.

MEASURED 2026-09-17 (probes/impeller_bore_order_probe.py), whole wheels built
through `impeller.build`, before the fix and after:

    parameters              before                      after
    shipped                 30,902.254 mm3, 0.000 in    identical, 0.000 in
    hub_top_radius 3.0      26,142.111 mm3, 1,018.427 mm3 inside the 12 mm bore
                            ok=True, one watertight solid, 7-fold symmetric
                                                        25,123.684, 0.000 in
    bore_radius 12.0        22,591.756 mm3, 1,294.076 mm3 inside the 24 mm bore
                            ok=True, one watertight solid, 7-fold symmetric
                                                        21,297.680, 0.000 in
"""
import pytest
from build123d import Cylinder

import impeller


def _plug(p):
    return Cylinder(radius=p.bore_radius, height=8.0 * p.hub_height)


PLUGGED = [
    ("a hub nose narrower than the bore",
     dict(hub_top_radius=3.0, blade_height_hub=18.0), 1018.427),
    ("a wider shaft", dict(bore_radius=12.0), 1294.076),
]


@pytest.mark.parametrize("name,kw,before", PLUGGED,
                         ids=[s[0].replace(" ", "_") for s in PLUGGED])
def test_a_blade_that_reaches_the_shaft_bore_is_cut_back(name, kw, before):
    p = impeller.ImpellerParams(**kw)
    blade = impeller._one_blade(p)
    assert blade.volume > 0, f"{name}: the cut emptied the blade"
    assert len(blade.solids()) == 1, f"{name}: the cut severed the blade"
    left = blade & _plug(p)
    vol = left.volume if left is not None else 0.0
    assert vol < 1e-9, (f"{name}: {vol:.3f} mm3 of blade inside the shaft "
                        f"bore (was {before} mm3 per blade group before)")
    assert before > 0


def test_the_shipped_impeller_is_untouched_to_the_last_digit():
    """A guard that changes correct geometry is the worse sin. The shipped
    blade starts at 9.0 mm against a 6.0 mm bore, so the cut must remove
    nothing — and the whole wheel measured 30,902.254 mm3, 39 faces, one
    watertight solid and 7-fold symmetric both before and after
    (probes/impeller_bore_order_probe.py)."""
    p = impeller.ImpellerParams()
    blade = impeller._one_blade(p)
    left = blade & _plug(p)
    assert (left.volume if left is not None else 0.0) < 1e-9, \
        "the shipped blade already clears its bore; this test proves nothing"
    assert blade.volume == pytest.approx(1488.0, rel=1e-9)


# ROUND FOUR: the other half of that cut — it may not SEVER a blade either.
# A bore that leaves two pieces would make the wheel 14 solids instead of one,
# and `impeller.build`'s spec (n_solids=1) would call it a failure with no
# sentence saying why. It cannot happen, and this is why: the cylinder is
# centred on the axis and the whole blade lies outside it, so what it takes is
# always the blade's inner END. Measured at every radius below
# (probes/impeller_round4_sever.py), with the volume left of a 1,488 mm3 blade.
BORES = [(2.0, 1488.000), (6.0, 1488.000), (9.0, 1488.000), (12.0, 1303.132),
         (20.0, 836.270), (30.0, 360.151), (39.0, 31.782), (39.9, 4.1404),
         (40.05, 0.29173)]


@pytest.mark.parametrize("bore,left", BORES, ids=[str(b[0]) for b in BORES])
def test_no_shaft_bore_can_sever_a_blade(bore, left):
    p = impeller.ImpellerParams(bore_radius=bore)
    blade = impeller._one_blade(p)
    assert len(blade.solids()) == 1, f"bore {bore} severed the blade"
    assert blade.volume == pytest.approx(left, rel=1e-4), bore
    # and past the tip radius there is simply nothing left — the hub is an
    # empty solid long before that (bore 22.0), and the build says so
    gone = impeller._one_blade(impeller.ImpellerParams(bore_radius=41.0))
    assert not gone.solids()
