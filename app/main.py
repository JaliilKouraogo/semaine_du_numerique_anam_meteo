import json
import re
from datetime import date, datetime
from typing import List, Optional

from pathlib import Path
import subprocess

from fastapi import Depends, FastAPI, HTTPException, Query, status, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from . import models, schemas
from .database import Base, engine, get_db, SessionLocal

app = FastAPI(
    title="API Météo Burkina",
    description=(
        "API REST pour suivre les bulletins météo et les relevés de stations "
        "issus du pipeline 'Semaine du numérique'."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent.parent
ALL_MERGED_PATH = BASE_DIR / "data" / "all_merged.json"
EVAL_METRICS_PATH = BASE_DIR / "data" / "evaluation_metrics.json"
MERGED_FILES_ROOT = BASE_DIR / "2024_temps_merged"


MONTHS_MAP = {
    "janvier": 1,
    "fevrier": 2,
    "février": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "aout": 8,
    "août": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "decembre": 12,
    "décembre": 12,
}


def parse_french_date(label: str) -> Optional[date]:
    if not label:
        return None
    # ISO
    iso_match = re.search(r"(20\d{2})[-_/](\d{2})[-_/](\d{2})", label)
    if iso_match:
        y, m, d = iso_match.groups()
        try:
            return date(int(y), int(m), int(d))
        except ValueError:
            return None

    match = re.search(
        r"(\d{1,2})\s+([A-Za-zéêàûîôùëï]+)\s+(20\d{2})",
        label,
        flags=re.IGNORECASE,
    )
    if match:
        day, month_txt, year = match.groups()
        month = MONTHS_MAP.get(month_txt.lower())
        if month:
            try:
                return date(int(year), month, int(day))
            except ValueError:
                return None
    return None


def seed_database_from_all_merged():
    if not ALL_MERGED_PATH.exists():
        return

    session = SessionLocal()
    try:
        existing = session.query(models.Bulletin).count()
        if existing > 0:
            return

        payload = json.loads(ALL_MERGED_PATH.read_text(encoding="utf-8"))
        bulletins = payload.get("bulletins", [])

        for entry in bulletins:
            date_obj = parse_french_date(entry.get("date_bulletin", ""))
            if not date_obj:
                continue

            existing_bulletin = (
                session.query(models.Bulletin)
                .filter(models.Bulletin.date_bulletin == date_obj)
                .first()
            )
            if existing_bulletin:
                continue

            bulletin = models.Bulletin(
                date_bulletin=date_obj,
                source_pdf=entry.get("_source_file"),
            )
            session.add(bulletin)
            session.flush()

            for station_data in entry.get("stations", []):
                station_payload = schemas.StationBase(
                    nom=station_data.get("nom", "Station"),
                    latitude=station_data.get("latitude"),
                    longitude=station_data.get("longitude"),
                )
                station = create_or_update_station(session, station_payload)
                report = models.StationReport(
                    bulletin_id=bulletin.id,
                    station_id=station.id,
                    Tmin_obs=station_data.get("Tmin_obs"),
                    Tmax_obs=station_data.get("Tmax_obs"),
                    temps_obs=station_data.get("temps_obs"),
                    Tmin_prev=station_data.get("Tmin_prev"),
                    Tmax_prev=station_data.get("Tmax_prev"),
                    temps_prev=station_data.get("temps_prev"),
                    interpretation_moore=station_data.get("interpretation_moore", ""),
                    interpretation_dioula=station_data.get("interpretation_dioula", ""),
                )
                session.add(report)

        session.commit()
    except Exception as exc:
        session.rollback()
        print(f"[seed] Impossible de charger data/all_merged.json : {exc}")
    finally:
        session.close()


@app.on_event("startup")
def startup_event():
    Base.metadata.create_all(bind=engine)
    seed_database_from_all_merged()


def normalize_station_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip()).upper()


def get_bulletin_or_404(bulletin_id: int, db: Session) -> models.Bulletin:
    bulletin = (
        db.query(models.Bulletin)
        .options(
            selectinload(models.Bulletin.station_reports).selectinload(
                models.StationReport.station
            )
        )
        .filter(models.Bulletin.id == bulletin_id)
        .first()
    )
    if not bulletin:
        raise HTTPException(status_code=404, detail="Bulletin introuvable")
    return bulletin


def get_station_or_404(station_id: int, db: Session) -> models.Station:
    station = db.query(models.Station).filter(models.Station.id == station_id).first()
    if not station:
        raise HTTPException(status_code=404, detail="Station introuvable")
    return station


def station_to_schema(
    station: models.Station,
    latest_report: Optional[models.StationReport] = None,
) -> schemas.StationOut:
    return schemas.StationOut(
        id=station.id,
        name=station.name,
        latitude=station.latitude,
        longitude=station.longitude,
        x_rel=station.x_rel,
        y_rel=station.y_rel,
        created_at=station.created_at,
        updated_at=station.updated_at,
        Tmin_obs=latest_report.Tmin_obs if latest_report else None,
        Tmax_obs=latest_report.Tmax_obs if latest_report else None,
        temps_obs=latest_report.temps_obs if latest_report else None,
        Tmin_prev=latest_report.Tmin_prev if latest_report else None,
        Tmax_prev=latest_report.Tmax_prev if latest_report else None,
        temps_prev=latest_report.temps_prev if latest_report else None,
    )


def report_to_schema(report: models.StationReport) -> schemas.StationReportOut:
    return schemas.StationReportOut(
        id=report.id,
        bulletin_id=report.bulletin_id,
        date_bulletin=report.bulletin.date_bulletin if report.bulletin else None,
        station=station_to_schema(report.station),
        Tmin_obs=report.Tmin_obs,
        Tmax_obs=report.Tmax_obs,
        temps_obs=report.temps_obs,
        Tmin_prev=report.Tmin_prev,
        Tmax_prev=report.Tmax_prev,
        temps_prev=report.temps_prev,
        interpretation_moore=report.interpretation_moore,
        interpretation_dioula=report.interpretation_dioula,
        created_at=report.created_at,
    )


def bulletin_to_detail(bulletin: models.Bulletin) -> schemas.BulletinDetail:
    return schemas.BulletinDetail(
        id=bulletin.id,
        date_bulletin=bulletin.date_bulletin,
        source_pdf=bulletin.source_pdf,
        map1_image=bulletin.map1_image,
        map2_image=bulletin.map2_image,
        notes=bulletin.notes,
        station_count=len(bulletin.station_reports),
        created_at=bulletin.created_at,
        updated_at=bulletin.updated_at,
        stations=[report_to_schema(r) for r in bulletin.station_reports],
    )


def bulletin_to_summary(bulletin: models.Bulletin) -> schemas.BulletinSummary:
    return schemas.BulletinSummary(
        id=bulletin.id,
        date_bulletin=bulletin.date_bulletin,
        source_pdf=bulletin.source_pdf,
        map1_image=bulletin.map1_image,
        map2_image=bulletin.map2_image,
        notes=bulletin.notes,
        station_count=len(bulletin.station_reports),
        created_at=bulletin.created_at,
        updated_at=bulletin.updated_at,
    )


def create_or_update_station(
    db: Session, payload: schemas.StationBase, allow_existing: bool = True
) -> models.Station:
    normalized = normalize_station_name(payload.name)
    station = (
        db.query(models.Station)
        .filter(models.Station.normalized_name == normalized)
        .first()
    )

    if station and not allow_existing:
        raise HTTPException(status_code=409, detail="Station déjà existante")

    if not station:
        station = models.Station(
            name=payload.name.strip(),
            normalized_name=normalized,
            latitude=payload.latitude,
            longitude=payload.longitude,
            x_rel=payload.x_rel,
            y_rel=payload.y_rel,
        )
        db.add(station)
        db.flush()
    else:
        # Mettre à jour les métadonnées si fournies
        if payload.name and payload.name.strip() != station.name:
            station.name = payload.name.strip()
        if payload.latitude is not None:
            station.latitude = payload.latitude
        if payload.longitude is not None:
            station.longitude = payload.longitude
        if payload.x_rel is not None:
            station.x_rel = payload.x_rel
        if payload.y_rel is not None:
            station.y_rel = payload.y_rel

    return station


@app.get("/health")
def health_check():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.post(
    "/bulletins/import",
    response_model=schemas.BulletinDetail,
    status_code=status.HTTP_201_CREATED,
)
def import_bulletin(
    payload: schemas.BulletinImport, db: Session = Depends(get_db)
):
    existing = (
        db.query(models.Bulletin)
        .options(
            selectinload(models.Bulletin.station_reports).selectinload(
                models.StationReport.station
            )
        )
        .filter(models.Bulletin.date_bulletin == payload.date_bulletin)
        .first()
    )

    if existing and not payload.replace_existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Bulletin déjà importé pour cette date. "
                "Utilisez replace_existing=true pour écraser."
            ),
        )

    if existing:
        db.query(models.StationReport).filter(
            models.StationReport.bulletin_id == existing.id
        ).delete()
        bulletin = existing
        bulletin.source_pdf = payload.source_pdf
        bulletin.map1_image = payload.map1_image
        bulletin.map2_image = payload.map2_image
        bulletin.notes = payload.notes
        bulletin.updated_at = datetime.utcnow()
    else:
        bulletin = models.Bulletin(
            date_bulletin=payload.date_bulletin,
            source_pdf=payload.source_pdf,
            map1_image=payload.map1_image,
            map2_image=payload.map2_image,
            notes=payload.notes,
        )
        db.add(bulletin)
        db.flush()

    for report_payload in payload.stations:
        station = create_or_update_station(db, report_payload)
        report = models.StationReport(
            bulletin_id=bulletin.id,
            station_id=station.id,
            Tmin_obs=report_payload.Tmin_obs,
            Tmax_obs=report_payload.Tmax_obs,
            temps_obs=report_payload.temps_obs,
            Tmin_prev=report_payload.Tmin_prev,
            Tmax_prev=report_payload.Tmax_prev,
            temps_prev=report_payload.temps_prev,
            interpretation_moore=report_payload.interpretation_moore,
            interpretation_dioula=report_payload.interpretation_dioula,
        )
        db.add(report)

    db.commit()

    refreshed = get_bulletin_or_404(bulletin.id, db)
    return bulletin_to_detail(refreshed)


@app.get("/bulletins", response_model=List[schemas.BulletinSummary])
def list_bulletins(
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(models.Bulletin).options(
        selectinload(models.Bulletin.station_reports)
    )

    if start_date:
        query = query.filter(models.Bulletin.date_bulletin >= start_date)
    if end_date:
        query = query.filter(models.Bulletin.date_bulletin <= end_date)

    bulletins = (
        query.order_by(models.Bulletin.date_bulletin.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [bulletin_to_summary(b) for b in bulletins]


@app.get("/bulletins/{bulletin_id}", response_model=schemas.BulletinDetail)
def get_bulletin(bulletin_id: int, db: Session = Depends(get_db)):
    bulletin = get_bulletin_or_404(bulletin_id, db)
    return bulletin_to_detail(bulletin)


@app.get(
    "/bulletins/{bulletin_id}/stations",
    response_model=List[schemas.StationReportOut],
)
def list_bulletin_reports(
    bulletin_id: int, db: Session = Depends(get_db)
):
    bulletin = get_bulletin_or_404(bulletin_id, db)
    return [report_to_schema(r) for r in bulletin.station_reports]


@app.delete("/bulletins/{bulletin_id}", response_model=schemas.DeleteResponse)
def delete_bulletin(bulletin_id: int, db: Session = Depends(get_db)):
    bulletin = get_bulletin_or_404(bulletin_id, db)
    db.delete(bulletin)
    db.commit()
    return schemas.DeleteResponse(
        deleted=True, detail=f"Bulletin {bulletin_id} supprimé"
    )


@app.post(
    "/stations",
    response_model=schemas.StationOut,
    status_code=status.HTTP_201_CREATED,
)
def create_station(payload: schemas.StationCreate, db: Session = Depends(get_db)):
    station = create_or_update_station(db, payload, allow_existing=False)
    db.commit()
    db.refresh(station)
    return station_to_schema(station)


@app.get("/stations", response_model=List[schemas.StationOut])
def list_stations(
    q: Optional[str] = Query(None, description="Filtrer par nom ou fragment"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(models.Station)
    if q:
        query = query.filter(models.Station.name.ilike(f"%{q}%"))

    stations = (
        query.order_by(models.Station.name.asc()).offset(offset).limit(limit).all()
    )

    station_ids = [s.id for s in stations]
    latest_reports = {}
    if station_ids:
        reports = (
            db.query(models.StationReport)
            .filter(models.StationReport.station_id.in_(station_ids))
            .order_by(
                models.StationReport.station_id.asc(),
                models.StationReport.created_at.desc(),
            )
            .all()
        )
        for report in reports:
            if report.station_id not in latest_reports:
                latest_reports[report.station_id] = report

    return [
        station_to_schema(s, latest_reports.get(s.id))
        for s in stations
    ]


@app.get("/stations/{station_id}", response_model=schemas.StationOut)
def get_station(station_id: int, db: Session = Depends(get_db)):
    station = get_station_or_404(station_id, db)
    latest_report = (
        db.query(models.StationReport)
        .filter(models.StationReport.station_id == station.id)
        .order_by(models.StationReport.created_at.desc())
        .first()
    )
    return station_to_schema(station, latest_report)


@app.patch("/stations/{station_id}", response_model=schemas.StationOut)
def update_station(
    station_id: int, payload: schemas.StationUpdate, db: Session = Depends(get_db)
):
    station = get_station_or_404(station_id, db)
    data = payload.dict(exclude_unset=True)

    if "name" in data and data["name"]:
        normalized = normalize_station_name(data["name"])
        duplicate = (
            db.query(models.Station)
            .filter(models.Station.normalized_name == normalized)
            .filter(models.Station.id != station.id)
            .first()
        )
        if duplicate:
            raise HTTPException(
                status_code=409,
                detail="Une autre station possède déjà ce nom.",
            )
        station.name = data["name"].strip()
        station.normalized_name = normalized

    for attr in ("latitude", "longitude", "x_rel", "y_rel"):
        if attr in data:
            setattr(station, attr, data[attr])

    db.commit()
    db.refresh(station)
    return station_to_schema(station)


@app.get(
    "/stations/{station_id}/reports",
    response_model=List[schemas.StationReportOut],
)
def list_station_reports(
    station_id: int,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    station = get_station_or_404(station_id, db)
    reports = (
        db.query(models.StationReport)
        .options(selectinload(models.StationReport.station))
        .filter(models.StationReport.station_id == station.id)
        .order_by(models.StationReport.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [report_to_schema(r) for r in reports]


@app.get("/stats/overview")
def stats_overview(db: Session = Depends(get_db)):
    bulletin_count = db.query(func.count(models.Bulletin.id)).scalar() or 0
    station_count = db.query(func.count(models.Station.id)).scalar() or 0
    report_count = db.query(func.count(models.StationReport.id)).scalar() or 0

    latest_bulletin = (
        db.query(models.Bulletin)
        .order_by(models.Bulletin.date_bulletin.desc())
        .first()
    )

    return {
        "bulletins": bulletin_count,
        "stations": station_count,
        "reports": report_count,
        "latest_bulletin": latest_bulletin.date_bulletin if latest_bulletin else None,
    }


@app.get("/exports/all-merged")
def get_all_merged_file():
    if not ALL_MERGED_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Fichier {ALL_MERGED_PATH} introuvable. Lancez merge_all_merged.py d'abord.",
        )
    try:
        data = json.loads(ALL_MERGED_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Impossible de lire {ALL_MERGED_PATH}: {exc}",
        ) from exc
    return data


@app.get("/evaluation/metrics")
def get_evaluation_metrics():
    if not EVAL_METRICS_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                f"Fichier {EVAL_METRICS_PATH} introuvable. "
                "Lancez evaluate_forecasts.py pour générer les métriques."
            ),
        )
    try:
        data = json.loads(EVAL_METRICS_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Impossible de lire {EVAL_METRICS_PATH}: {exc}",
        ) from exc
    return data


def resolve_merged_file(path: str) -> Path:
    if not path:
        raise HTTPException(status_code=400, detail="Paramètre 'path' obligatoire.")

    candidate = Path(path.strip())

    try:
        candidate = candidate.relative_to(MERGED_FILES_ROOT)
    except ValueError:
        if candidate.is_absolute():
            try:
                candidate = candidate.relative_to(BASE_DIR)
            except ValueError:
                pass
        if str(candidate).startswith("2024_temps_merged"):
            candidate = candidate.relative_to("2024_temps_merged")

    full_path = (MERGED_FILES_ROOT / candidate).resolve()
    root_resolved = MERGED_FILES_ROOT.resolve()
    if not str(full_path).startswith(str(root_resolved)):
        raise HTTPException(status_code=400, detail="Chemin hors du dossier autorisé.")
    return full_path


@app.get("/exports/merged-file")
def get_merged_file(path: str):
    full_path = resolve_merged_file(path)
    if not full_path.exists():
        raise HTTPException(status_code=404, detail=f"Fichier {path} introuvable.")
    try:
        content = json.loads(full_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Impossible de lire {path}: {exc}") from exc
    rel_path = str(full_path.relative_to(MERGED_FILES_ROOT))
    return {"path": rel_path, "content": content}


def run_pipeline():
    try:
        subprocess.run(["python", "meteo_scraper.py"], cwd=BASE_DIR, check=True)
        subprocess.run(
            ["python", "automate_pipeline.py", "--api-url", "http://127.0.0.1:8000"],
            cwd=BASE_DIR,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        print(f"[scraping] Erreur lors du scraping: {exc}")


@app.post("/scraping/start")
def start_scraping(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_pipeline)
    return {"status": "started", "detail": "Scraping déclenché sur le serveur."}
