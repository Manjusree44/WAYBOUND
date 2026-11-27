"""Pydantic models for community submissions.

These models validate data before it is stored. A client cannot set
``status`` here: every new submission is marked pending by the service.
"""

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

    name: str = Field(min_length=1, max_length=200, description="Name of the place, food, craft, or experience.")
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

    @field_validator("location", "contact", "source")
    @classmethod
    def blank_optional_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @model_validator(mode="after")
    def coordinates_must_be_a_pair(self):
        has_latitude = self.latitude is not None
        has_longitude = self.longitude is not None
        if has_latitude != has_longitude:
            raise ValueError(
                "Provide both latitude and longitude, or leave both empty."
            )
        return self


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
    status: SubmissionStatus
    created_at: str
    updated_at: str
