# Intent Logging Design

## Overview

A separate logging system that captures high-level model intentions - parallel to existing tool-call logging but on a semantic level.

**Purpose:**

- Accountability for stakeholders: What did the user want? What did the model try to do?
- Non-technical audit trail (no tool args, no durations)
- Retrievable as MCP Resource at end of session

**Components:**

1. `log_intent` Tool - Model documents its intentions
2. `IntentFileHandler` - Writes to JSONL file (optional, if AUDIT_LOG_DIR set)
3. In-memory store - Always keeps entries per session
4. `intent://session/{session_id}` Resource - Retrieve session entries

## Data Structure

**Intent Entry:**

```json
{
    "timestamp": "2026-01-03T12:34:56.789+00:00",
    "session_id": "abc-123-def",
    "intent": "Check invoice 4711 and change payment terms to ZB01",
    "context": {
        "tcode": "VA02",
        "document_id": "4711"
    }
}
```

**Tool Signature:**

```python
async def log_intent(
    intent: str,
    context: dict[str, str] | None = None
) -> IntentLogResult:
```

**Pydantic Models:**

```python
class IntentEntry(BaseModel):
    timestamp: AwareDatetime
    session_id: str
    intent: str
    context: dict[str, str] = Field(default_factory=dict)
    entry_id: str = Field(default_factory=lambda: str(uuid4()))

class IntentLogResult(ToolResult):
    logged: bool = Field(description="Whether the entry was recorded")
    entry_id: str | None = Field(default=None, description="UUID of the entry")
```

## Storage

### In-Memory (Always)

```python
# Per-session intent storage
_session_intents: dict[str, list[IntentEntry]] = {}
```

- Always active
- Serves the MCP Resource
- Cleared when session ends

### File (Optional)

**Filename format:**

```
audit_20260103T123456_{session_id}.jsonl
```

**Trigger:** New file created on `sap_login`

**Handler:**

```python
class IntentFileHandler(logging.Handler):
    """Writes intent logs to audit_YYYYMMDDTHHMMSS_{session_id}.jsonl"""

    def __init__(self, log_dir: Path):
        self.log_dir = log_dir

    def emit(self, record: LogRecord):
        if not record.getMessage().startswith("INTENT |"):
            return
        # Parse and write as JSON line
        ...
```

**Configuration:**

- `AUDIT_LOG_DIR` environment variable
- If empty: no file persistence, only in-memory
- If set: writes to specified directory (should be mounted volume for Docker)

## MCP Resource

**URI:** `intent://session/{session_id}`

**Implementation:**

```python
@mcp.resource("intent://session/{session_id}")
async def get_session_intent_log(session_id: str) -> str:
    """Returns all intent entries for a session as JSON array."""
    entries = _session_intents.get(session_id, [])
    return json.dumps([e.model_dump() for e in entries], default=str)
```

**Returns:** JSON Array of intent entries

## Logging Integration

**Logger:** Uses standard `__name__` convention

```python
# In sapguimcp/tools/intent_tools.py
_logger = logging.getLogger(__name__)

def log_intent(...):
    _logger.info("INTENT | session=%s | %s", session_id, intent)
```

**Handler routing:** `IntentFileHandler` filters by `"INTENT |"` prefix

## File Structure

**New files:**

```
src/sapguimcp/
├── tools/
│   └── intent_tools.py       # log_intent tool
├── loghandlers/
│   ├── __init__.py
│   └── audit_handler.py      # IntentFileHandler
├── resources/
│   ├── __init__.py
│   └── intent_resource.py    # intent://session/{id}
└── models/
    └── intent_models.py      # IntentEntry, IntentLogResult
```

**Changes:**

- `server.py` - Register handler if AUDIT_LOG_DIR is set
- `README.md` - Document environment variable

## Docker Configuration

**Volume mount for persistence:**

```json
"args": [
  "run", "-i", "--rm",
  "--network", "sapguimcp_default",
  "-v", "C:/Users/Username/.sapgui-mcp/audit:/app/audit",
  "-e", "AUDIT_LOG_DIR=/app/audit",
  ...
]
```

**Host side:** `~/.sapgui-mcp/audit/`
**Container side:** `/app/audit/`

## Usage Examples

**Model logs intent at start of request:**

```
User: "Check invoice 4711 and update payment terms"
Model calls: log_intent(
    intent="Check invoice 4711 and update payment terms to ZB01",
    context={"tcode": "VA02", "document_id": "4711"}
)
```

**Model logs milestone:**

```
Model calls: log_intent(
    intent="Changes saved successfully, proceeding to next document",
    context={"tcode": "VA02", "document_id": "4711"}
)
```

**User retrieves audit log:**

```
Resource: intent://session/abc-123-def
Returns: [
  {"timestamp": "...", "intent": "Check invoice 4711...", ...},
  {"timestamp": "...", "intent": "Changes saved...", ...}
]
```
