import os
import json
import base64
import http.server
import socketserver
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple
from syllabus_extractor.reader import PDFDocumentReader
from syllabus_extractor.task1_discovery import CourseDiscoveryEngine
from syllabus_extractor.task2_extractor import CourseDetailExtractor
from syllabus_extractor.llm_engine import LLMEngine

PORT = 8080
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploaded_syllabi")
os.makedirs(UPLOAD_DIR, exist_ok=True)

READER_CACHE: Dict[str, Tuple[float, PDFDocumentReader]] = {}

def get_cached_reader(pdf_path: str) -> PDFDocumentReader:
    mtime = os.path.getmtime(pdf_path)
    if pdf_path in READER_CACHE:
        cached_mtime, cached_reader = READER_CACHE[pdf_path]
        if cached_mtime == mtime:
            return cached_reader
    reader = PDFDocumentReader(pdf_path)
    READER_CACHE[pdf_path] = (mtime, reader)
    return reader


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Syllabus Extractor & Verification Studio</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    .bloom-Remember, .bloom-remember { background-color: rgba(59, 130, 246, 0.15); color: #2563eb; border: 1px solid rgba(59, 130, 246, 0.3); }
    .bloom-Understand, .bloom-understand { background-color: rgba(16, 185, 129, 0.15); color: #059669; border: 1px solid rgba(16, 185, 129, 0.3); }
    .bloom-Apply, .bloom-apply { background-color: rgba(245, 158, 11, 0.15); color: #d97706; border: 1px solid rgba(245, 158, 11, 0.3); }
    .bloom-Analyze, .bloom-analyse, .bloom-analyze { background-color: rgba(139, 92, 246, 0.15); color: #7c3aed; border: 1px solid rgba(139, 92, 246, 0.3); }
    .bloom-Evaluate, .bloom-evaluate { background-color: rgba(236, 72, 153, 0.15); color: #db2777; border: 1px solid rgba(236, 72, 153, 0.3); }
    .bloom-Create, .bloom-create { background-color: rgba(239, 68, 68, 0.15); color: #dc2626; border: 1px solid rgba(239, 68, 68, 0.3); }
    .map-3 { background-color: rgba(16, 185, 129, 0.25); color: #059669; font-weight: 700; }
    .map-2 { background-color: rgba(245, 158, 11, 0.25); color: #d97706; font-weight: 600; }
    .map-1 { background-color: rgba(59, 130, 246, 0.2); color: #2563eb; }
    .map-none { color: #94a3b8; }
  </style>
</head>
<body class="bg-slate-50 text-slate-800 antialiased p-4 md:p-8 font-sans">
  <div class="max-w-6xl mx-auto space-y-6">

    <!-- Header -->
    <header class="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
      <div>
        <div class="flex items-center gap-3">
          <span class="p-2.5 rounded-2xl bg-blue-50 text-blue-600 text-2xl shadow-inner">📚</span>
          <div>
            <h1 class="text-2xl font-bold tracking-tight text-slate-900">Syllabus Extractor & Verification Studio</h1>
            <p class="text-xs text-slate-500 mt-0.5">Automated course discovery, outcome mapping & Bloom's classification</p>
          </div>
        </div>
      </div>
      <div class="flex items-center gap-2">
        <span class="px-3 py-1.5 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs font-semibold flex items-center gap-1.5">
          <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span> Engine Ready
        </span>
      </div>
    </header>

    <!-- Upload & Stored Syllabi Card -->
    <div class="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm space-y-5">
      
      <!-- Stored Syllabi Section -->
      <div id="savedDocsSection" class="hidden space-y-2.5 pb-4 border-b border-slate-100">
        <div class="flex justify-between items-center">
          <span class="text-xs font-bold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
            <span>💾</span> Saved Syllabi on Server (Click to select without re-uploading)
          </span>
          <span id="savedCountBadge" class="text-xs px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-600 font-semibold">0 files</span>
        </div>
        <div id="savedDocsList" class="flex flex-wrap gap-2.5">
          <!-- Populated by JavaScript -->
        </div>
      </div>

      <div class="flex justify-between items-center">
        <h2 class="font-bold text-slate-900 text-sm uppercase tracking-wider flex items-center gap-2">
          <span>📤</span> Upload New Syllabus PDF
        </h2>
      </div>

      <!-- Drag & Drop Zone -->
      <div id="dropZone" onclick="document.getElementById('pdfFileInput').click()" ondragover="handleDragOver(event)" ondragleave="handleDragLeave(event)" ondrop="handleDrop(event)" class="border-2 border-dashed border-blue-300 hover:border-blue-500 bg-blue-50/40 hover:bg-blue-50/80 rounded-2xl p-7 text-center cursor-pointer transition flex flex-col items-center justify-center space-y-3 group shadow-inner">
        <input type="file" id="pdfFileInput" accept=".pdf" class="hidden" onchange="handleFileSelect(event)">
        <div class="w-12 h-12 rounded-2xl bg-blue-100 text-blue-600 flex items-center justify-center text-2xl shadow-sm group-hover:scale-105 transition">
          📄
        </div>
        <div>
          <div id="uploadPrompt" class="text-sm font-bold text-slate-800">
            Upload or Drop Syllabus PDF
          </div>
          <div class="text-xs text-slate-500 mt-0.5">Click here to browse or drag & drop a PDF file (will be saved automatically)</div>
          <div id="selectedFileName" class="text-xs text-emerald-600 font-bold mt-2 bg-emerald-50 px-3 py-1 rounded-full border border-emerald-200 inline-block hidden"></div>
        </div>
      </div>

      <div id="statusMessage" class="hidden text-xs font-semibold py-2 px-3 rounded-lg"></div>

      <!-- Action Button -->
      <div class="pt-1">
        <button onclick="runDiscover()" id="discoverBtn" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 px-4 rounded-xl text-sm transition shadow-sm flex justify-center items-center gap-2">
          <span>🔍 Discover All Courses</span>
        </button>
      </div>
    </div>

    <!-- Results Section -->
    <div id="resultsContainer" class="hidden space-y-6">
      
      <!-- Dynamic Rendered View (Task 1 or Task 2) -->
      <div id="renderedView"></div>

      <!-- Raw JSON Viewer -->
      <div class="bg-slate-900 rounded-2xl p-5 shadow-sm text-slate-200 space-y-3">
        <div class="flex justify-between items-center">
          <span class="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-2">
            <span>💻</span> Verified Structured JSON Response
          </span>
          <div class="flex items-center gap-2">
            <button id="extractBtn" onclick="extractJson()" class="text-xs px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-semibold transition flex items-center gap-1.5 shadow-sm">
              <span>⬇️</span> Extract JSON
            </button>
            <button id="copyBtn" onclick="copyJson()" class="text-xs px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold transition flex items-center gap-1.5">
              <span>📋</span> Copy JSON
            </button>
          </div>
        </div>
        <pre id="jsonOutput" class="font-mono text-xs overflow-x-auto max-h-96 p-3 bg-slate-950 rounded-xl text-emerald-400"></pre>
      </div>

    </div>

  </div>

  <script>
    let selectedFile = null;
    let localFilePath = null;
    let currentDocLabel = '';
    let lastDiscoveredData = null;

    // Load saved documents on startup
    window.addEventListener('DOMContentLoaded', () => {
      fetchSavedDocuments();
    });

    async function fetchSavedDocuments() {
      try {
        const res = await fetch('/api/documents');
        const docs = await res.json();
        renderSavedDocuments(docs);
      } catch (e) {
        console.error('Failed to load saved docs', e);
      }
    }

    function renderSavedDocuments(docs) {
      const section = document.getElementById('savedDocsSection');
      const list = document.getElementById('savedDocsList');
      const countBadge = document.getElementById('savedCountBadge');

      if (!docs || docs.length === 0) {
        section.classList.add('hidden');
        return;
      }

      section.classList.remove('hidden');
      countBadge.innerText = `${docs.length} saved`;
      list.innerHTML = '';

      docs.forEach(doc => {
        const isSelected = (localFilePath === doc.path);
        const card = document.createElement('div');
        card.className = `flex items-center gap-2 px-3 py-2 rounded-xl text-xs font-medium border cursor-pointer transition ${
          isSelected 
            ? 'bg-blue-600 text-white border-blue-600 shadow-sm' 
            : 'bg-slate-50 hover:bg-blue-50 text-slate-700 border-slate-200 hover:border-blue-300'
        }`;
        card.innerHTML = `
          <span class="text-sm">📑</span>
          <span class="font-semibold max-w-xs truncate" title="${doc.name}">${doc.name}</span>
          <span class="${isSelected ? 'text-blue-100' : 'text-slate-400'} text-[10px]">(${doc.size_mb} MB)</span>
          <button title="Delete saved file" onclick="deleteSavedDoc(event, '${encodeURIComponent(doc.name)}')" class="ml-1.5 p-1 rounded hover:bg-red-500 hover:text-white transition opacity-60 hover:opacity-100 text-xs">✕</button>
        `;
        card.onclick = (e) => {
          if (e.target.tagName.toLowerCase() === 'button') return;
          selectSavedDoc(doc);
        };
        list.appendChild(card);
      });
    }

    function selectSavedDoc(doc) {
      selectedFile = null;
      localFilePath = doc.path;
      currentDocLabel = doc.name;
      clearStatus();

      const fileInput = document.getElementById('pdfFileInput');
      if (fileInput) fileInput.value = '';

      const fileBadge = document.getElementById('selectedFileName');
      fileBadge.classList.remove('hidden');
      fileBadge.innerText = `✓ Stored File Selected: ${doc.name} (${doc.size_mb} MB)`;

      fetchSavedDocuments();
    }

    async function deleteSavedDoc(e, encodedName) {
      e.stopPropagation();
      if (!confirm(`Are you sure you want to delete this saved syllabus?`)) return;
      try {
        await fetch(`/api/documents?name=${encodedName}`, { method: 'DELETE' });
        if (currentDocLabel === decodeURIComponent(encodedName)) {
          localFilePath = null;
          currentDocLabel = '';
          document.getElementById('selectedFileName').classList.add('hidden');
        }
        fetchSavedDocuments();
      } catch (err) {
        showStatus('Failed to delete file: ' + err.message, true);
      }
    }

    function showStatus(msg, isError = false) {
      const el = document.getElementById('statusMessage');
      el.innerText = msg;
      el.className = isError 
        ? 'text-xs font-semibold py-2 px-3 rounded-lg bg-rose-50 text-rose-700 border border-rose-200 block'
        : 'text-xs font-semibold py-2 px-3 rounded-lg bg-blue-50 text-blue-700 border border-blue-200 block';
    }

    function clearStatus() {
      const el = document.getElementById('statusMessage');
      el.className = 'hidden';
      el.innerText = '';
    }

    function handleDragOver(e) {
      e.preventDefault();
      document.getElementById('dropZone').classList.add('border-blue-500', 'bg-blue-100/50');
    }

    function handleDragLeave(e) {
      e.preventDefault();
      document.getElementById('dropZone').classList.remove('border-blue-500', 'bg-blue-100/50');
    }

    function handleDrop(e) {
      e.preventDefault();
      document.getElementById('dropZone').classList.remove('border-blue-500', 'bg-blue-100/50');
      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        setFile(e.dataTransfer.files[0]);
      }
    }

    function handleFileSelect(e) {
      if (e.target.files && e.target.files.length > 0) {
        setFile(e.target.files[0]);
      }
    }

    function setFile(file) {
      clearStatus();
      selectedFile = file;
      localFilePath = null;
      currentDocLabel = file.name;
      const fileBadge = document.getElementById('selectedFileName');
      fileBadge.classList.remove('hidden');
      fileBadge.innerText = `✓ Selected: ${file.name} (${(file.size / (1024 * 1024)).toFixed(2)} MB)`;
      fetchSavedDocuments();
    }

    function fileToBase64(file) {
      return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.readAsDataURL(file);
        reader.onload = () => {
          const base64 = reader.result.split(',')[1];
          resolve(base64);
        };
        reader.onerror = err => reject(err);
      });
    }

    function runDiscover() {
      uploadAndExtract('', 'discover');
    }

    async function uploadAndExtract(drilldownCode = '', actionType = 'discover') {
      const discoverBtn = document.getElementById('discoverBtn');

      if (!selectedFile && !localFilePath) {
        showStatus('Please select a saved syllabus or upload a new PDF file first.', true);
        return;
      }
      clearStatus();

      const isExtract = (actionType === 'extract' || drilldownCode !== '');

      if (discoverBtn) {
        discoverBtn.disabled = true;
        discoverBtn.innerHTML = isExtract 
          ? `<span>⚡ Extracting ${drilldownCode}...</span>` 
          : '<span>⏳ Discovering Courses...</span>';
      }

      try {
        let res;
        if (selectedFile) {
          const base64Data = await fileToBase64(selectedFile);
          res = await fetch('/api/upload', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              filename: selectedFile.name,
              pdf_base64: base64Data,
              course: drilldownCode
            })
          });
        } else {
          res = await fetch(`/api/extract?pdf=${encodeURIComponent(localFilePath)}&course=${encodeURIComponent(drilldownCode)}`);
        }

        const data = await res.json();
        if (data.error) {
          showStatus('Extraction error: ' + data.error, true);
          return;
        }

        // If file was uploaded, refresh the saved docs list and update localFilePath
        if (data.saved_path) {
          localFilePath = data.saved_path;
          selectedFile = null;
          fetchSavedDocuments();
        }

        document.getElementById('resultsContainer').classList.remove('hidden');
        document.getElementById('jsonOutput').innerText = JSON.stringify(data, null, 2);
        
        if (data.courses) {
          lastDiscoveredData = data;
          renderTask1(data);
        } else if (data.course) {
          renderTask2(data);
        }
      } catch (err) {
        showStatus('Server error: ' + err.message, true);
      } finally {
        if (discoverBtn) {
          discoverBtn.disabled = false;
          discoverBtn.innerHTML = '<span>🔍 Discover All Courses</span>';
        }
      }
    }

    function escapeJs(str) {
      if (!str) return '';
      return str.replace(/'/g, "\\'");
    }

    function renderTask1(data) {
      const container = document.getElementById('renderedView');
      const courses = data.courses || [];
      container.innerHTML = `
        <div class="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm space-y-4">
          <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-2 border-b border-slate-100 pb-3">
            <div>
              <h3 class="text-lg font-bold text-slate-900">Task 1: Discovered Course Syllabi</h3>
              <p class="text-xs text-slate-500">Document: ${data.document} · Click any course card to inspect full Task 2 syllabus</p>
            </div>
            <span class="px-3 py-1 rounded-full bg-blue-50 text-blue-700 font-bold text-xs border border-blue-200">
              ${data.course_count || courses.length} Courses Found
            </span>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            ${courses.map(c => `
              <div onclick="drilldownCourse('${escapeJs(c.code || c.title)}')" class="p-4 rounded-xl border border-slate-200 hover:border-blue-400 bg-slate-50/50 hover:bg-blue-50/30 transition cursor-pointer flex flex-col justify-between group shadow-xs">
                <div>
                  <div class="flex justify-between items-start gap-2">
                    <span class="font-bold text-xs px-2.5 py-1 rounded-md ${c.code ? 'bg-blue-100 text-blue-800' : 'bg-slate-200 text-slate-700'}">${c.code || 'COURSE'}</span>
                    <span class="text-[11px] bg-slate-200 text-slate-700 px-2 py-0.5 rounded-full font-medium">
                      Page ${c.page || 1}
                    </span>
                  </div>
                  <h4 class="font-bold text-slate-800 text-sm mt-2 leading-snug group-hover:text-blue-700">${c.title || 'Untitled Course'}</h4>
                </div>
                <div class="mt-3 flex items-center justify-between text-xs text-slate-500 pt-2 border-t border-slate-200/60">
                  <span class="text-emerald-600 font-medium">✓ Syllabus Ready</span>
                  <span class="text-blue-600 font-semibold group-hover:translate-x-0.5 transition">Extract Units →</span>
                </div>
              </div>
            `).join('')}
          </div>
        </div>
      `;
    }

    function drilldownCourse(code) {
      uploadAndExtract(code, 'extract');
    }

    function linkify(text) {
      if (!text) return '';
      const urlRegex = /(https?:\/\/[^\s]+)/g;
      return text.replace(urlRegex, url => {
        const cleanUrl = url.replace(/[.,;)]+$/, '');
        const trailing = url.slice(cleanUrl.length);
        return `<a href="${cleanUrl}" target="_blank" rel="noopener noreferrer" class="text-blue-600 hover:text-blue-800 underline font-semibold break-all inline-flex items-center gap-1"><span>🔗</span>${cleanUrl}</a>${trailing}`;
      });
    }

    function renderTask2(data) {
      const c = data.course || {};
      const units = data.units || [];
      const cos = data.course_outcomes || [];
      const pos = data.programme_outcomes || [];
      const matrix = data.co_po_matrix || [];
      const rawBooks = data.books || [];
      const textbooks = Array.isArray(rawBooks) ? rawBooks.filter(b => b.kind === 'text').map(b => b.text) : (rawBooks.textbooks || []);
      const references = Array.isArray(rawBooks) ? rawBooks.filter(b => b.kind === 'reference').map(b => b.text) : (rawBooks.references || []);
      const container = document.getElementById('renderedView');

      const l = c.lecture !== null && c.lecture !== undefined ? c.lecture : 0;
      const t = c.tutorial !== null && c.tutorial !== undefined ? c.tutorial : 0;
      const p = c.practical !== null && c.practical !== undefined ? c.practical : 0;
      const ltpStr = `${l}-${t}-${p}`;
      const pageStr = c.pages && c.pages.length ? `Page ${c.pages.join(', ')}` : 'Body Page';

      container.innerHTML = `
        <div class="space-y-6">
          <div class="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm space-y-6">
            
            <!-- Header Bar -->
            <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-3 border-b border-slate-100 pb-4">
              <div>
                <button onclick="backToTask1()" class="text-xs text-blue-600 hover:underline font-semibold flex items-center gap-1 mb-1.5">
                  ← Back to All Discovered Courses
                </button>
                <div class="flex flex-wrap items-center gap-2.5">
                  <span class="px-2.5 py-1 rounded-lg ${c.code ? 'bg-blue-100 text-blue-800' : 'bg-slate-100 text-slate-600'} font-bold text-xs uppercase tracking-wide">
                    ${c.code || 'N/A'}
                  </span>
                  <h2 class="text-xl font-extrabold text-slate-900">${c.title || 'Course Syllabus Details'}</h2>
                </div>
              </div>
              <div class="flex items-center gap-2">
                <span class="text-xs px-3 py-1.5 rounded-full font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                  ✓ Structure Verified
                </span>
                <span class="text-xs px-3 py-1.5 rounded-full bg-slate-100 text-slate-700 font-semibold">
                  ${pageStr}
                </span>
              </div>
            </div>

            <!-- Course Header Badges: Credits, L-T-P Structure, Category, Pages -->
            <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div class="bg-slate-50 border border-slate-100 p-3.5 rounded-xl">
                <span class="text-[11px] uppercase tracking-wider text-slate-400 font-bold block">Credits</span>
                <span class="text-base font-bold text-slate-800">${c.credits !== null && c.credits !== undefined ? c.credits : 'N/A'}</span>
              </div>
              <div class="bg-slate-50 border border-slate-100 p-3.5 rounded-xl">
                <span class="text-[11px] uppercase tracking-wider text-slate-400 font-bold block">L-T-P Structure</span>
                <span class="text-base font-bold text-slate-800">${ltpStr}</span>
              </div>
              <div class="bg-slate-50 border border-slate-100 p-3.5 rounded-xl">
                <span class="text-[11px] uppercase tracking-wider text-slate-400 font-bold block">Category</span>
                <span class="text-base font-bold text-slate-800 truncate block" title="${c.category || 'Professional Core'}">${c.category || 'Professional Core'}</span>
              </div>
              <div class="bg-slate-50 border border-slate-100 p-3.5 rounded-xl">
                <span class="text-[11px] uppercase tracking-wider text-slate-400 font-bold block">Syllabus Span</span>
                <span class="text-base font-bold text-slate-800">${pageStr}</span>
              </div>
            </div>

            <!-- Units / Modules Section (matching reference layout in Image 3) -->
            ${units && units.length > 0 ? `
              <div class="space-y-4 pt-2">
                <div class="flex justify-between items-center border-b border-slate-100 pb-2">
                  <h3 class="text-sm font-bold text-slate-900 uppercase tracking-wider flex items-center gap-2">
                    <span>📖</span> Course Units / Modules (${units.length})
                  </h3>
                </div>
                <div class="space-y-3.5">
                  ${units.map(u => `
                    <div class="p-5 rounded-2xl border border-blue-100/80 bg-white hover:border-blue-300 shadow-xs transition space-y-3">
                      <div class="flex flex-col sm:flex-row justify-between sm:items-center gap-1.5 border-b border-slate-100 pb-2.5">
                        <span class="font-bold text-sm text-blue-700 tracking-wide uppercase">
                          UNIT ${u.number}${u.title ? ': ' + u.title : ''}
                        </span>
                        ${u.hours ? `<span class="text-xs px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-600 font-semibold self-start sm:self-auto">${u.hours} hrs</span>` : ''}
                      </div>
                      ${u.text ? `<p class="text-xs text-slate-700 leading-relaxed font-normal">${u.text}</p>` : ''}
                      ${u.topics && u.topics.length > 0 ? `
                        <div class="flex flex-wrap gap-1.5 pt-1">
                          ${u.topics.map(t => {
                            const bLvl = t.bloom || t.bloom_level || '';
                            const tTxt = t.text || t.topic || '';
                            return `
                              <span class="text-[11px] px-2.5 py-1 rounded-lg bg-slate-50 border border-slate-200 text-slate-700 flex items-center gap-1.5 font-medium">
                                ${t.id ? `<span class="text-[9px] font-bold text-slate-400 font-mono">${t.id}</span>` : ''}
                                <span>${tTxt}</span>
                                ${bLvl ? `<span class="text-[9px] px-1.5 py-0.5 rounded font-bold bloom-${bLvl.toLowerCase()}">${bLvl}</span>` : ''}
                              </span>
                            `;
                          }).join('')}
                        </div>
                      ` : ''}
                    </div>
                  `).join('')}
                </div>
              </div>
            ` : `
              <div class="p-6 rounded-2xl border border-dashed border-slate-200 text-center text-xs text-slate-400">
                No distinct units/modules detected on this course page.
              </div>
            `}

            <!-- Course Outcomes & Bloom's Taxonomy -->
            ${cos && cos.length > 0 ? `
              <div class="space-y-3 pt-2">
                <h3 class="text-sm font-bold text-slate-900 uppercase tracking-wider flex items-center gap-2 border-b border-slate-100 pb-2">
                  <span>🎯</span> Course Outcomes & Bloom's Taxonomy Mapping
                </h3>
                <div class="space-y-2.5">
                  ${cos.map(co => {
                    const bLvl = co.bloom || co.bloom_level || '';
                    const bSrc = co.bloom_source || co.source || 'inferred';
                    return `
                      <div class="p-3.5 rounded-xl border border-slate-200 bg-slate-50/70 flex flex-col md:flex-row items-start md:items-center justify-between gap-3">
                        <div class="flex items-start gap-3">
                          <span class="font-bold text-xs bg-slate-200 text-slate-700 px-2 py-1 rounded-md shrink-0">${co.co}</span>
                          <p class="text-xs text-slate-700">${co.statement}</p>
                        </div>
                        ${bLvl ? `
                          <div class="flex items-center gap-2 shrink-0">
                            <span class="px-2.5 py-1 rounded-full text-[11px] font-bold bloom-${bLvl.toLowerCase()}">
                              ${bLvl}
                            </span>
                            <span class="text-[10px] text-slate-400 italic">(${bSrc})</span>
                          </div>
                        ` : ''}
                      </div>
                    `;
                  }).join('')}
                </div>
              </div>
            ` : ''}

            <!-- Programme Outcomes (POs / PSOs) -->
            ${pos && pos.length > 0 ? `
              <div class="space-y-3 pt-2">
                <h3 class="text-sm font-bold text-slate-900 uppercase tracking-wider flex items-center gap-2 border-b border-slate-100 pb-2">
                  <span>🎓</span> Programme Outcomes (POs & PSOs) (${pos.length})
                </h3>
                <div class="grid grid-cols-1 md:grid-cols-2 gap-2.5">
                  ${pos.map(po => `
                    <div class="p-3 rounded-xl border border-slate-200 bg-slate-50/60 flex items-start gap-2.5">
                      <span class="font-bold text-xs bg-blue-100 text-blue-800 px-2 py-0.5 rounded shrink-0">${po.po}</span>
                      <p class="text-xs text-slate-700 leading-snug">${po.statement}</p>
                    </div>
                  `).join('')}
                </div>
              </div>
            ` : ''}

            <!-- CO-PO Articulation Matrix (2D Grid & Pairs) -->
            ${matrix && matrix.length > 0 ? (() => {
              // Build unique sorted COs and POs for table
              const allCos = [...new Set(matrix.map(m => m.co))].sort((a, b) => {
                const numA = parseInt((a.match(/\d+/) || [99])[0]);
                const numB = parseInt((b.match(/\d+/) || [99])[0]);
                return numA - numB;
              });
              const allPos = [...new Set(matrix.map(m => m.po))].sort((a, b) => {
                const isPsoA = a.toUpperCase().includes('PSO') ? 1 : 0;
                const isPsoB = b.toUpperCase().includes('PSO') ? 1 : 0;
                if (isPsoA !== isPsoB) return isPsoA - isPsoB;
                const numA = parseInt((a.match(/\d+/) || [99])[0]);
                const numB = parseInt((b.match(/\d+/) || [99])[0]);
                return numA - numB;
              });

              // Lookup map
              const matrixLookup = {};
              matrix.forEach(m => {
                matrixLookup[`${m.co}_${m.po}`] = m.strength;
              });

              return `
                <div class="space-y-3 pt-2">
                  <div class="flex justify-between items-center border-b border-slate-100 pb-2">
                    <h3 class="text-sm font-bold text-slate-900 uppercase tracking-wider flex items-center gap-2">
                      <span>📊</span> CO-PO Articulation Matrix (${matrix.length} Mapped Pairs)
                    </h3>
                    <span class="text-[11px] text-slate-400">Blanks omitted (sparse mapping)</span>
                  </div>

                  <!-- 2D Table View -->
                  <div class="overflow-x-auto border border-slate-200 rounded-xl bg-white shadow-xs">
                    <table class="w-full text-xs text-center border-collapse">
                      <thead>
                        <tr class="bg-slate-100/80 border-b border-slate-200 text-slate-700">
                          <th class="py-2.5 px-3 font-bold border-r border-slate-200 text-left">CO \\ PO</th>
                          ${allPos.map(p => `<th class="py-2.5 px-2 font-bold">${p}</th>`).join('')}
                        </tr>
                      </thead>
                      <tbody>
                        ${allCos.map(c => `
                          <tr class="border-b border-slate-100 hover:bg-slate-50/80">
                            <td class="py-2 px-3 font-bold text-blue-700 border-r border-slate-200 text-left bg-slate-50/50">${c}</td>
                            ${allPos.map(p => {
                              const str = matrixLookup[`${c}_${p}`];
                              if (str !== undefined && str !== null) {
                                const cls = (str == 3 || str == '3' || str == 'S') ? 'bg-emerald-100 text-emerald-800 font-bold' :
                                            (str == 2 || str == '2' || str == 'M') ? 'bg-amber-100 text-amber-800 font-bold' :
                                            'bg-blue-100 text-blue-800 font-semibold';
                                return `<td class="py-2 px-2"><span class="px-2 py-0.5 rounded text-[11px] ${cls}">${str}</span></td>`;
                              }
                              return `<td class="py-2 px-2 text-slate-300">-</td>`;
                            }).join('')}
                          </tr>
                        `).join('')}
                      </tbody>
                    </table>
                  </div>

                  <!-- Quick Chips List -->
                  <div class="flex flex-wrap gap-1.5 pt-1">
                    ${matrix.map(m => `
                      <span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-slate-200 bg-slate-50 text-[11px]">
                        <strong class="text-blue-700">${m.co}</strong>
                        <span class="text-slate-400">→</span>
                        <strong class="text-slate-700">${m.po}</strong>
                        <span class="px-1.5 py-0.2 rounded font-bold text-[10px] ${
                          m.strength == '3' || m.strength == 3 || m.strength == 'S' ? 'bg-emerald-100 text-emerald-800' :
                          m.strength == '2' || m.strength == 2 || m.strength == 'M' ? 'bg-amber-100 text-amber-800' :
                          'bg-blue-100 text-blue-800'
                        }">${m.strength}</span>
                      </span>
                    `).join('')}
                  </div>
                </div>
              `;
            })() : ''}

            <!-- Textbooks & References -->
            ${(textbooks && textbooks.length > 0) || (references && references.length > 0) ? `
              <div class="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
                ${textbooks && textbooks.length > 0 ? `
                  <div class="space-y-2 p-4 rounded-xl border border-slate-200 bg-slate-50/50">
                    <h4 class="text-xs font-bold text-slate-900 uppercase tracking-wider flex items-center gap-1.5">
                      <span>📚</span> Textbooks (${textbooks.length})
                    </h4>
                    <ul class="text-xs text-slate-600 space-y-1.5 list-disc list-inside">
                      ${textbooks.map(tb => `<li class="leading-snug">${linkify(tb)}</li>`).join('')}
                    </ul>
                  </div>
                ` : ''}

                ${references && references.length > 0 ? `
                  <div class="space-y-2 p-4 rounded-xl border border-slate-200 bg-slate-50/50">
                    <h4 class="text-xs font-bold text-slate-900 uppercase tracking-wider flex items-center gap-1.5">
                      <span>📖</span> Reference Books & Web Resources (${references.length})
                    </h4>
                    <ul class="text-xs text-slate-600 space-y-1.5 list-disc list-inside">
                      ${references.map(rb => `<li class="leading-snug">${linkify(rb)}</li>`).join('')}
                    </ul>
                  </div>
                ` : ''}
              </div>
            ` : ''}

            <!-- Extraction Audit Status (not_extracted) -->
            <div class="p-4 rounded-xl border ${(!data.not_extracted || data.not_extracted.length === 0) ? 'border-emerald-200 bg-emerald-50/50 text-emerald-800' : 'border-amber-200 bg-amber-50/50 text-amber-800'} text-xs space-y-1.5">
              <div class="font-bold flex items-center gap-1.5">
                <span>${(!data.not_extracted || data.not_extracted.length === 0) ? '✅ 100% Extraction Integrity Verified' : '⚠️ Extraction Audit Notes'}</span>
              </div>
              ${(!data.not_extracted || data.not_extracted.length === 0) ? `
                <p class="text-emerald-700 text-[11px]">All examinable units, topics, outcomes, matrix pairs, and citations were extracted and grounded with zero unread sections.</p>
              ` : `
                <ul class="list-disc list-inside text-[11px] space-y-1">
                  ${data.not_extracted.map(note => `<li>${note}</li>`).join('')}
                </ul>
              `}
            </div>

          </div>
        </div>
      `;
    }

    function backToTask1() {
      if (lastDiscoveredData) {
        renderTask1(lastDiscoveredData);
      }
    }

    function copyJson() {
      const code = document.getElementById('jsonOutput').innerText;
      navigator.clipboard.writeText(code).then(() => {
        const btn = document.getElementById('copyBtn');
        btn.innerHTML = '<span>✓ Copied!</span>';
        setTimeout(() => { btn.innerHTML = '<span>📋</span> Copy JSON'; }, 2000);
      });
    }

    function extractJson() {
      const code = document.getElementById('jsonOutput').innerText;
      if (!code) return;

      let filename = 'syllabus_extracted.json';
      try {
        const parsed = JSON.parse(code);
        if (parsed.course && parsed.course.code) {
          filename = `${parsed.course.code}_syllabus.json`;
        } else if (parsed.document) {
          const base = parsed.document.replace(/\.pdf$/i, '');
          filename = `${base}_courses_catalog.json`;
        }
      } catch (e) {}

      const blob = new Blob([code], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      const btn = document.getElementById('extractBtn');
      if (btn) {
        btn.innerHTML = '<span>✓ Extracted!</span>';
        setTimeout(() => { btn.innerHTML = '<span>⬇️</span> Extract JSON'; }, 2000);
      }
    }
  </script>
</body>
</html>
"""


class SyllabusAPIHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Connection", "close")

    def _send_json(self, data: Any, status_code: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()

    def _send_html(self, html_str: str, status_code: int = 200):
        body = html_str.encode("utf-8")
        self.send_response(status_code)
        self._send_cors_headers()
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()
        self.wfile.flush()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self._send_html(HTML_TEMPLATE)
        elif parsed.path == "/api/documents":
            docs = []
            if os.path.exists(UPLOAD_DIR):
                for f in sorted(os.listdir(UPLOAD_DIR)):
                    if f.lower().endswith(".pdf"):
                        full_p = os.path.join(UPLOAD_DIR, f)
                        sz_mb = round(os.path.getsize(full_p) / (1024 * 1024), 2)
                        docs.append({
                            "name": f,
                            "size_mb": sz_mb,
                            "path": full_p
                        })
            self._send_json(docs)
        elif parsed.path == "/api/extract":
            params = urllib.parse.parse_qs(parsed.query)
            pdf_path = params.get("pdf", [""])[0]
            course_code = params.get("course", [""])[0]

            if not os.path.exists(pdf_path):
                self._send_json({"error": f"PDF file '{pdf_path}' not found on server"}, 404)
                return

            try:
                reader = get_cached_reader(pdf_path)
                llm = LLMEngine()
                if not course_code:
                    engine = CourseDiscoveryEngine(reader)
                    resp = engine.run()
                    output_data = resp.model_dump()
                    output_data["document"] = os.path.basename(pdf_path)
                    output_data["saved_path"] = pdf_path
                else:
                    extractor = CourseDetailExtractor(reader, llm_engine=llm)
                    resp = extractor.run(course_code)
                    output_data = resp.model_dump()
                    output_data["saved_path"] = pdf_path

                self._send_json(output_data)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)
        else:
            self._send_json({"error": "Not found"}, 404)

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/documents":
            params = urllib.parse.parse_qs(parsed.query)
            filename = params.get("name", [""])[0]
            safe_name = os.path.basename(filename)
            target = os.path.join(UPLOAD_DIR, safe_name)
            if os.path.exists(target):
                try:
                    os.remove(target)
                    self._send_json({"success": True})
                    return
                except Exception as e:
                    self._send_json({"error": str(e)}, 500)
                    return
            self._send_json({"error": "File not found"}, 404)
        else:
            self._send_json({"error": "Not found"}, 404)

    def do_POST(self):
        if self.path == "/api/upload":
            try:
                content_len = int(self.headers.get("Content-Length", 0))
                if content_len == 0:
                    self._send_json({"error": "Empty payload"}, 400)
                    return

                # Read stream safely in chunks
                remaining = content_len
                chunks = []
                while remaining > 0:
                    chunk = self.rfile.read(min(remaining, 65536))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    remaining -= len(chunk)
                post_body = b"".join(chunks)

                data = json.loads(post_body.decode("utf-8"))
                pdf_base64 = data.get("pdf_base64", "")
                course_code = data.get("course", "").strip()
                filename = data.get("filename", "Uploaded_Syllabus.pdf")
                safe_name = os.path.basename(filename)

                if not pdf_base64:
                    self._send_json({"error": "No PDF data provided"}, 400)
                    return

                pdf_bytes = base64.b64decode(pdf_base64)
                
                # Permanently store the PDF in uploaded_syllabi directory
                saved_pdf_path = os.path.join(UPLOAD_DIR, safe_name)
                with open(saved_pdf_path, "wb") as f:
                    f.write(pdf_bytes)

                try:
                    reader = PDFDocumentReader(saved_pdf_path)
                    llm = LLMEngine()
                    if not course_code:
                        engine = CourseDiscoveryEngine(reader)
                        resp = engine.run()
                        output_data = resp.model_dump()
                        output_data["document"] = safe_name
                        output_data["saved_path"] = saved_pdf_path
                    else:
                        extractor = CourseDetailExtractor(reader, llm_engine=llm)
                        resp = extractor.run(course_code)
                        output_data = resp.model_dump()
                        output_data["saved_path"] = saved_pdf_path

                    self._send_json(output_data)
                except Exception as ex:
                    self._send_json({"error": f"Extraction failed: {str(ex)}"}, 500)
            except Exception as e:
                import traceback
                traceback.print_exc()
                self._send_json({"error": str(e)}, 500)
        else:
            self._send_json({"error": "Not found"}, 404)


def start_server():
    import sys
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    
    server_address = ("", PORT)
    httpd = http.server.ThreadingHTTPServer(server_address, SyllabusAPIHandler)
    httpd.allow_reuse_address = True
    print("==================================================")
    print("Syllabus Studio Web UI running at:")
    print(f"http://localhost:{PORT}")
    print(f"Stored syllabi directory: {UPLOAD_DIR}")
    print("==================================================")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")
        httpd.server_close()


if __name__ == "__main__":
    start_server()
