import sys
import os
import json
import argparse
from syllabus_extractor.reader import PDFDocumentReader
from syllabus_extractor.task1_discovery import CourseDiscoveryEngine
from syllabus_extractor.task2_extractor import CourseDetailExtractor
from syllabus_extractor.llm_engine import LLMEngine


def main():
    parser = argparse.ArgumentParser(
        description="Deterministic Syllabus Extraction Engine (Task 1 & Task 2) with LLM boundary assistance and strict verification.",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--pdf",
        type=str,
        required=True,
        help="Path to the syllabus PDF file"
    )
    parser.add_argument(
        "--course",
        type=str,
        default=None,
        help="Course code or title to extract in full (Task 2)"
    )
    parser.add_argument(
        "--llm-provider",
        type=str,
        default=None,
        choices=["gemini", "openai", "anthropic", "groq", "deepseek", "ollama", "heuristic"],
        help="LLM provider for variable boundary resolution (default: auto-detected from environment)"
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="API Key for the chosen LLM provider (or set via environment variable)"
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model name (e.g. gemini-1.5-flash, gpt-4o-mini, llama3)"
    )

    args = parser.parse_args()

    if not os.path.exists(args.pdf):
        sys.stderr.write(f"Error: PDF file '{args.pdf}' not found.\n")
        sys.exit(1)

    try:
        reader = PDFDocumentReader(args.pdf)
        llm_engine = LLMEngine(
            provider=args.llm_provider,
            api_key=args.api_key,
            model=args.model
        )

        if args.course is None:
            # Task 1: List all courses in the document
            engine = CourseDiscoveryEngine(reader)
            response = engine.run()
            
            # Print formatted JSON to stdout
            print(json.dumps(response.model_dump(), indent=2, ensure_ascii=False))
            sys.exit(0)
        else:
            # Task 2: Deep course extraction with LLM boundary assistance & grounding verification
            extractor = CourseDetailExtractor(reader, llm_engine=llm_engine)
            response = extractor.run(args.course)
            
            # Print formatted JSON to stdout
            print(json.dumps(response.model_dump(), indent=2, ensure_ascii=False))
            sys.exit(0)

    except Exception as e:
        sys.stderr.write(f"Execution Error: {str(e)}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
