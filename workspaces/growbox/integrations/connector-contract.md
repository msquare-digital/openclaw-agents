# Connector Contract - GrowBox

Dieses Dokument definiert die technische Schnittstelle zwischen Datenquellen (`acinfinity`, `ecowitt`) und der Evaluate-/Notify-Logik.

## Pull Interface
Jeder Connector liefert bei Polling ein einheitliches Ergebnisobjekt:

```json
{
  "source": "acinfinity",
  "status": "ok",
  "fetched_at": "2026-04-19T18:20:00Z",
  "metrics": [
    {
      "metric": "air_temp_c",
      "value": 24.8,
      "unit": "C",
      "timestamp": "2026-04-19T18:19:54Z"
    }
  ],
  "raw_ref": "optional-trace-id"
}
```

## Statuswerte
- `ok`: Daten erfolgreich gelesen.
- `degraded`: Teilweise Daten vorhanden, Teilfehler aufgetreten.
- `error`: Keine nutzbaren Daten.

## Fehlerobjekt
Bei `degraded` oder `error`:

```json
{
  "error": {
    "code": "auth_failed",
    "message": "Token expired",
    "retryable": true
  }
}
```

## Pflichtmetriken V1
### ACInfinity
- `air_temp_c`
- `humidity_pct`
- `airflow_pct` oder `fan_speed_pct`

### Ecowitt
- `soil_moisture_pct`
- `pump_state`

## Normalisierung
- Temperaturen in `C`
- Feuchte in Prozent (`pct`)
- Zeitstempel als ISO-8601 UTC
- Numerische Werte als Zahl, nicht String

## Evaluate Input
Der Evaluator verarbeitet ein kombiniertes Snapshot-Objekt:

```json
{
  "snapshot_at": "2026-04-19T18:20:01Z",
  "sources": ["acinfinity", "ecowitt"],
  "metrics": {
    "air_temp_c": 24.8,
    "humidity_pct": 61,
    "soil_moisture_pct": 33,
    "pump_state": "off"
  },
  "missing": ["soil_moisture_pct"]
}
```

## Notify Input
Notify bekommt nur bereits bewertete Events:

```json
{
  "severity": "warn",
  "metric": "air_temp_c",
  "current": 29.1,
  "expected": "20-28 C",
  "phase": "veg",
  "source": "acinfinity",
  "event_at": "2026-04-19T18:20:01Z",
  "cooldown_key": "warn:air_temp_c:veg"
}
```
