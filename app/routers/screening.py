"""Descriptor and screening endpoints -- the core of the tool."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..chemistry.descriptors import compute_descriptors, rule_checks
from ..chemistry.screening import rank_results, score_compound
from ..chemistry.smiles import SmilesError, parse_smiles
from ..chemistry.targets import get_target, list_targets
from ..database import get_db
from ..deps import get_current_user
from ..models import Compound, ScreenRun, User
from ..schemas import (
    DescriptorRequest,
    DescriptorResponse,
    ScreenRequest,
    ScreenResponse,
    ScreenRunDetail,
    ScreenRunOut,
    TargetOut,
)

router = APIRouter(prefix="/api", tags=["screening"])


@router.get("/targets", response_model=list[TargetOut], summary="Available targets")
def targets() -> list[TargetOut]:
    return [TargetOut(**t.to_dict()) for t in list_targets()]


@router.get("/targets/{slug}", response_model=TargetOut, summary="One target")
def target_detail(slug: str) -> TargetOut:
    target = get_target(slug)
    if target is None:
        available = ", ".join(t.slug for t in list_targets())
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No target called {slug!r}. Available: {available}",
        )
    return TargetOut(**target.to_dict())


@router.post("/descriptors", response_model=DescriptorResponse, summary="Compute descriptors")
def descriptors(payload: DescriptorRequest) -> DescriptorResponse:
    """Compute every descriptor for one SMILES string.

    No authentication: this is pure computation with no side effects, and
    letting a visitor try the engine before signing up is worth more than the
    marginal protection.
    """
    try:
        molecule = parse_smiles(payload.smiles)
    except SmilesError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    computed = compute_descriptors(molecule)
    from ..chemistry.descriptors import lipinski_violations

    return DescriptorResponse(
        smiles=payload.smiles,
        descriptors=computed.to_dict(),
        rule_checks=[check.to_dict() for check in rule_checks(computed)],
        lipinski_violations=lipinski_violations(computed),
    )


@router.post("/screen", response_model=ScreenResponse, summary="Screen a library")
def screen(
    payload: ScreenRequest,
    db: Session = Depends(get_db),
) -> ScreenResponse:
    """Score compounds against a target.

    Open to anonymous callers so a visitor can see the engine work, but the
    result is only persisted when a run is explicitly saved by a signed-in
    user -- see `/api/screen/save`.
    """
    target = get_target(payload.target)
    if target is None:
        available = ", ".join(t.slug for t in list_targets())
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No target called {payload.target!r}. Available: {available}",
        )

    candidates: list[tuple[str, str]] = [(item.name, item.smiles) for item in payload.compounds]

    if payload.compound_ids:
        rows = db.scalars(select(Compound).where(Compound.id.in_(payload.compound_ids))).all()
        by_id = {row.id: row for row in rows}
        missing = [cid for cid in payload.compound_ids if cid not in by_id]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Unknown compound id(s): {missing}",
            )
        candidates.extend((by_id[cid].name, by_id[cid].smiles) for cid in payload.compound_ids)

    if not candidates:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide at least one compound (inline or by id) to screen",
        )

    results = []
    errors: list[str] = []
    for name, smiles in candidates:
        try:
            molecule = parse_smiles(smiles)
        except SmilesError as exc:
            errors.append(f"{name}: {exc}")
            continue
        computed = compute_descriptors(molecule)
        results.append(score_compound(name, smiles, computed, target))

    if not results:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "No compound could be parsed", "errors": errors},
        )

    ranked = rank_results(results)
    hit_count = sum(1 for r in ranked if r.verdict == "hit")

    return ScreenResponse(
        target=target.to_dict(),
        results=[r.to_dict() for r in ranked],  # type: ignore[arg-type]
        hit_count=hit_count,
        compound_count=len(ranked),
    )


@router.post(
    "/screen/save",
    response_model=ScreenRunOut,
    status_code=status.HTTP_201_CREATED,
    summary="Persist a screening run",
)
def save_run(
    payload: ScreenRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ScreenRunOut:
    """Run a screen and store the full ranked output for later review."""
    computed_response = screen(payload, db)

    run = ScreenRun(
        owner_id=user.id,
        target_slug=str(computed_response.target["slug"]),
        target_name=str(computed_response.target["name"]),
        compound_count=computed_response.compound_count,
        hit_count=computed_response.hit_count,
        results_json=json.dumps([r.model_dump() for r in computed_response.results], default=str),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return ScreenRunOut.model_validate(run)


@router.get("/screen/runs", response_model=list[ScreenRunOut], summary="Your runs")
def list_runs(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[ScreenRunOut]:
    rows = db.scalars(
        select(ScreenRun).where(ScreenRun.owner_id == user.id).order_by(ScreenRun.created_at.desc())
    ).all()
    return [ScreenRunOut.model_validate(row) for row in rows]


@router.get("/screen/runs/{run_id}", response_model=ScreenRunDetail, summary="Re-open a run")
def get_run(
    run_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ScreenRunDetail:
    run = db.get(ScreenRun, run_id)
    if run is None or run.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    base = ScreenRunOut.model_validate(run).model_dump()
    return ScreenRunDetail(**base, results=json.loads(run.results_json))
