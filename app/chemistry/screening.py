"""The screening engine: score compounds against a target's pocket profile.

It matters that this is described accurately, because a "drug discovery
platform" that quietly implies molecular docking would be dishonest.

This engine does **ligand-based, property-driven triage**. Each target carries a
*pharmacophore profile*: a small set of weighted requirements derived from the
literature description of that pocket (hydrophobic contact fraction, hydrogen
bond donors and acceptors needed, aromatic stacking preference, an ideal
molecular-weight band, preferred formal charge). A compound is scored by how well
its computed descriptors satisfy those requirements, and every point of the score
is attributable to a named term.

That makes it useful for what triage is actually for: cutting a list of ten
thousand structures down to the few hundred worth running through a real
docking or experimental assay. It does **not** predict binding affinity, and the
API returns a `method` field saying exactly that.

Scoring model
-------------
Each term returns a value in [0, 1] and carries a weight. The final score is the
weighted mean, scaled to 0-100:

    score = 100 * sum(w_i * v_i) / sum(w_i)

Terms:

* `hydrophobic`     -- agreement between compound logP and the pocket's ideal.
                        Peak at the ideal, falloff outward on a fixed scale.
* `hbond_donor`     -- donor count against the pocket's requirement, saturating.
* `hbond_acceptor`  -- acceptor count against the pocket's requirement.
* `aromatic`        -- aromatic ring count against the pocket's preference.
* `size`            -- molecular weight inside the pocket's band.
* `shape`           -- fraction of sp3 carbons, i.e. how three-dimensional the
                        compound is. Flat, fully aromatic scaffolds score low
                        where the pocket asks for depth.
* `charge`          -- formal charge agreement.
* `flexibility`     -- rotatable bonds inside a workable range (not rigid, not
                        floppy).

Penalties are applied after the weighted mean, not folded into it, so the report
can show "this scored 71, then lost 15 to a metabolic liability" rather than
hiding the deduction inside a weight.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .descriptors import Descriptors, lipinski_violations

# A compound whose score clears this bar is flagged for a wet-lab look.
HIT_THRESHOLD = 60.0
# Below this the compound is deprioritised rather than reported as a near miss.
WEAK_THRESHOLD = 40.0


@dataclass(frozen=True)
class Term:
    """One scored contribution, keeping its arithmetic visible."""

    name: str
    value: float  # 0..1
    weight: float
    detail: str

    @property
    def points(self) -> float:
        return self.value * self.weight

    def to_dict(self) -> dict[str, str | float]:
        return {
            "name": self.name,
            "value": round(self.value, 4),
            "weight": self.weight,
            "points": round(self.points, 3),
            "detail": self.detail,
        }


@dataclass(frozen=True)
class Penalty:
    """A named deduction applied after the weighted mean."""

    reason: str
    points: float
    detail: str

    def to_dict(self) -> dict[str, str | float]:
        return {
            "reason": self.reason,
            "points": round(self.points, 2),
            "detail": self.detail,
        }


@dataclass(frozen=True)
class TargetProfile:
    """The pharmacophore requirements of a binding pocket.

    Every field is a property of the pocket, not of any compound, so the same
    profile scores an entire library consistently.
    """

    slug: str
    name: str
    gene: str
    family: str
    summary: str
    ideal_logp: float
    logp_tolerance: float
    hbd_required: int
    hba_required: int
    aromatic_rings_preferred: int
    mw_band: tuple[float, float]
    preferred_charge: int
    rotatable_band: tuple[int, int]
    # Relative importance of each term. Weights are normalised at scoring time,
    # so they can be read as "how much this pocket cares about X".
    weights: dict[str, float]
    # Compounds outside these are reported but flagged rather than silently cut.
    note: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "slug": self.slug,
            "name": self.name,
            "gene": self.gene,
            "family": self.family,
            "summary": self.summary,
            "ideal_logp": self.ideal_logp,
            "logp_tolerance": self.logp_tolerance,
            "hbd_required": self.hbd_required,
            "hba_required": self.hba_required,
            "aromatic_rings_preferred": self.aromatic_rings_preferred,
            "mw_band": list(self.mw_band),
            "preferred_charge": self.preferred_charge,
            "rotatable_band": list(self.rotatable_band),
            "weights": dict(self.weights),
            "note": self.note,
        }


DEFAULT_WEIGHTS: dict[str, float] = {
    "hydrophobic": 1.2,
    "hbond_donor": 1.0,
    "hbond_acceptor": 1.0,
    "aromatic": 0.9,
    "size": 1.1,
    "shape": 0.6,
    "charge": 0.5,
    "flexibility": 0.7,
}


@dataclass
class ScreeningResult:
    """One compound scored against one target, with the full reasoning trace."""

    compound_name: str
    smiles: str
    descriptors: Descriptors
    target: TargetProfile
    terms: list[Term] = field(default_factory=list)
    penalties: list[Penalty] = field(default_factory=list)
    raw_score: float = 0.0
    final_score: float = 0.0
    verdict: str = "weak"
    lipinski_violations: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "compound_name": self.compound_name,
            "smiles": self.smiles,
            "target": self.target.slug,
            "target_name": self.target.name,
            "descriptors": self.descriptors.to_dict(),
            "terms": [t.to_dict() for t in self.terms],
            "penalties": [p.to_dict() for p in self.penalties],
            "raw_score": round(self.raw_score, 2),
            "final_score": round(self.final_score, 2),
            "verdict": self.verdict,
            "lipinski_violations": list(self.lipinski_violations),
            "notes": list(self.notes),
            "method": "ligand-based property triage; not a docking or affinity prediction",
        }


def _band_score(value: float, low: float, high: float, softness: float) -> float:
    """1 inside [low, high], falling off linearly over `softness` outside it."""
    if low <= value <= high:
        return 1.0
    gap = low - value if value < low else value - high
    if softness <= 0:
        return 0.0
    return max(0.0, 1.0 - gap / softness)


def _peak_score(value: float, ideal: float, tolerance: float) -> float:
    """1 at `ideal`, decreasing to 0 at `ideal +/- tolerance`."""
    if tolerance <= 0:
        return 1.0 if value == ideal else 0.0
    return max(0.0, 1.0 - abs(value - ideal) / tolerance)


def _saturating_match(value: float, required: float) -> float:
    """Score how well a count satisfies a requirement.

    Meeting or exceeding the requirement scores 1. Falling short scales linearly
    down to 0. Exceeding by a lot is not penalised here -- overshooting is
    handled by the lipinski/penalty layer, which is where it belongs.
    """
    if required <= 0:
        # The pocket wants none: having none is perfect, having several is not.
        return 1.0 if value == 0 else max(0.0, 1.0 - value / 4.0)
    return min(1.0, value / required)


def score_compound(
    compound_name: str,
    smiles: str,
    descriptors: Descriptors,
    target: TargetProfile,
) -> ScreeningResult:
    """Score one compound against one target, with every term explained."""
    weights = {**DEFAULT_WEIGHTS, **target.weights}
    terms: list[Term] = []

    # -- hydrophobic contact ------------------------------------------------
    hydro = _peak_score(descriptors.clogp, target.ideal_logp, target.logp_tolerance)
    terms.append(
        Term(
            "hydrophobic",
            hydro,
            weights["hydrophobic"],
            f"cLogP {descriptors.clogp:.2f} vs pocket ideal {target.ideal_logp:.1f} "
            f"(+/-{target.logp_tolerance:.1f})",
        )
    )

    # -- hydrogen bonding ---------------------------------------------------
    donor = _saturating_match(descriptors.h_bond_donors, target.hbd_required)
    terms.append(
        Term(
            "hbond_donor",
            donor,
            weights["hbond_donor"],
            f"{descriptors.h_bond_donors} donor(s) vs {target.hbd_required} required",
        )
    )

    acceptor = _saturating_match(descriptors.h_bond_acceptors, target.hba_required)
    terms.append(
        Term(
            "hbond_acceptor",
            acceptor,
            weights["hbond_acceptor"],
            f"{descriptors.h_bond_acceptors} acceptor(s) vs {target.hba_required} required",
        )
    )

    # -- aromatic stacking --------------------------------------------------
    aromatic = _peak_score(
        descriptors.aromatic_ring_count,
        target.aromatic_rings_preferred,
        max(1.0, target.aromatic_rings_preferred),  # one-ring tolerance
    )
    terms.append(
        Term(
            "aromatic",
            aromatic,
            weights["aromatic"],
            f"{descriptors.aromatic_ring_count} aromatic ring(s) vs "
            f"{target.aromatic_rings_preferred} preferred",
        )
    )

    # -- size ---------------------------------------------------------------
    low, high = target.mw_band
    size = _band_score(descriptors.molecular_weight, low, high, softness=max(60.0, high * 0.25))
    terms.append(
        Term(
            "size",
            size,
            weights["size"],
            f"MW {descriptors.molecular_weight:.1f} vs band {low:.0f}-{high:.0f}",
        )
    )

    # -- three-dimensionality ----------------------------------------------
    # A pocket that wants depth is poorly served by a flat aromatic plate.
    shape = min(1.0, descriptors.fraction_csp3 / 0.5) if descriptors.fraction_csp3 else 0.0
    terms.append(
        Term(
            "shape",
            shape,
            weights["shape"],
            f"fraction sp3 {descriptors.fraction_csp3:.2f} (1.0 at >=0.50)",
        )
    )

    # -- charge -------------------------------------------------------------
    charge = 1.0 if descriptors.formal_charge == target.preferred_charge else 0.35
    terms.append(
        Term(
            "charge",
            charge,
            weights["charge"],
            f"formal charge {descriptors.formal_charge:+d} vs "
            f"{target.preferred_charge:+d} preferred",
        )
    )

    # -- flexibility --------------------------------------------------------
    rot_low, rot_high = target.rotatable_band
    flex = _band_score(
        descriptors.rotatable_bonds, rot_low, rot_high, softness=max(4.0, rot_high * 0.5)
    )
    terms.append(
        Term(
            "flexibility",
            flex,
            weights["flexibility"],
            f"{descriptors.rotatable_bonds} rotatable bond(s) vs band " f"{rot_low}-{rot_high}",
        )
    )

    # -- weighted mean ------------------------------------------------------
    total_weight = sum(t.weight for t in terms)
    raw = 100.0 * sum(t.points for t in terms) / total_weight if total_weight else 0.0

    # -- penalties ----------------------------------------------------------
    penalties: list[Penalty] = []
    notes: list[str] = []
    violations = lipinski_violations(descriptors)

    for violation in violations:
        penalties.append(
            Penalty(
                reason=f"rule_of_five:{violation}",
                points=6.0,
                detail=f"{violation} is outside Lipinski's Rule of Five",
            )
        )

    if descriptors.tpsa > 140.0:
        penalties.append(
            Penalty(
                reason="tpsa_high",
                points=5.0,
                detail=f"TPSA {descriptors.tpsa:.1f} A^2 exceeds Veber's 140 A^2 guidance",
            )
        )

    if descriptors.max_ring_size >= 8:
        penalties.append(
            Penalty(
                reason="large_ring",
                points=4.0,
                detail=f"largest ring has {descriptors.max_ring_size} atoms, which is "
                "usually strained",
            )
        )

    # Metabolic soft spots: many bare sp3 carbons with no heteroatom nearby are
    # the usual first place a CYP enzyme attacks.
    if descriptors.fraction_csp3 > 0.75 and descriptors.heteroatom_count <= 1:
        penalties.append(
            Penalty(
                reason="metabolic_soft_spot",
                points=5.0,
                detail="mostly saturated carbon with almost no heteroatom -- likely "
                "fast CYP turnover",
            )
        )

    if descriptors.molecular_weight > 600:
        notes.append(
            "Above 600 Da: large for an oral small molecule, though acceptable for " "other routes."
        )

    final = max(0.0, raw - sum(p.points for p in penalties))

    if final >= HIT_THRESHOLD:
        verdict = "hit"
    elif final >= WEAK_THRESHOLD:
        verdict = "borderline"
    else:
        verdict = "weak"

    return ScreeningResult(
        compound_name=compound_name,
        smiles=smiles,
        descriptors=descriptors,
        target=target,
        terms=terms,
        penalties=penalties,
        raw_score=raw,
        final_score=final,
        verdict=verdict,
        lipinski_violations=violations,
        notes=notes,
    )


def rank_results(results: list[ScreeningResult]) -> list[ScreeningResult]:
    """Sort by final score, breaking ties on the more conservative compound.

    Ties are broken by lower molecular weight then fewer rotatable bonds, so the
    ordering is total and reproducible rather than dependent on input order.
    """
    return sorted(
        results,
        key=lambda r: (
            -r.final_score,
            r.descriptors.molecular_weight,
            r.descriptors.rotatable_bonds,
        ),
    )
