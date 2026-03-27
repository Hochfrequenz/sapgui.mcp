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
| **Shared Folder** | CDM-gemappt | — | `C:\sapgui-relay-{random}\` auf dem Client, `\\Client\C$\sapgui-relay-{random}\` auf dem Server. |

### Designentscheidungen

| Entscheidung | Gewählt | Alternativen | Begründung |
|---|---|---|---|
| Transportkanal | Client Drive Mapping (CDM) | Clipboard, Virtual Channel, TCP | CDM ist meist standardmäßig aktiv, braucht keinen Citrix-Admin |
| Relay-Deployment | Standalone .exe (PyInstaller) | Python-Installation, MSI | Minimale Abhängigkeiten, User startet selbst |
| Kommunikationsmodell | File-based RPC (JSON) | WebSocket, gRPC | Einzige Option ohne direkten TCP-Zugang |
| Timeout-Handling | Heartbeat statt feste Timeouts | Feste Timeouts pro Methode | SAP-Operationen sind unvorhersehbar lang |
| Security | Shared Secret + NTFS ACLs | Keine Auth, mTLS | Verhindert Crosstalk; siehe Threat-Model |
| Protocol-Scope | Volles `SapUiBackend` (minus browser-only) | Core-Subset | Maximale Feature-Parität mit Desktop-Backend |

## Transportprotokoll (File-based RPC)

### Ordnerstruktur

Der Relay-Dir-Name enthält eine zufällige Komponente um Konflikte auf Shared-Servern
zu vermeiden. Der Relay generiert den Suffix beim Start und teilt ihn über stdout mit.

```
C:\sapgui-relay-a8f3b2\
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

### Atomare File-Writes

Alle Schreibvorgänge verwenden das **write-to-tmp + rename**-Pattern um partielle
Reads zu verhindern:

1. Daten werden in eine temporäre Datei geschrieben (z.B. `000001.json.tmp`)
2. `os.replace()` benennt atomar in den finalen Namen um (NTFS-Rename ist atomar)
3. Reader ignorieren `.tmp`-Dateien

```python
# Beide Seiten verwenden diese Hilfsfunktion:
def atomic_write_json(path: Path, data: dict) -> None:
    tmp_path = path.with_suffix(".json.tmp")
    tmp_path.write_text(json.dumps(data))
    os.replace(tmp_path, path)
```

Dies ist besonders wichtig für große Payloads wie Screenshots (~700KB JSON).

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

### Serialisierungsvertrag

Alle Responses werden als JSON serialisiert. Typzuordnung:

| Python-Typ | JSON-Serialisierung | Deserialisierung (Client) |
|---|---|---|
| Pydantic `BaseModel` | `model.model_dump()` → dict | `ModelClass(**result)` |
| `bytes` | `{"_type": "bytes", "data": "<base64>"}` | `base64.b64decode(result["data"])` |
| `None` | `null` | `None` |
| `str`, `int`, `float`, `bool` | Direkt | Direkt |
| `list`, `dict` | Direkt | Direkt |

Der Relay kodiert im `_execute()`, der CitrixBackend dekodiert in `_call()`.

### Verarbeitungsgarantien

- **FIFO:** Commands werden nach Dateinamen (= aufsteigender Zähler) sortiert abgearbeitet
- **At-most-once:** Jede Command-ID wird maximal einmal verarbeitet
- **Sequenziell:** Ein Command gleichzeitig — passt zum single-threaded COM-Modell

## Handshake & Security

### Threat-Model

Das Shared-Secret-Token **verhindert versehentlichen Crosstalk** zwischen Relay-Instanzen
und schützt gegen zufällige Command-Injection durch andere Prozesse. Es schützt **nicht**
gegen einen motivierten Angreifer mit Dateisystem-Zugang — dieser könnte `handshake.json`
lesen und eigene Commands einschleusen.

**Mitigationen:**
- Der Relay-Dir-Name enthält eine zufällige Komponente (`sapgui-relay-{random}`) —
  der Pfad ist nicht vorhersagbar
- Der Relay setzt **restriktive NTFS-ACLs** auf den Relay-Dir: nur der aktuelle User
  hat Lese-/Schreibzugang
- Das Token wird bei jedem Relay-Neustart rotiert

**Annahme:** Der Citrix-User, der den Relay startet, ist derselbe der den MCP-Server
auf dem Client betreibt. Andere User auf demselben Citrix-Server haben keinen Zugriff
auf den CDM-Pfad (CDM mappt pro User-Session).

### Ablauf

```
1. User startet relay.exe in der Citrix-Session
2. Relay erstellt Relay-Dir mit zufälligem Suffix und restriktiven NTFS ACLs
3. Relay generiert Token:  secrets.token_hex(32)
4. Relay schreibt handshake.json auf \\Client\C$\sapgui-relay-{random}\
5. Relay gibt den vollständigen Pfad auf stdout aus
6. User konfiguriert CITRIX_RELAY_DIR im MCP-Server (oder Client pollt bekannten Prefix)
7. CitrixBackend liest handshake.json, prüft protocol_version
8. Token wird gelesen → in allen Commands mitgeschickt
9. Relay validiert Token bei jedem Command
10. Commands mit falschem Token → ignoriert und gelöscht
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

**Protokoll-Validierung:** CitrixBackend prüft `protocol_version` beim Handshake.
Bei Mismatch wird ein `RelayProtocolError` mit Versionshinweis geworfen.

## CitrixBackend (Client-Seite)

Implementiert `SapUiBackend`-Protocol. Jede Methode ist ein 1:1-Proxy zum Relay:

```python
class CitrixBackend:
    """Proxy: Methode → Command-JSON → warten → Response → Result."""

    # backend_type wird von Tools abgefragt (z.B. für backend-spezifische Logik).
    # Gibt "citrix" zurück — NICHT "desktop", auch wenn der Relay intern
    # DesktopBackend nutzt. Tools die auf backend_type=="desktop" prüfen
    # müssen ggf. um "citrix" erweitert werden.
    backend_type = "citrix"

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
        return base64.b64decode(result["data"])

    # Browser-only Methoden (nicht unterstützt, wie beim DesktopBackend).
    # Signaturen matchen exakt das SapUiBackend-Protocol:
    def load_js(self, filename: str) -> None:  # sync im Protocol
        raise NotImplementedError("load_js is not available via Citrix relay")

    async def evaluate_javascript(self, script: str, arg: Any = None) -> Any:
        raise NotImplementedError("evaluate_javascript is not available via Citrix relay")

    async def fill_element_by_locator(self, locator: str, **kwargs) -> Any:
        raise NotImplementedError("fill_element_by_locator is not available via Citrix relay")

    async def click_element(self, selector: str) -> bool:  # bool im Protocol
        raise NotImplementedError("click_element is not available via Citrix relay")

    # Session-Management wird 1:1 an den Relay weitergeleitet.
    # Der Relay delegiert an DesktopBackend/DesktopSessionRegistry.
    async def list_sessions(self) -> list:
        return await self._call("list_sessions")

    async def bind_session(self, session_id: str, agent_id: str) -> None:
        await self._call("bind_session", session_id=session_id, agent_id=agent_id)

    async def release_session(self, agent_id: str) -> None:
        await self._call("release_session", agent_id=agent_id)

    async def close_session(self, session_id: str) -> None:
        await self._call("close_session", session_id=session_id)

    async def has_session(self, session_id: str) -> bool:
        return await self._call("has_session", session_id=session_id)

    # Alle weiteren SapUiBackend-Methoden (~40 total) folgen dem gleichen
    # Proxy-Pattern via _call(). Vollständige Liste der Proxy-Methoden:
    #
    # --- SapUiPrimitives (async, proxied) ---
    # fill_field, fill_main_input, fill_form, fill_grid_cell, click_button,
    # click_tab, press_key, type_text, set_checkbox, set_radio_button,
    # select_dropdown, focus_and_type
    #
    # --- SapUiInspection (async, proxied) ---
    # get_status_bar, get_screen_info, get_screen_text, discover_fields,
    # get_form_fields, discover_buttons, read_table, take_screenshot,
    # get_snapshot, click_table_cell, get_dropdown_options, get_page_title
    #
    # --- SapNavigation (async, proxied) ---
    # login, enter_transaction, get_session_status, wait_for_ready,
    # wait_for_sap_ready, wait, start_keepalive, stop_keepalive,
    # open_new_session, is_page_closed, close_page, bring_to_front,
    # list_connections, discover_clients
    # list_sessions, bind_session, release_session, close_session, has_session
    #
    # --- SapEditor (async, proxied) ---
    # read_editor_source, replace_editor_source, check_and_activate
    #
    # --- SapPopup (async, proxied) ---
    # check_popup, dismiss_popup, dismiss_language_dialog
    #
    # --- Sync-Methoden (KEIN Proxy via _call, lokal implementiert) ---
    # backend_type: Property, gibt "citrix" zurück (lokal)
    # get_session_token: def (sync), wird via synchronen RPC-Call proxied:
    #   def get_session_token(self) -> str:
    #       return asyncio.get_event_loop().run_until_complete(
    #           self._call("get_session_token"))
    #

    async def _call(self, method: str, **args) -> Any:
        self._counter += 1
        cmd_id = f"{self._counter:06d}"

        # Command atomar schreiben
        cmd = {
            "id": cmd_id,
            "token": self._token,
            "method": method,
            "args": args,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        cmd_path = self._relay_dir / "commands" / f"{cmd_id}.json"
        atomic_write_json(cmd_path, cmd)

        # Auf Response warten (mit Heartbeat-Check)
        while True:
            resp_path = self._relay_dir / "responses" / f"{cmd_id}.json"
            if resp_path.exists():
                resp = json.loads(resp_path.read_text())
                resp_path.unlink()
                if not resp["success"]:
                    raise RelayError(resp["error"])
                return self._deserialize(resp.get("result"))

            self._check_heartbeat()
            await asyncio.sleep(0.1)  # 100ms Poll-Intervall

    def _deserialize(self, result: Any) -> Any:
        """Deserialisiert Sondertypen aus dem JSON-Response."""
        if isinstance(result, dict) and result.get("_type") == "bytes":
            return base64.b64decode(result["data"])
        return result

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

### Nicht unterstützte Methoden (Browser-only)

Folgende `SapUiBackend`-Methoden sind browser-spezifisch und werden vom CitrixBackend
(wie auch vom DesktopBackend) mit `NotImplementedError` beantwortet:

- `load_js(filename)` — JavaScript in Browser laden
- `evaluate_javascript(script, arg)` — JavaScript ausführen
- `fill_element_by_locator(locator, ...)` — CSS/XPath-basierte Feldfüllung
- `click_element(selector)` — CSS/XPath-basierter Klick

Diese Methoden werden ausschließlich vom WebGUI-Backend implementiert.

### Session-Management

Alle Session-Methoden (`list_sessions`, `bind_session`, `release_session`,
`close_session`, `has_session`) werden als reguläre RPC-Commands an den Relay
weitergeleitet. Der Relay delegiert an den `DesktopBackend`, der intern seine
`DesktopSessionRegistry` verwaltet.

Der Session-State lebt vollständig auf dem Citrix-Server. Der CitrixBackend
hält keinen eigenen Session-Cache — er ist ein reiner Proxy.

## Relay-Agent (Server-Seite)

### Concurrency-Modell

Der Relay-Agent verwendet einen **persistenten asyncio Event-Loop** in einem
dedizierten Thread. Der Hauptthread pollt das Dateisystem synchron, delegiert
die Ausführung aber an den Event-Loop, da alle `DesktopBackend`-Methoden
`async def` sind.

```python
class RelayAgent:
    """Watch-Loop: Commands lesen → DesktopBackend ausführen → Response schreiben."""

    def __init__(self, relay_dir_base: Path):
        # Zufälliger Suffix für den Relay-Dir
        suffix = secrets.token_hex(4)
        self._relay_dir = relay_dir_base / f"sapgui-relay-{suffix}"
        self._relay_dir.mkdir(parents=True)
        self._set_ntfs_acls(self._relay_dir)
        (self._relay_dir / "commands").mkdir()
        (self._relay_dir / "responses").mkdir()

        # Async Event-Loop in eigenem Thread für DesktopBackend
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(
            target=self._loop.run_forever, daemon=True
        )
        self._loop_thread.start()

        # DesktopBackend im Event-Loop initialisieren
        self._backend = asyncio.run_coroutine_threadsafe(
            self._create_backend(), self._loop
        ).result()

        self._token = secrets.token_hex(32)

    async def _create_backend(self) -> DesktopBackend:
        backend = DesktopBackend(...)
        # ComThread wird hier gestartet
        return backend

    def _set_ntfs_acls(self, path: Path) -> None:
        """Setzt restriktive NTFS-ACLs: nur aktueller User hat Zugriff."""
        # Verwendet icacls oder win32security API
        # icacls <path> /inheritance:r /grant:r %USERNAME%:(OI)(CI)F
        ...

    def run(self):
        self._write_handshake()
        self._start_heartbeat_thread()
        print(f"Relay directory: {self._relay_dir}")
        print(f"Relay ready. Waiting for commands...")

        while True:
            for cmd_file in sorted(
                self._relay_dir.glob("commands/*.json"),
                key=lambda f: f.name,
            ):
                # .tmp-Dateien ignorieren (noch nicht fertig geschrieben)
                if cmd_file.suffix == ".tmp":
                    continue

                cmd = json.loads(cmd_file.read_text())

                # Token-Validierung
                if cmd.get("token") != self._token:
                    cmd_file.unlink()
                    continue

                # Heartbeat auf "busy" setzen
                self._update_heartbeat("busy", cmd["id"])

                # Async-Methode im Event-Loop ausführen
                start = time.monotonic()
                result = self._execute(cmd)
                elapsed_ms = int((time.monotonic() - start) * 1000)
                result["duration_ms"] = elapsed_ms

                # Response atomar schreiben, Command löschen
                resp_path = self._relay_dir / "responses" / f"{cmd['id']}.json"
                atomic_write_json(resp_path, result)
                cmd_file.unlink()

                self._update_heartbeat("idle", None)

            time.sleep(0.05)  # 50ms Poll-Intervall

    def _execute(self, cmd: dict) -> dict:
        method = getattr(self._backend, cmd["method"])
        try:
            # Async-Methode im persistenten Event-Loop ausführen
            future = asyncio.run_coroutine_threadsafe(
                method(**cmd["args"]), self._loop
            )
            result = future.result(timeout=300)  # 5min Safety-Timeout

            # Serialisierung
            result = self._serialize(result)
            return {
                "id": cmd["id"],
                "token": self._token,
                "success": True,
                "result": result,
            }
        except Exception as e:
            return {
                "id": cmd["id"],
                "token": self._token,
                "success": False,
                "error": f"{type(e).__name__}: {e}",
            }

    def _serialize(self, result: Any) -> Any:
        """Serialisiert Python-Objekte für JSON-Transport."""
        if result is None:
            return None
        if isinstance(result, bytes):
            return {"_type": "bytes", "data": base64.b64encode(result).decode()}
        if hasattr(result, "model_dump"):
            return result.model_dump()
        return result
```

### Logging

Der Relay-Agent loggt auf zwei Kanälen:

- **stdout/stderr:** Start-Informationen, Relay-Dir-Pfad, Fehler. Sichtbar im
  Citrix-Terminalfenster.
- **Log-Datei:** `relay.log` im Relay-Dir. Enthält alle Commands (ohne Token),
  Responses (ohne Ergebnis-Details), Errors und Heartbeat-Events.
  Konfigurierbar via `--log-level` (Default: INFO).

### Packaging

```
PyInstaller --onefile relay_agent.py → relay.exe
```

- Beinhaltet: Python-Runtime, DesktopBackend, sapsucker, COM-Dependencies
- Keine Installation nötig auf dem Citrix-Server
- Start: `relay.exe --relay-dir-base \\Client\C$\`
- Relay erstellt Unterordner mit zufälligem Namen und gibt den Pfad auf stdout aus

## Integration in den MCP-Server

### BackendManager

```python
# In manager.py — get_or_create() erweitern:
if settings.backend_type == "citrix":
    relay_dir = Path(settings.citrix_relay_dir)
    token = await self._wait_for_handshake(relay_dir)
    return CitrixBackend(relay_dir, token)
```

### Erforderliche Codeänderungen

| Datei | Änderung |
|---|---|
| `config.py` | `BackendType = Literal["webgui", "desktop", "citrix"]` — "citrix" hinzufügen |
| `config.py` | Neue Settings: `citrix_relay_dir`, `citrix_poll_interval_ms`, `citrix_heartbeat_timeout_s` |
| `manager.py` | `get_or_create()` um Citrix-Branch erweitern |
| `tools/_backend_utils.py` | `_is_desktop_backend()` durch `_is_com_backend()` ersetzen: gibt `True` für `"desktop"` und `"citrix"` zurück, da beide COM-basiert sind. Alle Aufrufer (`com_tools.py`, `sap_tools.py`) verwenden den neuen Helper. |
| `tools/*` | Alle weiteren `backend_type`-Checks auditieren und ggf. um `"citrix"` erweitern |
| `backend/protocol.py` | `SapNavigation.backend_type` Docstring um `"citrix"` erweitern |
| `manager.py` | `close()` um Citrix-Branch erweitern (Relay-Dir Cleanup, Shutdown-Signal) |
| Neues Package | `backend/citrix/` mit `CitrixBackend`, `RelayAgent`, `atomic_write`, `exceptions` |

### Konfiguration (.env)

```env
BACKEND_TYPE=citrix
CITRIX_RELAY_DIR=C:\sapgui-relay-a8f3b2
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
| **Verwaiste Responses (Client-Neustart)** | Token-basierte Invalidierung | Alte Responses mit falschem Token werden ignoriert |
| **Gleichzeitige Commands** | — | FIFO nach Dateinamen, sequenzielle Abarbeitung |
| **Partial File Read** | — | Verhindert durch atomare Writes (tmp + rename) |

## Cleanup-Strategie

```
Beim Start (Relay):
  → Neuen Relay-Dir mit zufälligem Suffix erstellen
  → NTFS ACLs setzen
  → handshake.json schreiben

Beim Start (Client):
  → responses/ leeren (alte Responses vom vorherigen Run)
  → Token aus handshake.json lesen

Laufzeit:
  → Command-Datei: gelöscht nach Verarbeitung (Relay)
  → Response-Datei: gelöscht nach Lesen (Client)
  → Heartbeat: atomar überschrieben (immer nur 1 Datei)

Beenden (Relay):
  → heartbeat.json: {"status": "shutdown"}
  → Laufenden Command noch abarbeiten (graceful)

Token-basierte Invalidierung ersetzt das pauschale Leeren von Verzeichnissen.
Commands/Responses mit falschem Token werden ignoriert und gelöscht.
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

7. **Browser-only Methoden:** `load_js`, `evaluate_javascript`, `fill_element_by_locator`,
   `click_element` sind nicht verfügbar (wie beim Desktop-Backend).

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
