from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field


# --- Task 1 Models ---

class CourseEntry(BaseModel):
    code: str
    title: str
    page: int


class Task1Response(BaseModel):
    document: str
    course_count: int
    courses: List[CourseEntry]


# --- Task 2 Models ---

class CourseMeta(BaseModel):
    code: str = ""
    title: str = ""
    category: Optional[str] = None
    lecture: Optional[Union[int, float]] = None
    tutorial: Optional[Union[int, float]] = None
    practical: Optional[Union[int, float]] = None
    credits: Optional[Union[int, float]] = None
    pages: List[int] = Field(default_factory=list)


class TopicEntry(BaseModel):
    id: str = ""
    text: str = ""
    bloom: Optional[str] = None
    bloom_source: Optional[str] = None  # "printed" or "inferred"


class UnitEntry(BaseModel):
    number: int
    title: str = ""
    hours: Optional[int] = None
    text: str = ""
    topics: List[TopicEntry] = Field(default_factory=list)


class CourseOutcome(BaseModel):
    co: str
    statement: str
    bloom: Optional[str] = None
    bloom_source: Optional[str] = None  # "printed" or "inferred"


class ProgrammeOutcome(BaseModel):
    po: str
    statement: str


class COPOMappingEntry(BaseModel):
    co: str
    po: str
    strength: Union[int, str]


class BookEntry(BaseModel):
    kind: str  # "text" or "reference"
    text: str


class Task2Response(BaseModel):
    course: CourseMeta
    units: List[UnitEntry] = Field(default_factory=list)
    course_outcomes: List[CourseOutcome] = Field(default_factory=list)
    programme_outcomes: List[ProgrammeOutcome] = Field(default_factory=list)
    co_po_matrix: List[COPOMappingEntry] = Field(default_factory=list)
    books: List[BookEntry] = Field(default_factory=list)
    not_extracted: List[str] = Field(default_factory=list)
