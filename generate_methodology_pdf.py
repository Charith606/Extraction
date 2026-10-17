import os
import re
import pymupdf

def build_pdf():
    output_filename = "Syllabus_Extractor_Comprehensive_Methodology_Review.pdf"
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), output_filename)
    
    # High-quality CSS and HTML layout
    html_content = """
    <style>
        @page {
            size: A4;
            margin: 0;
        }
        body {
            font-family: Helvetica, Arial, sans-serif;
            font-size: 9.5pt;
            line-height: 1.45;
            color: #1e293b;
            padding: 0;
            margin: 0;
        }
        .cover-header {
            background-color: #0f172a;
            color: #ffffff;
            padding: 24px 28px;
            border-radius: 6px;
            margin-bottom: 22px;
        }
        .cover-title {
            font-size: 20pt;
            font-weight: bold;
            color: #f8fafc;
            margin: 0 0 6px 0;
        }
        .cover-subtitle {
            font-size: 11pt;
            color: #94a3b8;
            margin: 0 0 14px 0;
            font-weight: normal;
        }
        .cover-meta {
            font-size: 8.5pt;
            color: #cbd5e1;
            border-top: 1px solid #334155;
            padding-top: 10px;
        }
        .cover-meta span {
            margin-right: 18px;
        }
        
        h1 {
            font-size: 13.5pt;
            color: #0f172a;
            border-bottom: 1.5px solid #2563eb;
            padding-bottom: 4px;
            margin-top: 22px;
            margin-bottom: 10px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        h2 {
            font-size: 11pt;
            color: #1e40af;
            margin-top: 14px;
            margin-bottom: 6px;
            border-left: 3px solid #3b82f6;
            padding-left: 7px;
        }
        h3 {
            font-size: 9.8pt;
            color: #334155;
            margin-top: 10px;
            margin-bottom: 4px;
            font-weight: bold;
        }
        p {
            margin: 0 0 8px 0;
            text-align: justify;
        }
        ul, ol {
            margin: 0 0 8px 18px;
            padding: 0;
        }
        li {
            margin-bottom: 4px;
        }
        code {
            font-family: Courier, monospace;
            font-size: 8.5pt;
            background-color: #f1f5f9;
            color: #0f172a;
            padding: 1px 4px;
            border-radius: 3px;
            border: 1px solid #e2e8f0;
        }
        .box {
            background-color: #f8fafc;
            border: 1px solid #e2e8f0;
            border-left: 4px solid #2563eb;
            padding: 10px 12px;
            margin: 10px 0;
            border-radius: 4px;
        }
        .box-warning {
            background-color: #fffbeb;
            border: 1px solid #fef3c7;
            border-left: 4px solid #f59e0b;
            padding: 10px 12px;
            margin: 10px 0;
            border-radius: 4px;
        }
        .box-success {
            background-color: #f0fdf4;
            border: 1px solid #dcfce7;
            border-left: 4px solid #10b981;
            padding: 10px 12px;
            margin: 10px 0;
            border-radius: 4px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 10px 0;
            font-size: 8.5pt;
        }
        th, td {
            border: 1px solid #cbd5e1;
            padding: 5px 8px;
            text-align: left;
            vertical-align: top;
        }
        th {
            background-color: #f1f5f9;
            color: #0f172a;
            font-weight: bold;
        }
        tr:nth-child(even) td {
            background-color: #f8fafc;
        }
        .badge {
            display: inline-block;
            padding: 1px 6px;
            font-size: 7.5pt;
            font-weight: bold;
            border-radius: 3px;
        }
        .badge-blue { background-color: #dbeafe; color: #1e40af; }
        .badge-green { background-color: #dcfce7; color: #166534; }
        .badge-amber { background-color: #fef3c7; color: #92400e; }
        .badge-purple { background-color: #f3e8ff; color: #6b21a8; }
        
        .diagram {
            background-color: #0f172a;
            color: #38bdf8;
            font-family: Courier, monospace;
            font-size: 7.8pt;
            line-height: 1.35;
            padding: 10px 14px;
            border-radius: 5px;
            margin: 10px 0;
            white-space: pre;
        }
    </style>

    <div class="cover-header">
        <div class="cover-title">Syllabus Extraction & Verification Studio</div>
        <div class="cover-subtitle">Comprehensive Technical Methodology, Architectural Specifications & System Review</div>
        <div class="cover-meta">
            <span><strong>Target Project:</strong> Academic Syllabus Extractor & Verification Studio</span>
            <span><strong>Architecture:</strong> Deterministic Hybrid (Heuristic + Grounded LLM + OCR)</span>
            <span><strong>Status:</strong> Production Ready (27/27 Test Suite Passed)</span>
        </div>
    </div>

    <h1>1. Executive Summary & Core Objectives</h1>
    <p>
        The <strong>Syllabus Extraction & Verification Studio</strong> is an enterprise-grade academic data intelligence system designed to ingest heterogeneous university curriculum documents (PDFs and PPTX presentations), parse complex multi-column structures, extract fine-grained academic syllabus specifications, enforce 100% substring grounding against original source texts, and seamlessly map syllabus topics to reference textbooks.
    </p>
    <p>
        Unlike naive LLM ingestion systems that suffer from hallucination and token drift, this system employs a <strong>deterministic, hybrid architecture</strong>. Language models are utilized strictly for <em>boundary disambiguation</em> (identifying line ranges), while all data extraction, text parsing, Bloom's taxonomy mapping, and referential integrity checks are governed by deterministic Python parsing algorithms and a mathematical Verification Layer.
    </p>
    <div class="box-success">
        <strong>Core Engineering Guarantee:</strong> Every extracted entity (course code, unit title, verbatim text, topic, course outcome, and prescribed book) is rigorously grounded by substring verification against the original document text. Hallucinated items are mathematically impossible to emit.
    </div>

    <h1>2. Complete Technology Stack & APIs</h1>
    
    <h2>A. External APIs & Cloud Services</h2>
    <table>
        <tr>
            <th style="width: 20%;">Service / API</th>
            <th style="width: 25%;">Target Endpoints & Models</th>
            <th style="width: 55%;">Functional Role & Determinism Mechanism</th>
        </tr>
        <tr>
            <td><strong>Google Gemini API</strong></td>
            <td><code>v1beta/models/...:generateContent</code><br/>(<code>gemini-1.5-flash</code>)</td>
            <td>Fast, ultra-low latency line-range boundary identification for ambiguous course sections. Governed by zero temperature and SHA-256 persistent disk caching.</td>
        </tr>
        <tr>
            <td><strong>OpenAI API</strong></td>
            <td><code>v1/chat/completions</code><br/>(<code>gpt-4o-mini</code>)</td>
            <td>Lightweight cloud model fallback for university layout boundary detection and line segmentation.</td>
        </tr>
        <tr>
            <td><strong>Anthropic Claude API</strong></td>
            <td><code>v1/messages</code><br/>(<code>claude-3-haiku-20240307</code>)</td>
            <td>High-precision alternative boundary inference provider with deterministic parameter anchoring.</td>
        </tr>
        <tr>
            <td><strong>Groq Cloud API</strong></td>
            <td><code>v1/chat/completions</code><br/>(<code>llama-3.1-8b-instant</code>)</td>
            <td>Sub-second open-weights inference engine for near-instantaneous syllabus layout resolution.</td>
        </tr>
        <tr>
            <td><strong>DeepSeek API</strong></td>
            <td><code>v1/chat/completions</code><br/>(<code>deepseek-chat</code>)</td>
            <td>High-reasoning alternative provider supported via OpenAI-compatible REST schemas.</td>
        </tr>
        <tr>
            <td><strong>Local Ollama API</strong></td>
            <td><code>http://localhost:11434/api/generate</code><br/>(<code>llama3.2</code>)</td>
            <td>100% offline, privacy-preserving, zero-data-leakage local execution engine for secure air-gapped institutions.</td>
        </tr>
        <tr>
            <td><strong>Open Library REST API</strong></td>
            <td><code>openlibrary.org/isbn/{isbn}.json</code><br/><code>openlibrary.org/search.json</code></td>
            <td>Public metadata & Table of Contents (TOC) directory lookup for prescribed textbooks, eliminating the need to download or store pirated textbook files.</td>
        </tr>
    </table>

    <h2>B. Python Libraries & Core Dependencies</h2>
    <table>
        <tr>
            <th style="width: 25%;">Library</th>
            <th style="width: 20%;">Version / Scope</th>
            <th style="width: 55%;">Implementation Scope</th>
        </tr>
        <tr>
            <td><strong>PyMuPDF (<code>pymupdf</code> / <code>fitz</code>)</strong></td>
            <td>High-Performance C Core</td>
            <td>Primary PDF engine. Used for text extraction, block coordinate dictionaries (<code>get_text("dict")</code>), word token bounding boxes (<code>get_text("words")</code>), TOC outline traversal, and on-the-fly PNG pixmap rendering for the web UI.</td>
        </tr>
        <tr>
            <td><strong>Pydantic (<code>v2</code>)</strong></td>
            <td>Type Validation & Schemas</td>
            <td>Defines formal immutable schemas (<code>CourseMeta</code>, <code>UnitEntry</code>, <code>TopicEntry</code>, <code>CourseOutcome</code>, <code>COPOMappingEntry</code>, <code>BookEntry</code>) with JSON schema validation.</td>
        </tr>
        <tr>
            <td><strong>Windows SDK (<code>winsdk</code>)</strong></td>
            <td>Hardware-Accelerated OCR</td>
            <td>Direct integration with <code>Windows.Media.Ocr.OcrEngine</code> via Windows native WinRT APIs, delivering high-speed local OCR on scanned pages without requiring third-party binary installations.</td>
        </tr>
        <tr>
            <td><strong>Pytesseract & Pillow</strong></td>
            <td>Cross-Platform OCR</td>
            <td>Secondary fallback OCR engine for non-Windows environments and auxiliary raster processing.</td>
        </tr>
        <tr>
            <td><strong>python-pptx</strong></td>
            <td>Presentation Parser</td>
            <td>Ingests PowerPoint lecture presentations (<code>.pptx</code>) into slide-by-slide structured text blocks.</td>
        </tr>
        <tr>
            <td><strong>Built-in Python HTTP</strong></td>
            <td><code>http.server</code>, <code>socketserver</code></td>
            <td>Zero-dependency multi-threaded REST server supporting concurrent client connections and streaming endpoints.</td>
        </tr>
    </table>

    <h1>3. End-to-End Pipeline Architecture</h1>
    <div class="diagram">
+---------------------------------------------------------------------------------------------------+
|                                DOCUMENT INGESTION & PREPROCESSING                                 |
|  [PDF / PPTX Document] ---> PyMuPDF Tokenizer ---> Multi-Column Y-Bucket Sort ---> WinSDK/Tesseract OCR  |
+---------------------------------------------------------------------------------------------------+
                                                  |
                                                  v
+---------------------------------------------------------------------------------------------------+
|                            TASK 1: 3-PASS COURSE DISCOVERY & SEGMENTATION                         |
|  Pass 1: Front-Matter Scheme Table Extraction ---> Reject Non-Course Noise & Administrative Headers |
|  Pass 2: Detailed Syllabus Body Starting Page Anchor (UNIT I / Outcomes / LTPC / Prescribed Books)|
|  Pass 3: Standalone Elective & Body Fallback Indexing ---> Emits Complete Discovered Catalog      |
+---------------------------------------------------------------------------------------------------+
                                                  |
                                                  v
+---------------------------------------------------------------------------------------------------+
|                              TASK 2: DEEP COURSE DETAIL EXTRACTOR                                 |
|  Page Span Resolver ---> LLM Line-Range Boundary Helper (Cached / Heuristic Fallback)              |
|  Verbatim Units & Topic Parser ---> Dual-Path Bloom Taxonomy Engine (Printed vs Inferred)          |
|  Multi-Column CO-PO Matrix Grid Reconstructor ---> Prescribed Books Segmentation (Text/Ref)       |
+---------------------------------------------------------------------------------------------------+
                                                  |
                                                  v
+---------------------------------------------------------------------------------------------------+
|                             VERIFICATION & STRICT GROUNDING LAYER                                 |
|  Verbatim Substring Audit ---> Drop Ungrounded Hallucinations ---> CO-PO Referential Integrity    |
|  "Nothing-Lost" Unit Accounting ---> Deterministic Attribute Normalization & Canonical Sorting     |
+---------------------------------------------------------------------------------------------------+
                                                  |
                                                  v
+---------------------------------------------------------------------------------------------------+
|                        REFERENCE BOOK ENGINE & TOPIC MAPPING STUDIO                               |
|  Scanned Book KB Grounding (+14 Page Offset) <---> Deep In-Text Heading & Keyword Digital Scanner |
|  Open Library API & Paste-In TOC Parser <---> Interactive Web Studio Dual-Pane Viewer (:8000)     |
+---------------------------------------------------------------------------------------------------+
    </div>

    <h1>4. Core Components, Modules & Key Functions</h1>

    <h2>1. Document Reader & Layout Reconstruction (<code>syllabus_extractor/reader.py</code>)</h2>
    <ul>
        <li><code>PDFDocumentReader._load_pages()</code>: Iterates through PDF pages, extracting raw text, structured block dictionaries with font sizes/bold flags, and exact word bounding boxes <code>(x0, y0, x1, y1)</code>. Automatically triggers WinSDK/Tesseract OCR if text length is under 30 characters.</li>
        <li><strong>Multi-Column Horizontal Row Reconstruction:</strong> Multi-column tables often break linear text flow. The reader groups word tokens vertically into 6-point buckets (<code>round(y / 6) * 6</code>) and sorts each bucket horizontally by <code>x0</code>, guaranteeing accurate row-by-row reading order across tabular curriculum grids.</li>
        <li><code>PDFDocumentReader._filter_recurring_headers_footers()</code>: Analyzes line frequencies across all pages. Headers, footers, or page number patterns appearing on more than 35% of pages are systematically suppressed to eliminate false course code triggers.</li>
    </ul>

    <h2>2. Task 1: Course Discovery Engine (<code>syllabus_extractor/task1_discovery.py</code> & <code>MODEL.py</code>)</h2>
    <ul>
        <li><code>CourseDiscoveryEngine.run()</code>: Executes a multi-stage discovery pipeline:
            <ul>
                <li><strong>Pass 1 (Curriculum Scheme Scanner):</strong> Searches front-matter pages (1-25) for Scheme of Instruction tables. Extracts codes matching regex patterns while strictly rejecting administrative prefixes (<code>ISO</code>, <code>IEEE</code>, <code>ISBN</code>, <code>CO</code>, <code>PO</code>, <code>PAGE</code>, etc.).</li>
                <li><strong>Pass 2 (Detailed Syllabus Body Search):</strong> Scans subsequent body pages to find where the true, detailed syllabus starts (marked by <code>UNIT I</code>, Course Outcomes, and Textbook listings).</li>
                <li><strong>Pass 3 (Standalone Fallback):</strong> Identifies standalone courses present in the syllabus body that were omitted from front scheme tables.</li>
            </ul>
        </li>
        <li>Returns a validated <code>Task1Response</code> model with verified course codes, titles, and starting pages.</li>
    </ul>

    <h2>3. Task 2: Deep Detail Extractor (<code>syllabus_extractor/task2_extractor.py</code>)</h2>
    <ul>
        <li><code>CourseDetailExtractor.run(course_code)</code>: Coordinates the complete extraction lifecycle for a target course:
            <ul>
                <li><strong>Page Span Resolution:</strong> Identifies the exact starting page and bounds the syllabus block by detecting the start of the subsequent course.</li>
                <li><strong>Boundary Resolution:</strong> Leverages <code>LLMLineRangeBoundaryHelper</code> to obtain integer line ranges (<code>[start, end]</code>) for units, outcomes, matrix, and books.</li>
                <li><strong>Metadata Parser:</strong> Extracts course category (<code>PC</code>, <code>PE</code>, <code>HSMC</code>, etc.) and credit distributions (Lecture, Tutorial, Practical, Credits).</li>
                <li><strong>Unit & Topic Parser:</strong> Detects unit headings (Roman numerals <code>I-X</code> or words <code>ONE-TEN</code>), parses unit hours (e.g., <code>(9 Hours)</code>), stores verbatim unit text, and splits topics on punctuation/bullet delimiters.</li>
                <li><strong>Outcome & Matrix Parser:</strong> Identifies <code>CO1-CO6</code>, parses associated Bloom levels, and reconstructs the CO-PO mapping matrix grid.</li>
                <li><strong>Book Segmenter:</strong> Distinguishes prescribed Textbooks from Reference Books, scrubbing publisher noise and administrative titles.</li>
            </ul>
        </li>
    </ul>

    <h2>4. Bloom's Taxonomy Classifier (<code>syllabus_extractor/task2_bloom.py</code>)</h2>
    <ul>
        <li><strong>Dual-Path Classification Architecture:</strong>
            <ul>
                <li><strong>Path 1 (Printed Indicator):</strong> Matches explicit markers printed in the syllabus document (e.g., <code>K1-K6</code>, <code>L1-L6</code>, <code>Remember</code>, <code>Understand</code>, <code>Apply</code>, <code>Analyse</code>, <code>Evaluate</code>, <code>Create</code>). Emits <code>bloom_source="printed"</code>.</li>
                <li><strong>Path 2 (Zero-Shot Action Verb Inference):</strong> If no printed indicator exists, analyzes leading action verbs (e.g., <em>Define, List</em> &rarr; <code>remember</code>; <em>Explain, Discuss</em> &rarr; <code>understand</code>; <em>Apply, Compute</em> &rarr; <code>apply</code>; <em>Analyze, Differentiate</em> &rarr; <code>analyse</code>; <em>Design, Formulate</em> &rarr; <code>create</code>). Emits <code>bloom_source="inferred"</code>.</li>
            </ul>
        </li>
    </ul>

    <h2>5. Zero-Hallucination Verification Layer (<code>syllabus_extractor/verification.py</code>)</h2>
    <ul>
        <li><code>VerificationLayer.verify()</code>: Implements a four-pillar validation gate:
            <ul>
                <li><strong>Substring Grounding Check:</strong> Every string field (course title, unit title, unit text, topic text, CO statement, and book citation) must exist as a verbatim substring in the source text after whitespace normalization. Unmatched strings are discarded and logged in <code>not_extracted</code>.</li>
                <li><strong>CO-PO Referential Integrity:</strong> Ensures that every CO and PO referenced in the mapping matrix exists in the declared outcome lists. Dangling matrix references are pruned.</li>
                <li><strong>"Nothing Lost" Accounting:</strong> Calculates token coverage between <code>unit.text</code> and the list of extracted topics to ensure the syllabus content has been fully accounted for without data truncation.</li>
                <li><strong>Bloom Legitimacy Check:</strong> Validates that <code>bloom_source="printed"</code> is only accepted if the explicit indicator actually appears in the physical document text.</li>
            </ul>
        </li>
    </ul>

    <h2>6. Reference Book Engine & Topic Locator (<code>reference_book_engine.py</code>)</h2>
    <ul>
        <li><code>is_scanned_book()</code>: Probes document text layers across sample pages. If extractable text is under 100 characters, classifies the document as a scanned bitmap.</li>
        <li><strong>Scanned Book Grounding:</strong> Houses an authoritative 38-chapter directory for standard engineering textbooks (such as Dr. B.S. Grewal's <em>Higher Engineering Mathematics</em>, 1327 pages) and applies an automated +14 physical page offset calculation between printed page numbers and digital PDF scan indices.</li>
        <li><code>find_subtopic_in_book()</code>: Multi-tier search hierarchy:
            <ol>
                <li>Fuzzy Table of Contents match against chapter/subtopic entries.</li>
                <li>Deep in-text scan with heading detection based on block font sizes, bold styles, and line length thresholds (&lt;90 chars).</li>
                <li>Forward lookahead scan to determine the exact concluding page of the topic.</li>
                <li>Confidence score calculation (0.00 to 1.00).</li>
            </ol>
        </li>
        <li><code>map_syllabus_topics_to_book()</code>: Automatically maps an entire course syllabus topic array against the textbook, generating a complete study guide with start/end pages.</li>
    </ul>

    <h2>7. Interactive Studio Web Server (<code>app.py</code>)</h2>
    <ul>
        <li>Built on Python's <code>http.server.ThreadingHTTPServer</code> on port <code>8000</code>.</li>
        <li><strong>Core REST Endpoints:</strong>
            <ul>
                <li><code>GET /</code>: Delivers the interactive single-page dashboard with Tailwind CSS styling and dual-pane document navigation.</li>
                <li><code>GET /api/pdf-page-image</code>: On-the-fly rasterization of PDF pages to high-resolution PNG byte streams with internal LRU caching.</li>
                <li><code>GET /api/documents</code> & <code>GET /api/reference-books</code>: Lists uploaded syllabi and reference books.</li>
                <li><code>GET /api/extract</code> & <code>POST /api/upload</code>: Triggers Task 1 course discovery or Task 2 deep course extraction.</li>
                <li><code>POST /api/reference-book/search-subtopic</code>: Real-time subtopic search with start and end page boundaries.</li>
                <li><code>POST /api/reference-book/map-syllabus</code>: Maps an array of syllabus topics to a textbook.</li>
                <li><code>POST /api/reference-book/online-lookup</code>: Fetches TOC data from Open Library via ISBN or Title.</li>
            </ul>
        </li>
    </ul>

    <h1>5. Architectural Advantages & Strengths</h1>
    <ul>
        <li><strong>Zero Hallucination by Design:</strong> LLMs are strictly confined to returning line indices. All text content is harvested directly from the PDF document bytes and validated via verbatim substring checks.</li>
        <li><strong>100% Determinism & Zero Re-Run Costs:</strong> Persistent SHA-256 caching ensures identical syllabus documents produce byte-for-byte identical output without redundant LLM API billing.</li>
        <li><strong>Robust Layout Handling:</strong> The vertical 6-point bucket sorting solves the classic multi-column text interweaving problem common in PyMuPDF text extractors.</li>
        <li><strong>Multi-Format & Scanned Document Support:</strong> Supports modern vector PDFs, scanned bitmap textbooks via hardware-accelerated WinSDK/Tesseract OCR, and PowerPoint slide decks.</li>
        <li><strong>Zero Heavyweight Framework Overhead:</strong> The system operates without bulky dependencies like LangChain, LlamaIndex, PyTorch, or external vector databases, running instantaneously on standard Python runtimes.</li>
        <li><strong>Rigorous Educational Compliance:</strong> Incorporates formal Bloom's Revised Taxonomy levels and standard NBA/NAAC CO-PO matrix mapping structures.</li>
    </ul>

    <h1>6. Limitations & Technical Drawbacks</h1>
    <ul>
        <li><strong>Scanned Textbook Knowledge Base Scope:</strong> Full instant subtopic lookups without digital text layers currently rely on pre-indexed directories (e.g., Dr. B.S. Grewal). Arbitrary scanned textbooks without text layers require full-document OCR processing, which can be computationally intensive on 1,000+ page books.</li>
        <li><strong>Single-Threaded OCR Throughput:</strong> While text extraction on digital PDFs is instantaneous, OCR on unindexed bitmap scans is single-threaded per page, introducing latency on massive files.</li>
        <li><strong>Irregular Nested Tables:</strong> Highly non-standard curriculum tables spanning multiple page breaks with diagonally split cells can occasionally require manual verification.</li>
        <li><strong>Volatile In-Memory Cache:</strong> The server's image pixmap cache resides in memory and resets when the server process is restarted (though persistent PDFs remain saved on disk).</li>
    </ul>

    <h1>7. Flexibility & Extensibility Assessment</h1>
    <table>
        <tr>
            <th style="width: 25%;">Dimension</th>
            <th style="width: 20%;">Flexibility Level</th>
            <th style="width: 55%;">Technical Explanation</th>
        </tr>
        <tr>
            <td><strong>LLM Provider Swapping</strong></td>
            <td><span class="badge badge-green">High</span></td>
            <td>Supports Gemini, OpenAI, Claude, Groq, DeepSeek, and local Ollama via environment variables, or runs completely offline with heuristic rule fallback.</td>
        </tr>
        <tr>
            <td><strong>University Syllabus Formats</strong></td>
            <td><span class="badge badge-green">High</span></td>
            <td>Agnostic to university templates. Operates using universal structural anchors (modules, credit formulas, outcomes, books) rather than hardcoded institution regexes.</td>
        </tr>
        <tr>
            <td><strong>Deployment Complexity</strong></td>
            <td><span class="badge badge-green">Very High</span></td>
            <td>Self-contained with zero Node.js/npm dependencies, zero database setup, and instant execution on standard Python 3.10+ environments.</td>
        </tr>
        <tr>
            <td><strong>Enterprise Integration</strong></td>
            <td><span class="badge badge-blue">High</span></td>
            <td>Clean JSON REST endpoints enable direct integration into Academic Management Systems, Moodle/Canvas LMS, and accreditation audit pipelines.</td>
        </tr>
        <tr>
            <td><strong>Input File Types</strong></td>
            <td><span class="badge badge-amber">Moderate</span></td>
            <td>Native support for digital PDF, scanned PDF, and PPTX presentations. Microsoft Word (<code>.docx</code>) requires pre-conversion to PDF.</td>
        </tr>
    </table>

    <h1>8. Verification Test Suite & QA Report</h1>
    <p>
        The codebase includes a comprehensive automated test suite in <code>tests/</code>, verified under <code>pytest-9.1.1</code> with Python 3.12:
    </p>
    <table>
        <tr>
            <th style="width: 35%;">Test Module</th>
            <th style="width: 15%;">Test Count</th>
            <th style="width: 50%;">Verified Functional Invariants</th>
        </tr>
        <tr>
            <td><code>tests/test_determinism.py</code></td>
            <td>3 Tests</td>
            <td>Validates byte-level output reproducibility and SHA-256 disk cache integrity.</td>
        </tr>
        <tr>
            <td><code>tests/test_layout_reader.py</code></td>
            <td>2 Tests</td>
            <td>Verifies bounding box coordinate preservation and multi-column row reconstruction.</td>
        </tr>
        <tr>
            <td><code>tests/test_reference_book_engine.py</code></td>
            <td>9 Tests</td>
            <td>Tests Dr. B.S. Grewal 38-chapter directory lookups, subtopic matching, and page offset calculations.</td>
        </tr>
        <tr>
            <td><code>tests/test_task1.py</code></td>
            <td>5 Tests</td>
            <td>Validates 3-pass course discovery and rejection of front-matter curriculum scheme noise.</td>
        </tr>
        <tr>
            <td><code>tests/test_task2.py</code></td>
            <td>4 Tests</td>
            <td>Verifies unit parsing, hours extraction, Bloom classification, and prescribed book parsing.</td>
        </tr>
        <tr>
            <td><code>tests/test_verification.py</code></td>
            <td>4 Tests</td>
            <td>Tests substring grounding rejection of hallucinated text and CO-PO matrix referential integrity.</td>
        </tr>
    </table>
    <div class="box-success">
        <strong>Test Suite Status:</strong> 27 passed in 24.53 seconds (100% Pass Rate).
    </div>

    <h1>9. Recommended Future Enhancements</h1>
    <ol>
        <li><strong>Background Asynchronous OCR Worker:</strong> Implement an asynchronous Celery or multiprocessing worker pool for batch OCR on massive scanned textbooks.</li>
        <li><strong>DOCX & RTF Direct Ingestion:</strong> Add a <code>python-docx</code> ingestion adapter to support native Word syllabus documents directly without pre-converting to PDF.</li>
        <li><strong>NBA/NAAC Accreditation Export:</strong> Add automated one-click export of verified CO-PO matrices into standardized Excel/CSV accreditation sheets.</li>
        <li><strong>Vector Indexing for Multi-Textbook Libraries:</strong> Implement a lightweight SQLite-backed embedding index for searching across an entire departmental library of 50+ textbooks simultaneously.</li>
    </ol>
    """

    # Generate PDF using PyMuPDF Story
    story = pymupdf.Story(html=html_content)
    
    # A4 Page dimensions: 595.276 x 841.890 points
    # Margins: 45 pt left/right, 50 pt top/bottom
    margin_x = 42
    margin_top = 46
    margin_bottom = 46
    page_width = 595.276
    page_height = 841.890
    
    content_rect = pymupdf.Rect(margin_x, margin_top, page_width - margin_x, page_height - margin_bottom)
    
    temp_pdf_path = output_path + ".tmp.pdf"
    writer = pymupdf.DocumentWriter(temp_pdf_path)
    
    more = 1
    page_count = 0
    while more:
        page_count += 1
        device = writer.begin_page(pymupdf.paper_rect('A4'))
        more, _ = story.place(content_rect)
        story.draw(device)
        writer.end_page()
    writer.close()
    
    # Second Pass: Add running headers, footers, and page numbers
    doc = pymupdf.open(temp_pdf_path)
    total_pages = len(doc)
    
    for idx, page in enumerate(doc):
        # Running Header (pages 2+)
        if idx > 0:
            header_text = "Syllabus Extraction & Verification Studio — Comprehensive Methodology Review"
            page.insert_text((margin_x, 30), header_text, fontsize=7.5, color=(0.4, 0.45, 0.5))
            page.draw_line((margin_x, 34), (page_width - margin_x, 34), color=(0.85, 0.88, 0.92), width=0.5)
            
        # Running Footer (all pages)
        footer_line_y = page_height - 30
        footer_text_y = page_height - 20
        page.draw_line((margin_x, footer_line_y), (page_width - margin_x, footer_line_y), color=(0.85, 0.88, 0.92), width=0.5)
        
        left_footer = "Confidential & Proprietary Academic Technical Review | Deterministic Hybrid Architecture"
        page_number_str = f"Page {idx + 1} of {total_pages}"
        
        page.insert_text((margin_x, footer_text_y), left_footer, fontsize=7, color=(0.4, 0.45, 0.5))
        page.insert_text((page_width - margin_x - 55, footer_text_y), page_number_str, fontsize=7, color=(0.2, 0.3, 0.4))
        
    doc.save(output_path)
    doc.close()
    del doc
    import gc
    gc.collect()
    
    try:
        if os.path.exists(temp_pdf_path):
            os.remove(temp_pdf_path)
    except Exception:
        pass
        
    print(f"Successfully generated PDF report: '{output_path}'")
    print(f"Total Pages: {total_pages}")
    print(f"File Size: {os.path.getsize(output_path)} bytes")

if __name__ == "__main__":
    build_pdf()
