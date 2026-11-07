# Setup

## Requirements

- Python 3.11 or newer
- Docker and Docker Compose (optional, for the container path)
- No chemistry toolchain — the engine is pure Python

## Local development

```bash
git clone https://github.com/mohdabrarbaloch-arch/day-14-iksir.git
cd day-14-iksir

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
pip install -r requirements-dev.txt   # tests and linters

cp .env.example .env
```

Open `.env` and set `SECRET_KEY` to something long and random:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Then start the server:

```bash
uvicorn app.main:app --reload
```

The app is at <http://127.0.0.1:8000>. Interactive API docs are at
<http://127.0.0.1:8000/api/docs>.

The database is created on first start. With the default `DATABASE_URL` it is a
file called `iksir.db` in the project root.

## Docker

```bash
cp .env.example .env      # set SECRET_KEY
docker compose up --build
```

That starts the app on port 8000 and a Postgres 16 instance. The app waits for
Postgres to report healthy before it starts.

To run only the app against SQLite:

```bash
docker build -t iksir .
docker run -p 8000:8000 --env-file .env iksir
```

## Environment variables

Every variable is documented in `.env.example`. The ones that matter:

| Variable | Default | Notes |
|---|---|---|
| `SECRET_KEY` | *(dev placeholder)* | **Change this.** The app refuses to start in production with the default. |
| `ENVIRONMENT` | `development` | `production` enables the strict checks |
| `DATABASE_URL` | `sqlite:///./iksir.db` | Any SQLAlchemy URL |
| `CORS_ORIGINS` | `http://localhost:8000` | Comma-separated allow-list |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | JWT lifetime |
| `BCRYPT_ROUNDS` | `12` | Drop to 4 in tests |
| `RATE_LIMIT_REQUESTS` | `120` | Per minute, per IP |
| `AUTH_RATE_LIMIT_REQUESTS` | `10` | Per minute, per IP, on `/api/auth/*` |
| `MAX_SMILES_LENGTH` | `1000` | Rejects oversized input |
| `MAX_COMPOUNDS_PER_SCREEN` | `200` | Caps a single screening request |

## Running the tests

```bash
pytest -q
```

60 tests, a few seconds. The suite sets `BCRYPT_ROUNDS=4` and raises the rate
limits so it does not throttle itself.

With coverage:

```bash
pytest --cov=app --cov-report=term-missing
```

## Linting and formatting

```bash
ruff check app tests scripts
black --check app tests scripts
```

Both must pass cleanly. To apply formatting:

```bash
black app tests scripts
ruff check app tests scripts --fix
```

## Capturing screenshots

With the server running:

```bash
pip install playwright
playwright install chromium
python3 scripts/capture_screenshots.py http://127.0.0.1:8000
```

Writes six PNGs into `screenshots/`. The script drives a real browser, so the
images show what the app actually renders.

## Troubleshooting

**`SECRET_KEY must be set` on startup.** You are running with
`ENVIRONMENT=production` and the development default key. Set a real one.

**`sqlite3.OperationalError: database is locked`.** Two processes are writing
the same SQLite file. Stop the extra one, or move to Postgres.

**Port 8000 already in use.** `uvicorn app.main:app --port 8001`.

**A SMILES string is rejected with a 422.** The error body carries the character
offset and a reason. Common causes: an unclosed ring bond number, unbalanced
parentheses, or a lowercase aromatic atom outside a ring.
