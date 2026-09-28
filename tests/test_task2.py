import json
import subprocess
import pytest
import pymupdf
from syllabus_extractor.task2_bloom import infer_bloom_from_text, normalize_printed_bloom


def test_bloom_classifier():
    assert normalize_printed_bloom("Understand") == "understand"
    assert normalize_printed_bloom("Analysing") == "analyse"
    assert normalize_printed_bloom("K3") == "apply"
    assert normalize_printed_bloom("L5") == "evaluate"
    assert normalize_printed_bloom("Create") == "create"

    lvl, src = infer_bloom_from_text("Design an optimal manufacturing process")
    assert lvl == "create"
    assert src == "inferred"

    lvl, src = infer_bloom_from_text("Calculate heat transfer coefficient")
    assert lvl == "apply"
    assert src == "inferred"

    lvl, src = infer_bloom_from_text("Explain the working principle of laser")
    assert lvl == "understand"
    assert src == "inferred"


def test_task2_end_to_end_synthetic(tmp_path):
    pdf_path = str(tmp_path / "CS101-Test.pdf")
    doc = pymupdf.open()
    
    # Page 1: Course Start
    p1 = doc.new_page()
    p1.insert_text((50, 70), """
    CS101
    DATA STRUCTURES AND ALGORITHMS
    Category
    L
    T
    P
    Credit
    PC
    3
    1
    0
    4
    PREAMBLE
    Basic fundamentals of data structures.
    COURSE OBJECTIVES:
    1. To study basic data structures.
    COURSE OUTCOMES:
    CO1: Understand array and linked list structures.
    Understand
    CO2: Design efficient graph algorithms.
    Create
    MAPPING WITH PROGRAMME OUTCOMES
    COs PO1 PO2 PO3 PO4 PO5 PO6 PO7 PO8 PO9 PO10 PO11 PO12 PSO1 PSO2 PSO3
    CO1 3 2 1 - - - - - - - - - 2 - -
    CO2 3 3 3 2 2 - - - - - - - 3 2 1
    SYLLABUS:
    UNIT I - LINEAR DATA STRUCTURES
    Arrays - Singly linked list - Doubly linked list - Circular linked list - Stacks - Queues.
    UNIT II - NON LINEAR DATA STRUCTURES
    Trees - Binary search tree - AVL tree - Graph representations - BFS - DFS.
    TEXT BOOKS:
    1. Mark Allen Weiss - Data Structures and Algorithm Analysis in C++ - Pearson 2014.
    REFERENCES:
    1. Cormen et al. - Introduction to Algorithms - MIT Press 2009.
    """, fontsize=11)
    
    doc.save(pdf_path)
    doc.close()

    cmd = ["python", "cli.py", "--pdf", pdf_path, "--course", "CS101"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0, f"Error: {result.stderr}"

    data = json.loads(result.stdout)
    assert data["course"]["code"] == "CS101"
    assert data["course"]["title"] == "DATA STRUCTURES AND ALGORITHMS"
    assert data["course"]["category"] == "PC"
    assert data["course"]["credits"] == 4
    assert data["course"]["lecture"] == 3
    assert data["course"]["tutorial"] == 1
    assert data["course"]["practical"] == 0

    assert len(data["units"]) == 2
    assert data["units"][0]["number"] == 1
    assert data["units"][0]["title"] == "LINEAR DATA STRUCTURES"
    assert len(data["units"][0]["topics"]) >= 4
    assert data["units"][0]["topics"][0]["id"] == "T1"
    assert data["units"][0]["topics"][0]["text"] == "Arrays"
    assert data["units"][0]["topics"][0]["bloom"] in ["remember", "understand", "apply", "analyse", "evaluate", "create"]

    assert len(data["course_outcomes"]) == 2
    assert data["course_outcomes"][0]["co"] == "CO1"
    assert data["course_outcomes"][0]["bloom"] == "understand"
    assert data["course_outcomes"][0]["bloom_source"] == "printed"
    assert data["course_outcomes"][1]["bloom"] == "create"

    # co_po_matrix contains only mapped pairs
    assert len(data["co_po_matrix"]) > 0
    co1_po1 = next((m for m in data["co_po_matrix"] if m["co"] == "CO1" and m["po"] == "PO1"), None)
    assert co1_po1 is not None
    assert co1_po1["strength"] == 3

    # books list with kind and text
    textbooks = [b for b in data["books"] if b["kind"] == "text"]
    references = [b for b in data["books"] if b["kind"] == "reference"]
    assert len(textbooks) == 1
    assert "Mark Allen Weiss" in textbooks[0]["text"]
    assert len(references) == 1
    assert "Cormen" in references[0]["text"]


def test_task2_unknown_course(tmp_path):
    pdf_path = str(tmp_path / "Dummy.pdf")
    doc = pymupdf.open()
    p = doc.new_page()
    p.insert_text((50, 70), "Some text without courses")
    doc.save(pdf_path)
    doc.close()

    cmd = ["python", "cli.py", "--pdf", pdf_path, "--course", "NONEXISTENT99"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0

    data = json.loads(result.stdout)
    assert data["course"]["code"] == "NONEXISTENT99"
    assert "course" in data["not_extracted"]


def test_task2_determinism(tmp_path):
    pdf_path = str(tmp_path / "Determinism.pdf")
    doc = pymupdf.open()
    p = doc.new_page()
    p.insert_text((50, 70), """
    MA101
    ENGINEERING MATHEMATICS
    Category: BS | L: 3 T: 1 P: 0 Credit: 4
    COURSE OUTCOMES:
    CO1: Solve linear differential equations.
    Apply
    SYLLABUS:
    UNIT I - MATRICES
    Eigen values - Eigen vectors - Cayley Hamilton theorem.
    TEXT BOOKS:
    1. Grewal B.S. - Higher Engineering Mathematics - Khanna Publishers.
    """)
    doc.save(pdf_path)
    doc.close()

    outputs = []
    for _ in range(3):
        cmd = ["python", "cli.py", "--pdf", pdf_path, "--course", "MA101"]
        res = subprocess.run(cmd, capture_output=True, text=True)
        assert res.returncode == 0
        outputs.append(res.stdout)

    assert outputs[0] == outputs[1] == outputs[2]
