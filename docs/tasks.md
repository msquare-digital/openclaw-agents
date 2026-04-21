# GrowBox Agent Tasks

## Milestone 1 - Foundation (US-01, US-02, US-03)

- [x] T-001 Verzeichnisstruktur `agents/growbox/agent` und `workspaces/growbox` anlegen.
- [x] T-002 Basisdateien `AGENTS.md`, `SOUL.md`, `USER.md` fuer `growbox` erstellen.
- [x] T-003 `growbox` in Dev-Config (`~/.openclaw-dev/openclaw.json`) registrieren.
- [x] T-004 Connector-Schnittstellen definieren (`collect/acinfinity`, `collect/ecowitt`).
- [x] T-005 ACInfinity Auth-Flow als Secret-basiertes Setup dokumentieren.
- [x] T-006 Ecowitt Auth-Flow als Secret-basiertes Setup dokumentieren.
- [x] T-007 ACInfinity Polling fuer Kerndaten implementieren.
- [x] T-008 Ecowitt Polling fuer Bodenfeuchte/Pumpenstatus implementieren.
- [x] T-009 Fehlerbehandlung fuer API-Timeouts/Rate-Limits umsetzen.

## Milestone 2 - Monitoring und Telegram (US-04, US-05, US-06)

- [x] T-010 Regeldefinitionen als Konfigurationsdatei anlegen (warn/critical, hysterese, cooldown).
- [x] T-011 Evaluate-Modul bauen (`ok/warn/critical/sensor_missing`).
- [x] T-012 State-Speicher fuer letzte Werte und letzte Alerts implementieren.
- [x] T-013 Telegram Alert-Formatter mit einheitlichem Nachrichtenformat erstellen.
- [x] T-014 Push-Alerts bei `warn/critical` implementieren.
- [x] T-015 Pull-Kommandos `/status`, `/werte`, `/alarme`, `/hilfe` implementieren.
- [x] T-016 Anti-Spam-Logik (Cooldown + Deduplizierung) testen.

## Milestone 3 - Grow-Kontext (US-07, US-08)

- [x] T-017 Pflanzenprofil-Schema definieren (Sorte, Phase, Anbauart).
- [x] T-018 Profil-Datei im Workspace laden und validieren.
- [x] T-019 Phasenabhaengige Grenzwerte im Regelwerk aktivieren.
- [x] T-020 Empfehlungstexte pro Regel und Phase hinterlegen.
- [x] T-021 Telegram-Ausgaben um Profil/Phase + Tagesanalyse (24h) + Wochen/Tag-Kontext erweitern.

## Milestone 4 - Sichere Steuerung (US-09, US-10)

- [ ] T-022 Telegram-Befehl fuer manuelle Pumpensteuerung entwerfen.
- [ ] T-023 Max-Laufzeit, Sperrzeit und Rate-Limit fuer Pumpenaktionen implementieren.
- [ ] T-024 Dry-Run-Modus fuer Aktorbefehle einbauen.
- [ ] T-025 Bestaetigungs-Flow fuer kritische Befehle implementieren.
- [ ] T-026 Audit-Log fuer alle Steueraktionen anlegen.

## Querschnitt: Qualitaet und Betrieb

- [ ] T-027 Unit-Tests fuer Regelengine (Grenzwerte, Hysterese, Cooldown).
- [ ] T-028 Integrations-Tests mit simulierten API-Antworten erstellen.
- [ ] T-029 End-to-End Test ueber Telegram in Dev-Umgebung durchfuehren.
- [ ] T-030 Deployment-Doku fuer `scripts/deploy-dev.sh --agent growbox` ergaenzen.
- [ ] T-031 Runbook fuer Stoerfaelle (API down, Sensor missing, Telegram down) dokumentieren.
