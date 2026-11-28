"""Pydantic models for community submissions and admin approval."""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SubmissionType(str, Enum):
    """Kinds of place or experience a community member can suggest."""

    destination = "destination"
    food = "food"
    craft = "craft"
    cultural_experience = "cultural_experience"

    @classmethod
    def _missing_(cls, value):
        if not isinstance(value, str):
            return None
        normalized = value.strip().lower().replace("-", " ").replace("_", " ")
        normalized = " ".join(normalized.split())
        aliases = {
            "destination": cls.destination,
            "food": cls.food,
            "craft": cls.craft,
            "cultural experience": cls.cultural_experience,
        }
        return aliases.get(normalized)


class SubmissionStatus(str, Enum):
    """Approval states. New records always start as pending."""

    pending = "pending"
    approved = "approved"
    rejected = "rejected"


TYPE_SPECIFIC_FIELDS: dict[SubmissionType, set[str]] = {
    SubmissionType.destination: {"category"},
    SubmissionType.food: {
        "origin_place",
        "ingredients",
        "cultural_significance",
        "gi_id",
        "destination_id",
    },
    SubmissionType.craft: {
        "origin_place",
        "destination_id",
        "gi_id",
        "materials",
        "techniques_process",
        "products",
        "artisan_community",
    },
    SubmissionType.cultural_experience: {
        "experience_type",
        "destination_id",
        "craft_id",
        "months_or_season",
        "availability_status",
        "availability_note",
        "price",
    },
}

ALL_TYPE_SPECIFIC_FIELDS = set().union(*TYPE_SPECIFIC_FIELDS.values())


class SubmissionCreate(BaseModel):
    """Body for POST /api/submissions."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        json_schema_extra={
            "examples": [
                {
                    "name": "Etikoppaka Toy Makers",
                    "description": (
                        "A village workshop where artisans turn Ankudu wood "
                        "into lacquered toys."
                    ),
                    "submission_type": "craft",
                    "state": "Andhra Pradesh",
                    "district": "Anakapalli",
                    "location": "Etikoppaka village",
                    "latitude": 17.4921,
                    "longitude": 82.7543,
                    "contact": "workshop@example.com",
                    "source": "https://anakapalli.ap.gov.in/odop-anakapalli/",
                }
            ]
        },
    )

    name: str = Field(
        min_length=1,
        max_length=200,
        description="Name of the place, food, craft, or experience.",
    )
    description: str = Field(min_length=1, max_length=4000)
    submission_type: SubmissionType = Field(
        description="One of: destination, food, craft, cultural experience."
    )
    state: str = Field(min_length=1, max_length=80)
    district: str = Field(min_length=1, max_length=80)
    location: Optional[str] = Field(
        default=None,
        max_length=300,
        description="Optional place name or address. Coordinates can be sent separately.",
    )
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    contact: Optional[str] = Field(
        default=None,
        max_length=300,
        description="Optional phone, email, or other contact details.",
    )
    source: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Optional source URL or other reference.",
    )

    # Proposed type-specific optional fields
    category: Optional[str] = Field(default=None, max_length=300)
    origin_place: Optional[str] = Field(default=None, max_length=300)
    ingredients: Optional[str] = Field(default=None, max_length=1000)
    cultural_significance: Optional[str] = Field(default=None, max_length=2000)
    gi_id: Optional[str] = Field(default=None, max_length=64)
    destination_id: Optional[str] = Field(default=None, max_length=64)
    materials: Optional[str] = Field(default=None, max_length=1000)
    techniques_process: Optional[str] = Field(default=None, max_length=2000)
    products: Optional[str] = Field(default=None, max_length=1000)
    artisan_community: Optional[str] = Field(default=None, max_length=500)
    experience_type: Optional[str] = Field(default=None, max_length=200)
    craft_id: Optional[str] = Field(default=None, max_length=64)
    months_or_season: Optional[str] = Field(default=None, max_length=200)
    availability_status: Optional[str] = Field(default=None, max_length=200)
    availability_note: Optional[str] = Field(default=None, max_length=1000)
    price: Optional[str] = Field(default=None, max_length=200)

    @field_validator(
        "location",
        "contact",
        "source",
        *sorted(ALL_TYPE_SPECIFIC_FIELDS),
    )
    @classmethod
    def blank_optional_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @model_validator(mode="after")
    def validate_coordinates_and_type_fields(self):
        has_latitude = self.latitude is not None
        has_longitude = self.longitude is not None
        if has_latitude != has_longitude:
            raise ValueError(
                "Provide both latitude and longitude, or leave both empty."
            )

        allowed = TYPE_SPECIFIC_FIELDS[self.submission_type]
        disallowed = [
            field
            for field in sorted(ALL_TYPE_SPECIFIC_FIELDS - allowed)
            if getattr(self, field) is not None
        ]
        if disallowed:
            raise ValueError(
                f"Fields {', '.join(disallowed)} are not valid for submission_type "
                f"'{self.submission_type.value}'."
            )
        return self


class ApproveSubmissionRequest(BaseModel):
    """Optional body for PATCH /api/submissions/{submission_id}/approve."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    canonical_record_id: Optional[str] = Field(default=None, max_length=64)

    @field_validator("canonical_record_id")
    @classmethod
    def blank_to_none(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class SubmissionRead(BaseModel):
    """A stored submission returned by the API."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    description: str
    submission_type: SubmissionType
    state: str
    district: str
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    contact: Optional[str] = None
    source: Optional[str] = None
    category: Optional[str] = None
    origin_place: Optional[str] = None
    ingredients: Optional[str] = None
    cultural_significance: Optional[str] = None
    gi_id: Optional[str] = None
    destination_id: Optional[str] = None
    materials: Optional[str] = None
    techniques_process: Optional[str] = None
    products: Optional[str] = None
    artisan_community: Optional[str] = None
    experience_type: Optional[str] = None
    craft_id: Optional[str] = None
    months_or_season: Optional[str] = None
    availability_status: Optional[str] = None
    availability_note: Optional[str] = None
    price: Optional[str] = None
    status: SubmissionStatus
    canonical_record_id: Optional[str] = None
    created_at: str
    updated_at: str


class SubmissionApprovedRead(SubmissionRead):
    """Approved submission returned on public listing endpoints."""

    verification_status: str = "community_approved_unverified"
    verified: bool = False
