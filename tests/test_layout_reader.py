import pymupdf
import pytest
from syllabus_extractor.reader import PDFDocumentReader, PDFPage


def test_reader_layout_words_and_tables(tmp_path):
    pdf_path = str(tmp_path / "layout_sample.pdf")
    doc = pymupdf.open()
    
    # Page 1 with text and table layout
    p1 = doc.new_page()
    p1.insert_text((50, 70), "CS101 PROGRAMMING IN PYTHON\nCredits: 4", fontsize=12)
    p1.draw_rect(pymupdf.Rect(50, 100, 300, 180))  # Table border
    p1.draw_line(pymupdf.Point(50, 140), pymupdf.Point(300, 140))
    p1.draw_line(pymupdf.Point(175, 100), pymupdf.Point(175, 180))
    p1.insert_text((60, 125), "Lecture", fontsize=10)
    p1.insert_text((185, 125), "3 Hours", fontsize=10)
    p1.insert_text((60, 165), "Practical", fontsize=10)
    p1.insert_text((185, 165), "2 Hours", fontsize=10)

    # Page 2
    p2 = doc.new_page()
    p2.insert_text((50, 70), "UNIT I: BASICS OF PYTHON\nVariables - Data types - Control structures.", fontsize=11)

    doc.save(pdf_path)
    doc.close()

    reader = PDFDocumentReader(pdf_path)

    # 1. Page count and page mapping
    assert len(reader.pages) == 2
    assert 1 in reader.page_map
    assert 2 in reader.page_map

    p1_obj = reader.get_page(1)
    assert p1_obj.page_num == 1
    assert "CS101" in p1_obj.raw_text
    # Check whitespace normalized copy
    assert "CS101 PROGRAMMING IN PYTHON Credits: 4" in p1_obj.normalized_text

    # 2. Word positions
    assert len(p1_obj.words) > 0
    first_word = p1_obj.words[0]
    assert "word" in first_word
    assert "bbox" in first_word
    assert len(first_word["bbox"]) == 4  # (x0, y0, x1, y1)

    # 3. Confidence on native digital text
    assert p1_obj.confidence == 1.0
    assert not p1_obj.is_ocr

    # 4. Normalized text per page vs full document
    assert "CS101" in reader.get_normalized_text(1)
    assert "BASICS OF PYTHON" in reader.get_normalized_text(2)
    assert "CS101" in reader.get_normalized_text() and "BASICS OF PYTHON" in reader.get_normalized_text()


def test_reader_empty_scanned_page_handling(tmp_path):
    pdf_path = str(tmp_path / "scanned_blank.pdf")
    doc = pymupdf.open()
    # Create empty page without text layer
    doc.new_page()
    doc.save(pdf_path)
    doc.close()

    reader = PDFDocumentReader(pdf_path)
    p = reader.get_page(1)
    assert p is not None
    # Marked as low confidence when text layer is empty
    assert p.confidence < 1.0
