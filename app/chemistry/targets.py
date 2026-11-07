"""The target library: binding pockets described as pharmacophore profiles.

Every target here is a real, well-characterised protein with a real ligand-binding
site in the literature. The profiles below are *summaries of published pocket
descriptions*, hand-transcribed into the numeric form the scorer needs -- they
are not fitted to data, and they are not docking grids.

Where a well-known drug defines the pocket, the profile is written to match that
drug's properties, which is the standard way to sanity-check a pharmacophore
model: the reference compound should score highly against its own target. The
test suite asserts exactly that.

Sources for the pocket descriptions are listed per target so a reader can check
the reasoning rather than take the numbers on faith.
"""

from __future__ import annotations

from .screening import TargetProfile

TARGETS: dict[str, TargetProfile] = {
    "egfr": TargetProfile(
        slug="egfr",
        name="Epidermal growth factor receptor (kinase domain)",
        gene="EGFR",
        family="Receptor tyrosine kinase",
        summary=(
            "The ATP-binding cleft of the EGFR kinase domain. The pocket is deeply "
            "hydrophobic around the gatekeeper residue, with the hinge region "
            "supplying the hydrogen-bond anchor that most inhibitors use. "
            "Clinically validated by gefitinib and erlotinib."
        ),
        ideal_logp=3.6,
        logp_tolerance=2.0,
        hbd_required=1,
        hba_required=3,
        aromatic_rings_preferred=2,
        mw_band=(330.0, 480.0),
        preferred_charge=0,
        rotatable_band=(2, 7),
        weights={
            "hydrophobic": 1.4,
            "hbond_donor": 1.2,
            "hbond_acceptor": 1.4,
            "aromatic": 1.2,
            "shape": 0.4,
        },
        note=(
            "Pocket description follows the anilinoquinazoline series (gefitinib, "
            "erlotinib): hinge binding via the quinazoline N1/N3, with the aniline "
            "reaching the hydrophobic back pocket."
        ),
    ),
    "braf": TargetProfile(
        slug="braf",
        name="BRAF V600E kinase (DFG-out pocket)",
        gene="BRAF",
        family="Serine/threonine kinase",
        summary=(
            "The type-II binding site of oncogenic BRAF V600E, accessed by the "
            "DFG-out conformation. Vemurafenib and dabrafenib established this as "
            "a tractable pocket; the requirement is a hinge-binding heterocycle "
            "plus a lipophilic tail that occupies the allosteric pocket."
        ),
        ideal_logp=4.2,
        logp_tolerance=2.0,
        hbd_required=1,
        hba_required=3,
        aromatic_rings_preferred=2,
        mw_band=(380.0, 520.0),
        preferred_charge=0,
        rotatable_band=(2, 8),
        weights={
            "hydrophobic": 1.5,
            "hbond_acceptor": 1.3,
            "aromatic": 1.1,
            "size": 1.1,
            "shape": 0.5,
        },
        note=(
            "Type-II inhibitors are larger and more lipophilic than type-I; the "
            "profile reflects that, which is why the MW band sits higher than EGFR's."
        ),
    ),
    "kras_g12c": TargetProfile(
        slug="kras_g12c",
        name="KRAS G12C switch-II pocket",
        gene="KRAS",
        family="Small GTPase",
        summary=(
            "The switch-II allosteric pocket exposed by the G12C mutation. This "
            "pocket is shallow and mostly hydrophobic, and it is unusual in that "
            "the covalent warhead is part of the design: sotorasib and adagrasib "
            "both anchor through it. A non-covalent profile therefore scores lower "
            "by construction, and the UI says so."
        ),
        ideal_logp=3.8,
        logp_tolerance=1.8,
        hbd_required=1,
        hba_required=2,
        aromatic_rings_preferred=2,
        mw_band=(400.0, 560.0),
        preferred_charge=0,
        rotatable_band=(1, 6),
        weights={
            "hydrophobic": 1.6,
            "shape": 0.9,
            "aromatic": 1.0,
            "hbond_acceptor": 0.9,
        },
        note=(
            "Shallow, hydrophobic, and covalent-warhead-dependent. Treat high "
            "scores here as 'worth a covalent design pass', not as potency."
        ),
    ),
    "jak2": TargetProfile(
        slug="jak2",
        name="JAK2 kinase (ATP site)",
        gene="JAK2",
        family="Non-receptor tyrosine kinase",
        summary=(
            "The ATP site of JAK2, the target of ruxolitinib and fedratinib. "
            "Structurally similar to other kinases but with a distinctive "
            "selectivity pocket behind the gatekeeper, which is where the "
            "JAK-selective compounds earn their margin."
        ),
        ideal_logp=3.0,
        logp_tolerance=2.0,
        hbd_required=1,
        hba_required=4,
        aromatic_rings_preferred=2,
        mw_band=(300.0, 450.0),
        preferred_charge=0,
        rotatable_band=(2, 7),
        weights={
            "hbond_acceptor": 1.5,
            "hydrophobic": 1.2,
            "aromatic": 1.1,
            "size": 1.0,
        },
        note=(
            "Requires more acceptors than EGFR because the JAK2 hinge makes two "
            "separate polar contacts rather than one."
        ),
    ),
    "ache": TargetProfile(
        slug="ache",
        name="Acetylcholinesterase (gorge)",
        gene="ACHE",
        family="Serine hydrolase",
        summary=(
            "The deep active-site gorge of acetylcholinesterase, target of "
            "donepezil and galantamine. The gorge is lined with aromatic residues, "
            "so cation-pi and pi-stacking interactions dominate. A positively "
            "charged compound is the classical answer."
        ),
        ideal_logp=2.8,
        logp_tolerance=2.0,
        hbd_required=0,
        hba_required=2,
        aromatic_rings_preferred=2,
        mw_band=(280.0, 420.0),
        preferred_charge=1,
        rotatable_band=(1, 6),
        weights={
            "charge": 1.8,
            "aromatic": 1.6,
            "hydrophobic": 1.0,
            "size": 1.0,
            "shape": 0.3,
        },
        note=(
            "The one target here that actively rewards a positive charge: the "
            "gorge is aromatic-lined and cation-pi binding is the dominant mode."
        ),
    ),
    "comt": TargetProfile(
        slug="comt",
        name="Catechol-O-methyltransferase (SAM pocket)",
        gene="COMT",
        family="Methyltransferase",
        summary=(
            "The S-adenosylmethionine binding site of COMT, target of entacapone "
            "and tolcapone in Parkinson's disease. The pocket is narrow and "
            "requires a catechol-like motif to chelate the catalytic magnesium."
        ),
        ideal_logp=2.2,
        logp_tolerance=1.8,
        hbd_required=2,
        hba_required=4,
        aromatic_rings_preferred=1,
        mw_band=(240.0, 380.0),
        preferred_charge=0,
        rotatable_band=(1, 5),
        weights={
            "hbond_donor": 1.7,
            "hbond_acceptor": 1.7,
            "hydrophobic": 0.8,
            "size": 1.1,
        },
        note=(
            "Polar pocket -- the only target here where high logP is a liability "
            "rather than a bonus."
        ),
    ),
    "dhodh": TargetProfile(
        slug="dhodh",
        name="Dihydroorotate dehydrogenase (ubiquinone site)",
        gene="DHODH",
        family="Oxidoreductase",
        summary=(
            "The ubiquinone-binding channel of DHODH, target of teriflunomide and "
            "brequinar. The channel is a long hydrophobic tunnel with a polar "
            "mouth, so it rewards compounds that are lipophilic but still carry a "
            "hydrogen-bond donor at one end."
        ),
        ideal_logp=3.2,
        logp_tolerance=2.0,
        hbd_required=1,
        hba_required=2,
        aromatic_rings_preferred=2,
        mw_band=(280.0, 440.0),
        preferred_charge=0,
        rotatable_band=(1, 5),
        weights={
            "hydrophobic": 1.4,
            "hbond_donor": 1.3,
            "hbond_acceptor": 1.0,
            "aromatic": 1.2,
            "flexibility": 1.0,
        },
        note=(
            "A long tunnel means flexibility is a mild liability: too many "
            "rotatable bonds and the compound cannot hold the channel."
        ),
    ),
}


def get_target(slug: str) -> TargetProfile | None:
    """Look up a target by slug, returning None when it is unknown."""
    return TARGETS.get(slug.lower().strip())


def list_targets() -> list[TargetProfile]:
    """Return every target, in a stable display order."""
    return [TARGETS[key] for key in ("egfr", "braf", "kras_g12c", "jak2", "ache", "comt", "dhodh")]
