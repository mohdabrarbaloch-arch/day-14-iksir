"""Pydantic request and response schemas.

Validation lives here so the routers stay thin. The SMILES field is validated by
actually parsing it -- a string that looks plausible but does not parse is
rejected at the edge with the parser's own error message, which is far more
useful than a generic 422.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .chemistry.smiles import SmilesError, parse_smiles
from .config import settings


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------
class RegisterRequest(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=72)

    @field_validator("display_name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("display_name cannot be blank")
        return cleaned


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    display_name: str
    role: str
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    user: UserOut


# --------------------------------------------------------------------------
# Compounds
# --------------------------------------------------------------------------
class CompoundCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    smiles: str = Field(min_length=1, max_length=settings.max_smiles_length)
    therapeutic_class: str = Field(default="", max_length=160)
    notes: str = Field(default="", max_length=2000)

    @field_validator("smiles")
    @classmethod
    def _must_parse(cls, value: str) -> str:
        cleaned = value.strip()
        try:
            parse_smiles(cleaned)
        except SmilesError as exc:
            raise ValueError(f"SMILES could not be parsed: {exc}") from exc
        return cleaned

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name cannot be blank")
        return cleaned


class CompoundOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    smiles: str
    therapeutic_class: str
    notes: str
    created_at: datetime


class CompoundWithDescriptors(CompoundOut):
    """A compound plus its freshly computed descriptors."""

    descriptors: dict[str, float | int | str]


# --------------------------------------------------------------------------
# Descriptor / screening
# --------------------------------------------------------------------------
class DescriptorRequest(BaseModel):
    smiles: str = Field(min_length=1, max_length=settings.max_smiles_length)

    @field_validator("smiles")
    @classmethod
    def _must_parse(cls, value: str) -> str:
        cleaned = value.strip()
        try:
            parse_smiles(cleaned)
        except SmilesError as exc:
            raise ValueError(f"SMILES could not be parsed: {exc}") from exc
        return cleaned


class DescriptorResponse(BaseModel):
    smiles: str
    descriptors: dict[str, float | int | str]
    rule_checks: list[dict[str, str | float | bool]]
    lipinski_violations: list[str]


class ScreenRequest(BaseModel):
    """Screen a set of compounds against one target.

    Compounds may be given inline as (name, smiles) pairs, or by referencing
    saved compound ids, or both. At least one source must be non-empty.
    """

    target: str = Field(min_length=1, max_length=60)
    compounds: list[CompoundCreate] = Field(default_factory=list)
    compound_ids: list[int] = Field(default_factory=list)
    save_run: bool = True

    @field_validator("compounds")
    @classmethod
    def _limit_size(cls, value: list[CompoundCreate]) -> list[CompoundCreate]:
        if len(value) > settings.max_library_size:
            raise ValueError(f"at most {settings.max_library_size} compounds per request")
        return value


class ScreenResultOut(BaseModel):
    compound_name: str
    smiles: str
    target: str
    target_name: str
    descriptors: dict[str, float | int | str]
    terms: list[dict[str, str | float]]
    penalties: list[dict[str, str | float]]
    raw_score: float
    final_score: float
    verdict: str
    lipinski_violations: list[str]
    notes: list[str]
    method: str


class ScreenResponse(BaseModel):
    target: dict[str, object]
    results: list[ScreenResultOut]
    hit_count: int
    compound_count: int
    run_id: int | None = None
    method: str = "ligand-based property triage; not a docking or affinity prediction"


class ScreenRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    target_slug: str
    target_name: str
    compound_count: int
    hit_count: int
    created_at: datetime


class ScreenRunDetail(ScreenRunOut):
    results: list[dict[str, object]]


class TargetOut(BaseModel):
    slug: str
    name: str
    gene: str
    family: str
    summary: str
    ideal_logp: float
    logp_tolerance: float
    hbd_required: int
    hba_required: int
    aromatic_rings_preferred: int
    mw_band: list[float]
    preferred_charge: int
    rotatable_band: list[int]
    weights: dict[str, float]
    note: str


class MessageResponse(BaseModel):
    detail: str
