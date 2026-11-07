# API reference

Base URL in development: `http://127.0.0.1:8000`

Interactive docs (Swagger UI): `/api/docs`
OpenAPI schema: `/api/openapi.json`

## Conventions

- All request and response bodies are JSON.
- Authenticated endpoints take `Authorization: Bearer <token>`.
- Errors use a consistent shape:

```json
{
  "detail": "Human-readable message"
}
```

  `detail` is a string for most errors. Validation failures (422) return the
  FastAPI default, where `detail` is a list of per-field objects.

- Rate limits are per client IP. Exceeding one returns `429` with a
  `Retry-After` header.

## Status codes

| Code | Meaning |
|---|---|
| 200 | OK |
| 201 | Created |
| 204 | Deleted, no body |
| 401 | Missing or invalid token |
| 404 | Unknown target, compound, or run |
| 409 | Email already registered, or duplicate compound name |
| 422 | Validation failed, or the SMILES could not be parsed |
| 429 | Rate limit exceeded |
| 500 | Unhandled server error |

---

## Health

### `GET /api/health`

```json
{"status": "ok", "version": "1.0.0", "environment": "development"}
```

---

## Authentication

### `POST /api/auth/register`

| Field | Type | Rules |
|---|---|---|
| `email` | string | valid address, unique |
| `display_name` | string | 1–120 characters |
| `password` | string | 8–72 characters |

The 72-character ceiling is bcrypt's own limit. A longer password is rejected
rather than silently truncated, because truncation would mean two different
passwords authenticate the same account.

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H 'Content-Type: application/json' \
  -d '{"email":"you@example.com","display_name":"You","password":"a-good-password"}'
```

`201`:

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in_minutes": 1440,
  "user": {
    "id": 1,
    "email": "you@example.com",
    "display_name": "You",
    "role": "member",
    "created_at": "2026-11-08T09:00:00"
  }
}
```

`409` if the email is taken. Rate limited to 10/minute.

### `POST /api/auth/login`

Same body minus `display_name`. Returns the same shape. `401` on bad
credentials — deliberately the same message for an unknown email and a wrong
password, so the endpoint cannot be used to enumerate accounts. The check runs
against a dummy hash when the account does not exist, so the response time does
not leak whether the address is registered either.

### `GET /api/auth/me` 🔒

Returns the current account.

```json
{"id": 1, "email": "you@example.com", "display_name": "You", "role": "member", "created_at": "2026-11-08T09:00:00"}
```

---

## Targets

### `GET /api/targets`

Returns all seven pocket profiles.

```json
[
  {
    "slug": "egfr",
    "name": "Epidermal growth factor receptor (kinase domain)",
    "gene": "EGFR",
    "family": "Receptor tyrosine kinase",
    "summary": "The ATP-binding cleft of the EGFR kinase domain...",
    "ideal_logp": 3.6,
    "logp_tolerance": 2.0,
    "hbd_required": 1,
    "hba_required": 3,
    "aromatic_rings_preferred": 2,
    "mw_band": [330.0, 480.0],
    "preferred_charge": 0,
    "rotatable_band": [2, 7],
    "weights": {
      "hydrophobic": 1.4, "hbond_donor": 1.2, "hbond_acceptor": 1.4,
      "aromatic": 1.2, "shape": 0.4
    },
    "note": "Pocket description follows the anilinoquinazoline series..."
  }
]
```

Available slugs: `egfr`, `braf`, `kras_g12c`, `jak2`, `ache`, `comt`, `dhodh`.

### `GET /api/targets/{slug}`

One profile. `404` if the slug is unknown; the error body lists the valid slugs.

---

## Compounds

### `GET /api/compounds/starter`

The twelve-compound reference library. No auth required.

```json
[
  {
    "slug": "gefitinib",
    "name": "Gefitinib",
    "smiles": "COc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1OCCCN1CCOCC1",
    "therapeutic_class": "EGFR tyrosine kinase inhibitor",
    "known_target": "egfr",
    "note": "First-line EGFR inhibitor; the anilinoquinazoline scaffold..."
  }
]
```

### `GET /api/compounds` 🔒

Your saved compounds, newest first.

### `POST /api/compounds` 🔒

| Field | Type | Rules |
|---|---|---|
| `name` | string | 1–160 characters, unique per account |
| `smiles` | string | must parse |
| `therapeutic_class` | string | optional, ≤ 160 characters |
| `notes` | string | optional, ≤ 2000 characters |

`201` with the created compound and its computed descriptors. `409` if you
already have a compound with that name. `422` if the SMILES does not parse.

### `GET /api/compounds/{id}` 🔒

One compound with its descriptors. `404` if it does not exist **or belongs to
someone else** — the same response either way, so this cannot be used to probe
for other people's compound ids.

### `DELETE /api/compounds/{id}` 🔒

`204` on success. `404` under the same rule as above.

---

## Descriptors

### `POST /api/descriptors`

No auth required.

| Field | Type | Rules |
|---|---|---|
| `smiles` | string | 1–2000 characters, must parse |

```bash
curl -X POST http://localhost:8000/api/descriptors \
  -H 'Content-Type: application/json' \
  -d '{"smiles": "CC(=O)Oc1ccccc1C(=O)O"}'
```

`200`:

```json
{
  "smiles": "CC(=O)Oc1ccccc1C(=O)O",
  "descriptors": {
    "molecular_formula": "C9H8O4",
    "molecular_weight": 180.159,
    "exact_mass": 180.0423,
    "heavy_atoms": 13,
    "total_atoms": 21,
    "ring_count": 1,
    "aromatic_ring_count": 1,
    "rotatable_bonds": 3,
    "h_bond_donors": 1,
    "h_bond_acceptors": 4,
    "tpsa": 47.92,
    "clogp": 0.924,
    "fraction_csp3": 0.111,
    "heteroatom_count": 4,
    "halogen_count": 0,
    "formal_charge": 0,
    "max_ring_size": 6
  },
  "rule_checks": [
    {"name": "Molecular weight", "value": 180.159, "threshold": 500.0, "passed": true, "direction": "max"}
  ],
  "lipinski_violations": []
}
```

`422` if the SMILES cannot be parsed. The message carries the character offset:

```json
{"detail": "Value error, SMILES could not be parsed: unclosed ring bond(s): 1 (at character 5)"}
```

---

## Screening

### `POST /api/screen`

No auth required. Scores a list of compounds against one target.

| Field | Type | Rules |
|---|---|---|
| `target` | string | a known target slug |
| `compounds` | array | up to 200 items, each `{name, smiles}` |
| `compound_ids` | array | optional; ids of your saved compounds to include |
| `save_run` | boolean | accepted for compatibility; persistence is via `/api/screen/save` |

At least one of `compounds` or `compound_ids` must be non-empty.

```bash
curl -X POST http://localhost:8000/api/screen \
  -H 'Content-Type: application/json' \
  -d '{
    "target": "egfr",
    "compounds": [
      {"name": "Gefitinib", "smiles": "COc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1OCCCN1CCOCC1"}
    ]
  }'
```

`200`:

```json
{
  "target": {"slug": "egfr", "name": "Epidermal growth factor receptor (kinase domain)"},
  "compound_count": 1,
  "hit_count": 1,
  "method": "ligand-based property triage; not a docking or affinity prediction",
  "results": [
    {
      "compound_name": "Gefitinib",
      "smiles": "COc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1OCCCN1CCOCC1",
      "target": "egfr",
      "target_name": "Epidermal growth factor receptor (kinase domain)",
      "raw_score": 85.08,
      "final_score": 85.08,
      "verdict": "hit",
      "descriptors": {"molecular_weight": 446.907, "clogp": 2.322, "max_ring_size": 6},
      "terms": [
        {"name": "hydrophobic", "value": 0.3608, "weight": 1.4, "points": 0.505, "detail": "cLogP 2.32 vs pocket ideal 3.6 (+/-2.0)"},
        {"name": "hbond_donor", "value": 1.0, "weight": 1.2, "points": 1.2, "detail": "1 donor(s) vs 1 required"}
      ],
      "penalties": [],
      "lipinski_violations": [],
      "notes": [],
      "method": "ligand-based property triage; not a docking or affinity prediction"
    }
  ]
}
```

Results are sorted by `final_score`, descending. Ties break on lower molecular
weight, then fewer rotatable bonds, so the order is total and reproducible.

### `POST /api/screen/save` 🔒

Same body as `/api/screen`. Scores and persists the run.

`201`:

```json
{"id": 1, "target_slug": "egfr", "target_name": "...", "compound_count": 12, "hit_count": 9, "created_at": "2026-11-08T09:00:00"}
```

### `GET /api/screen/runs` 🔒

Your saved runs, newest first. Summaries only — no result payloads.

### `GET /api/screen/runs/{id}` 🔒

One run with its full ranked output. `404` if it is not yours.

---

## Scoring reference

```
final = 100 · Σ(weight_i · value_i) / Σ(weight_i)  −  Σ(penalties)
```

Every `value_i` is in `[0, 1]`. Verdicts: `hit` ≥ 60, `borderline` 40–60,
`weak` < 40.

| Term | What it measures |
|---|---|
| `hydrophobic` | cLogP against the pocket's ideal, with a soft tolerance |
| `hbond_donor` | donor count against the pocket's requirement |
| `hbond_acceptor` | acceptor count against the pocket's requirement |
| `aromatic` | aromatic ring count against the pocket's preference |
| `size` | molecular weight inside the pocket's band |
| `shape` | fraction sp3 — how three-dimensional the molecule is |
| `charge` | formal charge against the pocket's preference |
| `flexibility` | rotatable bonds inside the pocket's band |

| Penalty | Trigger | Points |
|---|---|---|
| `rule_of_five:<criterion>` | one per Lipinski criterion failed | 6.0 each |
| `tpsa_high` | TPSA above Veber's 140 Å² | 5.0 |
| `large_ring` | largest ring has 8 or more atoms | 4.0 |
| `metabolic_soft_spot` | fraction sp3 > 0.75 with ≤ 1 heteroatom | 5.0 |

## Rate limits

| Scope | Default |
|---|---|
| `/api/auth/*` | 10 requests / minute / IP |
| everything else | 120 requests / minute / IP |

Both are configurable. Exceeding a limit returns `429` with `Retry-After`.
`/static/*`, `/healthz`, and `/api/health` are never rate limited, so a platform
probe cannot take the app down.
