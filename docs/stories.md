# GrowBox Agent Stories

## Epic A - Monitoring Foundation

### US-01 Agent-Grundgeruest
Als Betreiber moechte ich einen `growbox` Agent mit sauberer Struktur, damit ich Integrationen und Regeln iterativ entwickeln kann.

Akzeptanzkriterien:
- Agent- und Workspace-Verzeichnisse fuer `growbox` existieren.
- Basisdateien (`AGENTS.md`, `SOUL.md`, `USER.md`) sind vorhanden.
- Agent ist in der Dev-OpenClaw-Konfiguration registrierbar.

### US-02 ACInfinity Read Integration
Als Betreiber moechte ich Klima- und Geraetedaten aus ACInfinity lesen, damit der Agent den Zustand der Box bewerten kann.

Akzeptanzkriterien:
- Authentifizierung gegen ACInfinity funktioniert.
- Mindestens Temperatur, Luftfeuchte und Umluft/Luefterstatus werden gelesen.
- Bei API-Fehlern wird ein strukturierter Fehlerstatus erzeugt.

### US-03 Ecowitt Read Integration
Als Betreiber moechte ich Bodenfeuchte- und Pumpenstatusdaten aus Ecowitt lesen, damit ich die Bewaesserung beobachten kann.

Akzeptanzkriterien:
- Authentifizierung gegen Ecowitt funktioniert.
- Bodenfeuchte und Pumpenstatus sind abrufbar.
- Fehlende Daten werden als `sensor_missing` kenntlich gemacht.

## Epic B - Alerting und Telegram

### US-04 Regelengine und Schwellwerte
Als Betreiber moechte ich Messwerte gegen Grenzwerte pruefen, damit Abweichungen eindeutig klassifiziert werden.

Akzeptanzkriterien:
- Regeln erzeugen `ok`, `warn` oder `critical`.
- Hysterese verhindert ständiges Hin-und-Her um Schwellwerte.
- Regelausgabe enthaelt Ursache und betroffene Metrik.

### US-05 Push-Alerts in Telegram
Als Betreiber moechte ich bei Abweichungen proaktiv informiert werden, damit ich schnell reagieren kann.

Akzeptanzkriterien:
- `warn` und `critical` werden in den dedizierten Telegram-Kanal gesendet.
- Nachrichten enthalten Metrik, Istwert, Grenzwert, Zeitstempel.
- Cooldown verhindert doppelte Alerts im kurzen Abstand.

### US-06 Pull-Kommandos in Telegram
Als Betreiber moechte ich den Status jederzeit via Telegram abrufen, damit ich ohne UI sofort Einblick bekomme.

Akzeptanzkriterien:
- `/status` liefert kompakten Gesamtstatus.
- `/werte` liefert alle Kernmetriken.
- `/alarme` zeigt letzte Abweichungen.
- `/hilfe` listet alle verfuegbaren Befehle.

## Epic C - Grow-Kontext

### US-07 Pflanzenprofil und Wachstumsphase
Als Betreiber moechte ich Sorte, Phase und Anbauart hinterlegen, damit Regeln situativ bewertet werden.

Akzeptanzkriterien:
- Profil kann aus einer Konfigurationsdatei geladen werden.
- Phase beeinflusst die Schwellwerte.
- Statusausgabe zeigt aktives Profil und Phase.

### US-08 Phasenbasierte Empfehlungen
Als Betreiber moechte ich kontextbezogene Hinweise erhalten, damit ich bei Abweichungen zielgerichtet handeln kann.

Akzeptanzkriterien:
- Alerts enthalten kurzen Handlungshinweis pro Phase.
- Hinweise sind regelbasiert und nachvollziehbar.

## Epic D - Sichere Steuerung (v2)

### US-09 Manuelle Pumpensteuerung via Telegram
Als Betreiber moechte ich die Pumpe manuell ansteuern koennen, damit ich remote eingreifen kann.

Akzeptanzkriterien:
- Befehl z. B. `/pumpe an 10s` ist verfuegbar.
- Max-Laufzeit ist erzwungen.
- Aktion wird mit Zeitstempel protokolliert.

### US-10 Guardrails fuer Geraetesteuerung
Als Betreiber moechte ich Sicherheitsgrenzen bei Aktorbefehlen, damit Fehlbedienung minimiert wird.

Akzeptanzkriterien:
- Optionaler Dry-Run-Modus.
- Bestaetigungsmechanismus fuer kritische Aktionen.
- Sperrzeiten/Cooldowns fuer wiederholte Schaltvorgaenge.
