"""
Gold-Set Evaluation Harness for Syllabus Extractor & Verification Studio.

Compares automated extraction results against hand-labeled ground-truth JSON
to calculate precision, recall, and F1 metrics across diverse university syllabi.
"""

import os
import sys
import json
import argparse
from typing import Dict, Any, List

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from syllabus_extractor.reader import PDFDocumentReader
from syllabus_extractor.task1_discovery import CourseDiscoveryEngine
from syllabus_extractor.task2_extractor import CourseDetailExtractor
from syllabus_extractor.llm_engine import LLMEngine


def compute_prf1(extracted_set: set, gold_set: set) -> Dict[str, float]:
    """Computes Precision, Recall, and F1-Score for two sets of string tokens."""
    if not gold_set and not extracted_set:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    if not gold_set or not extracted_set:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0}

    intersection = len(extracted_set & gold_set)
    precision = intersection / len(extracted_set) if extracted_set else 0.0
    recall = intersection / len(gold_set) if gold_set else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4)
    }


def evaluate_single_syllabus(pdf_path: str, gold_json_path: str, course_code: str = None) -> Dict[str, Any]:
    with open(gold_json_path, "r", encoding="utf-8") as f:
        gold = json.load(f)

    reader = PDFDocumentReader(pdf_path)
    engine = LLMEngine()

    # Task 1 Evaluation
    t1_engine = CourseDiscoveryEngine(reader)
    t1_resp = t1_engine.run()
    extracted_courses = {c.code.upper().strip() for c in t1_resp.courses if c.code}
    gold_courses = {c.upper().strip() for c in gold.get("courses", [])}
    t1_metrics = compute_prf1(extracted_courses, gold_courses)

    # Task 2 Evaluation (if course specified)
    target_code = course_code or gold.get("sample_course_code")
    t2_metrics = {}
    if target_code:
        t2_extractor = CourseDetailExtractor(reader, llm_engine=engine)
        t2_resp = t2_extractor.run(target_code)

        # Compare units
        gold_units = set(gold.get("units", []))
        extracted_units = {f"Unit {u.number}: {u.title.strip().upper()}" for u in t2_resp.units}
        units_f1 = compute_prf1(extracted_units, gold_units)

        # Compare Course Outcomes
        gold_cos = set(gold.get("course_outcomes", []))
        extracted_cos = {co.co.upper().strip() for co in t2_resp.course_outcomes}
        cos_f1 = compute_prf1(extracted_cos, gold_cos)

        # Compare Books
        gold_books_count = len(gold.get("books", []))
        extracted_books_count = len(t2_resp.books)

        t2_metrics = {
            "course": target_code,
            "units_f1": units_f1["f1"],
            "cos_f1": cos_f1["f1"],
            "books_extracted": extracted_books_count,
            "books_gold": gold_books_count
        }

    return {
        "document": os.path.basename(pdf_path),
        "task1": t1_metrics,
        "task2": t2_metrics
    }


def run_benchmark():
    eval_dir = os.path.dirname(os.path.abspath(__file__))
    gold_dir = os.path.join(eval_dir, "gold_samples")
    os.makedirs(gold_dir, exist_ok=True)

    gold_files = [f for f in os.listdir(gold_dir) if f.endswith(".json")]
    if not gold_files:
        print("No gold standard JSON files found in evaluation/gold_samples/.")
        print(f"Place your labeled ground truth JSON files in: {gold_dir}")
        return

    print("=" * 80)
    print("         SYLLABUS EXTRACTOR & VERIFICATION BENCHMARK SUITE")
    print("=" * 80)
    print(f"{'Document':<30} | {'T1 Prec':<8} | {'T1 Rec':<8} | {'T1 F1':<8} | {'Units F1':<9} | {'COs F1':<8}")
    print("-" * 80)

    for gf in gold_files:
        full_gold_p = os.path.join(gold_dir, gf)
        try:
            with open(full_gold_p, "r", encoding="utf-8") as f:
                data = json.load(f)
            pdf_name = data.get("pdf_filename", "")
            base_dir = os.path.abspath(os.path.join(eval_dir, ".."))
            pdf_path = os.path.join(base_dir, "uploaded_syllabi", pdf_name)
            if not os.path.exists(pdf_path):
                pdf_path = os.path.join(base_dir, pdf_name)

            if not os.path.exists(pdf_path):
                print(f"{pdf_name:<30} | ERROR: PDF file not found")
                continue

            res = evaluate_single_syllabus(pdf_path, full_gold_p)
            t1 = res["task1"]
            t2 = res.get("task2", {})
            u_f1 = f"{t2.get('units_f1', 0.0):.2f}" if "units_f1" in t2 else "N/A"
            co_f1 = f"{t2.get('cos_f1', 0.0):.2f}" if "cos_f1" in t2 else "N/A"

            print(f"{res['document'][:30]:<30} | {t1['precision']:<8.2f} | {t1['recall']:<8.2f} | {t1['f1']:<8.2f} | {u_f1:<9} | {co_f1:<8}")
        except Exception as e:
            print(f"{gf:<30} | Failed: {str(e)}")

    print("=" * 80)


if __name__ == "__main__":
    run_benchmark()
