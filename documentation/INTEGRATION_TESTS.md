# Integration Tests Documentation

This document provides a comprehensive guide to all integration tests in the mvp_chat project, including what each test validates, the dialogue involved, and the testing patterns used.

## Overview

Integration tests are marked with `@pytest.mark.integration` and test end-to-end flows involving real API calls, world graphs, and complex game state management. Some integration tests are platform-specific (Linux/Railway only) and skip on Windows.

**Location**: `tests/backend/integration/`

---

## Test Files

### 1. `test_api_play_5_turns_world_time.py`

**Purpose**: Validates the complete 5-turn gameplay flow with world navigation, time advancement, and location tracking.

**Key Validations**:
- ✅ New game initialization with IU story and world graph
- ✅ Location extraction and canonicalization across 5 turns
- ✅ Time advancement calculations with movement cost
- ✅ World graph edge resolution and travel timing
- ✅ State persistence across multiple turns

#### Test: `test_api_end_to_end_5_turns_time_and_location`

**What it tests**:
1. Game initialization with story loading
2. Turn 1: Normal dialogue ("hello")
3. Turns 2-5: Sequential travel through world locations
4. Proper time calculation with movement penalties
5. Location state tracking and canonicalization

**Dialogue Flow**:

```
[Game Initialization]
User: __cmd_newgame__:iu_murder_mystery|M|Chris
→ Loads world graph with 11 locations
→ Sets starting location: "iu_apartment_room"
→ Initializes minute counter: 0

[Turn 1 - Normal Dialogue]
User: "hello"
→ Time cost: BASE_TURN_MINS(1) + word_count(1) * MINS_PER_WORD(0.25) = 2 minutes
→ No location change
→ State.minute = 2

[Turn 2 - First Movement]
User: "go to iu_apartment_lobby"
→ Location extraction identifies destination
→ Time cost: 2 (dialogue) + 1 (exit) + 2 (edge weight) = 5 minutes
→ Location changes from "iu_apartment_room" → "iu_apartment_lobby"
→ State.minute = 7

[Turn 3 - Continue Travel]
User: "go to apartment_parking_garage"
→ Time cost: 2 + 1 + 3 = 6 minutes
→ Location: "iu_apartment_lobby" → "apartment_parking_garage"
→ State.minute = 13

[Turn 4 - Vehicle Travel]
User: "go to my_car"
→ Time cost: 2 + 1 + 1 = 4 minutes
→ Location: "apartment_parking_garage" → "my_car"
→ State.minute = 17

[Turn 5 - Long Distance Travel]
User: "go to workplace_lobby"
→ Time cost: 2 + 1 + 15 = 18 minutes (15-minute edge weight)
→ Location: "my_car" → "workplace_lobby"
→ State.minute = 35
```

**Time Calculation Breakdown**:
- Formula: `BASE_TURN_MINS + word_count * MINS_PER_WORD + travel_edge_weight + EXIT_PENALTY`
- Each location change adds:
  - Dialog cost: 2 minutes (1 base + 1 for word)
  - Exit cost: 1 minute
  - Edge weight: varies by route (2, 3, 1, 15 in this test)

**Assertions**:
```python
assert st.location_id == "workplace_lobby"
assert st.location == "EDAM Entertainment Lobby"
assert st.minute == 35  # Total time elapsed
assert not reply_text.startswith("[")  # No timestamp prefix
assert reply_text.lstrip().startswith("*")  # Starts with dialogue
```

**Mocking Pattern**:
- Knowledge retrieval mocked to empty list (speeds up test)
- OpenAI HTTP calls mocked with simple responses
- Session state maintained across all 5 turns

---

### 2. `test_hybrid_retrieval.py`

**Purpose**: Validates that the hybrid BM25 + FAISS retrieval system returns real character knowledge with quality metrics.

**Key Validations**:
- ✅ Real character indexes load from persistent cache
- ✅ Hybrid retrieval combines BM25 (lexical) + FAISS (semantic) search
- ✅ Retrieved chunks contain actual character facts
- ✅ High recall rate on factual queries

#### Test: `test_character_hybrid_retrieval_recall_threshold`

**What it tests**:
1. Loads persistent character indexes from `/data` directory (Railway only)
2. Runs 22 diverse factual queries about IU
3. Validates that each query returns relevant chunks
4. Checks recall threshold (min 18/22 queries must succeed = 81% recall)

**Test Data**:
```python
TEST_CASES_BY_CHARACTER = {
    "1_iu": [
        {"section": "identity", "q": "What is the legal name?", "ans": "iu_1_identity_basic"},
        {"section": "physical", "q": "How tall?", "ans": "iu_2_personal_physical"},
        {"section": "career timeline", "q": "Which song was breakthrough in 2010?", "ans": "iu_7_career_2010_breakthrough"},
        # ... 19 more test cases covering all knowledge domains
    ]
}
```

**Knowledge Categories Tested**:
- Identity & personal facts
- Physical attributes
- Fashion/style
- Public image & nickname
- Financial status
- Career timeline (debut, breakthrough songs)
- Music albums & EPs
- Remake series
- Signature songs
- Song summaries ("Good Day" musical features)
- Acting roles (dramas, films)
- Philanthropy work
- Personal life & relationships
- Notable quotes
- Education & family background
- Living situation & childhood memories
- Audition anecdotes
- Narrative memories

**Query Dialogue Example**:
```
Query 1: "What is the legal name?"
→ BM25 search finds "iu_1_identity_basic" chunk
→ FAISS semantic search finds related identity chunks
→ Hybrid merge ranks "iu_1_identity_basic" highest
→ Chunk returned: "IU's legal name is Lee Ji-eun..."

Query 7: "Which song was breakthrough in 2010?"
→ BM25 matches "2010", "breakthrough", "song"
→ FAISS finds semantic similarity: [debut, career, famous]
→ Result: "iu_7_career_2010_breakthrough"
→ Chunk content: "In 2010, IU's breakthrough hit was 'Good Day'..."

Query 22: "Which narrative mentions KBS Music Bank and Lost and Found?"
→ BM25: exact phrase match on both terms
→ FAISS: semantic clustering of music program episodes
→ Result: "iu_49_narrative_music_bank"
```

**Success Metrics**:
- Recall threshold: ≥ 18/22 queries succeed (81%)
- Each chunk must have non-empty text content
- Character ID mentioned in combined results

**Platform Requirements**:
- ⚠️ **Linux/Railway only** - skips on Windows
- Requires `/data/knowledge_cache` with pre-built indexes
- Depends on `KNOWLEDGE_CACHE_DIR` environment variable

**Environment Variables**:
```bash
KNOWLEDGE_CACHE_DIR=/data/knowledge_cache    # Must start with /data
TEST_CHARACTER_ID=1_iu                       # Optional, defaults to "1_iu"
```

---

### 3. `test_retrieval_e2e.py`

**Purpose**: End-to-end validation that knowledge retrieval actually returns real character knowledge (not hallucinations).

**Key Validations**:
- ✅ Character indexes load successfully
- ✅ Retrieval returns non-empty chunks
- ✅ Chunks contain actual character knowledge
- ✅ No silently hallucinating generic answers

#### Test: `test_character_retrieval_returns_real_knowledge`

**What it tests**:
1. Loads real character indexes from cache
2. Runs single query: "who are you"
3. Validates retrieval returns real chunks with content
4. Ensures chunks are not empty/hallucinated

**Dialogue Flow**:
```
Query: "who are you"
→ Character bundle loaded: indexes, chunks, BM25, FAISS
→ Hybrid retrieval runs on query
→ Expected to find identity-related chunks
→ Example returned chunks:
   - "IU (real name: Lee Ji-eun) is a South Korean actress and singer..."
   - "Known for vocal range and songwriting abilities..."
   - "Career began in 2008 with debut 'Lost and Found'..."

Validation:
✅ chunks is non-empty list
✅ chunks[0].get("text") has content (length > 0)
✅ Joined text from all chunks is substantial
❌ Would fail if retrieval returns: [] or [{"text": ""}]
```

**Hard Fail Conditions**:
```python
assert chunks, "Retrieval returned no chunks"  # Empty list fails
assert isinstance(chunks, list)                # Must be list
joined_text = " ".join((c.get("text", "") or "").lower() for c in chunks)
assert len(joined_text) > 0                    # Must have content
```

**Platform Requirements**:
- ⚠️ **Linux/Railway only** - skips on Windows
- Requires `/data/knowledge_cache` with character indexes
- Environment variable: `TEST_CHARACTER_ID` (optional, defaults to "1_iu")

**Purpose in CI/CD**:
- Validates that knowledge system is properly initialized
- Detects broken indexes at deployment time
- Ensures real character knowledge is available

---

### 4. `test_location_extractor_e2e.py`

**Purpose**: Integration tests for the LocationExtractor that call the real OpenAI API to validate LLM-powered location extraction.

**Key Validations**:
- ✅ LLM correctly classifies movement intents
- ✅ Destination IDs are valid and exist in world graph
- ✅ Confidence scores are reasonable (≥ 0.7 for positive cases)
- ✅ Natural language variations are handled
- ✅ Questions/hypotheticals are correctly rejected

#### Tests Overview

**World Graph Setup** (available for all tests):
```python
_WorldGraph():
  "office_lobby"
  "office_conference_room"
  "coffee_shop"
  "apartment"
  "apartment_bedroom"
  "workplace_lobby"
  "edam_building"
  "rooftop"
  "parking_garage"
  ... (13 locations total)
```

**Test 1: `test_location_extractor_real_api_explicit_command`**

**Dialogue**:
```
User: "go to office lobby"
LLM Classification:
→ is_movement_intent? YES (explicit "go to" command)
LLM Extraction:
→ destination: "office_lobby" ✓
→ confidence: 0.95

Result:
✅ intent == LocationIntent.MOVE
✅ destination_id == "office_lobby"
✅ confidence >= 0.7
```

---

**Test 2: `test_location_extractor_real_api_natural_language`**

**Dialogue**:
```
User: "i'm going to the workplace lobby"
LLM Classification:
→ is_movement_intent? YES (implicit movement)
LLM Extraction:
→ destination: "workplace_lobby" ✓
→ confidence: 0.88

Result:
✅ intent == LocationIntent.MOVE
✅ destination_id in world_graph.locations
✅ confidence >= 0.7
```

---

**Test 3: `test_location_extractor_real_api_head_to`**

**Dialogue**:
```
User: "head to the coffee shop"
LLM Classification:
→ is_movement_intent? YES ("head to" variant)
LLM Extraction:
→ destination: "coffee_shop" ✓
→ confidence: 0.92

Pattern tested:
- Validates alternative phrasing ("head to" vs "go to")
- Ensures variability in user input is handled
```

---

**Test 4: `test_location_extractor_real_api_rejects_question`**

**Dialogue**:
```
User: "can we go to the office?"
LLM Classification:
→ is_movement_intent? NO (question, not command)
→ confidence: 0.95 (high confidence in rejection)

Result:
✅ intent == LocationIntent.NONE
✅ destination_id is None
```

**Key insight**: LLM distinguishes between:
- **Command**: "I'm going to X" → MOVE
- **Question**: "Can we go to X?" → NONE
- **Suggestion**: "Should I head to X?" → NONE

---

**Test 5: `test_location_extractor_real_api_should_i_go`**

**Dialogue**:
```
User: "should I head to the apartment?"
LLM Classification:
→ is_movement_intent? NO (question form)
→ confidence: 0.94

Result:
✅ intent == LocationIntent.NONE
✅ destination_id is None
```

---

**Test 6: `test_location_extractor_real_api_ambiguous_extraction`**

**Dialogue**:
```
User: "go to office"
Challenge: "office" could match:
  - "office_lobby"
  - "office_conference_room"

LLM Extraction:
→ LLM picks most likely: "office_lobby"
→ confidence: 0.75

Result:
✅ intent == LocationIntent.MOVE
✅ destination_id in ["office_lobby", "office_conference_room"] (valid)
✅ Gracefully handles ambiguity
```

**Note**: LLM uses knowledge context (when available in pipeline) to disambiguate:
- If knowledge mentions "office_conference_room" meeting, prefers that
- Otherwise defaults to primary location "office_lobby"

---

**Test 7: `test_location_extractor_real_api_long_narrative`**

**Dialogue**:
```
User: "actually I'm going to your workplace see you in a bit"
Challenge: Complex multi-clause natural language

LLM Classification:
→ is_movement_intent? YES (contains "going to")
LLM Extraction:
→ destination: "workplace_lobby" or "workplace_hallway"
→ confidence: 0.82

Result:
✅ intent == LocationIntent.MOVE
✅ destination_id in world_graph.locations
✅ Handles complex, natural dialogue
```

---

**Test 8: `test_location_extractor_real_api_no_empty_messages`**

**Dialogue**:
```
User: "" (empty)
LLM Classification:
→ is_movement_intent? NO (no content)
LLM Extraction:
→ destination: None
→ confidence: 0.0

Result:
✅ intent == LocationIntent.NONE
✅ destination_id is None
✅ Gracefully handles edge case
```

---

**Test 9: `test_location_extractor_real_api_move_to_variant`**

**Dialogue**:
```
User: "move to conference room"
Alternative phrasing test

LLM Classification:
→ is_movement_intent? YES ("move to" variant)
LLM Extraction:
→ destination: "office_conference_room"
→ confidence: 0.90

Pattern tested:
- "go to", "head to", "move to" all recognized
- Validates synonym handling
```

---

**Platform Requirements**:
- Requires valid `OPENAI_API_KEY` environment variable
- Skips if API key not available (not marked as integration, optional)
- Real API calls add ~1-2 seconds per test
- Total suite runtime: ~20-30 seconds

**Skip Conditions**:
```python
@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set")
```

---

## Running Integration Tests

### Run all integration tests (Linux/Railway):
```bash
KNOWLEDGE_CACHE_DIR=/data/knowledge_cache pytest tests/backend/integration -v
```

### Run specific test file:
```bash
pytest tests/backend/integration/test_api_play_5_turns_world_time.py -v
```

### Run with test character override:
```bash
TEST_CHARACTER_ID=1_iu KNOWLEDGE_CACHE_DIR=/data/knowledge_cache \
  pytest tests/backend/integration/test_hybrid_retrieval.py -v
```

### Skip integration tests (unit testing only):
```bash
pytest tests/backend/app -v  # Excludes tests/backend/integration
```

### Run on Windows (expects most to skip):
```bash
pytest tests/backend/integration -v
# Output: skipped on Windows (requires Railway Linux environment)
```

---

## Integration Test Patterns

### Pattern 1: Mocking External Services
```python
# Mock LLM responses for deterministic testing
def _fake_post(self, url, headers=None, json=None):
    return _FakeResponse(_make_assistant_reply(turn))

monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)
```

**Why**: Removes dependency on OpenAI API rate limits and costs during CI/CD.

### Pattern 2: Real Knowledge Index Loading
```python
# Load real persisted indexes for retrieval validation
bundle = load_character_indexes(character_id)
chunks = bundle.chunks  # Real knowledge data
```

**Why**: Validates that deployment builds correct knowledge artifacts.

### Pattern 3: Platform Detection
```python
if platform.system() == "Windows":
    pytest.skip("Integration test skipped on Windows (requires Railway Linux)")
```

**Why**: Integration tests assume Linux `/data` paths (Railway deployment environment).

### Pattern 4: End-to-End State Validation
```python
# Validate internal game state after multi-turn gameplay
sess = chat_module.SESSIONS["t1"]
st = sess["state"]
assert st.location_id == "workplace_lobby"
assert st.minute == 35  # Specific time calculation
```

**Why**: Ensures state machines are working correctly across turns.

---

## Debugging Integration Tests

### Disable Mocking to Call Real OpenAI:
```bash
OPENAI_API_KEY=sk-... pytest tests/backend/integration/test_location_extractor_e2e.py -xvs
```

### Inspect Knowledge Indexes:
```python
from backend.app.knowledge.runtime.load_indexes import load_character_indexes
bundle = load_character_indexes("1_iu")
print(f"Total chunks: {len(bundle.chunks)}")
print(f"First chunk: {bundle.chunks[0]}")
```

### Check Time Calculation Details:
```python
# In test output:
assert st.minute == 35  # Shows expected time
# Breakdown: 2 + (2+1+2) + (2+1+3) + (2+1+1) + (2+1+15) = 35
```

---

## CI/CD Integration

### Railway Deployment:
```yaml
# In railway.toml or CI config
env:
  KNOWLEDGE_CACHE_DIR: /data/knowledge_cache
  SKIP_KNOWLEDGE_INDEX_BUILD: 0

test:
  cmd: pytest tests/backend/integration -v --tb=short
```

### GitHub Actions (if applicable):
```yaml
- name: Run Integration Tests
  if: github.ref == 'refs/heads/main'
  env:
    OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
    KNOWLEDGE_CACHE_DIR: /data/knowledge_cache
  run: pytest tests/backend/integration -v
```

---

## Test Maintenance

### Adding New Integration Tests:

1. **Determine scope**: End-to-end flow vs. single component
2. **Choose location**: Add to appropriate file or create new
3. **Use existing patterns**:
   - Mock external services (OpenAI, HTTP)
   - Platform detection for Linux-only tests
   - JSON logging for debugging
4. **Document dialogue flow**: Show example user/system exchanges
5. **Validate hard invariants**: Use `assert` for non-negotiable contracts

### Updating Test Data:

- **Location lists**: Edit `tests/backend/integration/test_location_extractor_e2e.py` `_WorldGraph`
- **Knowledge test cases**: Update `TEST_CASES_BY_CHARACTER` in `test_hybrid_retrieval.py`
- **Time calculations**: Update `test_api_play_5_turns_world_time.py` expectations

---

## Related Documentation

- [CODEBASE_DOCUMENTATION.md](CODEBASE_DOCUMENTATION.md) - Full API and engine documentation
- [ARCHITECTURE_DIAGRAMS.md](ARCHITECTURE_DIAGRAMS.md) - System architecture and data flows
- [../../.github/copilot-instructions.md](../../.github/copilot-instructions.md) - Development guidelines

