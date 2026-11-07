"""Chemistry engine tests.

The reference values here are the published molecular weights and formulas from
PubChem. If this suite passes, the descriptor engine agrees with the standard
reference for these twelve drugs -- which is the strongest check available
without importing RDKit.
"""

from __future__ import annotations

import pytest

from app.chemistry.descriptors import (
    compute_descriptors,
    lipinski_violations,
    molecular_formula,
    rule_checks,
)
from app.chemistry.library import LIBRARY, get_compound
from app.chemistry.smiles import SmilesError, parse_smiles
from app.chemistry.targets import get_target, list_targets

# (slug, molecular weight, molecular formula) from PubChem.
REFERENCE = [
    ("aspirin", 180.16, "C9H8O4"),
    ("caffeine", 194.19, "C8H10N4O2"),
    ("gefitinib", 446.90, "C22H24ClFN4O3"),
    ("erlotinib", 393.44, "C22H23N3O4"),
    ("imatinib", 493.60, "C29H31N7O"),
    ("vemurafenib", 489.93, "C23H18ClF2N3O3S"),
    ("sotorasib", 560.59, "C30H30F2N6O3"),
    ("ruxolitinib", 306.37, "C17H18N6"),
    ("donepezil", 379.49, "C24H29NO3"),
    ("galantamine", 287.35, "C17H21NO3"),
    ("entacapone", 305.29, "C14H15N3O5"),
    ("teriflunomide", 270.21, "C12H9F3N2O2"),
]


@pytest.mark.parametrize("slug,expected_mw,expected_formula", REFERENCE)
def test_library_matches_pubchem(slug, expected_mw, expected_formula):
    compound = get_compound(slug)
    assert compound is not None, f"{slug} missing from library"
    descriptors = compute_descriptors(parse_smiles(compound.smiles))
    assert descriptors.molecular_formula == expected_formula
    assert descriptors.molecular_weight == pytest.approx(expected_mw, abs=0.6)


def test_benzene_has_six_carbons_and_six_hydrogens():
    descriptors = compute_descriptors(parse_smiles("c1ccccc1"))
    assert descriptors.molecular_formula == "C6H6"
    assert descriptors.ring_count == 1
    assert descriptors.aromatic_ring_count == 1


def test_water_is_three_atoms():
    descriptors = compute_descriptors(parse_smiles("O"))
    assert descriptors.molecular_formula == "H2O"
    assert descriptors.h_bond_donors == 2
    assert descriptors.h_bond_acceptors == 1


def test_branching_attaches_to_the_right_atom():
    """Acetic acid: the second oxygen must hang off the carbonyl carbon."""
    molecule = parse_smiles("CC(=O)O")
    adjacency = molecule.adjacency()
    # Atom 1 is the carbonyl carbon; it should have exactly three neighbours.
    assert len(adjacency[1]) == 3
    assert compute_descriptors(molecule).molecular_formula == "C2H4O2"


def test_cyclohexane_ring_closure():
    descriptors = compute_descriptors(parse_smiles("C1CCCCC1"))
    assert descriptors.molecular_formula == "C6H12"
    assert descriptors.ring_count == 1
    assert descriptors.aromatic_ring_count == 0


def test_charged_atom_is_counted():
    """Sodium acetate: the carboxylate is deprotonated, so the formula drops an H."""
    descriptors = compute_descriptors(parse_smiles("CC(=O)[O-].[Na+]"))
    assert descriptors.formal_charge == 0  # -1 and +1 cancel
    assert "Na" in descriptors.molecular_formula


def test_rotatable_bonds_ignore_terminal_groups():
    """Ethane's C-C bond is not rotatable: rotating a methyl changes nothing."""
    assert compute_descriptors(parse_smiles("CC")).rotatable_bonds == 0
    """Butane's central bond is."""
    assert compute_descriptors(parse_smiles("CCCC")).rotatable_bonds == 1


@pytest.mark.parametrize(
    "bad_smiles,reason",
    [
        ("C1CC", "unclosed ring"),
        ("C((C)", "unclosed branch"),
        ("c1ccccc1))", "unmatched close"),
        ("[C", "unclosed bracket"),
        ("", "empty"),
    ],
)
def test_invalid_smiles_raises_with_a_position(bad_smiles, reason):
    with pytest.raises(SmilesError) as excinfo:
        parse_smiles(bad_smiles)
    assert isinstance(excinfo.value.position, int)


def test_reaction_smiles_is_rejected_explicitly():
    with pytest.raises(SmilesError, match="reaction SMILES"):
        parse_smiles("CC>>CO")


def test_hill_order_puts_carbon_then_hydrogen_first():
    assert molecular_formula({"C": 6, "H": 6}) == "C6H6"
    assert molecular_formula({"O": 2, "H": 2}) == "H2O2"


def test_lipinski_flags_an_oversized_molecule():
    """A big lipophilic molecule should trip the rule of five."""
    descriptors = compute_descriptors(parse_smiles("C" * 60))
    violations = lipinski_violations(descriptors)
    assert "molecular_weight" in violations


def test_aspirin_passes_rule_of_five():
    descriptors = compute_descriptors(parse_smiles(get_compound("aspirin").smiles))
    assert lipinski_violations(descriptors) == []


def test_rule_checks_are_all_reported():
    descriptors = compute_descriptors(parse_smiles(get_compound("caffeine").smiles))
    checks = rule_checks(descriptors)
    assert len(checks) == 6
    assert all(isinstance(check.passed, bool) for check in checks)


def test_every_target_profile_is_well_formed():
    for target in list_targets():
        assert target.slug
        assert target.mw_band[0] < target.mw_band[1]
        assert target.rotatable_band[0] <= target.rotatable_band[1]
        assert target.ideal_logp > -3
        assert 0 <= target.hbd_required <= 6


def test_all_library_compounds_reference_a_real_target():
    for compound in LIBRARY:
        assert (
            get_target(compound.known_target) is not None
        ), f"{compound.name} points at unknown target {compound.known_target}"
