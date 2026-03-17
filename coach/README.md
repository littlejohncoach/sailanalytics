# SailAnalytics Coach Dashboard (FastAPI + Static Frontend)

## Truth layer
- CSV truth lives at: `SailAnalytics/data/totalraces/*.csv`
- The app reads these files **read-only**.

## Run
From `SailAnalytics/coach/`:

```bash
python run_dashboard.py
```

Open:
- Dashboard: `http://127.0.0.1:8000/`
- API docs: `http://127.0.0.1:8000/docs`

## Requirements
Install once (in your chosen venv):

```bash
pip install fastapi uvicorn pandas
```

## Phase 1 behaviour
- Sidebar loads races from `data/totalraces/*.csv`
- Selecting a race loads sailors + legs (best-effort column detection)
- Refresh loads:
  - track (first selected sailor) if lat/lon exist
  - data slice table

If your CSV column names differ, Phase 1 still works as long as it can detect:
- sailor column: e.g. `sailor_name`
- leg column: e.g. `leg_instance_id`
- time column: `timestamp` or `sample_idx` (optional for Phase 1)
- lat/lon columns (optional for viewer): `latitude_deg`, `longitude_deg`
