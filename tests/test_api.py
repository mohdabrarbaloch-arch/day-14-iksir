"""API tests: auth, compounds, descriptors, and screening over HTTP."""

from __future__ import annotations

import uuid

import pytest

ASPIRIN = "CC(=O)Oc1ccccc1C(=O)O"


# ---------------------------------------------------------------- health ----
def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_index_page_serves_html(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Iksir" in response.text


# ------------------------------------------------------------------ auth ----
def test_register_returns_a_token(client):
    email = f"a-{uuid.uuid4().hex[:8]}@example.com"
    response = client.post(
        "/api/auth/register",
        json={"email": email, "display_name": "Ada", "password": "sufficiently-long"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == email
    assert "password" not in str(body).lower() or "password_hash" not in str(body)


def test_duplicate_email_is_rejected(client):
    email = f"dup-{uuid.uuid4().hex[:8]}@example.com"
    payload = {"email": email, "display_name": "Ada", "password": "sufficiently-long"}
    assert client.post("/api/auth/register", json=payload).status_code == 201
    assert client.post("/api/auth/register", json=payload).status_code == 409


def test_short_password_is_rejected(client):
    response = client.post(
        "/api/auth/register",
        json={
            "email": f"s-{uuid.uuid4().hex[:8]}@example.com",
            "display_name": "Ada",
            "password": "short",
        },
    )
    assert response.status_code == 422


def test_wrong_password_is_rejected(client):
    email = f"w-{uuid.uuid4().hex[:8]}@example.com"
    client.post(
        "/api/auth/register",
        json={"email": email, "display_name": "Ada", "password": "sufficiently-long"},
    )
    response = client.post("/api/auth/login", json={"email": email, "password": "definitely-wrong"})
    assert response.status_code == 401


def test_me_requires_a_token(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_returns_the_signed_in_user(auth_client):
    response = auth_client.get("/api/auth/me")
    assert response.status_code == 200
    assert response.json()["display_name"] == "Test Chemist"


# ------------------------------------------------------------- descriptors ----
def test_descriptors_for_aspirin(client):
    response = client.post("/api/descriptors", json={"smiles": ASPIRIN})
    assert response.status_code == 200
    body = response.json()
    assert body["descriptors"]["molecular_formula"] == "C9H8O4"
    assert body["descriptors"]["molecular_weight"] == pytest.approx(180.16, abs=0.6)
    assert body["lipinski_violations"] == []
    assert len(body["rule_checks"]) == 6


def test_descriptors_reject_broken_smiles_with_422(client):
    response = client.post("/api/descriptors", json={"smiles": "C1CC"})
    assert response.status_code == 422
    assert "parsed" in response.text.lower() or "ring" in response.text.lower()


# --------------------------------------------------------------- compounds ----
def test_save_and_read_back_a_compound(auth_client):
    response = auth_client.post(
        "/api/compounds",
        json={"name": "Aspirin copy", "smiles": ASPIRIN, "therapeutic_class": "NSAID"},
    )
    assert response.status_code == 201
    compound_id = response.json()["id"]
    assert response.json()["descriptors"]["molecular_formula"] == "C9H8O4"

    fetched = auth_client.get(f"/api/compounds/{compound_id}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Aspirin copy"


def test_duplicate_compound_name_is_rejected(auth_client):
    payload = {"name": "Twin", "smiles": ASPIRIN}
    assert auth_client.post("/api/compounds", json=payload).status_code == 201
    assert auth_client.post("/api/compounds", json=payload).status_code == 409


def test_compound_with_bad_smiles_is_rejected(auth_client):
    response = auth_client.post("/api/compounds", json={"name": "Broken", "smiles": "C((("})
    assert response.status_code == 422


def test_delete_removes_the_compound(auth_client):
    created = auth_client.post("/api/compounds", json={"name": "Gone", "smiles": ASPIRIN})
    compound_id = created.json()["id"]
    assert auth_client.delete(f"/api/compounds/{compound_id}").status_code == 204
    assert auth_client.get(f"/api/compounds/{compound_id}").status_code == 404


# --------------------------------------------------------------- screening ----
def test_targets_are_listed(client):
    response = client.get("/api/targets")
    assert response.status_code == 200
    slugs = [t["slug"] for t in response.json()]
    assert "egfr" in slugs
    assert len(slugs) >= 7


def test_unknown_target_returns_404_with_the_valid_options(client):
    response = client.get("/api/targets/not-a-target")
    assert response.status_code == 404
    assert "egfr" in response.json()["detail"]


def test_screening_the_starter_library_ranks_the_egfr_drug_highly(client):
    """Gefitinib was designed for EGFR, so it must come out as a hit and near
    the top. It is not asserted to be rank 1: ruxolitinib is a real kinase
    inhibitor that plausibly fits this pocket, and a ligand-based model that
    claimed otherwise would be overfitted to one compound.
    """
    starter = client.get("/api/compounds/starter").json()
    payload = {
        "target": "egfr",
        "compounds": [{"name": c["name"], "smiles": c["smiles"]} for c in starter],
    }
    response = client.post("/api/screen", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["compound_count"] == len(starter)

    names = [r["compound_name"] for r in body["results"]]
    assert "Gefitinib" in names[:3], f"gefitinib ranked {names.index('Gefitinib') + 1}"

    gefitinib = next(r for r in body["results"] if r["compound_name"] == "Gefitinib")
    assert gefitinib["verdict"] == "hit"

    # Ranked descending by score.
    scores = [r["final_score"] for r in body["results"]]
    assert scores == sorted(scores, reverse=True)
    assert "not a docking" in body["method"].lower()


def test_screening_with_no_compounds_is_422(client):
    response = client.post("/api/screen", json={"target": "egfr", "compounds": []})
    assert response.status_code == 422


def test_saved_run_can_be_reopened(auth_client):
    saved = auth_client.post(
        "/api/screen/save",
        json={"target": "egfr", "compounds": [{"name": "Aspirin", "smiles": ASPIRIN}]},
    )
    assert saved.status_code == 201
    run_id = saved.json()["id"]

    detail = auth_client.get(f"/api/screen/runs/{run_id}")
    assert detail.status_code == 200
    assert len(detail.json()["results"]) == 1


def test_runs_require_authentication(client):
    assert client.get("/api/screen/runs").status_code == 401
