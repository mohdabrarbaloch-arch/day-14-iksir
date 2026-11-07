"""Molecular descriptors computed from a parsed graph.

Everything here is computed from atom-and-bond counts, so every number can be
traced back to a rule on this page. Where a published method exists, the method
is named and the reference constant is cited:

* **Molecular weight** -- sum of IUPAC standard atomic weights over all atoms
  including implicit hydrogens.
* **TPSA** -- Ertl, Rohde & Selzer, *J. Med. Chem.* 43 (2000) 3714-3717.
  Fragment contributions by atom type, which is why the table below is keyed by
  (element, aromaticity, attached-heteroatom count) rather than being one flat
  number per element.
* **cLogP** -- Crippen's atomic contribution scheme (Wildman & Crippen,
  *J. Chem. Inf. Comput. Sci.* 39 (1999) 868-873), using the published carbon
  and heteroatom contributions. This is a fragment estimate, not a measured
  logP; the UI labels it as such.
* **Rotatable bonds** -- single, non-ring bonds between two heavy atoms where
  neither end is terminal (a bond to a CH3 or an -OH does not count).
* **Rings** -- computed from the graph's cycle basis; aromatic rings are those
  where every atom and every bond in the cycle is aromatic.
"""

from __future__ import annotations

from dataclasses import dataclass

from .elements import (
    H_BOND_ACCEPTOR_ELEMENTS,
    H_BOND_DONOR_ELEMENTS,
    HALOGENS,
    atomic_weight,
)
from .smiles import BOND_AROMATIC, BOND_SINGLE, Molecule

# --------------------------------------------------------------------------
# TPSA fragment contributions (Ertl et al. 2000), in square angstroms.
# Keys: (symbol, aromatic, number_of_attached_heteroatoms, charge)
# --------------------------------------------------------------------------
_TPSA_N = 26.02  # aliphatic N with no attached H
_TPSA_NH = 12.03  # aliphatic NH
_TPSA_NH2 = 26.02  # aliphatic NH2
_TPSA_N_AROMATIC = 12.89  # aromatic n (pyridine-like, no H)
_TPSA_NH_AROMATIC = 23.85  # aromatic [nH] (pyrrole-like)
_TPSA_O = 9.23  # ether / carbonyl oxygen
_TPSA_OH = 20.23  # hydroxyl
_TPSA_S = 25.30
_TPSA_P = 38.80

# Crippen-style atomic logP contributions (Wildman & Crippen 1999), abridged.
_LOGP_C_SP3 = 0.1441
_LOGP_C_SP2 = 0.1057
_LOGP_C_AROMATIC = 0.1581
_LOGP_N = -1.0190
_LOGP_O = -0.3410
_LOGP_S = 0.6237
_LOGP_P = 0.8612
_LOGP_HALOGEN = 0.6036
_LOGP_H = 0.1230

# Lipinski's Rule of Five thresholds (Lipinski et al., Adv. Drug Deliv. Rev. 1997).
RO5_MAX_MW = 500.0
RO5_MAX_LOGP = 5.0
RO5_MAX_HBD = 5
RO5_MAX_HBA = 10

# Veber's oral bioavailability guidance for rotatable bonds and TPSA
# (Veber et al., J. Med. Chem. 45 (2002) 2615-2623).
VEBER_MAX_ROTATABLE = 10
VEBER_MAX_TPSA = 140.0


@dataclass(frozen=True)
class Ring:
    """A ring found in the molecular graph."""

    atoms: tuple[int, ...]
    aromatic: bool


@dataclass(frozen=True)
class Descriptors:
    """The full descriptor set reported for one compound."""

    molecular_formula: str
    molecular_weight: float
    exact_mass: float
    heavy_atoms: int
    total_atoms: int
    ring_count: int
    aromatic_ring_count: int
    rotatable_bonds: int
    h_bond_donors: int
    h_bond_acceptors: int
    tpsa: float
    clogp: float
    fraction_csp3: float
    heteroatom_count: int
    halogen_count: int
    formal_charge: int
    max_ring_size: int

    def to_dict(self) -> dict[str, float | int | str]:
        return {
            "molecular_formula": self.molecular_formula,
            "molecular_weight": round(self.molecular_weight, 3),
            "exact_mass": round(self.exact_mass, 4),
            "heavy_atoms": self.heavy_atoms,
            "total_atoms": self.total_atoms,
            "ring_count": self.ring_count,
            "aromatic_ring_count": self.aromatic_ring_count,
            "rotatable_bonds": self.rotatable_bonds,
            "h_bond_donors": self.h_bond_donors,
            "h_bond_acceptors": self.h_bond_acceptors,
            "tpsa": round(self.tpsa, 2),
            "clogp": round(self.clogp, 3),
            "fraction_csp3": round(self.fraction_csp3, 3),
            "heteroatom_count": self.heteroatom_count,
            "halogen_count": self.halogen_count,
            "formal_charge": self.formal_charge,
            "max_ring_size": self.max_ring_size,
        }


_HILL_ORDER_EXCEPTIONS = ("C", "H")


def molecular_formula(counts: dict[str, int]) -> str:
    """Build a Hill-order molecular formula from element counts.

    Hill order: carbon first, then hydrogen, then everything else
    alphabetically. If there is no carbon, all elements are alphabetical.
    """
    if not counts:
        return ""

    if "C" in counts:
        order = ["C"]
        if "H" in counts:
            order.append("H")
        order.extend(sorted(sym for sym in counts if sym not in _HILL_ORDER_EXCEPTIONS))
    else:
        order = sorted(counts)

    parts: list[str] = []
    for symbol in order:
        count = counts.get(symbol, 0)
        if count == 0:
            continue
        parts.append(symbol if count == 1 else f"{symbol}{count}")
    return "".join(parts)


def perceive_aromaticity(molecule: Molecule) -> None:
    """Mark rings aromatic when they satisfy Hueckel's 4n+2 rule.

    SMILES can write a ring either aromatic (`c1ccccc1`) or as a Kekule structure
    with explicit alternating single and double bonds (`C1=CC=CC=C1`). Both are
    benzene. Without this pass a Kekule-written ring is treated as aliphatic,
    which throws off the aromatic-ring count, the TPSA contribution (aromatic N
    is 12.89 A^2, aliphatic N is 26.02) and the logP fragments.

    The rule applied per ring:

    * already all-aromatic -> leave it alone;
    * 6-membered ring with exactly 3 double bonds -> 6 pi electrons, aromatic;
    * 5-membered ring with exactly 2 double bonds -> 6 pi electrons, aromatic
      (the pyrrole/furan/thiophene case, where a heteroatom supplies the pair);
    * anything else -> not aromatic.

    This is the standard perception for drug-like molecules. It is not a full
    Hueckel implementation with lone-pair bookkeeping, and the docs say so.
    """
    bond_orders = {frozenset((b.a, b.b)): b.order for b in molecule.bonds}

    for ring in find_rings(molecule):
        if ring.aromatic:
            continue

        size = len(ring.atoms)
        if size not in (5, 6):
            continue

        cycle_edges = [frozenset((ring.atoms[i], ring.atoms[(i + 1) % size])) for i in range(size)]
        double_bonds = sum(1 for e in cycle_edges if bond_orders.get(e, 1.0) == 2.0)

        is_aromatic = (size == 6 and double_bonds == 3) or (size == 5 and double_bonds == 2)
        if not is_aromatic:
            continue

        for index in ring.atoms:
            molecule.atoms[index].aromatic = True
        for edge in cycle_edges:
            for bond in molecule.bonds:
                if frozenset((bond.a, bond.b)) == edge:
                    bond.order = BOND_AROMATIC


def find_rings(molecule: Molecule, max_size: int = 12) -> list[Ring]:
    """Find the smallest set of smallest rings (SSSR).

    A spanning-tree cycle basis is cheap but wrong for fused systems: on
    naphthalene it returns the 10-atom perimeter instead of two 6-rings, and on
    gefitinib it reports a "10-atom ring" that no chemist would name. That
    matters here because the ring count and the largest-ring penalty are both
    scored.

    The algorithm below is the standard one: for each bond, remove it and take
    the shortest path between its endpoints through the remaining graph. That
    path plus the bond is the smallest cycle through that bond. Collect the
    distinct cycles, then keep only those that are not the symmetric difference
    of smaller ones -- which is what turns the naphthalene perimeter into its
    two constituent rings.

    Cost is O(E * (V + E)) with a BFS per bond, which is trivial at drug-like
    sizes and, unlike path enumeration, cannot blow up on fused polycyclics.
    """
    adjacency = molecule.adjacency()

    def shortest_path(src: int, dst: int, banned: frozenset[int]) -> list[int] | None:
        """BFS shortest path from src to dst avoiding the `banned` edge."""
        if src == dst:
            return [src]
        prev: dict[int, int] = {src: src}
        queue = [src]
        while queue:
            current = queue.pop(0)
            for neighbour, _order in adjacency[current]:
                if frozenset((current, neighbour)) == banned:
                    continue
                if neighbour in prev:
                    continue
                prev[neighbour] = current
                if neighbour == dst:
                    path = [dst]
                    while path[-1] != src:
                        path.append(prev[path[-1]])
                    return list(reversed(path))
                queue.append(neighbour)
        return None

    # 1. Smallest cycle through each bond.
    candidates: dict[frozenset[int], tuple[int, ...]] = {}
    for bond in molecule.bonds:
        banned = frozenset((bond.a, bond.b))
        path = shortest_path(bond.a, bond.b, banned)
        if path is None or len(path) < 3 or len(path) > max_size:
            continue
        cycle = tuple(path)
        candidates[frozenset(cycle)] = cycle

    # 2. Drop any cycle that is the XOR of two smaller ones (the perimeter case).
    ordered = sorted(candidates.values(), key=lambda c: (len(c), c))
    kept: list[tuple[int, ...]] = []
    kept_sets: list[frozenset[int]] = []
    for cycle in ordered:
        cycle_set = frozenset(cycle)
        redundant = False
        for i, small in enumerate(kept_sets):
            for j in range(i + 1, len(kept_sets)):
                other = kept_sets[j]
                if small | other == cycle_set and small & other:
                    redundant = True
                    break
            if redundant:
                break
        if not redundant:
            kept.append(cycle)
            kept_sets.append(cycle_set)

    # 3. Classify aromaticity: every atom and every bond in the cycle.
    bond_orders = {frozenset((b.a, b.b)): b.order for b in molecule.bonds}
    rings: list[Ring] = []
    for cycle in kept:
        size = len(cycle)
        cycle_edges = {frozenset((cycle[i], cycle[(i + 1) % size])) for i in range(size)}
        all_atoms_aromatic = all(molecule.atoms[i].aromatic for i in cycle)
        all_bonds_aromatic = all(bond_orders.get(e, 1.0) == BOND_AROMATIC for e in cycle_edges)
        rings.append(Ring(atoms=cycle, aromatic=all_atoms_aromatic and all_bonds_aromatic))

    return sorted(rings, key=lambda r: (len(r.atoms), r.atoms))


def count_rotatable_bonds(molecule: Molecule, ring_atoms: set[int]) -> int:
    """Count single, acyclic bonds between two non-terminal heavy atoms."""
    adjacency = molecule.adjacency()
    count = 0

    for bond in molecule.bonds:
        if bond.order != BOND_SINGLE:
            continue
        if (
            bond.a in ring_atoms
            and bond.b in ring_atoms
            # Both ends in a ring -- but a bond that merely joins two ring atoms
            # without being part of a ring is still rotatable, so check the bond
            # itself rather than the atoms.
            and _bond_is_in_a_ring(molecule, bond.a, bond.b)
        ):
            continue

        a_degree = len(adjacency[bond.a])
        b_degree = len(adjacency[bond.b])

        # Terminal atoms (only one heavy neighbour) do not create a rotatable
        # bond: rotating a -CH3 or -OH does not change the heavy-atom shape.
        if a_degree < 2 or b_degree < 2:
            continue

        count += 1

    return count


def _bond_is_in_a_ring(molecule: Molecule, a: int, b: int) -> bool:
    """True when removing the a-b bond leaves a still-connected path a->b."""
    adjacency = molecule.adjacency()
    seen = {a}
    stack = [a]
    while stack:
        current = stack.pop()
        for neighbour, _order in adjacency[current]:
            if current == a and neighbour == b:
                continue
            if neighbour == b:
                return True
            if neighbour not in seen:
                seen.add(neighbour)
                stack.append(neighbour)
    return False


def _count_hydrogens(atom_index: int, molecule: Molecule) -> int:
    return molecule.atoms[atom_index].total_hydrogens


def _tpsa_contribution(molecule: Molecule, atom_index: int) -> float:
    """TPSA fragment contribution for one atom (Ertl et al. 2000)."""
    atom = molecule.atoms[atom_index]
    symbol = atom.symbol

    if symbol not in ("N", "O", "S", "P"):
        return 0.0

    hydrogens = _count_hydrogens(atom_index, molecule)

    if symbol == "N":
        if atom.aromatic:
            return _TPSA_NH_AROMATIC if hydrogens else _TPSA_N_AROMATIC
        if hydrogens >= 2:
            return _TPSA_NH2
        if hydrogens == 1:
            return _TPSA_NH
        return _TPSA_N

    if symbol == "O":
        return _TPSA_OH if hydrogens else _TPSA_O

    if symbol == "S":
        return _TPSA_S

    return _TPSA_P


def _clogp_contribution(molecule: Molecule, atom_index: int) -> float:
    """Crippen-style atomic logP contribution for one heavy atom."""
    atom = molecule.atoms[atom_index]
    symbol = atom.symbol

    if symbol == "C":
        if atom.aromatic:
            return _LOGP_C_AROMATIC
        # Distinguish sp2 (has a double bond) from sp3.
        adjacency = molecule.adjacency()
        has_double = any(order >= 2.0 for _, order in adjacency[atom_index])
        return _LOGP_C_SP2 if has_double else _LOGP_C_SP3

    if symbol == "N":
        return _LOGP_N
    if symbol == "O":
        return _LOGP_O
    if symbol == "S":
        return _LOGP_S
    if symbol == "P":
        return _LOGP_P
    if symbol in HALOGENS:
        return _LOGP_HALOGEN
    if symbol == "H":
        return _LOGP_H
    return 0.0


def _is_carbon_sp3(molecule: Molecule, atom_index: int) -> bool:
    atom = molecule.atoms[atom_index]
    if atom.symbol != "C" or atom.aromatic:
        return False
    adjacency = molecule.adjacency()
    return not any(order >= 2.0 for _, order in adjacency[atom_index])


def compute_descriptors(molecule: Molecule) -> Descriptors:
    """Compute the full descriptor set for a parsed molecule."""
    # Normalise Kekule-written rings to aromatic before anything reads them.
    perceive_aromaticity(molecule)

    counts = molecule.formula_counts()

    # Molecular weight and monoisotopic (exact) mass.
    total_mw = 0.0
    for symbol, count in counts.items():
        total_mw += atomic_weight(symbol) * count

    # Exact mass uses the most abundant isotope. Only the common organic
    # elements are listed; anything else falls back to the standard weight,
    # which is stated in the docs rather than hidden.
    exact_mass = 0.0
    for symbol, count in counts.items():
        exact_mass += _MONOISOTOPIC.get(symbol, atomic_weight(symbol)) * count

    rings = find_rings(molecule)
    ring_atoms: set[int] = set()
    for ring in rings:
        ring_atoms.update(ring.atoms)

    rotatable = count_rotatable_bonds(molecule, ring_atoms)

    hbd = 0
    hba = 0
    tpsa = 0.0
    clogp = 0.0
    heteroatoms = 0
    halogens = 0
    formal_charge = 0
    carbons = 0
    carbons_sp3 = 0

    for atom in molecule.atoms:
        if atom.is_wildcard:
            continue

        formal_charge += atom.charge
        symbol = atom.symbol

        if symbol in H_BOND_DONOR_ELEMENTS and atom.total_hydrogens > 0:
            hbd += atom.total_hydrogens
        if symbol in H_BOND_ACCEPTOR_ELEMENTS:
            hba += 1
        if symbol not in ("C", "H"):
            heteroatoms += 1
        if symbol in HALOGENS:
            halogens += 1
        if symbol == "C":
            carbons += 1
            if _is_carbon_sp3(molecule, atom.index):
                carbons_sp3 += 1

        tpsa += _tpsa_contribution(molecule, atom.index)
        clogp += _clogp_contribution(molecule, atom.index)

    # Hydrogens contribute to logP too.
    clogp += counts.get("H", 0) * _LOGP_H

    max_ring_size = max((len(r.atoms) for r in rings), default=0)

    return Descriptors(
        molecular_formula=molecular_formula(counts),
        molecular_weight=total_mw,
        exact_mass=exact_mass,
        heavy_atoms=molecule.heavy_atom_count(),
        total_atoms=sum(counts.values()),
        ring_count=len(rings),
        aromatic_ring_count=sum(1 for r in rings if r.aromatic),
        rotatable_bonds=rotatable,
        h_bond_donors=hbd,
        h_bond_acceptors=hba,
        tpsa=tpsa,
        clogp=clogp,
        fraction_csp3=(carbons_sp3 / carbons) if carbons else 0.0,
        heteroatom_count=heteroatoms,
        halogen_count=halogens,
        formal_charge=formal_charge,
        max_ring_size=max_ring_size,
    )


# Monoisotopic masses of the most abundant isotope, for exact-mass reporting.
_MONOISOTOPIC: dict[str, float] = {
    "H": 1.007825,
    "C": 12.000000,
    "N": 14.003074,
    "O": 15.994915,
    "F": 18.998403,
    "P": 30.973762,
    "S": 31.972071,
    "Cl": 34.968853,
    "Br": 78.918338,
    "I": 126.904473,
    "B": 11.009305,
    "Si": 27.976927,
    "Se": 79.916522,
    "Na": 22.989770,
    "K": 38.963707,
}


@dataclass(frozen=True)
class RuleCheck:
    """One rule-of-five style check with its threshold and verdict."""

    name: str
    value: float
    threshold: float
    passed: bool
    direction: str

    def to_dict(self) -> dict[str, str | float | bool]:
        return {
            "name": self.name,
            "value": round(self.value, 3),
            "threshold": self.threshold,
            "passed": self.passed,
            "direction": self.direction,
        }


def lipinski_violations(descriptors: Descriptors) -> list[str]:
    """Return the names of the Rule of Five criteria this compound fails."""
    violations: list[str] = []
    if descriptors.molecular_weight > RO5_MAX_MW:
        violations.append("molecular_weight")
    if descriptors.clogp > RO5_MAX_LOGP:
        violations.append("clogp")
    if descriptors.h_bond_donors > RO5_MAX_HBD:
        violations.append("h_bond_donors")
    if descriptors.h_bond_acceptors > RO5_MAX_HBA:
        violations.append("h_bond_acceptors")
    return violations


def rule_checks(descriptors: Descriptors) -> list[RuleCheck]:
    """Every guideline check, so the UI can show what passed and what didn't."""
    return [
        RuleCheck(
            "Molecular weight",
            descriptors.molecular_weight,
            RO5_MAX_MW,
            descriptors.molecular_weight <= RO5_MAX_MW,
            "max",
        ),
        RuleCheck(
            "cLogP",
            descriptors.clogp,
            RO5_MAX_LOGP,
            descriptors.clogp <= RO5_MAX_LOGP,
            "max",
        ),
        RuleCheck(
            "H-bond donors",
            descriptors.h_bond_donors,
            RO5_MAX_HBD,
            descriptors.h_bond_donors <= RO5_MAX_HBD,
            "max",
        ),
        RuleCheck(
            "H-bond acceptors",
            descriptors.h_bond_acceptors,
            RO5_MAX_HBA,
            descriptors.h_bond_acceptors <= RO5_MAX_HBA,
            "max",
        ),
        RuleCheck(
            "Rotatable bonds",
            descriptors.rotatable_bonds,
            VEBER_MAX_ROTATABLE,
            descriptors.rotatable_bonds <= VEBER_MAX_ROTATABLE,
            "max",
        ),
        RuleCheck(
            "TPSA",
            descriptors.tpsa,
            VEBER_MAX_TPSA,
            descriptors.tpsa <= VEBER_MAX_TPSA,
            "max",
        ),
    ]
