import os
import json
import subprocess
import pymupdf
import pytest
from syllabus_extractor.models import Task1Response


def create_sample_syllabus_pdf(output_path: str):
    """
    Creates a realistic sample syllabus PDF with TOC/Curriculum Scheme and Course Syllabus sections.
    """
    doc = pymupdf.open()

    # Page 1: Title and Scheme of Instruction
    p1 = doc.new_page()
    p1_text = """
    ABC INSTITUTE OF TECHNOLOGY
    CURRICULUM & SCHEME OF INSTRUCTION (R2023)
    DEPARTMENT OF COMPUTER SCIENCE AND ENGINEERING

    SEMESTER III
    S.No  Course Code  Course Title                 L  T  P  C
    1.    MA23101      ENGINEERING MATHEMATICS III  3  1  0  4
    2.    CS23301      DATA STRUCTURES              3  0  0  3
    3.    CS23302      OBJECT ORIENTED PROGRAMMING  3  0  2  4
    """
    p1.insert_text((50, 70), p1_text, fontsize=11)

    # Page 2: Mathematics Syllabus
    p2 = doc.new_page()
    p2_text = """
    MA23101: ENGINEERING MATHEMATICS III
    L T P C: 3 1 0 4

    COURSE OBJECTIVES:
    To introduce Fourier series and partial differential equations.

    UNIT I: FOURIER SERIES (9 Hours)
    Dirichlet's conditions - General Fourier series - Half range sine and cosine series - Parseval's identity.

    UNIT II: PARTIAL DIFFERENTIAL EQUATIONS (9 Hours)
    Formation of PDEs - Solutions of standard types of first order PDEs - Lagrange's linear equation.
    """
    p2.insert_text((50, 70), p2_text, fontsize=11)

    # Page 3: Data Structures Syllabus
    p3 = doc.new_page()
    p3_text = """
    CS23301 - DATA STRUCTURES
    Category: PC | L T P C: 3 0 0 3

    COURSE OBJECTIVES:
    Understand linear and non-linear data structures.

    UNIT I: LINEAR DATA STRUCTURES (9 Hours)
    Arrays - Linked lists - Singly linked list - Doubly linked list - Applications of lists.

    UNIT II: STACKS AND QUEUES (9 Hours)
    Stack ADT - Array and linked implementation - Applications of stacks - Queue ADT - Circular queue.
    """
    p3.insert_text((50, 70), p3_text, fontsize=11)

    # Page 4: Object Oriented Programming Syllabus
    p4 = doc.new_page()
    p4_text = """
    CS23302: OBJECT ORIENTED PROGRAMMING
    L T P C: 3 0 2 4

    COURSE OBJECTIVES:
    To learn object-oriented paradigms in C++ and Java.

    UNIT I: OOP BASICS (9 Hours)
    Classes and objects - Encapsulation - Inheritance - Polymorphism - Abstract classes.
    """
    p4.insert_text((50, 70), p4_text, fontsize=11)

    doc.save(output_path)
    doc.close()


def test_task1_discovery_and_cli(tmp_path):
    pdf_path = str(tmp_path / "TestCollege-R2023-CSE.pdf")
    create_sample_syllabus_pdf(pdf_path)

    # Run CLI
    cmd = ["python", "cli.py", "--pdf", pdf_path]
    result = subprocess.run(cmd, capture_output=True, text=True)

    assert result.returncode == 0, f"CLI failed with error: {result.stderr}"
    
    # Parse JSON
    data = json.loads(result.stdout)
    assert data["document"] == "TestCollege-R2023-CSE.pdf"
    assert data["course_count"] == 3
    
    codes = {c["code"]: c for c in data["courses"]}
    assert "MA23101" in codes
    assert "CS23301" in codes
    assert "CS23302" in codes

    # Check that starting pages point to the detailed syllabus pages (2, 3, 4)
    assert codes["MA23101"]["page"] == 2
    assert codes["CS23301"]["page"] == 3
    assert codes["CS23302"]["page"] == 4

    # Validate against Pydantic schema
    response_obj = Task1Response(**data)
    assert response_obj.course_count == 3


def test_task1_repeatability(tmp_path):
    pdf_path = str(tmp_path / "Repeatability-Test.pdf")
    create_sample_syllabus_pdf(pdf_path)

    cmd = ["python", "cli.py", "--pdf", pdf_path]

    # Run 3 consecutive times and verify bit-for-bit identity
    run1 = subprocess.run(cmd, capture_output=True, text=True).stdout
    run2 = subprocess.run(cmd, capture_output=True, text=True).stdout
    run3 = subprocess.run(cmd, capture_output=True, text=True).stdout

    assert run1 == run2 == run3, "Output was non-deterministic across repeated executions!"


def test_task1_real_world_layout_simulation(tmp_path):
    """
    Simulates a realistic college syllabus:
    Page 1: University cover page (Regulations 2023, CBCS, B.E. Computer Science)
    Page 2: Vision, Mission & PEOs
    Page 3: Curriculum table (lists CS23301 on page 3)
    Page 4: Detailed syllabus of MA23101 (page 4)
    Page 5-6: Detailed syllabus of CS23301 (true syllabus start page 5, NOT page 3!)
    Page 7: Detailed syllabus with no code (ENVIRONMENTAL SCIENCE, start page 7)
    """
    pdf_path = str(tmp_path / "AnnaUniv-CSE-R2023.pdf")
    doc = pymupdf.open()

    # Page 1: Cover Page (Must NOT be detected as a course)
    p1 = doc.new_page()
    p1.insert_text((50, 70), """
    ANNA UNIVERSITY, CHENNAI - 600 025
    REGULATIONS 2023 - CHOICE BASED CREDIT SYSTEM
    B.E. COMPUTER SCIENCE AND ENGINEERING
    I - VIII SEMESTERS CURRICULUM AND SYLLABI
    """, fontsize=12)

    # Page 2: Prelude (Must NOT be detected as a course)
    p2 = doc.new_page()
    p2.insert_text((50, 70), """
    VISION AND MISSION OF THE INSTITUTION
    PROGRAM EDUCATIONAL OBJECTIVES (PEOs)
    PEO 1: To provide sound foundation in mathematics and engineering.
    """, fontsize=11)

    # Page 3: Curriculum Table (Lists courses, but is NOT the syllabus body)
    p3 = doc.new_page()
    p3.insert_text((50, 70), """
    CURRICULUM & SCHEME OF INSTRUCTION
    SEMESTER III
    Sl.No  Course Code  Course Title                 L  T  P  C
    1.     MA23101      MATHEMATICS III              3  1  0  4
    2.     CS23301      DATA STRUCTURES              3  0  0  3
    3.     GE23101      ENVIRONMENTAL STUDIES        3  0  0  3
    """, fontsize=11)

    # Page 4: Mathematics detailed syllabus
    p4 = doc.new_page()
    p4.insert_text((50, 70), """
    MA23101 - MATHEMATICS III
    L T P C: 3 1 0 4
    COURSE OBJECTIVES:
    Fourier analysis and partial differential equations.
    UNIT I: FOURIER SERIES (9 Hours)
    Dirichlet conditions - Half range sine series - Parseval theorem.
    """, fontsize=11)

    # Page 5: Data Structures detailed syllabus (Page 5, NOT Page 3)
    p5 = doc.new_page()
    p5.insert_text((50, 70), """
    CS23301: DATA STRUCTURES
    Category: PC | L T P C: 3 0 0 3
    COURSE OBJECTIVES:
    Linear and non-linear data structures.
    UNIT I: LINEAR DATA STRUCTURES (9 Hours)
    Arrays - Linked lists - Singly linked list - Doubly linked list.
    """, fontsize=11)

    # Page 6: Data Structures Unit 2 & Outcomes
    p6 = doc.new_page()
    p6.insert_text((50, 70), """
    UNIT II: NON-LINEAR STRUCTURES (9 Hours)
    Trees - Binary search tree - Graph traversals.
    COURSE OUTCOMES:
    CO1: Implement linear data structures.
    """, fontsize=11)

    # Page 7: Environmental Studies with no code printed on header
    p7 = doc.new_page()
    p7.insert_text((50, 70), """
    ENVIRONMENTAL STUDIES
    L T P C: 3 0 0 3
    COURSE OBJECTIVES:
    Ecology and natural resources.
    UNIT I: ECOSYSTEMS (9 Hours)
    Structure and function of ecosystem - Food chains - Biodiversity.
    """, fontsize=11)

    doc.save(pdf_path)
    doc.close()

    cmd = ["python", "cli.py", "--pdf", pdf_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, f"Error: {result.stderr}"

    data = json.loads(result.stdout)
    
    # 1. Total courses should be exactly 3 (no cover page false positives!)
    assert data["course_count"] == 3
    
    codes = {c["code"]: c for c in data["courses"]}
    assert "MA23101" in codes
    assert "CS23301" in codes
    
    # 2. Start page must point to the real detailed syllabus page (4 and 5), NOT the curriculum table (page 3)!
    assert codes["MA23101"]["page"] == 4
    assert codes["CS23301"]["page"] == 5

    # 3. No cover page terms mistakenly extracted as courses
    titles = [c["title"].upper() for c in data["courses"]]
    for t in titles:
        assert "REGULATIONS" not in t
        assert "VISION" not in t
        assert "CURRICULUM" not in t


def test_task1_avit_multiline_headers(tmp_path):
    """
    Simulates the exact AVIT syllabus format from user images:
    Page 42:
      17CHBS01
      Environmental Science &
      Engineering
      (Common to All Branches)
      Category: BS | L:3 T:0 P:0 C:3
      Course Objectives ...
      Course Outcomes ...
    Page 214:
      17ECCC18
      INTERNET OF THINGS FOR
      ELECTRONICS
      Category: CC | L:3 T:0 P:0 Credit:3
      Course Objectives ...
      Course Outcomes ...
    """
    pdf_path = str(tmp_path / "AVIT-MultiLine-Test.pdf")
    doc = pymupdf.open()

    # Preceding dummy pages to simulate page 42 and 214
    for _ in range(41):
        doc.new_page()

    # Page 42
    p42 = doc.new_page()
    p42.insert_text((50, 70), """
    17CHBS01
    Environmental Science &
    Engineering
    (Common to All Branches)
    Category: BS | L: 3 T: 0 P: 0 C: 3
    Preamble
    Environmental science and Engineering is an interdisciplinary field...
    Course Objectives
    1. Applying Science and Engineering knowledge to protect environment
    Course Outcomes:
    CO1. Comprehend the impact of engineering solutions
    """, fontsize=11)

    for _ in range(171):
        doc.new_page()

    # Page 214
    p214 = doc.new_page()
    p214.insert_text((50, 70), """
    17ECCC18
    INTERNET OF THINGS FOR
    ELECTRONICS
    Category: CC | L: 3 T: 0 P: 0 Credit: 3
    PREAMBLE
    The purpose of this course is to impart knowledge on Internet of Things...
    COURSE OBJECTIVES
    1. Understanding of IoT value chain structure
    COURSE OUTCOMES
    CO1. Explain the concept of Internet of Things.
    """, fontsize=11)

    doc.save(pdf_path)
    doc.close()

    cmd = ["python", "cli.py", "--pdf", pdf_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, f"Error: {result.stderr}"

    data = json.loads(result.stdout)
    assert data["course_count"] == 2

    courses_map = {c["code"]: c for c in data["courses"]}
    
    assert "17CHBS01" in courses_map
    assert courses_map["17CHBS01"]["title"] == "Environmental Science & Engineering"
    assert courses_map["17CHBS01"]["page"] == 42

    assert "17ECCC18" in courses_map
    assert courses_map["17ECCC18"]["title"] == "INTERNET OF THINGS FOR ELECTRONICS"
    assert courses_map["17ECCC18"]["page"] == 214


def test_task1_tqm_exact_pages(tmp_path):
    """
    Simulates the exact Total Quality Management pages 22 & 23 from user images:
    Page 22:
      17MBHS04
      TOTAL QUALITY
      MANAGEMENT
      Category: HSS | L: 3 T: 0 P: 0 Credit: 3
      PREAMBLE: ...
    Page 23:
      QUALITY SYSTEMS
      Need for ISO 9000 and Other Quality Systems- ISO 9000:2000 Quality System ... QS 9000- ISO 14000
      TEXT BOOKS:
      1. Dale H.Besterfiled- et at. - Total Quality Management- PHI-1999. (Indian reprint 2002).
      REFERENCES:
      1. James R.Evans ...
    """
    pdf_path = str(tmp_path / "TQM-Test.pdf")
    doc = pymupdf.open()

    for _ in range(21):
        doc.new_page()

    # Page 22
    p22 = doc.new_page()
    p22.insert_text((50, 70), """
    17MBHS04
    TOTAL QUALITY
    MANAGEMENT
    Category: HSS | L: 3 T: 0 P: 0 Credit: 3
    PREAMBLE:
    To introduce quality management principles.
    COURSE OBJECTIVES
    1. To understand TQM concepts
    COURSE OUTCOMES
    CO1. Explain quality concepts
    """, fontsize=11)

    # Page 23 (Units 4-5 and Textbooks - MUST NOT produce any courses)
    p23 = doc.new_page()
    p23.insert_text((50, 70), """
    QUALITY SYSTEMS
    Need for ISO 9000 and Other Quality Systems- ISO 9000:2000 Quality System – Elements- Implementation of
    Quality System- Documentation- Quality Auditing- QS 9000- ISO 14000 – Concept- Requirements and Benefits.
    TEXT BOOKS:
    1. Dale H.Besterfiled- et at. - Total Quality Management- PHI-1999. (Indian reprint 2002).
    2. Feigenbaum.A.V. "Total Quality Management- McGraw-Hill- 1991.
    REFERENCES:
    1. James R.Evans & William M.Lidsay - (ISBN 0-324-06680-5).
    """, fontsize=11)

    doc.save(pdf_path)
    doc.close()

    cmd = ["python", "cli.py", "--pdf", pdf_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, f"Error: {result.stderr}"

    data = json.loads(result.stdout)
    
    # Must have EXACTLY 1 course (17MBHS04) and ZERO false positives from page 23
    assert data["course_count"] == 1
    course = data["courses"][0]
    assert course["code"] == "17MBHS04"
    assert course["title"] == "TOTAL QUALITY MANAGEMENT"
    assert course["page"] == 22




