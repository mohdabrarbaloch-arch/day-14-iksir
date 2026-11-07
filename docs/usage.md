# Usage

## The short version

1. Open the app.
2. Pick a target from the dropdown.
3. Tick compounds from the reference library, or paste your own SMILES.
4. Hit **Run screen**.
5. Read the ranked list. Click a result to see the per-term breakdown.

Sign in if you want to save runs. Everything else works without an account.

## Reading a result

Each result card shows:

- **Rank** — position in the sorted list, 1 is best.
- **Name** — the compound's name.
- **Verdict** — `hit` (≥70), `borderline` (50–70), or `miss` (<50).
- **Score** — the final number, 0–100.
- **SMILES** — the structure that was scored.
- **Term bars** — one row per scoring term. The bar length is the term's value
  in `[0, 1]`; the number on the right is the points it contributed after
  weighting.
- **Penalties** — anything subtracted, and why.

The bars are the useful part. A compound that scores 78 because it nails the
H-bond terms but is weak on shape is a different proposition from one that
scores 78 by being mediocre at everything, and the bars tell you which you have.

## Worked example: gefitinib against EGFR

Gefitinib is an EGFR inhibitor, so it should score well. It does — 81.1, a hit:

| Term | Value | Weight | Points |
|---|---|---|---|
| hydrophobic | 0.36 | 1.4 | 0.51 |
| hbond donor | 1.00 | 1.2 | 1.20 |
| hbond acceptor | 1.00 | 1.4 | 1.40 |
| aromatic | 1.00 | 1.2 | 1.20 |
| size | 1.00 | 1.1 | 1.10 |
| shape | 0.73 | 0.4 | 0.29 |
| charge | 1.00 | 0.5 | 0.50 |
| flexibility | 0.75 | 0.7 | 0.53 |

Sum of weights: 7.9. Sum of points: 6.73. `100 × 6.73 / 7.9 = 85.2`, minus a
4.0 penalty for a large ring, giving 81.1.

The weak term is hydrophobicity: gefitinib's cLogP is 2.32 and the pocket wants
about 3.6. That is a real observation about the molecule, not a bug — gefitinib
is a relatively polar kinase inhibitor, and the model notices.

## Worked example: caffeine as a decoy

Caffeine is drug-like by every Rule-of-Five measure — MW 194, cLogP −0.07, two
H-bond donors, six acceptors, no violations and it is a weak, non-selective
scorer here. That is the point of including it: a scorer that ranked caffeine
alongside gefitinib would be measuring "is this a drug" rather than "does this
fit this pocket."

## Using the descriptor calculator

The **Descriptors** tab takes any SMILES and returns the full descriptor set
without scoring it. Useful when you want the numbers on their own, or when you
are debugging a structure and want to see whether the parser read it the way you
meant.

## The reference library

The **Library** tab lists all twelve compounds with their SMILES, formula, and
key descriptors. Every value there is checked against PubChem in the test suite.

## Saving runs

Sign in, then use **Save run** after a screen. Saved runs appear under the
**Runs** tab with their full ranked output, so a result you looked at last week
is still there and still says exactly what it said.

## Using the engine directly

The chemistry package has no web dependencies and can be imported on its own:

```python
from app.chemistry.smiles import parse_smiles
from app.chemistry.descriptors import compute_descriptors
from app.chemistry.screening import score_compound
from app.chemistry.targets import get_target

mol = parse_smiles("COC1=C(C=C2C(=C1)N=CN=C2NC3=CC(=C(C=C3)F)Cl)OCCCN4CCOCC4")
desc = compute_descriptors(mol)

print(desc.molecular_formula)   # C22H24ClFN4O3
print(desc.molecular_weight)    # 446.907
print(desc.clogp)               # 2.322

result = score_compound("Gefitinib", mol.smiles, desc, get_target("egfr"))
print(result.final_score)       # 81.08
print(result.verdict)           # hit
```

## SMILES support

The parser handles the subset of SMILES that covers drug-like molecules:

| Feature | Example |
|---|---|
| Atoms | `C`, `N`, `O`, `Cl`, `Br` |
| Aromatic atoms | `c`, `n`, `o`, `s` |
| Branches | `CC(=O)O` |
| Ring closures | `c1ccccc1`, `C1CC1` |
| Bond orders | `-`, `=`, `#`, `:` |
| Directional bonds | `F/C=C/F` |
| Bracket atoms | `[NH4+]`, `[O-]`, `[13CH4]` |
| Charges | `[Na+]`, `[Fe+2]` |
| Explicit hydrogens | `[CH3]` |
| Disconnected fragments | `[Na+].[Cl-]` |

Not supported: reaction arrows, atom mapping (`[CH3:1]`), and the `~` any-bond
symbol. These are rejected with a 422 and a character offset rather than being
silently misread.

## Common mistakes

**"Unclosed ring bond 1"** — a ring number was opened and never closed. Every
`1` needs a partner.

**"Unbalanced parentheses"** — a `(` with no `)`, or the reverse.

**"Unexpected character"** — usually a lowercase aromatic atom outside a ring,
or a stray space. Whitespace inside a SMILES string is not legal.

**A structure parses but the formula looks wrong** — check for a missing
hydrogen. `C1CC1` is cyclopropane (C3H6); `C1CCC1` is cyclobutane (C4H8).
