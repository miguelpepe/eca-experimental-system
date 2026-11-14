# MetaHuman-Frontend

Dieses Projekt verwendet **Unreal Engine 5.6**, trotz des historischen Namens
`METAHUMAN_5_5`.

Für Backend und Frontend gemeinsam: **`Setup.bat` im übergeordneten Hauptordner**
ausführen und „Both“ wählen. Danach startet dessen `Start.bat` das Docker-Backend
und öffnet Unreal. Anleitung: [Docker-Einrichtung](../docs/docker.md).

Nur dieses Unreal-Projekt einrichten:

Die öffentlichen Content-Dateien werden beim Setup aus GitHub Releases geladen
und geprüft. Git LFS ist nicht erforderlich; lokale Änderungen bleiben erhalten.

1. Unreal Engine 5.6 und die C++-Werkzeuge von Visual Studio 2022 installieren.
2. Einmal `Setup.bat` ausführen. Das kompiliert den Editor und richtet die
   Backend-Verbindung im Voice-Manager ein.
3. Den eigenen MetaHuman importieren und unter **Project Settings > ECA > Avatar**
   als **MetaHuman Blueprint** auswählen.
4. Prompt, Wissensbasis und Referenzstimme im Backend konfigurieren und das Backend starten.
5. `Open.bat` ausführen, in der öffentlichen Demo `ECA_Demo` **Play** drücken
   und die Leertaste zum Sprechen halten.

Eine vorhandene `Config/ECA.local.ini` hat lokal Vorrang. In der ursprünglichen
Arbeitskopie öffnet sie weiterhin die private Szene `Main` mit ihrem bisherigen
MetaHuman. Private Szene und Charakter werden nicht veröffentlicht.

Voraussetzungen, Plugins und Anpassungen: [Einrichtung des Frontends](../docs/unreal.md).
