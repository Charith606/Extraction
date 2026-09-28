"""
Syllabus Extractor Package
"""
from .models import (
    CourseEntry, Task1Response, CourseMeta, TopicEntry,
    UnitEntry, CourseOutcome, ProgrammeOutcome, COPOMappingEntry,
    BookEntry, Task2Response
)
from .reader import PDFPage, PDFDocumentReader
from .task1_discovery import CourseDiscoveryEngine
from .task2_extractor import CourseDetailExtractor
from .verification import VerificationLayer
from .llm_helper import LLMLineRangeBoundaryHelper
from .llm_engine import LLMEngine

__all__ = [
    "CourseEntry",
    "Task1Response",
    "CourseMeta",
    "TopicEntry",
    "UnitEntry",
    "CourseOutcome",
    "ProgrammeOutcome",
    "COPOMappingEntry",
    "BookEntry",
    "Task2Response",
    "PDFPage",
    "PDFDocumentReader",
    "CourseDiscoveryEngine",
    "CourseDetailExtractor",
    "VerificationLayer",
    "LLMLineRangeBoundaryHelper",
    "LLMEngine"
]
