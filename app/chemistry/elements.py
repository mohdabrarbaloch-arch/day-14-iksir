"""Element data used by the chemistry engine.

Atomic weights are the IUPAC 2021 standard atomic weights (abridged to five
significant figures), which is what every cheminformatics toolkit ships. The
values below are *not* averages chosen to make a number look nice -- they are
the published constants, so a molecular weight computed here matches what you
would get from RDKit to within rounding.

`DEFAULT_VALENCE` is the valence an atom uses when deciding how many implicit
hydrogens to add. It is the standard organic-chemistry valence for the
element's neutral ground state. Aromatic atoms and charged atoms are handled
separately in the parser, because their counting rules differ.
"""

from __future__ import annotations

# IUPAC 2021 standard atomic weights.
ATOMIC_WEIGHT: dict[str, float] = {
    "H": 1.008,
    "He": 4.0026,
    "Li": 6.94,
    "Be": 9.0122,
    "B": 10.81,
    "C": 12.011,
    "N": 14.007,
    "O": 15.999,
    "F": 18.998,
    "Ne": 20.180,
    "Na": 22.990,
    "Mg": 24.305,
    "Al": 26.982,
    "Si": 28.085,
    "P": 30.974,
    "S": 32.06,
    "Cl": 35.45,
    "Ar": 39.948,
    "K": 39.098,
    "Ca": 40.078,
    "Sc": 44.956,
    "Ti": 47.867,
    "V": 50.942,
    "Cr": 51.996,
    "Mn": 54.938,
    "Fe": 55.845,
    "Co": 58.933,
    "Ni": 58.693,
    "Cu": 63.546,
    "Zn": 65.38,
    "Ga": 69.723,
    "Ge": 72.630,
    "As": 74.922,
    "Se": 78.971,
    "Br": 79.904,
    "Kr": 83.798,
    "Rb": 85.468,
    "Sr": 87.62,
    "Y": 88.906,
    "Zr": 91.224,
    "Nb": 92.906,
    "Mo": 95.95,
    "Ru": 101.07,
    "Rh": 102.906,
    "Pd": 106.42,
    "Ag": 107.868,
    "Cd": 112.414,
    "In": 114.818,
    "Sn": 118.710,
    "Sb": 121.760,
    "Te": 127.60,
    "I": 126.904,
    "Xe": 131.293,
    "Cs": 132.905,
    "Ba": 137.327,
    "La": 138.905,
    "Ce": 140.116,
    "Pr": 140.908,
    "Nd": 144.242,
    "Pm": 145.0,
    "Sm": 150.36,
    "Eu": 151.964,
    "Gd": 157.25,
    "Tb": 158.925,
    "Dy": 162.500,
    "Ho": 164.930,
    "Er": 167.259,
    "Tm": 168.934,
    "Yb": 173.045,
    "Lu": 174.967,
    "Hf": 178.49,
    "Ta": 180.948,
    "W": 183.84,
    "Re": 186.207,
    "Os": 190.23,
    "Ir": 192.217,
    "Pt": 195.084,
    "Au": 196.967,
    "Hg": 200.592,
    "Tl": 204.38,
    "Pb": 207.2,
    "Bi": 208.980,
    "Th": 232.038,
    "U": 238.029,
}

# Neutral ground-state valence used for implicit-hydrogen counting.
DEFAULT_VALENCE: dict[str, int] = {
    "B": 3,
    "C": 4,
    "N": 3,
    "O": 2,
    "P": 3,
    "S": 2,
    "F": 1,
    "Cl": 1,
    "Br": 1,
    "I": 1,
    "Si": 4,
    "Se": 2,
}

# The "organic subset" from the OpenSMILES specification: symbols that may be
# written without brackets, and which therefore receive implicit hydrogens.
ORGANIC_SUBSET: frozenset[str] = frozenset({"B", "C", "N", "O", "P", "S", "F", "Cl", "Br", "I"})

# Lowercase aromatic symbols from OpenSMILES.
AROMATIC_LOWER: dict[str, str] = {
    "b": "B",
    "c": "C",
    "n": "N",
    "o": "O",
    "p": "P",
    "s": "S",
}

# Elements that count as hydrogen-bond donors / acceptors under Lipinski's
# original rule: donors are N-H and O-H, acceptors are N and O.
H_BOND_DONOR_ELEMENTS: frozenset[str] = frozenset({"N", "O"})
H_BOND_ACCEPTOR_ELEMENTS: frozenset[str] = frozenset({"N", "O"})

# Halogens, used by the screening heuristics.
HALOGENS: frozenset[str] = frozenset({"F", "Cl", "Br", "I"})


def atomic_weight(symbol: str) -> float:
    """Return the standard atomic weight for an element symbol.

    Raises:
        KeyError: if the symbol is not in the table, so callers can report
            precisely which element is unsupported rather than silently
            substituting a made-up mass.
    """
    try:
        return ATOMIC_WEIGHT[symbol]
    except KeyError as exc:  # pragma: no cover - guarded by the parser
        raise KeyError(f"no atomic weight on file for element {symbol!r}") from exc
