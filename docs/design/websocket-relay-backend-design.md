# WebSocket Relay Backend — Design Specification

**Date:** 2026-03-27
**Status:** Draft — zur Diskussion mit dem Team
**Branch:** `design/citrix-relay-backend`
**Context:** Alternative zu File-RPC (siehe `citrix-relay-backend-design.md`), entstanden aus PR #586 Diskussion

## Motivation

SAP GUI Desktop läuft innerhalb einer Citrix-Session. Der MCP-Server auf dem Client-PC
hat keinen COM-Zugriff (Session-Isolation, bestätigt durch SAP Notes 480149/1027024).
Der Browser im Citrix darf ins Internet — das nutzen wir als Transport.

Statt File-RPC über Citrix Client Drive Mapping setzen wir auf **WebSocket** als
Transportkanal. Die SAP-Automation erfolgt über **sapsucker** (bestehende typed
COM-Wrapper-Library).

### Design-Prinzip: Separation of Concerns

Der MCP-Server kennt kein Citrix. Der Relay Server kennt kein SAP.
Die SAP-Logik sitzt ausschließlich im Agent auf dem Citrix-Host.

## Architektur

```
┌─────────────────────────────────┐
│        Citrix Session           │
│                                 │
│  SAP GUI Desktop                │
│    ▲                            │
│    │ COM (sapsucker)            │
│    │                            │
│  Relay Agent (.exe / pip)       │
│    │                            │
│    │ WSS (ausgehend, Port 443)  │
└────┼────────────────────────────┘
     │
     ▼
┌─────────────────────────────────┐
│  Relay Server (Cloud)           │
│  Stateless WebSocket Broker     │
│  Pairing via Session-Token      │
└────┬────────────────────────────┘
     │
     ▼ WSS
┌─────────────────────────────────┐
│  MCP Server (Client PC)         │
│  sapwebgui.mcp                  │
│  RelayBackend                   │
└─────────────────────────────────┘
```

### Repos

| Repo | Inhalt | Sprache |
|------|--------|---------|
| `sap-relay-server` | Stateless WebSocket-Broker | Python oder Node |
| `sap-relay-agent` | Citrix-seitiger Agent (sapsucker + WS-Client) | Python |
| `sapwebgui.mcp` | Dünnes `RelayBackend` (bestehend) | Python |

## Protokoll

JSON-RPC-artig über WebSocket. Der Relay Server leitet opake JSON-Messages
bidirektional weiter — er versteht den Inhalt nicht.

### Protokoll-Version

Beim Connect sendet der Agent eine Handshake-Nachricht. Der Relay leitet sie
transparent an den Client durch (wie alle Messages). Der Client validiert.

```json
{
  "type": "handshake",
  "protocol_version": "1.0",
  "agent_version": "0.1.0"
}
```

Der Client validiert `protocol_version`. Bei Mismatch: Verbindung trennen mit
Fehlermeldung `"Incompatible protocol version: expected 1.0, got X.Y"`.
Der Client sendet keine eigene Handshake-Nachricht — der Agent benötigt keine
Client-Validierung.

Versionierungsregeln:
- **Minor** (1.0 → 1.1): Neue Methoden, abwärtskompatibel. Client akzeptiert.
- **Major** (1.x → 2.0): Breaking Changes. Client lehnt ab.

### Request (MCP → Agent)

```json
{
  "id": "uuid-1234",
  "method": "enter_transaction",
  "params": {"tcode": "SE16"}
}
```

### Response (Agent → MCP)

```json
{
  "id": "uuid-1234",
  "result": {"success": true, "transaction": "SE16", "screen_title": "Data Browser: Initial Screen"}
}
```

### Error

```json
{
  "id": "uuid-1234",
  "error": {"code": "COM_ERROR", "message": "SAP GUI not responding"}
}
```

### Heartbeat (Agent → MCP, kein Response)

```json
{
  "type": "heartbeat",
  "status": "idle"
}
```

Status-Werte:
- `"idle"` — Agent verbunden mit SAP GUI, kein aktiver Call
- `"busy"` — Agent führt gerade einen COM-Call aus
- `"com_disconnected"` — Agent hat die COM-Verbindung zu SAP GUI verloren (WebSocket zum Relay ist noch aktiv)

Nicht zu verwechseln mit WebSocket-Disconnect: Wenn der Agent die WebSocket-Verbindung
verliert, sendet der Relay `{"type": "peer_disconnected"}` an den Client (separater Mechanismus).

Heartbeat-Intervall: 5 Sekunden.

### Spezialfälle

Binärdaten werden generisch als Envelope serialisiert:

```json
{"_type": "bytes", "data": "<base64-encoded>"}
```

Betrifft `take_screenshot` (PNG-Bytes) und jede andere Methode die `bytes` zurückgibt.
Der Client erkennt das Envelope am `_type`-Feld und decodiert automatisch.

`get_snapshot`: Result enthält den COM-Tree als verschachteltes dict.

### Methoden-Set

1:1-Mapping auf die `SapUiBackend`-Protokoll-Methoden (~50 Methoden).
Der Agent implementiert alle COM-basierten Methoden, der Relay Server kennt keine davon.

Vollständige Liste in `src/sapwebguimcp/backend/protocol.py` (die fünf Sub-Protokolle
SapUiPrimitives, SapUiInspection, SapNavigation, SapEditor, SapPopup).

### Browser-only Methoden

Folgende Methoden aus `SapUiPrimitives` sind browser-spezifisch und haben kein
COM-Äquivalent:

- `load_js(filename)` → `NOT_SUPPORTED`
- `evaluate_javascript(script, arg)` → `NOT_SUPPORTED`
- `fill_element_by_locator(locator, value, delay_ms)` → `NOT_SUPPORTED`
- `click_element(selector)` → `NOT_SUPPORTED`

Der Agent antwortet mit Error-Code `NOT_SUPPORTED`:

```json
{
  "id": "uuid-1234",
  "error": {"code": "NOT_SUPPORTED", "message": "load_js is not available in COM/desktop mode"}
}
```

### Message-Ordering

Requests werden **sequentiell** verarbeitet — der Agent verarbeitet immer nur einen
Request gleichzeitig, da COM Single-Threaded Apartment (STA) erfordert. Der Client
darf pipelinen (mehrere Requests senden ohne auf Response zu warten), aber der Agent
bearbeitet sie FIFO.

### Error Codes

| Code | Bedeutung |
|------|-----------|
| `COM_ERROR` | Transienter COM-Fehler (SAP busy, call rejected) |
| `COM_DISCONNECTED` | SAP GUI COM-Verbindung verloren (fatal) |
| `NOT_SUPPORTED` | Methode nicht verfügbar im COM-Backend |
| `UNKNOWN_METHOD` | Methode existiert nicht im Protokoll |
| `SESSION_NOT_FOUND` | Angefragte Session-ID existiert nicht |
| `TIMEOUT` | COM-Call hat Agent-seitiges Timeout überschritten |
| `CONNECTION_LOST` | WebSocket-Verbindung zum Relay verloren (Client-seitig) |
| `PEER_DISCONNECTED` | Gegenstelle hat die Verbindung getrennt |
| `INTERNAL_ERROR` | Unerwarteter Fehler im Agent |

### Auth

Session-Token im WebSocket-Connect-URL:

```
wss://relay.example.com/session/<token>?role=agent
wss://relay.example.com/session/<token>?role=client
```

Token: `secrets.token_hex(32)` — 256-Bit Entropy, generiert vom Agent beim Start.

## Relay Server

### Verhalten

- Akzeptiert WebSocket-Verbindungen auf `wss://host/session/<token>?role=agent|client`
- Pro Token: maximal 1 Agent + 1 Client
- Wenn beide verbunden: Messages bidirektional weiterleiten
- Heartbeats vom Agent werden an den Client durchgereicht
- Wenn eine Seite disconnected: `{"type": "peer_disconnected"}` an die andere Seite
- Kein State über die Verbindung hinaus

### Sicherheit

- WSS only (TLS)
- Kein Logging von Payloads — nur Connection-Metadata (Timestamps, `sha256(token)[:12]`, IP)
- Rate Limiting pro IP
- Second Connect mit gleicher Rolle wird abgelehnt (verhindert Agent-Impersonation)
- Optional: Token-TTL (z.B. 24h)

### Tech Stack

Leichtgewichtig:
- Python + `websockets` lib, oder
- Node + `ws`, oder
- Cloudflare Workers Durable Objects (kein eigener Server nötig)

Geschätzte Größe: ~100-150 Zeilen Kernlogik.

## Relay Agent (Citrix-Seite)

### Startup-Flow

1. Agent startet, generiert Session-Token
2. Zeigt Token im Terminal an: `Session token: a1b2c3... — configure this in your MCP server`
3. Initialisiert sapsucker: `SapGui.connect()` → `GuiApplication`
4. Verbindet sich zum Relay: `wss://relay.example.com/session/<token>?role=agent`
5. Startet Heartbeat-Loop (alle 5s)
6. Wartet auf Commands

### Command-Handling

```python
async def handle_command(msg: dict) -> dict:
    method = msg["method"]
    params = msg["params"]

    # COM ist STA — alle Calls über einen dedizierten Thread
    result = await run_in_com_thread(method, params)

    return {"id": msg["id"], "result": result}
```

### COM-Thread

Gleiche Architektur wie das bestehende DesktopBackend in sapwebgui.mcp:
- Dedizierter Thread mit `pythoncom.CoInitialize()`
- Work-Queue für serielle COM-Calls
- `asyncio.wrap_future` für async/await Integration
- Adaptive Throttling bei COM-Pressure (optional, Phase 2)

### Methoden-Dispatch

Dispatch-Map statt einzelne Handler:

```python
METHODS: dict[str, Callable] = {
    "login": agent.login,
    "enter_transaction": agent.enter_transaction,
    "fill_field": agent.fill_field,
    "click_button": agent.click_button,
    "take_screenshot": agent.take_screenshot,
    "get_screen_text": agent.get_screen_text,
    # ... alle ~50 SapUiBackend-Methoden
}

handler = METHODS.get(msg["method"])
if handler is None:
    return {"id": msg["id"], "error": {"code": "UNKNOWN_METHOD", "message": f"Unknown: {msg['method']}"}}
```

### Session-Management

- Agent verwaltet eine `GuiApplication` mit mehreren `GuiSession`s
- Session-ID-Mapping wie in `DesktopSessionRegistry`
- `login` erstellt eine neue Connection+Session
- `open_new_session` öffnet eine weitere Session
- `close_session` beendet eine Session via `/nex`

### Login: Credentials-Handling

Das `SapNavigation.login()` Protokoll erwartet `url, username, password, client, language`
als Parameter. Über den WebSocket werden **keine Credentials** gesendet.

Stattdessen sendet der MCP-Client:

```json
{
  "id": "uuid-1234",
  "method": "login",
  "params": {"client": "100", "language": "DE", "connection_name": "S4H"}
}
```

Der Agent ergänzt `username` und `password` aus seiner lokalen `.env`-Datei auf dem
Citrix-Host. `url` entfällt (COM braucht keine URL, sapsucker verbindet sich lokal).

Das bedeutet: `RelayBackend.login()` ist **nicht** ein einfacher 1:1-Proxy.
Die Signatur auf MCP-Seite bleibt kompatibel mit `SapUiBackend`, aber `url`,
`username` und `password` werden ignoriert:

```python
async def login(self, url: str, username: str, password: str,
                client: str, language: str, session_id: str | None = None,
                connection_name: str | None = None) -> LoginResult:
    # url, username, password werden NICHT über den Wire gesendet
    return await self._call("login", client=client, language=language,
                            connection_name=connection_name, session_id=session_id)
```

### `get_session_token`: Sync-Methode über async Transport

`get_session_token()` ist im `SapNavigation`-Protokoll als **synchrone** Methode definiert.
Da der Relay-Transport async ist (WebSocket), braucht der `RelayBackend` eine Sync-Bridge:

```python
class RelayBackend:
    def __init__(self):
        # Privater Event-Loop in eigenem Thread für sync→async Bridge
        self._sync_loop = asyncio.new_event_loop()
        self._sync_thread = threading.Thread(target=self._sync_loop.run_forever, daemon=True)
        self._sync_thread.start()

    def get_session_token(self) -> str:
        """Sync method — bridges to async _call via dedicated thread loop."""
        future = asyncio.run_coroutine_threadsafe(
            self._call("get_session_token"), self._sync_loop
        )
        return future.result(timeout=self._timeout)
```

Dies vermeidet den Deadlock, der bei `asyncio.get_event_loop().run_until_complete()`
innerhalb eines laufenden Event-Loops auftreten würde.

### Fehler-Handling

| Fehler | Verhalten |
|--------|-----------|
| COM-Error (transient) | Retry mit Backoff, Error-Response wenn erschöpft |
| `RPC_E_DISCONNECTED` | Heartbeat → `"com_disconnected"`, Versuch: SAP GUI Reconnect |
| Unbekannte Methode | `{"error": {"code": "UNKNOWN_METHOD"}}` |
| WebSocket-Disconnect | Reconnect zum Relay mit Exponential Backoff |

### Graceful Shutdown

Wenn der Agent sich beendet (Ctrl+C, SIGTERM), sendet er vor dem Disconnect:

```json
{
  "type": "shutdown",
  "reason": "Agent shutting down"
}
```

Der Client kann dadurch einen geplanten Shutdown von einem Crash unterscheiden.
Bei Crash: kein Shutdown-Message, Client bemerkt es über `peer_disconnected` vom Relay
oder Heartbeat-Timeout.

### Delivery

- **pip:** `pip install sap-relay-agent` (braucht Python 3.11+ / pywin32 / sapsucker)
- **Binary:** PyInstaller Single-File .exe (~30MB)
- **CLI:** `sap-relay-agent --relay-url wss://relay.example.com [--token <token>]`

Ohne `--token` wird ein neuer Token generiert und angezeigt.

## MCP-Seite (RelayBackend)

Dünner WebSocket-Client im bestehenden sapwebgui.mcp.

### Implementation

```python
class RelayBackend:
    """Proxy SapUiBackend calls over WebSocket to a remote relay agent."""

    backend_type = "relay"

    def __init__(self, ws, timeout: int = 30):
        self._ws = ws
        self._timeout = timeout
        self._pending: dict[str, asyncio.Future] = {}
        # Sync-Bridge für get_session_token()
        self._sync_loop = asyncio.new_event_loop()
        self._sync_thread = threading.Thread(target=self._sync_loop.run_forever, daemon=True)
        self._sync_thread.start()

    async def _receive_loop(self) -> None:
        """Background task: read messages, resolve pending futures, handle heartbeats."""
        async for raw in self._ws:
            msg = json.loads(raw)
            if msg.get("type") == "heartbeat":
                self._last_heartbeat = time.monotonic()
                self._agent_status = msg["status"]
                continue
            if msg.get("type") == "peer_disconnected":
                # Fail all pending futures
                for fut in self._pending.values():
                    if not fut.done():
                        fut.set_exception(RelayError("PEER_DISCONNECTED", "Agent disconnected"))
                self._pending.clear()
                continue
            msg_id = msg.get("id")
            if msg_id and msg_id in self._pending:
                self._pending[msg_id].set_result(msg)
                # Cleanup happens in _call after await

    async def _call(self, method: str, **params) -> Any:
        msg_id = str(uuid4())
        msg = {"id": msg_id, "method": method, "params": params}
        fut = asyncio.get_running_loop().create_future()
        self._pending[msg_id] = fut
        try:
            await self._ws.send(json.dumps(msg))
            resp = await asyncio.wait_for(fut, timeout=self._timeout)
        except asyncio.TimeoutError:
            raise RelayError("TIMEOUT", f"{method} timed out after {self._timeout}s")
        finally:
            self._pending.pop(msg_id, None)  # Cleanup in allen Fällen
        if "error" in resp:
            raise RelayError(resp["error"]["code"], resp["error"]["message"])
        return resp["result"]

    async def enter_transaction(self, tcode: str) -> TransactionResult:
        return await self._call("enter_transaction", tcode=tcode)

    async def take_screenshot(self) -> bytes:
        envelope = await self._call("take_screenshot")
        return base64.b64decode(envelope["data"])  # Bytes-Envelope

    # ... ~50 weitere One-Liner
```

### Receive-Loop und Pending-Futures Lifecycle

Der `RelayBackend` startet eine `_receive_loop` als Background-Task beim Connect.
Diese Loop:
1. Liest alle WebSocket-Messages
2. Heartbeats → Update `_last_heartbeat` und `_agent_status`
3. `peer_disconnected` → Alle pending Futures mit Fehler auflösen, Dict leeren
4. Responses → Future via `msg["id"]` resolven

Cleanup: `_call()` entfernt den Eintrag aus `_pending` im `finally`-Block —
sowohl bei Erfolg, Timeout, als auch bei Fehler. Orphaned Responses (Agent antwortet
nach Client-Timeout) werden in der Receive-Loop ignoriert (`msg_id not in _pending`).

### WebSocket-Reconnect (MCP-Seite)

Wenn die WebSocket-Verbindung zum Relay abbricht:
1. Alle pending Futures mit `RelayError("CONNECTION_LOST")` auflösen
2. Reconnect mit Exponential Backoff (1s, 2s, 4s, max 30s)
3. Nach Reconnect: Handshake-Validierung abwarten
4. Neue Calls sind erst nach erfolgreichem Reconnect möglich

In-Flight Calls gehen verloren — der Agent hat sie möglicherweise bereits ausgeführt,
aber die Response erreicht den Client nicht. Tools müssen damit umgehen (Retry-Logik
auf Tool-Ebene, nicht auf Transport-Ebene).

### Konfiguration

Neue Felder in `Settings`:

```python
BackendType = Literal["webgui", "desktop", "relay"]

# Neue Felder:
relay_url: str = ""           # wss://relay.example.com
relay_token: str = ""         # Session-Token vom Agent
relay_timeout_s: int = 30     # Timeout pro Call
```

### Heartbeat-Monitoring

Client empfängt Heartbeats vom Agent. Wenn >15s kein Heartbeat:
Session als disconnected markieren, Tools bekommen eine klare Fehlermeldung.

### Rückgabewerte

Ergebnisse kommen als raw dicts zurück, nicht als rekonstruierte Pydantic-Models.
Konsistent mit dem bestehenden Verhalten — Tools erwarten dicts.

### `_is_com_backend`

`RelayBackend` nutzt COM über sapsucker auf dem Agent. Daher muss `_is_desktop_backend`
zu `_is_com_backend` umbenannt werden und `"relay"` einschließen:

```python
def _is_com_backend(backend: SapUiBackend) -> bool:
    return backend.backend_type in ("desktop", "relay")

_is_desktop_backend = _is_com_backend  # Backwards-Compat Alias
```

**Betroffene Dateien** (aus `grep -r _is_desktop_backend src/sapwebguimcp/tools/`):

- `_backend_utils.py` — Definition ändern
- `abapgit_tools.py`, `com_tools.py`, `quick_report_tools.py`, `sap_tools.py`,
  `se09_tools.py`, `se11_tools.py`, `se16_tools.py`, `se24_tools.py`,
  `se24_edit_tools.py`, `se37_tools.py`, `se38_edit_tools.py`, `se93_tools.py`,
  `slg1_tools.py`, `sm30_tools.py`, `sm37_tools.py`, `spro_tools.py`,
  `st22_tools.py` — Import umbenennen (17 Consumer-Dateien)

**Direkte `backend_type == "desktop"` String-Checks** (müssen zu `in ("desktop", "relay")` werden):

- `sap_tools.py:885` und `sap_tools.py:892` — `get_settings().backend_type == "desktop"`

### Prerequisite-Änderungen im MCP-Server

Folgende Dateien außerhalb von `tools/` müssen ebenfalls angepasst werden:

1. **`models/config.py`** — `BackendType` Literal erweitern:
   ```python
   BackendType = Literal["webgui", "desktop", "relay"]
   ```
   Ohne diese Änderung lehnt `BackendManager` den Typ `"relay"` ab
   (`_VALID_BACKEND_TYPES` wird via `get_args(BackendType)` abgeleitet).

2. **`backend/manager.py`** — Neuer Branch in `get_or_create()`:
   ```python
   if self.backend_type == "relay":
       # WebSocket-Verbindung zum Relay Server, RelayBackend instanziieren
   ```
   Plus Platform-Check: `"relay"` braucht kein `sys.platform == "win32"` (COM läuft remote).

3. **`server.py:212-215`** — Instruction/Name-Selection ist aktuell binär:
   ```python
   # Aktuell:
   SERVER_INSTRUCTIONS = _DESKTOP_INSTRUCTIONS if _settings.backend_type == "desktop" else _WEBGUI_INSTRUCTIONS
   _SERVER_NAME = "sap-desktop-mcp" if _settings.backend_type == "desktop" else "sap-webgui-mcp"
   # Muss werden:
   _is_com = _settings.backend_type in ("desktop", "relay")
   SERVER_INSTRUCTIONS = _DESKTOP_INSTRUCTIONS if _is_com else _WEBGUI_INSTRUCTIONS
   _SERVER_NAME = "sap-desktop-mcp" if _is_com else "sap-webgui-mcp"
   ```

4. **`backend/protocol.py:187`** — `backend_type` Docstring erweitern:
   ```python
   """Return backend identifier: ``'desktop'``, ``'webgui'``, or ``'relay'``."""
   ```

### Geschätzte Größe

~300-400 Zeilen (inkl. Receive-Loop, Reconnect, Sync-Bridge). Keine Citrix-Logik, kein COM-Wissen.

## Sicherheit

### Transport

- WSS (TLS) zwischen allen Parteien
- Session-Token: `secrets.token_hex(32)` — 256-Bit Entropy

### Relay Server: Zero-Knowledge

- Leitet opake JSON weiter, speichert nichts
- Kein Payload-Logging
- Token nur als `sha256(token)[:12]` in Logs

### Risiken und Mitigations

| Risiko | Mitigation |
|--------|-----------|
| Token erraten | 256-Bit Entropy, Rate Limiting |
| Relay-Betreiber liest mit | TLS schützt vor Netzwerk-Sniffing. Phase 2: optionale Payload-Verschlüsselung mit Pre-Shared Key |
| SAP-Credentials im Transit | Agent liest Credentials aus lokaler `.env` — `login`-Kommando sendet nur `{connection_name, client, language}` |
| Replay-Attacke | Praktisch irrelevant: Token hat 256-Bit Entropy, WSS verhindert Mitlesen, und die 1:1 Agent/Client-Bindung schließt Dritte aus. UUIDs als Message-IDs verhindern versehentliche Doppelverarbeitung auf Anwendungsebene. |
| Agent-Impersonation | Nur ein Agent pro Token, Second Connect abgelehnt |

## Vergleich mit File-RPC-Ansatz

| | File-RPC (`citrix-relay-backend-design.md`) | WebSocket Relay (dieses Dokument) |
|---|---|---|
| Latenz | ~200ms (File-Polling) | ~50-100ms (WebSocket RTT + COM-Call) |
| MCP-Code | ~1500 Zeilen | ~300-400 Zeilen |
| Separation of Concerns | Citrix-Code im MCP | Saubere Trennung (3 Repos) |
| Host braucht | Python .exe + CDM aktiv | Python .exe + Internet-Zugang (Browser reicht) |
| Netzwerk nötig | Nein (nur CDM) | Ja (HTTPS ausgehend) |
| Wartung bei Protokoll-Änderung | Beide Seiten updaten | Beide Seiten updaten (aber weniger Code) |
| Cloud-Dependency | Keine | Relay Server muss laufen |

## Offene Fragen

1. **Relay Server Hosting:** Eigener Server (Azure VM) oder Serverless (Cloudflare Workers)?
2. **Fallback auf File-RPC:** Brauchen wir File-RPC als Fallback wenn kein Internet? Oder ist das ein separates Projekt?
3. **Multi-Agent:** Kann ein Agent mehrere MCP-Clients bedienen? (Aktuell: 1:1 Pairing pro Token)

### Entschiedene Designfragen

**ComThread:** Der Agent dupliziert den ComThread-Code initial. Die ~100 Zeilen sind
stabil und ändern sich selten. Extraction in eine shared lib ist Phase 2 — nur wenn
sich zeigt, dass die Implementierungen divergieren.
