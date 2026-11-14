# MetaHuman-Projekt verwenden

Das Unreal-Frontend liegt in `unreal/`, das Python-Backend in `avatar_backend/`.
Der historische Projektname lautet `METAHUMAN_5_5`, die benötigte Engine-Version
ist aber **Unreal Engine 5.6**. Die ursprüngliche Projektkopie wird weiterhin
separat aufbewahrt.

## Eigenen MetaHuman auswählen

Die öffentliche Startszene ist `/Game/ECA/ECA_Demo` und verwendet standardmäßig
den neutralen Beispielcharakter **Keiji**. Die Gesprächssteuerung hängt nicht
mehr von einem bestimmten Charakter-Blueprint ab.

1. Einen assemblierten MetaHuman für UE 5.6 mit seinem Blueprint ins Projekt importieren.
2. **Edit > Project Settings > ECA > Avatar** öffnen.
3. Unter **MetaHuman Blueprint** den eigenen `BP_...` auswählen.
4. Im Backend Persona-Prompt, RAG-Sammlung und Referenzaufnahme einstellen.
5. Das eingerichtete Backend starten, `ECA_Demo` öffnen und **Play** drücken.

Die Session erzeugt den ausgewählten Charakter, findet seine `Face`-Komponente
und richtet gemeinsame Face-Animation und ACE-Audiokomponente automatisch ein.
Die normalen UE-5.6-MetaHuman-Blueprints benötigen dafür keine Graph-Änderungen.
Bei abweichenden eigenen Komponenten stehen Face-Komponentenname und Face-Anim-
Blueprint als erweiterte Einstellungen zur Verfügung. Vorhandene Körperanimationen
des importierten Charakters bleiben erhalten.

Backend-Adresse, Aufnahme-Taste und Audio2Face-Provider stehen ebenfalls auf
dieser Einstellungsseite. Für einzelne Szenen kann am `ECAAvatarSession`-Actor
unter den erweiterten Einstellungen ein anderer Charakter ausgewählt werden.

## Private lokale Variante

Die vorhandene lokale Szene `Main` und ihr spezifischer Charakter bleiben
unverändert erhalten. Sie und die zugehörigen alten Voice-/Animations-Blueprints
sind von Git ausgeschlossen. Die öffentliche Demo referenziert sie nicht.

`unreal/Config/ECA.local.ini` enthält die lokale Startszene samt bisherigem GameMode und kann zusätzlich
die öffentlichen Avatar-Einstellungen überschreiben. Diese Datei wird ignoriert.
`Setup.bat` übernimmt die lokale Startszene in die ebenfalls ignorierte
Editor-Konfiguration; `Open.bat` berücksichtigt sie direkt. Ein neuer Git-Klon
hat dieses Profil nicht und öffnet daher die neutrale Demo.

Die Profilwerte werden nur in eine temporäre Laufzeitkopie geladen; die
öffentliche `DefaultECA.ini` enthält weiterhin die neutrale Auswahl. Eigene
zusätzliche private Assets können unter `/Game/Local/` abgelegt werden; dieser
Ordner ist nicht Teil der Inhaltsfreigabe für Git.

## Voraussetzungen

- Windows und Unreal Engine 5.6 über den Epic Games Launcher.
- Visual Studio 2022 mit **Game development with C++**, einem Windows SDK und
  den C++-Build-Tools. Die mitgelieferte `unreal/.vsconfig` beschreibt die Komponenten.
- Die MetaHuman-Plugins für UE 5.6, die bereits beim ursprünglichen Projekt
  verwendet wurden.
- Eine passende NVIDIA-GPU für lokale ACE-Gesichtsanimation und das CUDA-Backend.
  Die Modelle von LLM, Whisper, TTS und Gesichtsanimation benötigen gemeinsam
  GPU-Speicher. Eine andere Backend-Maschine lässt sich konfigurieren.

Die Quellcode-Kopien von BlueprintWebsockets und RuntimeAudioImporter sind
einschließlich Lizenzdateien im Repository vorgesehen. Ihre Binaries und
Build-Caches werden lokal erzeugt und bleiben ausgeschlossen. Herkunft und
weitere eingebettete Bibliotheken stehen in
[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).

Die NVIDIA-Pakete und Modelle liegen in der lokalen Projektkopie, werden aber
nicht mit Git veröffentlicht. Für einen Git-Klon müssen sie separat installiert
werden:

| Plugin | Verwendung | Bereitstellung |
| --- | --- | --- |
| EasyWebsockets / BlueprintWebsockets | Verbindung zum Backend | Quellcode mit MIT-Lizenz enthalten |
| RuntimeAudioImporter | Empfangene WAV-Antworten importieren | Quellcode mit MIT- und eingebetteten Drittanbieter-Lizenzen enthalten |
| NV_ACE_Reference, Version 2.5 für UE 5.6 | Gesichtsanimation mit NVIDIA ACE | Separat installieren |
| NvAudio2FaceClaire, NvAudio2FaceJames, NvAudio2FaceMark, Version 2.4 für UE 5.6 | Lokale Audio2Face-Modelle der bestehenden Konfiguration | Separat installieren |

Bei den NVIDIA-Downloads müssen die Versionen zur Engine und zur vorhandenen
Projektkonfiguration passen. Installation und Anforderungen stehen in der
[NVIDIA-Anleitung für ACE 2.5](https://docs.nvidia.com/ace/ace-unreal-plugin/2.5/ace-unreal-plugin-install.html)
und der [Support-Matrix](https://docs.nvidia.com/ace/ace-unreal-plugin/2.5/ace-unreal-plugin-support-matrix.html).
Die mitkopierten offenen Plugins stammen aus
[BlueprintWebsockets](https://github.com/minimpoun/BlueprintWebsockets) und
[RuntimeAudioImporter](https://github.com/gtreshchev/RuntimeAudioImporter).
Der zusätzliche BlueprintSerializer ist ein optionales Entwicklungswerkzeug,
in dieser Kopie deaktiviert und weiterhin von Git ausgeschlossen.

## Einmal einrichten

Im Projekt-Hauptordner:

```powershell
.\unreal\Setup.bat
```

Das Skript sucht die passende Engine, prüft die Projektplugins, kompiliert das
Projekt, legt die öffentliche Demo an, falls sie fehlt, und berücksichtigt ein
vorhandenes lokales Profil. Der alte Voice-Manager wird nur aktualisiert, wenn
die private Variante lokal vorhanden ist. Das Skript kann erneut ausgeführt werden
und überschreibt keine bereits vorhandene Demo-Szene.

Wenn die Engine an einem anderen Ort liegt:

```powershell
.\unreal\Setup.bat -EngineRoot "D:\Epic Games\UE_5.6"
```

Alternativ kann `UE_ROOT` auf diesen Installationsordner gesetzt werden.
`unreal/Generate.bat` erzeugt bei Bedarf eine Visual-Studio-Projektmappe;
`unreal/Build.bat` kompiliert spätere C++-Änderungen.

## Starten

1. Backend mit `Setup.bat` im Hauptordner einrichten und danach mit `Start.bat`
   starten; siehe [Docker-Anleitung](docker.md). Alternativ das Backend manuell
   entsprechend der [Backend-Anleitung](../README.md) starten.
2. `unreal/Open.bat` ausführen oder `unreal/METAHUMAN_5_5.uproject` öffnen.
3. In der öffentlichen Vorlage `ECA_Demo` laden und **Play** drücken. Mit lokalem
   Profil bleibt die private Startszene `Main` verfügbar.
4. In das Spielfenster klicken. **Leertaste halten** zum Aufnehmen,
   **loslassen** zum Abschicken.

Die öffentliche Demo nutzt standardmäßig `ws://127.0.0.1:8000/ws`. Bei einem
anderen Rechner die **Backend URL** unter **Project Settings > ECA > Avatar**
ändern. Die Einstellung wird in `unreal/Config/DefaultECA.ini` gespeichert:

```ini
[/Script/METAHUMAN_5_5.ECAAvatarSettings]
BackendUrl="http://192.168.1.10:8000"
```

Die Session bildet daraus automatisch die WebSocket-Adresse mit `/ws`.
Für HTTPS wird `wss://` verwendet. Nach einer Konfigurationsänderung den Editor
neu starten. Auf einer anderen Backend-Maschine muss Uvicorn auf einer
erreichbaren Adresse lauschen, beispielsweise mit `--host 0.0.0.0`.
Die unveränderte private Legacy-Szene verwendet weiterhin `BackendBaseUrl` im
Abschnitt `MetaHumanBackend` der `DefaultEngine.ini`.

## Individualisieren

Bei Docker liegen Persona und Stimmkonfiguration in `.eca/config/` und RAG wird
aus `RAG/` importiert; siehe [Docker-Anpassungen](docker.md#individualisieren).
Die folgende Tabelle beschreibt die bisherige native Backend-Installation.

| Was? | Wo? |
| --- | --- |
| Name, Rolle, Persönlichkeit und Sprechstil | Platzhalter in `avatar_backend/config/system_prompt.txt` ersetzen |
| Fachwissen / RAG | Dokumente in Open WebUI in eine Knowledge-Sammlung importieren und deren ID in `.env` setzen; `RAG/` dient als lokaler Ablageordner |
| Stimme | In `avatar_backend/config/conditions.py` zusammengehörige `ref_audio` und `ref_text` ändern |
| Baseline oder Enhanced | `ENHANCED=false` bzw. `ENHANCED=true` in `.env`, danach das Backend neu starten |
| Sprachmodell | Modell-ID `avatar` in Open WebUI auf das gewünschte Ollama-Modell konfigurieren |
| Backend-Rechner | Project Settings > ECA > Avatar > Backend URL |
| Aufnahme-Taste | Project Settings > ECA > Avatar > Push To Talk Key |
| Sichtbarer MetaHuman | Project Settings > ECA > Avatar > MetaHuman Blueprint |
| Darstellung und Szene | Map `/Game/ECA/ECA_Demo`; die private `Main` bleibt lokal |

Die Standardstimmen stammen aus `voices/warmup.wav` (Englisch und Enhanced)
und `voices/warmup-de.wav` (Baseline Deutsch). Ein neuer Referenztext muss
genau zum Inhalt der jeweiligen Aufnahme passen. Die bisherigen privaten
Referenzaufnahmen bleiben lokal und werden nicht mit Git veröffentlicht.

Der Persona-Prompt ändert das Verhalten, nicht das sichtbare 3D-Modell. Der
Charakterwechsel erfolgt über die Blueprint-Auswahl; Gespräch, Mikrofon und
Backend-Verbindung bleiben im gemeinsamen Session-Actor. Die bestehende private
Szene verwendet weiterhin ihren ursprünglichen Charakter und Ablauf.

Das Backend muss für **Play** bereits eingerichtet und erreichbar sein. Die
Demo verbindet sich automatisch erneut, falls es später startet. `Start.bat` im
Hauptordner startet die Docker-Dienste und importiert geänderte RAG-Dateien vor
dem Öffnen von Unreal. **Play** selbst startet keine Container.

## Prüfen und weitergeben

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\unreal.ps1 -Action Check
powershell -ExecutionPolicy Bypass -File .\scripts\unreal.ps1 -Action Verify
```

`Check` prüft Dateien und Engine-Version. `Verify` lädt beide vorhandenen
Szenen ohne Editorfenster, prüft den Wechsel zwischen neutralen MetaHumans,
die lokale Auswahl sowie die Abhängigkeiten der öffentlichen Demo und schreibt
das Ergebnis nach `unreal/Saved/Validation/eca-project.json`.
Das ersetzt keinen Test von Mikrofon, Sprachantwort und Gesichtsanimation im Spiel.

Für die Weitergabe des vollständigen lokalen Projekts werden `.uproject`,
`Config/`, `Content/`, `Source/`, die benötigten `Plugins/` und die Skripte aus
diesem Repository benötigt. `Saved/`, `Intermediate/`, `DerivedDataCache/`,
`.vs/` und erzeugte Projekt-Binaries werden auf dem Zielrechner neu erstellt.
Die Laufzeitdateien unter `Plugins/.../ThirdParty/` gehören dagegen zu den Plugins.

Unreal-Inhalte werden als geprüfte ZIP-Pakete über
[GitHub Releases](https://github.com/miguelpepe/eca-experimental-system/releases/tag/unreal-assets-v1)
verteilt. `Setup.bat` lädt sie automatisch; `Open.bat` ergänzt bei Bedarf fehlende
Inhalte. Ein Git-Klon enthält Code, Konfiguration und die beiden mitgelieferten
Plugin-Quellcodes. Git LFS wird nicht benötigt. NVIDIA-Pakete und Modelle werden
weiterhin separat installiert.

Version, Download-URLs und Paket-/Dateiprüfsummen stehen in `unreal/assets.json`.
Geprüfte ZIPs bleiben unter `.eca/downloads/` im Cache. Bereits vorhandene Dateien
werden geprüft; eigene Asset-Änderungen bleiben erhalten. Unveränderte, zuvor
installierte Assets können bei einem neuen Paketstand aktualisiert werden.
Private Szenen und der spezifische lokale MetaHuman sind nicht im Paketmanifest
enthalten und werden beim Download nicht angefasst.

Für einen neuen Asset-Release kann der Maintainer die Pakete neu erstellen:

```powershell
python scripts/package_unreal.py --version unreal-assets-v2
```

Das Skript verwendet die geprüfte Dateiliste aus dem bestehenden Manifest.
Neue öffentliche Assets müssen dieser Liste ausdrücklich hinzugefügt werden;
es wird nicht der gesamte lokale Content-Ordner eingepackt. Die Archive und
Prüfsummen liegen danach unter `.eca/releases/<Version>/`. Code und aktualisiertes
Manifest committen und pushen, danach mit
`python scripts/publish_unreal_release.py --publish` hochladen. Der Upload nutzt
den vorhandenen Git-Zugang und prüft die von GitHub gemeldeten SHA-256-Werte.
Bereits veröffentlichte Paketversionen sollten unverändert bleiben.

Für einen reproduzierbaren Dateitest kann der Editor mit `-ECAPublicProfile`
ohne lokales Avatar-Profil gestartet werden. `-ECAEndpoint=http://127.0.0.1:8000`
überschreibt die Backend-Adresse nur für diesen Lauf. `-ECAAudioFile="C:\sample.wav"`
sendet diese Datei nach dem Verbindungsaufbau; `-ECAExitWhenDone` beendet den
Lauf nach der vollständigen Antwort. Ohne diese Optionen bleibt der normale
interaktive Ablauf aktiv.
