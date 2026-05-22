# GitHub Issue Creation from Feedback

## Overview

Automatically create GitHub issues from model feedback logged via `log_feedback` tool. Issues are bundled and rate-limited to avoid spam.

## Configuration

Two new env vars in `SapGuiSettings`:

| Variable      | Description                                       | Default                      |
| ------------- | ------------------------------------------------- | ---------------------------- |
| `GITHUB_PAT`  | GitHub PAT for creating issues (empty = disabled) | (empty)                      |
| `GITHUB_REPO` | Repository for issues (owner/repo)                | `Hochfrequenz/sapgui.mcp` |

## Architecture

```
log_feedback tool
    │
    ▼ logs "FEEDBACK | ..."
logging.Logger
    │
    ├──▶ IntentFileHandler (existing, writes JSONL)
    │
    └──▶ FeedbackIssueHandler (new)
              │
              ├── Buffers entries per session
              ├── Groups by tags
              ├── Rate limits (1 issue/min/session)
              │
              ▼
         GitHub REST API
              │
              ▼
         Issue created with label "model-feedback"
```

## Model Changes

Extend `FeedbackLogResult` with issue status fields:

```python
issue_created: bool = Field(default=False)
issue_url: str | None = Field(default=None)
issue_error: str | None = Field(default=None)
```

Note: These fields reflect the _previous_ flush, not immediate creation (due to buffering).

## FeedbackIssueHandler

New handler in `loghandlers/feedback_issue_handler.py`:

- Listens for `FEEDBACK |` log messages
- Buffers entries per session
- Groups entries by tags (frozenset)
- Rate limit: 1 issue per 60 seconds per session
- Creates bundled issues via httpx to GitHub API
- Hardcoded label: `model-feedback`

### Bundled Issue Format

**Title**: `Feedback (3 entries): selector, timing`

**Body**:

```markdown
**Session**: abc123

## Entry 1 - 2024-01-03T10:15:00Z

Couldn't find save button until I tried selector 'span:has-text(Sichern)'

## Entry 2 - 2024-01-03T10:16:30Z

browser_wait timeout after 30s on SE16 table load

## Entry 3 - 2024-01-03T10:17:00Z

...
```

## Error Handling

- API failures logged but don't break feedback logging
- Buffered entries retained on failure, retried on next flush
- Network errors caught and logged

## Testing

Unit tests with `respx` (httpx mocking):

- Successful issue creation (mock 201)
- API failure (mock 401/403/500)
- Network error (mock timeout)
- PAT not configured (no API call)
- Bundling logic (multiple entries → single issue)
- Rate limiting (entries buffered until window passes)

## Files to Create/Modify

1. `src/sapguimcp/models/config.py` - Add `github_pat`, `github_repo`
2. `src/sapguimcp/models/intent_models.py` - Extend `FeedbackLogResult`
3. `src/sapguimcp/loghandlers/feedback_issue_handler.py` - New handler
4. `src/sapguimcp/loghandlers/__init__.py` - Export new handler
5. `src/sapguimcp/server.py` - Register handler if PAT configured
6. `README.md` - Document new env vars
7. `unittests/test_feedback_issue_handler.py` - Unit tests
