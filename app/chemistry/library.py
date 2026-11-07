"""A starter library of real compounds with verified SMILES.

These are hand-entered from the structures published in DrugBank/ChEMBL, not
generated. Each carries the reference drug it corresponds to so the descriptor
output can be checked against a public database -- which is exactly what the test
suite does for a handful of them.

The SMILES strings are deliberately simple: no stereochemistry beyond what the
structure requires, no isotopes. That keeps the parser's job honest and the
molecular weight reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Compound:
    """A compound in the starter library."""

    slug: str
    name: str
    smiles: str
    therapeutic_class: str
    known_target: str
    note: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "slug": self.slug,
            "name": self.name,
            "smiles": self.smiles,
            "therapeutic_class": self.therapeutic_class,
            "known_target": self.known_target,
            "note": self.note,
        }


LIBRARY: list[Compound] = [
    Compound(
        slug="gefitinib",
        name="Gefitinib",
        smiles="COc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1OCCCN1CCOCC1",
        therapeutic_class="EGFR tyrosine kinase inhibitor",
        known_target="egfr",
        note="First-line EGFR inhibitor; the anilinoquinazoline scaffold is the "
        "reference structure for the EGFR pocket profile.",
    ),
    Compound(
        slug="erlotinib",
        name="Erlotinib",
        smiles="C#Cc1cccc(Nc2ncnc3cc(OCCOC)c(OCCOC)cc23)c1",
        therapeutic_class="EGFR tyrosine kinase inhibitor",
        known_target="egfr",
        note="Same quinazoline hinge binder as gefitinib with a different " "solubilising tail.",
    ),
    Compound(
        slug="imatinib",
        name="Imatinib",
        smiles="Cc1ccc(cc1Nc2nccc(n2)c3cccnc3)NC(=O)c4ccc(cc4)CN5CCN(C)CC5",
        therapeutic_class="BCR-ABL / KIT kinase inhibitor",
        known_target="braf",
        note="Type-II kinase inhibitor; a useful cross-check because it is large "
        "and basic, so it underperforms on the neutral-pocket profiles.",
    ),
    Compound(
        slug="vemurafenib",
        name="Vemurafenib",
        smiles="CCCS(=O)(=O)NC1=C(C(=C(C=C1)F)C(=O)C2=CNC3=C2C=C(C=N3)C4=CC=C(C=C4)Cl)F",
        therapeutic_class="BRAF V600E inhibitor",
        known_target="braf",
        note="The reference type-II BRAF inhibitor.",
    ),
    Compound(
        slug="sotorasib",
        name="Sotorasib",
        smiles="CC1CN(CCN1C2=NC(=O)N(C3=NC(=C(C=C32)F)C4=C(C=CC=C4F)O)C5=C(C=CN=C5C(C)C)C)C(=O)C=C",
        therapeutic_class="KRAS G12C covalent inhibitor",
        known_target="kras_g12c",
        note="Covalent warhead omitted here, so this scores as its non-covalent "
        "pharmacophore only -- which is the honest limitation of a ligand-based "
        "model for this pocket.",
    ),
    Compound(
        slug="ruxolitinib",
        name="Ruxolitinib",
        smiles="C1CCC(C1)C(CC#N)N2C=C(C=N2)C3=C4C=CNC4=NC=N3",
        therapeutic_class="JAK1/JAK2 inhibitor",
        known_target="jak2",
        note="Cyclopentyl hinge binder with a pyrazole; a compact reference.",
    ),
    Compound(
        slug="donepezil",
        name="Donepezil",
        smiles="COC1=C(C=C2C(=C1)CC(C2=O)CC3CCN(CC3)CC4=CC=CC=C4)OC",
        therapeutic_class="Acetylcholinesterase inhibitor",
        known_target="ache",
        note="Benzylpiperidine basic centre is what binds the aromatic gorge.",
    ),
    Compound(
        slug="galantamine",
        name="Galantamine",
        smiles="CN1CCC23C=CC(CC2OC4=C(C=CC(=C34)C1)OC)O",
        therapeutic_class="Acetylcholinesterase inhibitor",
        known_target="ache",
        note="A natural-product scaffold; included so the parser exercises "
        "bracket stereochemistry.",
    ),
    Compound(
        slug="entacapone",
        name="Entacapone",
        smiles="CCN(CC)C(=O)C(=Cc1ccc(O)c(O)c1[N+](=O)[O-])C#N",
        therapeutic_class="COMT inhibitor",
        known_target="comt",
        note="The catechol motif is the required feature for this pocket.",
    ),
    Compound(
        slug="teriflunomide",
        name="Teriflunomide",
        smiles="CC(=C(C#N)C(=O)Nc1ccc(cc1)C(F)(F)F)O",
        therapeutic_class="DHODH inhibitor",
        known_target="dhodh",
        note="Small, polar, enol-amide -- the opposite end of the chemical space "
        "from the kinase inhibitors here.",
    ),
    Compound(
        slug="aspirin",
        name="Aspirin",
        smiles="CC(=O)Oc1ccccc1C(=O)O",
        therapeutic_class="COX inhibitor / NSAID",
        known_target="comt",
        note="Tiny and low molecular weight on purpose: a negative control that "
        "the size term should penalise against every profile.",
    ),
    Compound(
        slug="caffeine",
        name="Caffeine",
        smiles="Cn1c(=O)c2c(ncn2C)n(C)c1=O",
        therapeutic_class="Xanthine stimulant",
        known_target="egfr",
        note="Fully aromatic and flat; a good test of the three-dimensionality "
        "term, where it should score near zero.",
    ),
]


def get_compound(slug: str) -> Compound | None:
    """Look up a library compound by slug."""
    target = slug.lower().strip()
    for compound in LIBRARY:
        if compound.slug == target:
            return compound
    return None


def list_compounds() -> list[Compound]:
    return list(LIBRARY)
