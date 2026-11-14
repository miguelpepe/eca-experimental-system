# Docker-Einrichtung

Docker betreibt das Python-Backend, Ollama und Open WebUI. Unreal läuft direkt
unter Windows. Die Auswahl im Installer legt fest, welche Teile auf diesem
Rechner eingerichtet werden.

## Voraussetzungen

- Für das Backend: Docker Desktop, Linux-Container, WSL 2 und ein aktueller
  NVIDIA-Treiber. Die GPU muss in Docker verfügbar sein. Unter Windows ist
  WSL 2 für diesen CUDA-Containerbetrieb erforderlich.
- Internet für den ersten Image-Build und die Modelldownloads; ausreichend
  freier Speicher für Images, Modelle und Caches. Die Downloads umfassen viele GB.
- Die Modelle für LLM, Whisper und OmniVoice teilen sich den GPU-Speicher;
  bei „beides“ kommen Unreal und Audio2Face dazu. Bei Speichermangel ein
  kleineres LLM wählen oder Backend und Frontend auf zwei Rechner verteilen.
- Für das Frontend: UE 5.6, Visual Studio C++-Build-Tools und die separat
  installierten NVIDIA-Plugins aus der [Unreal-Anleitung](unreal.md).
- Git zum Klonen oder die Quellcode-ZIP von GitHub. Git LFS wird nicht benötigt.

Die Unreal-Inhalte sind separate ZIP-Pakete im
[Asset-Release](https://github.com/miguelpepe/eca-experimental-system/releases/tag/unreal-assets-v1).
Sie werden nur bei Frontend/Beides automatisch geladen und geprüft. Bei einem
reinen Backend-Rechner entfällt dieser Download. Version, URLs und SHA-256-Werte
stehen in `unreal/assets.json`; die Pakete bleiben unter `.eca/downloads/` im Cache.

Docker Desktop und Engine/Plugin-Installationen müssen einmal vorhanden sein;
der Installer prüft sie und erklärt fehlende Voraussetzungen. Er installiert
keine Systemtreiber und löst keinen Windows-Neustart aus.

Quellen: [Docker GPU unter Windows](https://docs.docker.com/desktop/features/gpu/),
[GPU mit Compose](https://docs.docker.com/compose/how-tos/gpu-support/).

## Einrichten und starten

`Setup.bat` im Hauptordner ausführen:

| Auswahl | Ergebnis |
| --- | --- |
| Backend | Docker-Images bauen, GPU prüfen, Ollama/Open WebUI einrichten, RAG importieren und Sprachmodelle laden |
| Frontend | Backend-Adresse abfragen, Unreal prüfen und kompilieren; kein Docker erforderlich |
| Beides | Backend einrichten und die lokale Adresse für Unreal übernehmen |

Beim ersten Lauf werden eigene Zugangsdaten erzeugt. Das Setup legt für seine
Open-WebUI-Instanz einen Admin, einen API-Key, das Modell `avatar` und eine
Knowledge-Sammlung an. Es verwendet eigene Docker-Volumes und übernimmt keine
bisherige Open-WebUI-Datenbank. Ollama ist intern erreichbar; vorhandenes
Windows-Ollama auf Port 11434 kann bestehen bleiben.

Beim ersten Backend-Start werden Whisper und OmniVoice heruntergeladen und mit
einem kurzen Audio geprüft. Erst danach startet die Backend-API. Der erste Lauf
kann entsprechend lange dauern. Die heruntergeladenen Modelle bleiben im Cache.

Danach:

1. Persona, Stimme und RAG wie unten anpassen.
2. `Start.bat` starten. Es verwendet die zuletzt gewählte Installation, importiert
   geänderte RAG-Dateien und wartet auf das Backend. Mit Frontend öffnet es Unreal.
3. In Unreal den MetaHuman unter **Project Settings > ECA > Avatar** auswählen,
   `ECA_Demo` laden und **Play** drücken. Leertaste halten zum Aufnehmen.

Deine vorhandene private lokale Variante öffnet weiterhin `Main` mit ihrem
spezifischen Charakter. Der Installer ändert dessen Auswahl nicht.

Die Auswahl kann per Parameter geändert werden:

```powershell
.\Setup.bat -Mode Backend
.\Setup.bat -Mode Frontend -BackendUrl http://192.168.1.20:8000
.\Setup.bat -Mode Both
```

`unreal/Setup.bat` richtet weiterhin nur Unreal ein; der neue gemeinsame
Installer ist **`Setup.bat` im Hauptordner**.

## Individualisieren

Die Dateien werden beim ersten Setup angelegt. Ein erneutes Setup überschreibt
vorhandene lokale Einstellungen nicht.

| Einstellung | Datei / Ort |
| --- | --- |
| Name, Rolle, Persönlichkeit, Antwortstil | `.eca/config/persona.txt` |
| Referenzaufnahme | Datei in `voices/`, dann `[voice]` in `.eca/config/avatar.toml` |
| Transkript der Referenzaufnahme | `voice.text` in derselben Datei; muss zur Aufnahme passen |
| LLM | `llm.base_model`, standardmäßig `qwen3.5:9b`; Download beim nächsten Start |
| Whisper-Modell | `stt.model`, standardmäßig `turbo` |
| Enhanced oder Baseline | `conversation.enhanced`, standardmäßig `true` |
| Gesprächsverlauf | `conversation.max_history_messages` |
| Wissen | Dateien in `RAG/`; `rag.enabled`, `top_k` und `timeout` in der Konfiguration |
| Sichtbarer Charakter, Face-Blueprint, Aufnahme-Taste | Unreal: Project Settings > ECA > Avatar |
| Ports, Bind-Adresse, Open-WebUI-Zugang | `.eca/docker.env` |

Ollama verwendet zunächst 4096 Kontext-Tokens und höchstens ein geladenes Modell.
Für mehr Kontext kann `OLLAMA_CONTEXT_LENGTH` in `.eca/docker.env` gesetzt werden;
das benötigt zusätzlichen GPU-Speicher.

Beispiel für eine eigene Stimme:

```toml
[voice]
file = "meine-stimme.wav"
text = "Dieser Text entspricht genau meiner Aufnahme."
```

Der Dateiname ist relativ zu `voices/`. Die mitgelieferte englische Warmup-Datei
ist die Standardreferenz für das mehrsprachige OmniVoice. Eigene Aufnahmen in
`voices/` bleiben von Git ausgeschlossen; nur die zwei Warmup-Dateien sind öffentlich.

Nach Änderungen `Start.bat` erneut ausführen. Es startet das Backend mit der
aktuellen Konfiguration neu. Die native Installation verwendet weiterhin
`avatar_backend/config/system_prompt.txt`, `conditions.py` und `.env`.

Baseline nutzt F5-TTS statt OmniVoice. Dafür müssen zusätzlich die englischen
und deutschen F5-Modelldateien unter `models/` liegen und die entsprechenden
Einträge in `avatar_backend/config/conditions.py` stimmen. Der automatische
Standardweg richtet Enhanced ein; F5-Checkpoints werden nicht automatisch geladen.

## RAG aktualisieren

Dokumente in `RAG/` ablegen und `Update-RAG.bat` ausführen; `Start.bat` macht
denselben Abgleich automatisch. Dateien werden hochgeladen, verarbeitet und
danach der Knowledge-Sammlung hinzugefügt. Der Import wartet auf die Verarbeitung.

Unveränderte Dateien werden anhand ihres SHA-256 nicht erneut hochgeladen.
Geänderte Dateien ersetzen ihre alten Einträge in der verwalteten Sammlung;
gelöschte Dateien werden daraus entfernt. Andere manuell hinzugefügte Einträge
werden nicht entfernt. Versteckte Dateien und symbolische Dateilinks werden
übersprungen. Eine leere Sammlung deaktiviert die RAG-Abfrage bis zum nächsten Import.

Das Backend wird für den Abgleich kurz gestoppt und danach neu gestartet.
Fehlerhafte oder nicht lesbare Dokumente werden als Fehler gemeldet; der Start
wartet auf einen erfolgreichen Import. Bei gescannten PDFs kann vorherige OCR nötig sein.

Die Dokumente werden nur in die eigene Open-WebUI-Instanz im Docker-Netz importiert.
Sie sind weder im Docker-Build-Kontext noch im veröffentlichten Image enthalten.

## Zwei Rechner

Auf dem Backend-Rechner `.eca/docker.env` bearbeiten:

```env
BACKEND_BIND=0.0.0.0
BACKEND_PORT=8000
```

Dann `Start.bat -Mode Backend` ausführen. Auf dem Frontend-Rechner:

```powershell
.\Setup.bat -Mode Frontend -BackendUrl http://192.168.1.20:8000
```

Die echte LAN-Adresse des Backend-Rechners einsetzen. In der Windows-Firewall
den Backend-Port für das gewünschte private Netz freigeben. Die Backend-API hat
keine eigene Anmeldung; sie sollte nur für die vorgesehenen Clients erreichbar sein.
Open WebUI bleibt standardmäßig nur auf dem Backend-Rechner erreichbar.

## Status und Daten

| Befehl | Zweck |
| --- | --- |
| `Start.bat` | Backend starten, RAG abgleichen, gegebenenfalls Unreal öffnen |
| `Stop.bat` | Container stoppen; Daten bleiben erhalten, Unreal bleibt offen |
| `Status.bat` | Containerstatus anzeigen |
| `Update-RAG.bat` | RAG abgleichen und Backend neu starten |
| `powershell -File scripts/setup.ps1 -Action Logs` | Laufende Logs anzeigen, mit Strg+C verlassen |

Open WebUI: `http://localhost:3100`. E-Mail und zufälliges Passwort stehen lokal
in `.eca/docker.env`. Der vom Setup angelegte API-Key wird intern im Volume
`eca_state` gespeichert. Die native `.env` wird nicht verändert.

| Speicher | Inhalt |
| --- | --- |
| `.eca/` | Lokale Persona, Avatar-Konfiguration, Zugangsdaten und Installationsauswahl; Git ignoriert den Ordner |
| `eca_ollama` | Ollama-Modelle |
| `eca_openwebui` | Benutzer, hochgeladene Dateien, Vektordaten und Embedding-Modell |
| `eca_state` | API-Konfiguration und RAG-Importmanifest |
| `eca_cache` | Whisper-, OmniVoice- und weitere Modellcaches |

Ein Stoppen oder erneutes Erstellen von Containern löscht diese Volumes nicht.
`docker compose down -v` würde sie löschen und gehört nicht zum normalen Ablauf.
Zum Sichern gehören sowohl die persönlichen Dateien als auch die Docker-Volumes.
Temporäre Aufnahme- und Antwortdateien des Backends liegen im flüchtigen Speicher.

Die Compose-Datei setzt feste Open-WebUI- und Ollama-Versionen. Wichtige
Python-Modellpakete werden zusätzlich in `docker/constraints.txt` festgelegt.
Das ist kein vollständiger Lock aller transitiven Pakete. Updates sollten mit
einem Test von Anmeldung, RAG und einer gesprochenen Antwort erfolgen.

## Häufige Probleme

- **Docker nicht erreichbar:** Docker Desktop starten, Linux-Container und
  WSL-2-Backend aktivieren. Das Setup installiert WSL nicht selbst.
- **GPU-Prüfung fehlgeschlagen:** NVIDIA-Treiber und WSL aktualisieren, Docker
  neu starten. `docker run --rm --gpus all nvidia/cuda:12.8.1-base-ubuntu22.04 nvidia-smi`
  muss funktionieren.
- **Port belegt:** `BACKEND_PORT` oder `WEBUI_PORT` in `.eca/docker.env` ändern.
  Bei Frontend auch die Backend-Adresse entsprechend setzen.
- **GPU-Speicher voll:** Kleineres `llm.base_model` wählen, andere GPU-Anwendungen
  schließen oder das Backend auf einen anderen Rechner auslagern.
- **Erster Start dauert:** Logs prüfen. Modelldownloads und Initialisierung
  können dauern; fehlgeschlagene Downloads lassen sich mit `Start.bat` wiederholen.
- **Open-WebUI-Login geht nach Passwortänderung nicht:** Zugangsdaten in
  `.eca/docker.env` an die Änderung anpassen. Die dortigen Werte setzen das
  Passwort einer bereits vorhandenen Datenbank nicht zurück.
- **Unreal-Plugin fehlt:** Die NVIDIA-Pakete separat installieren; sie werden
  aus diesem Repository nicht automatisch heruntergeladen.
- **Unreal-Download unterbrochen:** Setup erneut ausführen. Vollständig geprüfte
  Pakete werden aus `.eca/downloads/` wiederverwendet. Lokale Asset-Änderungen
  werden erhalten und als Hinweis angezeigt.

Die Automatisierung verwendet die Schnittstellen der festgelegten Open-WebUI-
Version. Grundlage: [Admin-Erstellung](https://docs.openwebui.com/reference/env-configuration/#webui_admin_email)
und [Datei-/Knowledge-API](https://docs.openwebui.com/reference/api-endpoints/).
