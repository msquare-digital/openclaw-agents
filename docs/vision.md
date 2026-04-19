# GrowBox Agent Vision

## 1. Problem und Zielbild
Der GrowBox Agent soll die Umgebungs- und Bodenwerte zentral ueberwachen, Abweichungen frueh erkennen und ueber einen dedizierten Telegram-Kanal verlässlich melden.

Der Agent nutzt zwei Datenquellen:
- ACInfinity fuer Klima- und Geraetewerte (z. B. Temperatur, Luftfeuchte, Umluft/Luefterstatus)
- Ecowitt fuer Bodenfeuchte und Pumpen-/Bewaesserungswerte

Langfristig soll der Agent nicht nur monitoren, sondern auch kontrolliert Aktionen ausfuehren (Pumpe/Geraete), immer mit Sicherheitsgrenzen.

## 2. Produktvision
Ein robuster, fehlertoleranter Operations-Agent fuer den Anbau, der:
- Messwerte kontinuierlich erfasst,
- sie phasenabhaengig bewertet (Keimung/Veg/Bluete),
- relevante Alerts ohne Spam an Telegram sendet,
- und spaeter manuelle sowie abgesicherte Steueraktionen unterstuetzt.

## 3. Scope
### In Scope (v1)
- Read-only Monitoring fuer ACInfinity und Ecowitt
- Regelbasierte Bewertung (OK/WARN/CRITICAL)
- Telegram Push-Alerts bei Abweichungen
- Telegram Pull-Kommandos (`/status`, `/werte`, `/alarme`, `/hilfe`)
- Cooldown/Hysterese gegen Alert-Spam

### Out of Scope (v1)
- Vollautomatische Aktor-Steuerung ohne Nutzerfreigabe
- Komplexe ML-Prognosen
- Multi-GrowBox-Mandantenbetrieb

## 4. Nutzer und Nutzen
### Hauptnutzer
- GrowBox-Betreiber (du)

### Nutzen
- Weniger manuelle Kontrollen
- Schnellere Reaktion bei kritischen Werten
- Nachvollziehbarkeit ueber Verlauf und Alarmhistorie

## 5. Nicht-funktionale Anforderungen
- Zuverlaessigkeit: Polling-Ausfall darf nicht still bleiben, sondern muss als `sensor_missing` sichtbar werden.
- Sicherheit: Secrets bleiben lokal auf dem Raspberry, nicht im Git.
- Nachvollziehbarkeit: Jede Warnung ist mit Zeitstempel, Quelle und betroffener Regel dokumentiert.
- Wartbarkeit: Integrationen, Regeln und Telegram-Logik sind modular getrennt.

## 6. Architekturprinzipien
- `collect`: Rohdaten von ACInfinity/Ecowitt holen
- `evaluate`: Schwellwerte, Hysterese, Cooldown, Anomalie-Logik
- `notify`: Telegram Push/Pull
- `state`: letzter Messwert, letzter Alert, Cooldown-Status, Fehlerstatus

## 7. Datenmodell (fachlich)
Pro Messpunkt:
- `source`: `acinfinity` | `ecowitt`
- `metric`: z. B. `air_temp_c`, `humidity_pct`, `soil_moisture_pct`
- `value`, `unit`, `timestamp`

Pro Regel:
- `metric`
- `phase` (optional)
- `warn_min`, `warn_max`, `critical_min`, `critical_max`
- `cooldown_minutes`
- `hysteresis`

## 8. Roadmap
### Sprint 1 (Foundation)
- Agent-Geruest `growbox` im Repo
- Read-Connectoren fuer ACInfinity/Ecowitt (nur lesen)
- Basiskommando `/status`

### Sprint 2 (Monitoring)
- Bewertungsengine + Alarmstufen
- Telegram Push-Alerts + Cooldown/Hysterese
- Kommandos `/werte`, `/alarme`, `/hilfe`

### Sprint 3 (Grow-Kontext)
- Pflanzenprofil (Sorte/Phase/Anbauart)
- Phasenabhaengige Grenzwerte
- Verbesserte Empfehlungstexte in Alerts

### Sprint 4 (Controlled Actions)
- Manuelle Telegram-Steuerbefehle fuer Pumpe/Geraete
- Guardrails: Max-Laufzeit, Bestaetigung, Sperrzeiten, Dry-Run

## 9. Erfolgskriterien
- 48h stabiler Betrieb in Dev ohne Absturz
- Korrekte Warnung bei simulierten Grenzwertverletzungen
- Keine Alert-Flut bei konstantem Problem (Cooldown wirkt)
- Telegram-Abfragen liefern aktuelle, konsistente Werte
