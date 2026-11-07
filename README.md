# Iksir

**A compound screening workbench that shows its work.**

Iksir takes a SMILES string, parses it into a real molecular graph, computes
descriptors from published fragment methods, and scores the molecule against the
pharmacophore profile of a known drug target. Every number on screen traces back
to an atom count or a published constant — there is no model to trust and no
black box to take on faith.

The name is Urdu for *elixir*.

![Iksir screening a reference library against EGFR](screenshots/04-screening.png)

---

## What it actually does

Paste a SMILES string, or pick from a library of twelve real drugs. Iksir will:

- **Parse the structure** with its own SMILES parser — branches, ring closures,
  aromatic lowercase atoms, bracket atoms with charges and explicit hydrogens,
  and the `\` / `/` directional bonds.
- **Compute descriptors**: molecular formula, molecular weight, exact mass,
  heavy-atom count, ring count, aromatic ring count, rotatable bonds, H-bond
  donors and acceptors, TPSA, cLogP, fraction sp3, and the Rule of Five checks.
- **Score it against a target**: seven real binding pockets, each described as a
  pharmacophore profile with weighted terms and explicit penalties.
- **Rank a whole library** and save the run so it can be reopened later.

### The honesty note, up front

**This is ligand-based triage, not docking.** Iksir does not simulate a protein,
does not place your molecule in a pocket, and does not predict a binding affinity
in kcal/mol. It compares your molecule's *properties* against the properties a
known inhibitor of that target happens to have, and tells you whether it is worth
spending a docking run on.

A high score means "this looks like the kind of molecule that binds here." It does
not mean "this binds." The app says so on the page, the API says so in every
response, and the tests assert that the disclaimer is present.

---

## Screenshots

| | |
|---|---|
| ![Landing](screenshots/01-landing.png) | ![Workbench](screenshots/02-workbench.png) |
| **Landing** — what the tool is, and what it is not | **Workbench** — pick a target, pick compounds |
| ![Descriptors](screenshots/03-descriptors.png) | ![Screening](screenshots/04-screening.png) |
| **Descriptors** — every value computed from the graph | **Screening** — ranked hits with per-term breakdown |
| ![Library](screenshots/05-library.png) | ![Mobile](screenshots/06-mobile.png) |
| **Reference library** — twelve drugs, verified SMILES | **Mobile** — the same tool on a phone |

---

## Features

- **Own SMILES parser.** No RDKit, no Open Babel, no C dependencies. The parser
  is ~620 lines of pure Python and is tested against twelve molecules whose
  molecular weights are published.
- **SSSR ring perception.** Finds the smallest set of smallest rings, so
  naphthalene is two 6-rings rather than one 10-atom perimeter, and fused
  polycyclics do not blow up the request.
- **Hückel aromaticity perception.** A ring written as a Kekulé structure
  (`C1=CC=CC=C1`) is recognised as aromatic, so the aromatic-ring count and the
  TPSA contribution come out right either way.
- **Seven real targets** — EGFR, BRAF V600E, KRAS G12C, JAK2, acetylcholinesterase,
  COMT, and DHODH — each with a pocket profile grounded in the literature for
  that target's known inhibitors.
- **Auditable scoring.** Every result carries the per-term value, weight, and
  points, plus any penalties and why they were applied.
- **JWT auth** with bcrypt hashing, so runs are saved per account.
- **Rate limiting** on every endpoint, with a tighter budget on auth.
- **No build step.** The front end is plain HTML, CSS, and JavaScript served
  straight from FastAPI.

---

## Quick start

### Docker (recommended)

```bash
git clone https://github.com/mohdabrarbaloch-arch/day-14-iksir.git
cd day-14-iksir
cp .env.example .env          # then edit SECRET_KEY
docker compose up --build
```

Open <http://localhost:8000>.

### Local

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then edit SECRET_KEY
uvicorn app.main:app --reload
```

SQLite is the default, so there is nothing else to install. To use Postgres,
set `DATABASE_URL` in `.env` and start the `db` service from the compose file.

### Tests and lint

```bash
pip install -r requirements-dev.txt
pytest -q                     # 60 tests
ruff check app tests scripts
black --check app tests scripts
```

---

## API

Full reference in [`docs/api.md`](docs/api.md). The short version:

| Method | Path | What it does |
|---|---|---|
| `GET` | `/api/health` | Liveness probe |
| `POST` | `/api/auth/register` | Create an account, returns a JWT |
| `POST` | `/api/auth/login` | Exchange credentials for a JWT |
| `GET` | `/api/auth/me` | The current account |
| `GET` | `/api/targets` | All seven target profiles |
| `GET` | `/api/targets/{slug}` | One target profile |
| `GET` | `/api/compounds/starter` | The twelve-compound reference library |
| `POST` | `/api/descriptors` | Descriptors for one SMILES string |
| `POST` | `/api/screen` | Score a list of compounds against a target |
| `POST` | `/api/screen/save` | Score and persist a run (auth required) |
| `GET` | `/api/screen/runs` | Your saved runs (auth required) |
| `GET` | `/api/screen/runs/{id}` | One saved run (auth required) |

```bash
curl -X POST http://localhost:8000/api/descriptors \
  -H 'Content-Type: application/json' \
  -d '{"smiles": "CC(=O)Oc1ccccc1C(=O)O"}'
```

```json
{
  "smiles": "CC(=O)Oc1ccccc1C(=O)O",
  "descriptors": {
    "molecular_formula": "C9H8O4",
    "molecular_weight": 180.159,
    "clogp": 0.924,
    "tpsa": 47.92,
    "h_bond_donors": 1,
    "h_bond_acceptors": 4
  },
  "lipinski_violations": []
}
```

---

## How the scoring works

Each target defines a pocket as a set of weighted terms. A term returns a value
in `[0, 1]`; the score is the weighted mean, scaled to 100, minus penalties.

```
final = 100 * Σ(weight_i * value_i) / Σ(weight_i)  −  Σ(penalties)
```

For EGFR the terms are hydrophobicity (weight 1.4), H-bond donors (1.2),
H-bond acceptors (1.4), aromatic rings (1.2), molecular size (1.1), shape (0.4),
formal charge (0.5), and flexibility (0.7). A molecule whose largest ring has 8
or more atoms takes a penalty, because strained macrocycles are usually an
artefact of a bad structure rather than a design choice.

Verdicts: **hit** at 60 and above, **borderline** at 40–60, **weak** below 40.

The weights are not fitted to data. They encode the qualitative importance of
each property for that pocket's known inhibitors, and they are visible in the
API response so you can disagree with them.

---

## Reference library

Twelve compounds with SMILES transcribed from PubChem. The test suite checks
every one against its published molecular weight and formula.

| Compound | Target class | Formula | MW |
|---|---|---|---|
| Gefitinib | EGFR inhibitor | C22H24ClFN4O3 | 446.91 |
| Erlotinib | EGFR inhibitor | C22H23N3O4 | 393.44 |
| Imatinib | BCR-ABL inhibitor | C29H31N7O | 493.60 |
| Vemurafenib | BRAF inhibitor | C23H18ClF2N3O3S | 489.93 |
| Sotorasib | KRAS G12C inhibitor | C30H30F2N6O3 | 560.59 |
| Ruxolitinib | JAK inhibitor | C17H18N6 | 306.37 |
| Donepezil | AChE inhibitor | C24H29NO3 | 379.50 |
| Galantamine | AChE inhibitor | C17H21NO3 | 287.36 |
| Entacapone | COMT inhibitor | C14H15N3O5 | 305.29 |
| Teriflunomide | DHODH inhibitor | C12H9F3N2O2 | 270.21 |
| Aspirin | COX inhibitor | C9H8O4 | 180.16 |
| Caffeine | (decoy) | C8H10N4O2 | 194.19 |

Caffeine is in there on purpose. It is drug-like by every Rule-of-Five measure
and it should *not* score well against a kinase pocket — a useful sanity check
that the scorer is not just rewarding "looks like a drug."

---

## Project layout

```
app/
  chemistry/          the engine — no web framework, no database
    elements.py       atomic weights and valences
    smiles.py         SMILES tokenizer and graph builder
    descriptors.py    SSSR rings, aromaticity, all descriptors
    screening.py      the scoring function
    targets.py        seven pocket profiles
    library.py        twelve reference compounds
  routers/            auth, compounds, screening
  static/             the front end
  config.py           settings from the environment
  database.py         SQLAlchemy engine and session
  models.py           User, Compound, ScreeningRun
  security.py         bcrypt and JWT
  schemas.py          Pydantic request/response models
  ratelimit.py        sliding-window limiter
  main.py             the FastAPI app
tests/                60 tests
docs/                 setup, usage, API reference
scripts/              screenshot capture
```

The `chemistry/` package imports nothing from the web layer. It is a plain
library and can be used on its own:

```python
from app.chemistry.smiles import parse_smiles
from app.chemistry.descriptors import compute_descriptors

mol = parse_smiles("CC(=O)Oc1ccccc1C(=O)O")
print(compute_descriptors(mol).molecular_weight)   # 180.159
```

---

## Limitations

Worth stating plainly, because a tool like this is only useful if you know where
it stops:

- **No 3D structure.** Everything is computed from the 2D graph. Shape is
  approximated by fraction sp3 and ring count, not by a conformer.
- **cLogP is a fragment estimate.** It uses an atom-contribution scheme, not an
  experimental measurement. Expect ±0.5 against a measured value.
- **Aromaticity is a simplified Hückel check.** It handles the 5- and 6-membered
  cases that cover drug-like molecules. It is not a full implementation with
  lone-pair bookkeeping, and it will misclassify exotic heterocycles.
- **The pocket profiles are qualitative.** They are not derived from crystal
  structures or fitted to binding data.
- **No stereochemistry in the descriptors.** `@` and `@@` are parsed and
  preserved in the graph, but the descriptors are computed on the constitutional
  graph, so enantiomers score identically.

---

## License

MIT — see [LICENSE](LICENSE).

Built by [ABraz Baloch](https://github.com/mohdabrarbaloch-arch) as Day 14 of a
30-day build challenge.
