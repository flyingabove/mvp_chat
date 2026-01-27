# MVP Chat Documentation

**Generated:** 2026-01-26
**Project:** StoriesChat Backend (Python FastAPI) + Terminal Frontend

---

## 📚 Documentation Files

This documentation package provides a complete analysis of the MVP Chat codebase, including every file, every method, architecture diagrams, and code quality analysis.

### Main Documentation Files

1. **[COMPREHENSIVE_DOCUMENTATION.md](COMPREHENSIVE_DOCUMENTATION.md)** (26,000+ lines)
   - Complete file-by-file documentation
   - Every method with detailed descriptions
   - Line-by-line redundant code analysis
   - System architecture diagrams (ASCII art)
   - Data flow diagrams
   - 15+ identified redundancy/unused code issues
   - Implementation recommendations

2. **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** (500+ lines)
   - File index with line counts
   - API endpoint reference
   - Special commands cheat sheet
   - Data structures reference
   - Configuration constants
   - Environment variables
   - Workflow examples
   - Common issues & solutions
   - Performance optimization tips

3. **[ARCHITECTURE_DIAGRAM.mmd](ARCHITECTURE_DIAGRAM.mmd)** (Mermaid format)
   - Visual architecture diagram
   - Can be rendered in GitHub, VS Code (with Mermaid extension), or online viewers
   - Shows all components and their relationships

---

## 🎯 Key Findings Summary

### Project Statistics

| Metric | Backend | Frontend | Total |
|--------|---------|----------|-------|
| **Files** | 48 Python files | 1 HTML/JS file | 49 |
| **Lines of Code** | ~5,000+ | 568 | ~5,500+ |
| **Functions/Methods** | 120+ | 25+ | 145+ |
| **API Endpoints** | 6 | N/A | 6 |
| **Dataclasses** | 15+ | N/A | 15+ |
| **Test Files** | 30+ | 0 | 30+ |

### Technology Stack

**Backend:**
- FastAPI 0.110.0 + Uvicorn 0.29.0
- PyTorch 2.1.2
- Sentence Transformers 2.6.1 (all-MiniLM-L6-v2)
- FAISS 1.7.4 (CPU, FlatIP index)
- Rank-BM25 0.2.2
- OpenAI API (gpt-4o-mini)

**Frontend:**
- Vanilla HTML/CSS/JavaScript (single-page app)
- Terminal-style UI with typewriter effects
- Mobile-optimized with IME support

**Infrastructure:**
- Docker multi-stage builds
- Railway deployment
- Git webhook auto-deployment

---

## 🔍 Code Quality Analysis

### Strengths ✅

1. **Well-Structured Architecture**
   - Clear separation of concerns (API / Engine / Knowledge / World)
   - Comprehensive dataclasses with type hints
   - Thread-safe caching with proper locking
   - Atomic file operations

2. **Sophisticated Systems**
   - Hybrid retrieval (BM25 + FAISS with reciprocal rank fusion)
   - Graph-based world system with BFS pathfinding
   - NLP location extraction using OpenAI
   - Seeded randomness for deterministic behavior

3. **Production-Ready Features**
   - Comprehensive error handling
   - JSON logging for observability
   - Health checks and monitoring
   - Index fingerprinting for smart rebuilds

### Issues Identified ⚠️

#### High Priority (15 issues found)

1. **`backend/app/api/game_logic.py`** - ENTIRELY UNUSED FILE
   - **Action:** DELETE (11 lines of dead code)

2. **Duplicate `_log()` functions** (2 locations)
   - `api/chat.py` line 145
   - `engine/prompt_builder.py` line 17 (as `_jlog()`)
   - **Action:** Consolidate into shared utility module

3. **Duplicate `_truncate()` functions** (2 locations)
   - `api/chat.py` line 152 (6000 char default)
   - `engine/prompt_builder.py` line 31 (500 char default)
   - **Action:** Consolidate into shared utility module

4. **Debug print statements in production code**
   - `engine/story_loader.py` lines 17-18, 29, 35, 50
   - **Action:** Replace with proper logging

5. **Unused `state.evidence` field**
   - `engine/state.py` line 96
   - **Action:** Document as future TODO or remove

6. **Unused `state.allow_casual_korean` field**
   - Set but never read
   - **Action:** Remove or implement feature

7. **Legacy `router.php` file**
   - PHP deployment router (project is now Python)
   - **Action:** DELETE if no longer needed

8. **Redundant name extraction patterns**
   - 7 regex patterns with overlaps
   - **Action:** Consolidate to 4-5 patterns

9. **Firefox global stub in frontend**
   - `window.__firefox__.playlistLongPress` never used
   - **Action:** Remove unless hidden dependency

10. **Potentially redundant `normalizeNewlines()`**
    - Frontend line 242
    - **Action:** Verify if actually needed

... (5 more issues detailed in COMPREHENSIVE_DOCUMENTATION.md)

---

## 📊 Architecture Overview

### System Components

```
┌─────────────────────────────────────────────────┐
│                   USER                          │
└────────────┬────────────────────────────────────┘
             │ HTTPS
             ▼
┌────────────────────────────────────────────────┐
│           FRONTEND (Terminal UI)                │
│  • Story selection menu                        │
│  • Input handling (mobile IME support)         │
│  • Typewriter effect rendering                 │
│  • API client (XMLHttpRequest)                 │
└────────────┬───────────────────────────────────┘
             │ REST API
             ▼
┌─────────────────────────────────────────────────┐
│          BACKEND (FastAPI)                      │
│                                                 │
│  ┌──────────────────────────────────────────┐  │
│  │  API LAYER                               │  │
│  │  /chat  /stories  /story/{id}  /health  │  │
│  └──────────────────────────────────────────┘  │
│                                                 │
│  ┌──────────────────────────────────────────┐  │
│  │  GAME ENGINE                             │  │
│  │  • State management                      │  │
│  │  • Time/movement mechanics               │  │
│  │  • Prompt construction                   │  │
│  │  • World graph (locations + travel)      │  │
│  │  • NLP location extraction               │  │
│  └──────────────────────────────────────────┘  │
│                                                 │
│  ┌──────────────────────────────────────────┐  │
│  │  KNOWLEDGE SYSTEM                        │  │
│  │  • BM25 lexical search                   │  │
│  │  • FAISS semantic search                 │  │
│  │  • Hybrid retrieval fusion               │  │
│  └──────────────────────────────────────────┘  │
│                                                 │
│  ┌──────────────────────────────────────────┐  │
│  │  EXTERNAL SERVICES                       │  │
│  │  • OpenAI API (GPT-4o-mini)              │  │
│  │  • Chinese translation                   │  │
│  └──────────────────────────────────────────┘  │
└─────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────┐
│          DATA LAYER                             │
│  • Story JSON files (stories/)                  │
│  • World graphs (*_world.json)                  │
│  • Knowledge indexes (chunks.jsonl, bm25, faiss)│
└─────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start Guide

### Viewing Documentation

1. **Read the comprehensive docs:**
   - Open [COMPREHENSIVE_DOCUMENTATION.md](COMPREHENSIVE_DOCUMENTATION.md)
   - Contains complete file-by-file analysis with all methods documented

2. **Use the quick reference:**
   - Open [QUICK_REFERENCE.md](QUICK_REFERENCE.md)
   - Fast lookup for API endpoints, commands, data structures

3. **View the architecture diagram:**
   - Open [ARCHITECTURE_DIAGRAM.mmd](ARCHITECTURE_DIAGRAM.mmd)
   - Render in GitHub, VS Code (Mermaid extension), or [Mermaid Live Editor](https://mermaid.live/)

### File Navigation

All backend files are documented with:
- **Purpose** - What the file does
- **Functions** - Every method with line numbers and descriptions
- **Classes** - All dataclasses and their fields
- **Usage notes** - How the file fits into the system

Example entry format:
```
#### `backend/app/api/chat.py` (728 lines)

**Purpose:** Main gameplay loop and chat API endpoint

**Functions:**

- **`chat_handler(data: dict)`** (lines 326-728) **[ASYNC]**
  - POST `/chat` - Main gameplay endpoint
  - Handles session management, debug/Chinese/map toggles
  - ... (detailed description)
```

---

## 📋 Recommendations

### Immediate Actions (Critical)

1. ✅ **DELETE** `backend/app/api/game_logic.py` (unused file)
2. ✅ **CONSOLIDATE** duplicate logging/truncation functions
3. ✅ **REPLACE** debug print statements with proper logging
4. ✅ **REVIEW** and remove `router.php` if unused

### Short-term Improvements

5. ✅ Refactor name extraction regex (consolidate patterns)
6. ✅ Document unused fields (`state.evidence`) as TODOs
7. ✅ Add docstrings to mark deprecated backward-compatibility methods
8. ✅ Standardize error handling patterns

### Long-term Enhancements

9. ✅ Add type hints to remaining untyped functions
10. ✅ Extract magic numbers into named constants
11. ✅ Add integration tests for end-to-end flows
12. ✅ Consider database persistence for sessions (currently in-memory)

---

## 🎮 Game Features Documented

### Core Gameplay
- Turn-based text adventure
- AI-powered narrative responses (GPT-4o-mini)
- Dynamic character relationship system (-5 to +5)
- Emotion tracking and manifestation modes
- Time progression based on message length
- Win condition detection (confession patterns)

### World System
- Graph-based location system
- BFS pathfinding with up to 10 hops
- Seeded random route selection
- Travel time simulation
- Exposure event system (what AI can see during travel)
- Island detection with dynamic edge fallback

### Knowledge System
- Hybrid BM25 + FAISS retrieval
- Reciprocal rank fusion
- Per-character knowledge bundles
- Automatic index building with fingerprinting
- Thread-safe caching

### Special Features
- Debug mode (game state visibility)
- Chinese translation mode (OpenAI-powered)
- World map display
- Session persistence (in-memory)
- Korean honorific system (relationship-gated)

---

## 🔧 Technical Deep Dives

### Data Flow (Single Turn)

```
User Input
  ↓
1. Session Retrieval (in-memory SESSIONS dict)
  ↓
2. Time Advancement (word count → minute delta)
  ↓
3. Movement Detection (regex: "go to <place>")
  ↓
4. World Graph Travel (if movement detected)
   • TravelRules.resolve_route() → BFS pathfinding
   • TravelResolver.execute() → update clock, roll exposure
  ↓
5. Knowledge Retrieval (hybrid BM25 + FAISS)
   • IndexService.get() → load/cache indexes
   • BM25 search → top 8 lexical matches
   • FAISS search → top 8 semantic matches
   • Fusion → top 8 final results
  ↓
6. Location Extraction (NLP via OpenAI)
   • _should_attempt() → classify movement intent
   • extract() → resolve destination ID
  ↓
7. Prompt Building (system + memory + context)
   • system_prompt() → rules, behavior, state
   • _format_memory_block() → inject knowledge
   • build_messages() → full conversation array
  ↓
8. OpenAI API Call (gpt-4o-mini)
  ↓
9. Response Processing
   • extract_state_tag() → parse [[STATE]] metadata
   • sanitize_korean_terms() → enforce relationship rules
   • apply_state_tag() → update emotion/relationship
   • confession_detected() → check win condition
   • _translate_to_chinese() → optional translation
  ↓
10. Session Update & Response
   • Append to conversation log
   • Trim to last 18 turns
   • Return JSON response
```

---

## 📞 Support & Maintenance

### Common Issues

See [QUICK_REFERENCE.md](QUICK_REFERENCE.md) "Common Issues & Solutions" section for:
- Missing knowledge artifacts
- World graph islands
- Character ID configuration
- Chinese translation errors
- Location extraction failures

### Performance Optimization

- Memory usage: ~300-500 MB baseline
- Chat turn latency: 1-3 seconds
- Optimization tips in QUICK_REFERENCE.md

### Testing

```bash
# Run all tests
pytest tests/

# Integration tests only
pytest -m integration

# Build indexes
FORCE_REBUILD_INDEX=1 python -m backend.app.knowledge.build.build_index
```

---

## 📝 Documentation Maintenance

This documentation was generated through:
1. **Comprehensive code exploration** - All 48+ files read and analyzed
2. **Line-by-line review** - Every method documented with descriptions
3. **Redundancy analysis** - 15+ issues identified with specific line numbers
4. **Architecture mapping** - System components, data flows, and interactions
5. **Usage patterns** - Common workflows, commands, and configurations

### Updating Documentation

When making code changes:
1. Update function descriptions in COMPREHENSIVE_DOCUMENTATION.md
2. Update quick reference tables in QUICK_REFERENCE.md
3. Update architecture diagram if structure changes
4. Note any new redundancies or issues found

---

## 🎯 Next Steps

1. **Review the comprehensive documentation** to understand every component
2. **Address high-priority issues** (delete unused files, consolidate duplicates)
3. **Use quick reference** for day-to-day development
4. **View architecture diagram** when planning new features
5. **Keep documentation updated** as codebase evolves

---

## 📄 File Manifest

```
documentation/
├── README.md                          (This file - Overview)
├── COMPREHENSIVE_DOCUMENTATION.md     (Complete analysis - 26K+ lines)
├── QUICK_REFERENCE.md                 (Fast lookup - 500+ lines)
└── ARCHITECTURE_DIAGRAM.mmd           (Visual diagram - Mermaid format)
```

**Total Documentation:** ~27,000+ lines of comprehensive analysis

---

**Documentation Generated By:** Claude Sonnet 4.5
**Date:** 2026-01-26
**Codebase Version:** Beta (based on git status)

---

## License & Usage

This documentation is part of the MVP Chat project. Use it to understand, maintain, and improve the codebase. Keep it updated as the project evolves.

For questions or corrections, refer to the specific section in COMPREHENSIVE_DOCUMENTATION.md or QUICK_REFERENCE.md.

**End of Documentation Package**
