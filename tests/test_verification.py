import pytest
from syllabus_extractor.models import (
    CourseMeta, TopicEntry, UnitEntry, CourseOutcome,
    ProgrammeOutcome, COPOMappingEntry, BookEntry, Task2Response
)
from syllabus_extractor.verification import VerificationLayer, ALLOWED_BLOOM_LEVELS


def test_verification_substring_grounding():
    source_text = """
    CS101 DATA STRUCTURES
    Category: PC
    UNIT I: LINEAR DATA STRUCTURES (9 Hours)
    Arrays - Singly linked list - Doubly linked list.
    COURSE OUTCOMES:
    CO1: Understand linear data structures.
    Understand
    TEXT BOOKS:
    1. Mark Allen Weiss - Data Structures.
    """

    # Create response with grounded and hallucinated/unsupported elements
    raw_response = Task2Response(
        course=CourseMeta(
            code="CS101",
            title="DATA STRUCTURES",
            category="PC",
            pages=[1]
        ),
        units=[
            UnitEntry(
                number=1,
                title="LINEAR DATA STRUCTURES",
                text="Arrays - Singly linked list - Doubly linked list.",
                topics=[
                    TopicEntry(id="T1", text="Arrays", bloom="understand", bloom_source="inferred"),
                    TopicEntry(id="T2", text="Singly linked list", bloom="understand", bloom_source="inferred"),
                    TopicEntry(id="T3", text="Hallucinated Quantum Trees", bloom="create", bloom_source="inferred"),  # Not in source!
                ]
            )
        ],
        course_outcomes=[
            CourseOutcome(co="CO1", statement="Understand linear data structures.", bloom="understand", bloom_source="printed"),
            CourseOutcome(co="CO2", statement="Design distributed quantum blockchain systems.", bloom="create", bloom_source="inferred"),  # Not in source!
        ],
        programme_outcomes=[],
        co_po_matrix=[],
        books=[
            BookEntry(kind="text", text="Mark Allen Weiss - Data Structures."),
            BookEntry(kind="text", text="Fake Book That Does Not Exist in Source")  # Not in source!
        ],
        not_extracted=[]
    )

    verified = VerificationLayer.verify(raw_response, block_source_text=source_text)

    # 1. Hallucinated topic dropped
    topic_names = [t.text for t in verified.units[0].topics]
    assert "Arrays" in topic_names
    assert "Singly linked list" in topic_names
    assert "Hallucinated Quantum Trees" not in topic_names
    assert any("Hallucinated Quantum Trees" in log for log in verified.not_extracted)

    # 2. Grounded CO kept, ungrounded CO statement cleared/dropped
    assert verified.course_outcomes[0].statement == "Understand linear data structures."
    assert verified.course_outcomes[1].statement == ""
    assert any("CO2 statement dropped" in log for log in verified.not_extracted)

    # 3. Grounded book kept, fake book dropped
    book_texts = [b.text for b in verified.books]
    assert "Mark Allen Weiss - Data Structures." in book_texts
    assert "Fake Book That Does Not Exist in Source" not in book_texts
    assert any("Fake Book" in log for log in verified.not_extracted)


def test_verification_co_po_matrix_consistency():
    source_text = """
    CS101 DATA STRUCTURES
    COURSE OUTCOMES:
    CO1: Understand basic data structures.
    MAPPING WITH PROGRAMME OUTCOMES
    COs PO1 PO2
    CO1 3 2
    CO5 3 1
    """

    raw_response = Task2Response(
        course=CourseMeta(code="CS101", title="DATA STRUCTURES", pages=[1]),
        units=[],
        course_outcomes=[
            CourseOutcome(co="CO1", statement="Understand basic data structures.", bloom="understand", bloom_source="inferred")
        ],
        programme_outcomes=[
            ProgrammeOutcome(po="PO1", statement="Engineering knowledge")
        ],
        co_po_matrix=[
            COPOMappingEntry(co="CO1", po="PO1", strength=3),
            COPOMappingEntry(co="CO1", po="PO2", strength=2),
            COPOMappingEntry(co="CO5", po="PO1", strength=3)  # CO5 not in course_outcomes!
        ],
        books=[],
        not_extracted=[]
    )

    verified = VerificationLayer.verify(raw_response, block_source_text=source_text, document_source_text=source_text)

    # CO5 not in outcomes list -> logged in not_extracted
    assert any("CO5" in log and "not found in course outcomes" in log for log in verified.not_extracted)
    # PO2 in CO1 mapping but not in programme_outcomes list -> logged in not_extracted
    assert any("PO2" in log and "not found in programme outcomes" in log for log in verified.not_extracted)


def test_verification_bloom_levels_and_source():
    source_text = """
    CS101 DATA STRUCTURES
    COURSE OUTCOMES:
    CO1: State definition of tree. (K1)
    CO2: Develop complex software algorithms.
    """

    raw_response = Task2Response(
        course=CourseMeta(code="CS101", title="DATA STRUCTURES", pages=[1]),
        units=[],
        course_outcomes=[
            CourseOutcome(co="CO1", statement="State definition of tree. (K1)", bloom="remember", bloom_source="printed"),
            # Marked printed, but "Create" or "K6" does NOT appear in source text!
            CourseOutcome(co="CO2", statement="Develop complex software algorithms.", bloom="create", bloom_source="printed"),
        ],
        programme_outcomes=[],
        co_po_matrix=[],
        books=[],
        not_extracted=[]
    )

    verified = VerificationLayer.verify(raw_response, block_source_text=source_text)

    # CO1 has K1 in source text -> stays "printed"
    assert verified.course_outcomes[0].bloom == "remember"
    assert verified.course_outcomes[0].bloom_source == "printed"

    # CO2 has no printed indicator -> downgraded to "inferred"
    assert verified.course_outcomes[1].bloom == "create"
    assert verified.course_outcomes[1].bloom_source == "inferred"
    assert any("CO2" in log and "bloom source changed" in log for log in verified.not_extracted)


def test_verification_nothing_lost_unit_accounting():
    source_text = """
    CS101 DATA STRUCTURES
    UNIT I: LINEAR DATA STRUCTURES
    Arrays - Singly linked list - Doubly linked list - Circular linked list - Skip lists - Stacks - Queues - Deques.
    """

    # Only extracted first 2 topics, losing "Skip lists", "Stacks", "Queues", "Deques"
    raw_response = Task2Response(
        course=CourseMeta(code="CS101", title="DATA STRUCTURES", pages=[1]),
        units=[
            UnitEntry(
                number=1,
                title="LINEAR DATA STRUCTURES",
                text="Arrays - Singly linked list - Doubly linked list - Circular linked list - Skip lists - Stacks - Queues - Deques.",
                topics=[
                    TopicEntry(id="T1", text="Arrays", bloom="understand", bloom_source="inferred"),
                    TopicEntry(id="T2", text="Singly linked list", bloom="understand", bloom_source="inferred"),
                ]
            )
        ],
        course_outcomes=[],
        programme_outcomes=[],
        co_po_matrix=[],
        books=[],
        not_extracted=[]
    )

    verified = VerificationLayer.verify(raw_response, block_source_text=source_text)

    # Should detect missing topics and log unit text unaccounted warning
    assert any("unit 1" in log and "topics do not fully account for unit text" in log for log in verified.not_extracted)
