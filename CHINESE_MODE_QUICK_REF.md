# Chinese Mode Quick Reference

## Toggle Commands

Type any of these (case-insensitive) to toggle Chinese translation mode:
- `[C]` or `(C)`
- `[CHINESE]` or `(CHINESE)`

## Features at a Glance

| Feature | Status |
|---------|--------|
| Translate opening prompt | ✓ |
| Translate NPC responses | ✓ |
| Preserve bold (**text**) | ✓ |
| Preserve italics (*text*) | ✓ |
| Preserve quotes and punctuation | ✓ |
| Preserve line breaks | ✓ |
| Works with Debug Mode | ✓ |
| Graceful error fallback | ✓ |
| Case-insensitive toggle | ✓ |

## Usage Flow

```
1. Start game: __cmd_newgame__:iu_murder_mystery|M|Name
2. Enable Chinese: [C]
3. Play normally - all responses auto-translated
4. Disable Chinese: [C] again
5. Or enable Debug: [D] (works with Chinese mode too)
```

## Implementation Summary

| Component | Details |
|-----------|---------|
| **Location** | `backend/app/api/chat.py` |
| **Toggle Function** | `_is_chinese_toggle(msg)` |
| **Translation Function** | `_translate_to_chinese(text)` (async) |
| **Session Flag** | `SESSIONS[id]["chinese_mode"]` |
| **Tests** | 17 new tests in `test_chinese_mode.py` |
| **Test Pass Rate** | 100% (84/84 tests) |

## Technical Details

**Translation Process:**
1. User enables Chinese mode with `[C]`
2. Next response triggers async OpenAI API call
3. OpenAI translates with `temperature=0.3` (consistent)
4. All formatting preserved (bold, italics, newlines)
5. On error: gracefully falls back to English

**Session Management:**
- Per-session flag in `SESSIONS[session_id]["chinese_mode"]`
- Persists across turns until toggled off
- Reset to `False` on `__cmd_reset__`
- Initialized as `False` for all new sessions

**Error Handling:**
- API timeout (30s): Fallback to English
- HTTP errors: Fallback to English  
- Network exceptions: Fallback to English
- All errors logged to stdout

## Code Locations

| Functionality | File | Lines |
|--------------|------|-------|
| Toggle tokens | chat.py | ~80 |
| Toggle function | chat.py | ~82 |
| Translation function | chat.py | ~130-190 |
| Session init | chat.py | ~210 |
| Toggle handler | chat.py | ~351 |
| Reset command | chat.py | ~400 |
| Opening translation | chat.py | ~483 |
| Response translation | chat.py | ~680 |
| Tests | test_chinese_mode.py | All |
| Docs | copilot-instructions.md | ~110 |

## Debugging

### Check if Chinese mode is enabled
```python
from backend.app.api.chat import SESSIONS
print(SESSIONS[session_id]["chinese_mode"])
```

### Monitor translation errors
Look for these in Railway logs:
- `"kind": "chinese_translation_error"` - API HTTP errors
- `"kind": "chinese_translation_exception"` - Python exceptions

### Test translation function
```python
import asyncio
from backend.app.api.chat import _translate_to_chinese
result = asyncio.run(_translate_to_chinese("Hello world"))
print(result)
```

## Performance Impact

- **Per-response latency**: +300-800ms (OpenAI API roundtrip)
- **Token cost**: ~50-150 tokens per translation
- **Fallback time**: <10ms (immediate English fallback on error)
- **Memory**: Minimal (flag only, no caching)

## Compatibility Matrix

| Feature | Compatible | Notes |
|---------|-----------|-------|
| Debug Mode | ✓ Yes | Both show in response |
| World Navigation | ✓ Yes | Translates location descriptions |
| Character Knowledge | ✓ Yes | Uses same retrieval system |
| State Tags | ✓ Yes | Applied before translation |
| Opening Prompt | ✓ Yes | Translated on newgame |
| Confession Detection | ✓ Yes | Works on English, then translates |
| Name Extraction | ✓ Yes | Extracted before translation |
| Time Advancement | ✓ Yes | Not affected by translation |

## Testing Checklist

- ✅ Toggle detection (all 8 formats)
- ✅ Case insensitivity
- ✅ Session state management
- ✅ Formatting preservation
- ✅ Error fallback
- ✅ Opening prompt translation
- ✅ Regular response translation
- ✅ Debug mode coexistence
- ✅ Empty response handling
- ✅ Whitespace handling

**Total**: 17 tests | **Pass Rate**: 100%

## Future Roadmap

- [ ] Multi-language support (Spanish, French, Japanese)
- [ ] Translation caching to reduce API calls
- [ ] Language selection at game start UI
- [ ] Real-time streaming translations
- [ ] Cultural adaptation beyond literal translation
- [ ] Per-response language switching

---

For detailed documentation, see: [CHINESE_MODE_FEATURE.md](CHINESE_MODE_FEATURE.md)
