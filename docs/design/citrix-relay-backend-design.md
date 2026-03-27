# Citrix Relay Backend — Design Specification

**Date:** 2026-03-27
**Status:** Draft — zur Diskussion mit dem Team
**Branch:** `design/citrix-relay-backend`

## Motivation

SAP GUI ist in vielen Unternehmen nur über Citrix-Sessions erreichbar. Der MCP-Server
läuft auf dem Client-PC, hat aber keinen direkten Zugriff auf die SAP-GUI-Instanz innerhalb
der Citrix-Session — weder per COM (Desktop-Backend) noch per Browser (WebGUI-Backend).

Ein Vision/OCR-basierter Ansatz wurde evaluiert und verworfen: 50-100x langsamer,
token-intensiv, fragil und nicht-deterministisch.

Stattdessen: Ein **Relay-Agent** auf dem Citrix-Server, der den bestehenden
`DesktopBackend` einbettet und über einen File-basierten Kanal mit dem Client kommuniziert.

## Architektur

```
┌──────────────────┐     Citrix Client Drive Mapping      ┌──────────────────┐
│   MCP Server     │          (\\Client\C$\...)            │  Citrix Session  │
│   (Client PC)    │                                       │                  │
│                  │  C:\sapgui-relay\commands\001.json ──► │  Relay Agent     │
│  CitrixBackend   │                                       │  (.exe)          │
│  (Proxy)         │ ◄── C:\sapgui-relay\responses\001.json│                  │
│                  │                                       │  DesktopBackend  │
│                  │  ◄── heartbeat.json (alle 2s)         │  (COM Scripting) │
└──────────────────┘                                       └──────────────────┘
```

### Komponenten

| Komponente | Ort | Sprache | Beschreibung |
|---|---|---|---|
| **CitrixBackend** | Client-PC | Python | Implementiert `SapUiBackend`-Protocol als Proxy. Teil des MCP-Servers. |
| **Relay-Agent** | Citrix-Server | Python → PyInstaller .exe | Standalone-Executable. Bettet `DesktopBackend` ein. Keine Python-Installation nötig. |
| **Shared Folder** | CDM-gemappt | — | `C:\sapgui-relay\` auf dem Client, `\\Client\C$\sapgui-relay\` auf dem Server. |

### Designentscheidungen

| Entscheidung | Gewählt | Alternativen | Begründung |
|---|---|---|---|
| Transportkanal | Client Drive Mapping (CDM) | Clipboard, Virtual Channel, TCP | CDM ist meist standardmäßig aktiv, braucht keinen Citrix-Admin |
| Relay-Deployment | Standalone .exe (PyInstaller) | Python-Installation, MSI | Minimale Abhängigkeiten, User startet selbst |
| Kommunikationsmodell | File-based RPC (JSON) | WebSocket, gRPC | Einzige Option ohne direkten TCP-Zugang |
| Timeout-Handling | Heartbeat statt feste Timeouts | Feste Timeouts pro Methode | SAP-Operationen sind unvorhersehbar lang |
| Security | Shared Secret (Token) | Keine Auth, mTLS | Verhindert Command-Injection durch andere Prozesse |
| Protocol-Scope | Volles `SapUiBackend` | Core-Subset | Maximale Feature-Parität mit Desktop-Backend |

## Transportprotokoll (File-based RPC)

### Ordnerstruktur

```
C:\sapgui-relay\
├── handshake.json          # Shared-Secret-Austausch beim Start
├── commands\               # Client → Server
│   ├── 000001.json
│   ├── 000002.json
│   └── ...
├── responses\              # Server → Client
│   ├── 000001.json
│   ├── 000002.json
│   └── ...
└── heartbeat.json          # Relay schreibt alle 2s Timestamp
```

### Message-Formate

**Command (Client → Server):**

```json
{
  "id": "000001",
  "token": "a3f8b2...",
  "method": "fill_field",
  "args": {
    "label": "Tabelle",
    "value": "MARA"
  },
  "timestamp": "2026-03-27T14:30:00.000Z"
}
```

**Response (Server → Client):**

```json
{
  "id": "000001",
  "token": "a3f8b2...",
  "success": true,
  "result": { "...": "Pydantic-Model als dict" },
  "duration_ms": 142
}
```

**Heartbeat (Server → Client, alle 2s):**

```json
{
  "status": "idle",
  "current_command": null,
  "timestamp": "2026-03-27T14:30:01.000Z"
}
```

```json
{
  "status": "busy",
  "current_command": "000001",
  "timestamp": "2026-03-27T14:30:01.500Z"
}
```

### Verarbeitungsgarantien

- **FIFO:** Commands werden nach Dateinamen (= aufsteigender Zähler) sortiert abgearbeitet
- **At-most-once:** Jede Command-ID wird maximal einmal verarbeitet
- **Sequenziell:** Ein Command gleichzeitig — passt zum single-threaded COM-Modell

## Handshake & Security

### Ablauf

```
1. User startet relay.exe in der Citrix-Session
2. Relay generiert Token:  secrets.token_hex(32)
3. Relay schreibt handshake.json auf \\Client\C$\sapgui-relay\
4. CitrixBackend (Client) pollt auf C:\sapgui-relay\handshake.json
5. Token wird gelesen → in allen Commands mitgeschickt
6. Relay validiert Token bei jedem Command
7. Commands mit falschem Token → ignoriert und gelöscht
```

### handshake.json

```json
{
  "token": "a3f8b2c9d4e5f6...",
  "relay_version": "1.0.0",
  "protocol_version": 1,
  "backend_ready": true,
  "pid": 12345,
  "started_at": "2026-03-27T14:29:55.000Z"
}
```

**Token-Rotation:** Bei jedem Relay-Neustart wird ein neues Token generiert.
Verwaiste Commands mit altem Token werden beim Scan gelöscht.

## CitrixBackend (Client-Seite)

Implementiert `SapUiBackend`-Protocol. Jede Methode ist ein 1:1-Proxy:

```python
class CitrixBackend:
    """Proxy: Methode → Command-JSON → warten → Response → Result."""

    def __init__(self, relay_dir: Path, token: str):
        self._relay_dir = relay_dir
        self._token = token
        self._counter = 0

    async def fill_field(self, label: str, value: str) -> None:
        await self._call("fill_field", label=label, value=value)

    async def read_table(self, **kwargs) -> TableData:
        return await self._call("read_table", **kwargs)

    async def take_screenshot(self) -> bytes:
        result = await self._call("take_screenshot")
        return base64.b64decode(result["png_base64"])

    # ... alle weiteren SapUiBackend-Methoden analog

    async def _call(self, method: str, **args) -> Any:
        self._counter += 1
        cmd_id = f"{self._counter:06d}"

        # Command schreiben
        cmd = {
            "id": cmd_id,
            "token": self._token,
            "method": method,
            "args": args,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        cmd_path = self._relay_dir / "commands" / f"{cmd_id}.json"
        cmd_path.write_text(json.dumps(cmd))

        # Auf Response warten (mit Heartbeat-Check)
        while True:
            resp_path = self._relay_dir / "responses" / f"{cmd_id}.json"
            if resp_path.exists():
                resp = json.loads(resp_path.read_text())
                resp_path.unlink()
                if not resp["success"]:
                    raise RelayError(resp["error"])
                return resp.get("result")

            self._check_heartbeat()
            await asyncio.sleep(0.1)  # 100ms Poll-Intervall

    def _check_heartbeat(self):
        hb_path = self._relay_dir / "heartbeat.json"
        if not hb_path.exists():
            return  # Noch kein Heartbeat — Relay startet gerade
        hb = json.loads(hb_path.read_text())
        age = (datetime.utcnow() - datetime.fromisoformat(hb["timestamp"])).total_seconds()
        if age > 10:
            raise RelayDisconnectedError(f"Heartbeat ist {age:.0f}s alt")
        if hb.get("status") == "shutdown":
            raise RelayDisconnectedError("Relay wurde beendet")
```

## Relay-Agent (Server-Seite)

```python
class RelayAgent:
    """Watch-Loop: Commands lesen → DesktopBackend ausführen → Response schreiben."""

    def __init__(self, relay_dir: Path):
        self._backend = DesktopBackend(...)
        self._relay_dir = relay_dir   # \\Client\C$\sapgui-relay\
        self._token = secrets.token_hex(32)

    def run(self):
        self._write_handshake()
        self._start_heartbeat_thread()

        while True:
            for cmd_file in sorted(self._relay_dir.glob("commands/*.json")):
                cmd = json.loads(cmd_file.read_text())

                # Token-Validierung
                if cmd.get("token") != self._token:
                    cmd_file.unlink()
                    continue

                # Heartbeat auf "busy" setzen
                self._update_heartbeat("busy", cmd["id"])

                # Ausführen
                result = self._execute(cmd)

                # Response schreiben, Command löschen
                resp_path = self._relay_dir / "responses" / f"{cmd['id']}.json"
                resp_path.write_text(json.dumps(result))
                cmd_file.unlink()

                self._update_heartbeat("idle", None)

            time.sleep(0.05)  # 50ms Poll-Intervall

    def _execute(self, cmd: dict) -> dict:
        method = getattr(self._backend, cmd["method"])
        try:
            result = method(**cmd["args"])
            # Pydantic-Models → dict für JSON-Serialisierung
            if hasattr(result, "model_dump"):
                result = result.model_dump()
            return {
                "id": cmd["id"],
                "token": self._token,
                "success": True,
                "result": result,
                "duration_ms": ...,
            }
        except Exception as e:
            return {
                "id": cmd["id"],
                "token": self._token,
                "success": False,
                "error": f"{type(e).__name__}: {e}",
            }
```

### Packaging

```
PyInstaller --onefile relay_agent.py → relay.exe
```

- Beinhaltet: Python-Runtime, DesktopBackend, sapsucker, COM-Dependencies
- Keine Installation nötig auf dem Citrix-Server
- Start: `relay.exe --relay-dir \\Client\C$\sapgui-relay`

## Integration in den MCP-Server

### BackendManager

```python
# In manager.py — get_or_create() erweitern:
if settings.backend_type == "citrix":
    relay_dir = Path(settings.citrix_relay_dir)
    token = await self._wait_for_handshake(relay_dir)
    return CitrixBackend(relay_dir, token)
```

### Konfiguration (.env)

```env
BACKEND_TYPE=citrix
CITRIX_RELAY_DIR=C:\sapgui-relay
CITRIX_POLL_INTERVAL_MS=100
CITRIX_HEARTBEAT_TIMEOUT_S=10
```

### Settings-Model

```python
# In config.py — SapWebGuiSettings erweitern:
backend_type: Literal["desktop", "webgui", "citrix"] = "webgui"
citrix_relay_dir: str = r"C:\sapgui-relay"
citrix_poll_interval_ms: int = 100
citrix_heartbeat_timeout_s: int = 10
```

## Fehlerszenarien & Recovery

| Szenario | Erkennung | Verhalten |
|---|---|---|
| **Relay-Prozess stirbt** | Heartbeat bleibt aus >10s | `RelayDisconnectedError` → sauberer Fehler an Tools |
| **Citrix-Session trennt sich** | COM-Fehler im Relay | Heartbeat: `{"status": "disconnected"}`, Relay wartet auf Reconnect |
| **CDM-Verbindung bricht ab** | Relay kann `\\Client\C$` nicht lesen | Relay pausiert + lokales Log. Client erkennt es über fehlenden Heartbeat |
| **SAP-Popup blockiert** | `_execute` bekommt PopupInfo | Normal als Teil des Results zurückgegeben |
| **Verwaiste Commands (Relay-Neustart)** | Token stimmt nicht | Dateien werden gelöscht |
| **Verwaiste Responses (Client-Neustart)** | Cleanup beim Start | commands/ und responses/ werden geleert |
| **Gleichzeitige Commands** | — | FIFO nach Dateinamen, sequenzielle Abarbeitung |

## Cleanup-Strategie

```
Beim Start (beide Seiten):
  → commands/ und responses/ leeren
  → handshake.json löschen (Client) bzw. neu schreiben (Relay)

Laufzeit:
  → Command-Datei: gelöscht nach Verarbeitung (Relay)
  → Response-Datei: gelöscht nach Lesen (Client)
  → Heartbeat: überschrieben (immer nur 1 Datei)

Beenden (Relay):
  → heartbeat.json: {"status": "shutdown"}
  → Laufenden Command noch abarbeiten (graceful)
```

## Limitierungen (Phase 1)

1. **Latenz:** ~150-300ms Overhead pro Call (2x File-I/O + 2x Poll-Intervall) zusätzlich zur
   SAP-Operation selbst. Deutlich schneller als Vision-Ansatz, aber spürbar langsamer als
   direkte Backends.

2. **Screenshots:** `take_screenshot()` liefert PNG als Base64 im JSON. Große Screenshots
   (~500KB) erzeugen ~700KB JSON-Dateien. Funktioniert, ist aber nicht optimal.

3. **Single-User:** Ein Relay bedient einen Client. Multi-User bräuchte separate Relay-Dirs
   pro User.

4. **CDM-Abhängigkeit:** Wenn Client Drive Mapping deaktiviert ist, funktioniert Phase 1 nicht.

5. **Kein Streaming:** Ergebnisse werden erst nach Abschluss der Operation übertragen.
   Fortschritt nur über Heartbeat sichtbar.

6. **Sequenzielle Verarbeitung:** Ein Command gleichzeitig. Passt zum COM-Threading-Modell,
   das ohnehin single-threaded ist.

## Zukünftige Erweiterungen (nicht in Phase 1)

### Alternative Transportkanäle

| Kanal | Voraussetzung | Vorteil |
|---|---|---|
| **Direkter TCP/WebSocket** | Firewall-Freischaltung | ~10ms statt ~200ms Latenz |
| **Citrix Virtual Channel SDK** | Citrix-Admin-Zugang | Nativer Kanal, sehr performant |
| **Clipboard-basiert** | Keine | Fallback wenn CDM deaktiviert — interferiert aber mit User-Clipboard |

Bei TCP/WebSocket in Phase 2 würde `CitrixBackend._call()` intern umschalten —
die äußere `SapUiBackend`-API bleibt identisch.

### Weitere Ideen

- **Multi-User:** Relay-Dir pro Session-ID
- **Auto-Discovery:** Relay registriert sich per Broadcast/mDNS
- **Bidirektionale Events:** Relay pusht SAP-Events (z.B. Session-Timeout) zum Client
