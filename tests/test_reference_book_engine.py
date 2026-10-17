"""
tests/test_reference_book_engine.py - Tests for Reference Book Engine & Deep Subtopic Locator.
"""
import os
import pytest
import fitz
from reference_book_engine import (
    _get_bs_grewal_toc,
    find_subtopic_in_book,
    search_all_subtopics_in_book,
    _extract_clean_toc,
    get_cached_book
)

BS_GREWAL_PATH = "uploaded_reference_books/695353477-BS-Grewal.pdf"


def test_bs_grewal_toc_structure():
    """Verify Dr. B.S. Grewal TOC contains all 38 verified chapters with correct scan offset (+14)."""
    toc = _get_bs_grewal_toc(1327)
    assert len(toc) == 38, f"Expected 38 chapters, got {len(toc)}"
    
    # Check Chapter 1
    assert toc[0]["title"] == "Unit 1: Solution of Equations"
    assert toc[0]["start"] == 1
    assert toc[0]["pdf_start"] == 15
    
    # Check Chapter 8 Vector Calculus
    ch8 = toc[7]
    assert "Vector Calculus" in ch8["title"]
    assert ch8["start"] == 315
    assert ch8["pdf_start"] == 329
    
    # Check Chapter 21 Laplace Transforms
    ch21 = toc[20]
    assert "Laplace Transforms" in ch21["title"]
    assert ch21["start"] == 726
    assert ch21["pdf_start"] == 740
    
    # Check Chapter 28 Numerical Solution of Equations
    ch28 = toc[27]
    assert "Numerical Solution of Equations" in ch28["title"]
    assert ch28["start"] == 918
    assert ch28["pdf_start"] == 932
    
    # Check Chapter 32 Numerical Solution of ODEs
    ch32 = toc[31]
    assert "Numerical Solution of Ordinary Differential Equations" in ch32["title"]
    assert ch32["start"] == 1008
    assert ch32["pdf_start"] == 1022


def test_find_subtopic_vector_calculus():
    """Verify searching for 'Vector Calculus' returns Chapter 8 starting on scan page 329 (printed page 315)."""
    if not os.path.exists(BS_GREWAL_PATH):
        pytest.skip("BS Grewal PDF not present in environment")
    
    res = find_subtopic_in_book(BS_GREWAL_PATH, "Vector Calculus")
    assert res["found"] is True
    assert res["pdf_start"] == 329, f"Expected pdf_start 329, got {res.get('pdf_start')}"
    assert res["start_page"] == 315, f"Expected start_page 315, got {res.get('start_page')}"
    assert "Vector Calculus" in res["matched_title"]


def test_find_subtopic_greens_and_stokes_and_gauss():
    """Verify Green's, Stokes', and Gauss Divergence theorems map accurately within Chapter 8."""
    if not os.path.exists(BS_GREWAL_PATH):
        pytest.skip("BS Grewal PDF not present in environment")
    
    green = find_subtopic_in_book(BS_GREWAL_PATH, "Green's Theorem")
    assert green["found"] is True
    assert green["pdf_start"] == 360, f"Expected Green's theorem on scan 360, got {green.get('pdf_start')}"
    assert green["start_page"] == 346
    
    stokes = find_subtopic_in_book(BS_GREWAL_PATH, "Stokes' Theorem")
    assert stokes["found"] is True
    assert stokes["pdf_start"] == 365, f"Expected Stokes' theorem on scan 365, got {stokes.get('pdf_start')}"
    assert stokes["start_page"] == 351

    gauss = find_subtopic_in_book(BS_GREWAL_PATH, "Gauss Divergence Theorem")
    assert gauss["found"] is True
    assert gauss["pdf_start"] == 370, f"Expected Gauss theorem on scan 370, got {gauss.get('pdf_start')}"
    assert gauss["start_page"] == 356


def test_find_subtopic_runge_kutta():
    """Verify searching for 'Runge Kutta' returns scan page 1031 (printed page 1017)."""
    if not os.path.exists(BS_GREWAL_PATH):
        pytest.skip("BS Grewal PDF not present in environment")
    
    res = find_subtopic_in_book(BS_GREWAL_PATH, "Runge Kutta")
    assert res["found"] is True
    assert res["pdf_start"] == 1031, f"Expected pdf_start 1031, got {res.get('pdf_start')}"
    assert res["start_page"] == 1017, f"Expected start_page 1017, got {res.get('start_page')}"


def test_find_subtopic_laplace():
    """Verify searching for 'Laplace Transforms' returns scan page 740 (printed page 726)."""
    if not os.path.exists(BS_GREWAL_PATH):
        pytest.skip("BS Grewal PDF not present in environment")
    
    res = find_subtopic_in_book(BS_GREWAL_PATH, "Laplace Transforms")
    assert res["found"] is True
    assert res["pdf_start"] == 740, f"Expected pdf_start 740, got {res.get('pdf_start')}"
    assert res["start_page"] == 726, f"Expected start_page 726, got {res.get('start_page')}"


def test_find_subtopic_newton_raphson():
    """Verify searching for 'Newton Raphson' returns Chapter 28."""
    if not os.path.exists(BS_GREWAL_PATH):
        pytest.skip("BS Grewal PDF not present in environment")
    
    res = find_subtopic_in_book(BS_GREWAL_PATH, "Newton Raphson")
    assert res["found"] is True
    # Either section 28.3 (printed 926 / scan 940) or chapter start (printed 918 / scan 932)
    assert res["pdf_start"] in [932, 940]


def test_search_all_subtopics_in_book_multi_results():
    """Verify search_all_subtopics_in_book returns ranked list of matching topics."""
    if not os.path.exists(BS_GREWAL_PATH):
        pytest.skip("BS Grewal PDF not present in environment")
    
    results = search_all_subtopics_in_book(BS_GREWAL_PATH, "Vector Calculus", limit=5)
    assert len(results) > 0
    top = results[0]
    assert top["pdf_start"] == 329
    assert top["start_page"] == 315


def test_general_reference_book_digital_search(tmp_path):
    """Verify that search_all_subtopics_in_book and find_subtopic_in_book work dynamically for ANY uploaded reference book with digital text."""
    test_pdf = str(tmp_path / "general_ref_book.pdf")
    doc = fitz.open()
    
    # Page 1: Title
    p1 = doc.new_page()
    p1.insert_text((50, 50), "Advanced Operating Systems Reference Manual\nAuthor: Andrew Tanenbaum", fontsize=14)
    
    # Page 2: Table of Contents
    p2 = doc.new_page()
    p2.insert_text((50, 50), "Contents\nChapter 1: Process Management ....... 3\nChapter 2: Memory Virtualization ....... 4\nChapter 3: File System Implementation ....... 5", fontsize=12)
    
    # Page 3: Process Management
    p3 = doc.new_page()
    p3.insert_text((50, 50), "Chapter 1: Process Management\nProcess control blocks (PCB), CPU scheduling, context switching, and inter-process communication.", fontsize=12)
    
    # Page 4: Memory Virtualization
    p4 = doc.new_page()
    p4.insert_text((50, 50), "Chapter 2: Memory Virtualization\nPaging, segmentation, TLB caches, and page replacement algorithms including LRU and Clock.", fontsize=12)
    
    # Page 5: File System Implementation
    p5 = doc.new_page()
    p5.insert_text((50, 50), "Chapter 3: File System Implementation\nInodes, directory structures, journaling, and disk block allocation algorithms.", fontsize=12)
    
    doc.save(test_pdf)
    doc.close()
    
    # Test subtopic search on this general reference book
    res_sched = find_subtopic_in_book(test_pdf, "CPU scheduling")
    assert res_sched["found"] is True
    assert res_sched["start_page"] == 3, f"Expected page 3, got {res_sched.get('start_page')}"
    assert "Process Management" in res_sched["snippet"] or "scheduling" in res_sched["snippet"]
    
    res_lru = find_subtopic_in_book(test_pdf, "page replacement")
    assert res_lru["found"] is True
    assert res_lru["start_page"] == 4, f"Expected page 4, got {res_lru.get('start_page')}"
    
    # Test search_all_subtopics_in_book on this general reference book
    all_res = search_all_subtopics_in_book(test_pdf, "Inodes")
    assert len(all_res) > 0
    assert all_res[0]["start_page"] == 5


def test_extract_from_open_library():
    """Verify online catalog lookup cleans queries, resolves authors, and returns metadata safely."""
    from extract_topic_pages import extract_from_open_library
    res = extract_from_open_library("Higher Engineering Mathematics by Dr. B.S. Grewal (Khanna Publishers)")
    assert res is not None
    assert "Higher Engineering Mathematics" in res["book_title"]
    assert "B.S. Grewal" in res["author"]
    assert "topics" in res
    assert "openlibrary_url" in res
