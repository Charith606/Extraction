import json
import subprocess
import pymupdf
import pytest
from syllabus_extractor.llm_helper import LLMLineRangeBoundaryHelper
from syllabus_extractor.llm_engine import LLMEngine


def test_hash_caching_determinism():
    llm = LLMEngine(provider="heuristic")
    helper = LLMLineRangeBoundaryHelper(llm_engine=llm)
    lines = [
        "CS201 DATA STRUCTURES",
        "Category: PC | L T P C: 3 0 0 3",
        "COURSE OBJECTIVES:",
        "To understand trees and graphs.",
        "COURSE OUTCOMES:",
        "CO1: Implement graph algorithms.",
        "MAPPING WITH PROGRAMME OUTCOMES",
        "COs PO1 PO2",
        "CO1 3 2",
        "SYLLABUS:",
        "UNIT I: TREES (9 Hours)",
        "Binary trees - AVL trees - Red-black trees.",
        "TEXT BOOKS:",
        "1. Cormen et al. - Introduction to Algorithms.",
        "REFERENCES:",
        "1. Sedgewick - Algorithms."
    ]

    hash1 = llm.get_hash("sys_prompt", "user_prompt")
    hash2 = llm.get_hash("sys_prompt", "user_prompt")
    assert hash1 == hash2

    res1 = helper.identify_section_ranges(lines)
    res2 = helper.identify_section_ranges(lines)
    res3 = helper.identify_section_ranges(lines)

    assert res1 == res2 == res3
    assert res1["course_outcomes"] is not None
    assert res1["units"] is not None
    assert res1["books"] is not None


def test_llm_engine_caching():
    llm = LLMEngine(provider="heuristic")
    # Store synthetic response in cache
    prompt = "identify ranges"
    text = "line 0\nline 1\nline 2"
    h = llm.get_hash(prompt, text)
    llm.cache[h] = json.dumps({"units": [0, 1], "course_outcomes": [2, 2]})

    resp = llm.generate(prompt, text)
    assert resp is not None
    data = json.loads(resp)
    assert data["units"] == [0, 1]
    assert data["course_outcomes"] == [2, 2]


def test_cli_three_run_diff_determinism(tmp_path):
    pdf_path = str(tmp_path / "DeterminismTripleTest.pdf")
    doc = pymupdf.open()
    
    # Page 1: Curriculum Scheme Table
    p1 = doc.new_page()
    p1.insert_text((50, 70), """
    CURRICULUM SCHEME
    1. EC101 ELECTRONIC CIRCUITS 3 0 0 3
    2. CS101 DATA STRUCTURES 3 0 0 3
    """)

    # Page 2: EC101 Syllabus
    p2 = doc.new_page()
    p2.insert_text((50, 70), """
    EC101: ELECTRONIC CIRCUITS
    Category: PC | L T P C: 3 0 0 3
    COURSE OBJECTIVES:
    To study diode and transistor circuits.
    COURSE OUTCOMES:
    CO1: Analyze diode rectifier circuits. (Analyze)
    UNIT I: DIODE CIRCUITS (9 Hours)
    PN junction - Rectifiers - Filters - Zener diode regulators.
    TEXT BOOKS:
    1. Boylestad - Electronic Devices and Circuit Theory.
    """)

    doc.save(pdf_path)
    doc.close()

    # Run Task 1 CLI 3 times and diff
    t1_outputs = []
    for _ in range(3):
        res = subprocess.run(["python", "cli.py", "--pdf", pdf_path], capture_output=True, text=True)
        assert res.returncode == 0
        t1_outputs.append(res.stdout)

    assert t1_outputs[0] == t1_outputs[1] == t1_outputs[2], "Task 1 output is non-deterministic!"

    # Run Task 2 CLI 3 times and diff
    t2_outputs = []
    for _ in range(3):
        res = subprocess.run(["python", "cli.py", "--pdf", pdf_path, "--course", "EC101"], capture_output=True, text=True)
        assert res.returncode == 0
        t2_outputs.append(res.stdout)

    assert t2_outputs[0] == t2_outputs[1] == t2_outputs[2], "Task 2 output is non-deterministic!"
