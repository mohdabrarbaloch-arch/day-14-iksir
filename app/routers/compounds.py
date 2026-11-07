"""Compound library endpoints: save, list, read, and delete structures."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..chemistry.descriptors import compute_descriptors
from ..chemistry.library import list_compounds
from ..chemistry.smiles import SmilesError, parse_smiles
from ..database import get_db
from ..deps import get_current_user
from ..models import Compound, User
from ..schemas import CompoundCreate, CompoundOut, CompoundWithDescriptors

router = APIRouter(prefix="/api/compounds", tags=["compounds"])


@router.get(
    "/starter",
    response_model=list[dict],
    summary="The built-in reference library",
)
def starter_library() -> list[dict]:
    """Return the 12 reference compounds shipped with the app.

    Public on purpose: a new visitor should be able to try a screening run
    without creating an account first.
    """
    return [compound.to_dict() for compound in list_compounds()]


@router.get("", response_model=list[CompoundOut], summary="Your saved compounds")
def list_saved(
    db: Session = Depends(get_db), user: User = Depends(get_current_user)
) -> list[CompoundOut]:
    rows = db.scalars(
        select(Compound).where(Compound.owner_id == user.id).order_by(Compound.created_at.desc())
    ).all()
    return [CompoundOut.model_validate(row) for row in rows]


@router.post(
    "",
    response_model=CompoundWithDescriptors,
    status_code=status.HTTP_201_CREATED,
    summary="Save a compound",
)
def create_compound(
    payload: CompoundCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CompoundWithDescriptors:
    duplicate = db.scalar(
        select(Compound).where(Compound.owner_id == user.id, Compound.name == payload.name)
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"You already have a compound named {payload.name!r}",
        )

    compound = Compound(
        owner_id=user.id,
        name=payload.name,
        smiles=payload.smiles,
        therapeutic_class=payload.therapeutic_class,
        notes=payload.notes,
    )
    db.add(compound)
    db.commit()
    db.refresh(compound)

    try:
        descriptors = compute_descriptors(parse_smiles(compound.smiles)).to_dict()
    except SmilesError as exc:  # pragma: no cover - guarded at validation
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    return CompoundWithDescriptors(
        **CompoundOut.model_validate(compound).model_dump(), descriptors=descriptors
    )


@router.get("/{compound_id}", response_model=CompoundWithDescriptors, summary="One compound")
def get_compound(
    compound_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CompoundWithDescriptors:
    compound = db.get(Compound, compound_id)
    if compound is None or compound.owner_id != user.id:
        # Same response whether it does not exist or belongs to someone else,
        # so this cannot be used to probe for other people's compound ids.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compound not found")

    descriptors = compute_descriptors(parse_smiles(compound.smiles)).to_dict()
    return CompoundWithDescriptors(
        **CompoundOut.model_validate(compound).model_dump(), descriptors=descriptors
    )


@router.delete(
    "/{compound_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete a compound",
)
def delete_compound(
    compound_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    compound = db.get(Compound, compound_id)
    if compound is None or compound.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compound not found")
    db.delete(compound)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
