# Architecture

## What this is

A single-service web application with a pure-Python chemistry engine at its
core. The engine has no dependencies on the web layer, the database, or any
third-party chemistry library — it is the part of the project that would still
be useful if everything else were deleted.

## System diagram

```
                          ┌──────────────────────────────┐
                          │        Browser (SPA)         │
                          │  index.html + app.js + css   │
                          │  no framework, no build step │
                          └───────────────┬──────────────┘
                                          │  fetch() JSON
                                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          FastAPI application                            │
│                                                                         │
│  middleware:  CORS allow-list  →  security headers  →  rate limiter     │
│                                                                         │
│  ┌───────────────┐  ┌────────────────┐  ┌──────────────────────────┐    │
│  │ routers/auth  │  │routers/compounds│ │   routers/screening      │    │
│  │ register      │  │ list / get      │ │   /descriptors           │    │
│  │ login         │  │ create / delete │ │   /screen                │    │
│  │ me            │  │ starter library │ │   /screen/save           │    │
│  └───────┬───────┘  └────────┬────────┘ │   /screen/runs[/{id}]    │    │
│          │                   │          └────────────┬─────────────┘    │
│          │                   │                       │                  │
│          ▼                   ▼                       ▼                  │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  schemas.py (Pydantic)  ·  security.py (bcrypt + JWT)            │   │
│  │  deps.py (current_user) ·  ratelimit.py (sliding window)         │   │
│  └───────────────────────────────┬──────────────────────────────────┘   │
│                                  │                                      │
│                                  ▼                                      │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    chemistry/  (pure, no I/O)                    │   │
│  │                                                                  │   │
│  │   smiles.py ──parse──▶ Molecule ──▶ descriptors.py ──▶ Descriptors│   │
│  │      │                    │              │                       │   │
│  │      │                    │              │  SSSR rings           │   │
│  │      │                    │              │  Hückel aromaticity   │   │
│  │      │                    │              │  TPSA / cLogP / Ro5   │   │
│  │      │                    │              ▼                       │   │
│  │      │                    │        screening.py ◀── targets.py   │   │
│  │      │                    │              │                       │   │
│  │      │                    │              ▼                       │   │
│  │      │                    │        ScoredResult                 │   │
│  │      │                    │                                      │   │
│  │   library.py ─────────────┘  (12 reference compounds)            │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                  │                                      │
│                                  ▼                                      │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │  database.py (SQLAlchemy 2.0)  ·  models.py                      │   │
│  │  User  ·  Compound  ·  ScreeningRun                              │   │
│  └───────────────────────────────┬──────────────────────────────────┘   │
└──────────────────────────────────┼──────────────────────────────────────┘
                                   ▼
                    ┌──────────────────────────────┐
                    │  SQLite (default)            │
                    │  PostgreSQL (docker-compose) │
                    └──────────────────────────────┘
```

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Web framework | FastAPI 0.115 | Async, typed, generates OpenAPI for free |
| Validation | Pydantic v2 | Request/response contracts in one place |
| ORM | SQLAlchemy 2.0 | Typed `Mapped[]` models, works on SQLite and Postgres unchanged |
| Database | SQLite / PostgreSQL | SQLite for zero-setup local use, Postgres in compose |
| Auth | JWT (HS256) + bcrypt | Stateless tokens, no session store to run |
| Rate limiting | In-process sliding window | One dependency fewer than slowapi; see the note below |
| Front end | Vanilla HTML/CSS/JS | No build step, no node_modules, loads instantly |
| Chemistry | Hand-written | The point of the project — see below |

### Why the chemistry is hand-written

The obvious move would be `pip install rdkit`. That would have made the
descriptor layer a one-line call and the project a thin CRUD wrapper around
somebody else's library.

Writing the parser and the descriptor engine is what makes this a project rather
than a form. It also means the numbers are auditable: when the app says a
molecule has a TPSA of 63.6, that figure came from a table of fragment
contributions in this repository, not from a compiled C extension.

The cost is real — the parser is the most bug-prone part of the codebase, and
the test suite spends most of its effort there. That trade was made deliberately.

## Data flow

### Descriptor request

```
POST /api/descriptors {"smiles": "..."}
  │
  ├─ Pydantic validates the body (non-empty, length cap)
  ├─ rate limiter checks the client's window
  ├─ parse_smiles()  ──▶  Molecule (atoms, bonds, rings)
  │     └─ on failure: 422 with the character offset and a reason
  ├─ compute_descriptors()
  │     ├─ perceive_aromaticity()   Kekulé → aromatic
  │     ├─ find_rings()             SSSR via BFS closure
  │     ├─ molecular weight / exact mass / formula
  │     ├─ TPSA, cLogP from fragment tables
  │     └─ rotatable bonds, fraction sp3, Rule of Five
  └─ 200 with descriptors + violations
```

### Screening request

```
POST /api/screen {"target": "egfr", "compounds": [...]}
  │
  ├─ resolve the target profile (404 if unknown)
  ├─ for each compound:
  │     parse → descriptors → score_compound()
  │        ├─ per-term value in [0,1] × weight
  │        ├─ penalties (large ring, PAINS-style flags)
  │        └─ final = 100·Σ(w·v)/Σw − Σpenalties
  ├─ sort descending by final score
  └─ 200 with ranked results, per-term breakdown, and the method disclaimer
```

### Saving a run

```
POST /api/screen/save   (Authorization: Bearer <jwt>)
  │
  ├─ decode + verify the JWT, load the user
  ├─ run the same scoring path
  ├─ persist ScreeningRun with the full result JSON
  └─ 201 with the run id
```

The full ranked output is stored as JSON rather than normalised into tables.
A run is an immutable snapshot of a computation; there is no query pattern that
needs to reach inside it, and storing it whole means a saved run always replays
exactly what the user saw.

## Database schema

```
users
  id            integer  pk
  email         text     unique, indexed
  display_name  text
  password_hash text
  role          text     default 'member'
  created_at    datetime

compounds
  id            integer  pk
  owner_id      integer  fk → users.id, nullable (null = built-in)
  name          text
  smiles        text
  notes         text     nullable
  created_at    datetime
  index (owner_id, name)

screening_runs
  id             integer  pk
  owner_id       integer  fk → users.id, indexed
  target_slug    text
  target_name    text
  compound_count integer
  hit_count      integer
  results_json   text     full ranked output
  created_at     datetime
```

## Security

- **Passwords** hashed with bcrypt. The cost factor is configurable and drops to
  4 in the test suite so the tests stay fast.
- **Tokens** are HS256 JWTs with an expiry. The signing key is read from
  `SECRET_KEY`; the app refuses to start in production with the development
  default.
- **Rate limiting** is a sliding window keyed by client IP, with a separate and
  tighter budget for `/api/auth/*` so credential stuffing is expensive.
- **CORS** is an explicit allow-list from `CORS_ORIGINS`, never `*` in
  production.
- **Security headers** (`X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`) are set on every response.
- **Input caps** on SMILES length and compound count, so a single request cannot
  pin a worker.
- **No secrets in the repo.** `.env` is gitignored; `.env.example` documents
  every variable with a placeholder.

### A note on the rate limiter

It is an in-process dictionary of timestamps. That is correct for a single
worker and wrong for a fleet — behind a load balancer each worker would enforce
its own budget, so the effective limit multiplies by the worker count. The
honest fix is Redis. It is not here because the project runs as one container,
and adding a Redis dependency to enforce a limit that only matters at a scale
this app does not operate at would be cargo-culting. The code says so in a
comment at the top of `ratelimit.py`.

## Scaling notes

Where this would break first, in order:

1. **The rate limiter.** In-process state, as above. Move to Redis before
   running more than one worker.
2. **Synchronous scoring.** `POST /api/screen` computes every compound inline.
   The cap is 200 compounds per request, which is fine for a workbench and wrong
   for a real library screen. The fix is a job queue: accept the request, return
   a job id, score in a worker, let the client poll or subscribe.
3. **SQLite write contention.** Fine for a single user, poor for concurrent
   writers. Postgres is already wired up; it is a `DATABASE_URL` change.
4. **The chemistry engine is CPU-bound and pure.** It parallelises trivially —
   no shared state, no I/O. A `ProcessPoolExecutor` over the compound list would
   scale it across cores with no changes to the engine itself.
5. **`results_json` grows with library size.** A 200-compound run with full
   per-term breakdowns is a few hundred KB. Past that, store the summary in the
   row and the detail in object storage.

## Testing strategy

60 tests, in three groups:

- **`test_chemistry.py`** — the parser and descriptors. The reference values are
  published molecular weights and formulas for twelve real drugs, so a
  regression in the parser shows up as a wrong number rather than a wrong shape.
  Also covers the failure modes: unclosed rings, unbalanced parentheses, empty
  input, and the specific inputs that used to hang the parser.
- **`test_screening.py`** — the scoring arithmetic. Checks that a perfect match
  scores 100, that penalties subtract, that the verdict thresholds are where
  they claim to be, and that the method disclaimer is present.
- **`test_api.py`** — the HTTP surface. Auth round-trips, 401s on protected
  routes, 422s on malformed SMILES, 404s on unknown targets, and a full
  library screen end to end.

The chemistry tests are the ones that matter. Everything else is plumbing.
