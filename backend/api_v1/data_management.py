import io
import json
import logging
import re
import unicodedata
import uuid
import zipfile

import os
import re
import time
from datetime import datetime, timedelta

from pathlib import Path
from typing import Any, List, Optional, Union

from fastapi import APIRouter, UploadFile, File, BackgroundTasks, HTTPException, Request, Depends, Query, Path as ApiPath, Body
import threading
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, Field

from backend.api_v1.models import (
    ScrapeRequest, ScrapeResponse, ScrapeManifestResponse,
    UploadResponse, UploadJobResponse, UploadJobStatus,
    UploadBatchResponse, UploadBatchStatus
)
import backend.api_v1.core as core
from backend.api_v1.core import _ensure_services_ready, _ensure_db_ready, ErrorCode
from backend.api_v1.utils import (
    _resolve_scrape_output_dir,
    _sanitize_filename,
    _serialize_temperature_payload,
    extract_date_from_filename
)
from backend.modules.pdf_scrap import MeteoBurkinaScraper, ManifestStore, ScrapeConfig
from backend.modules.pdf_extractor import PDFExtractor
from backend.modules.temperature_extractor import TemperatureExtractor

from backend.modules.ai_vlm_extractor import AIVLMExtractor
from backend.modules.language_interpreter import LanguageInterpreter
import os


logger = logging.getLogger("anam.api")
router = APIRouter(tags=["data_management"])

_MONTHS_FR = {
    "janvier": 1,
    "fevrier": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "aout": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "decembre": 12,
}


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def _parse_bulletin_date(filename: str) -> Optional[str]:
    match = re.search(r"Bulletin_du_(\d{1,2})_([A-Za-z\u00c0-\u017f]+)_(\d{4})", filename)
    if not match:
        return None
    day_str, month_raw, year_str = match.groups()
    month_key = _strip_accents(month_raw).lower()
    month_num = _MONTHS_FR.get(month_key)
    if not month_num:
        return None
    try:
        return datetime(int(year_str), month_num, int(day_str)).strftime("%Y-%m-%d")
    except ValueError:
        return None


def _map_type_from_name(filename: str) -> Optional[str]:
    lowered = filename.lower()
    if "observed" in lowered or "observation" in lowered:
        return "observed"
    if "forecast" in lowered or "prevision" in lowered:
        return "forecast"
    return None


def _infer_bulletin_type_from_filename(filename: str) -> Optional[str]:
    lowered = filename.lower()
    if "forecast" in lowered or "prevision" in lowered or "prévision" in lowered:
        return "forecast"
    if "observed" in lowered or "observation" in lowered or "obs" in lowered:
        return "observation"
    return None


def _normalize_manual_map_type(value: str) -> Optional[str]:
    lowered = value.lower().strip()
    if lowered in {"observed", "observation", "obs"}:
        return "observation"
    if lowered in {"forecast", "prevision", "prev"}:
        return "forecast"
    return None


def _sanitize_source(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", value.strip())
    return cleaned.strip("_") or "manual"


class ManualMetricsStation(BaseModel):
    nom: Optional[str] = None
    tmin: Optional[float] = None
    tmax: Optional[float] = None
    weather_icon: Optional[str] = None


class ManualMetricsEntry(BaseModel):
    date: str = Field(..., min_length=8)
    mapType: str = Field(..., min_length=3)
    source: Optional[str] = None
    stations: List[ManualMetricsStation] = Field(default_factory=list)


class ManualMetricsIngestRequest(BaseModel):
    source: Optional[str] = None
    entries: List[ManualMetricsEntry] = Field(default_factory=list)


class ManualMetricsIngestResponse(BaseModel):
    inserted_bulletins: int
    updated_payloads: int
    skipped: int


@router.get("/json-metrics/files")
async def list_json_metrics_files():
    """Liste les fichiers JSON de métriques disponibles dans backend/json."""
    base_dir = (core.config.project_root / "json") if core.config else None
    if base_dir is None or not base_dir.exists():
        return {"files": [], "total": 0}

    files: List[dict] = []
    for json_path in sorted(base_dir.rglob("*.json")):
        try:
            stat = json_path.stat()
        except OSError:
            continue
        rel_path = json_path.relative_to(base_dir).as_posix()
        date_value = _parse_bulletin_date(json_path.name)
        files.append(
            {
                "path": rel_path,
                "name": json_path.name,
                "size_bytes": stat.st_size,
                "modified_at": datetime.utcfromtimestamp(stat.st_mtime).isoformat() + "Z",
                "date": date_value,
                "month": date_value[:7] if date_value else None,
                "year": int(date_value[:4]) if date_value else None,
                "map_type": _map_type_from_name(json_path.name),
            }
        )

    return {"files": files, "total": len(files)}


@router.get("/json-metrics/file")
async def get_json_metrics_file(path: str = Query(..., min_length=1)):
    """Retourne le contenu d'un fichier JSON de métriques."""
    base_dir = (core.config.project_root / "json") if core.config else None
    if base_dir is None:
        raise HTTPException(status_code=500, detail="Configuration indisponible.")

    base_dir = base_dir.resolve()
    target = (base_dir / path).resolve()
    if base_dir != target and base_dir not in target.parents:
        raise HTTPException(status_code=400, detail="Chemin invalide.")
    if target.suffix.lower() != ".json":
        raise HTTPException(status_code=400, detail="Seuls les fichiers JSON sont autorisés.")
    if not target.exists():
        raise HTTPException(status_code=404, detail="Fichier introuvable.")

    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Lecture JSON impossible: {exc}")

    return {"path": path, "data": payload}


@router.post("/json-metrics/ingest", response_model=ManualMetricsIngestResponse)
async def ingest_json_metrics(payload: ManualMetricsIngestRequest):
    """Insere des donnees JSON/CSV traitees dans la base."""
    _ensure_db_ready()
    if core.db_manager is None:
        raise HTTPException(status_code=500, detail="Base de donnees indisponible.")

    inserted = 0
    updated = 0
    skipped = 0
    source = payload.source or "manual"
    source_key = _sanitize_source(source)

    for index, entry in enumerate(payload.entries):
        try:
            datetime.strptime(entry.date, "%Y-%m-%d")
        except ValueError:
            skipped += 1
            continue

        bulletin_type = _normalize_manual_map_type(entry.mapType or "")
        if not bulletin_type:
            skipped += 1
            continue

        pdf_path = f"manual-import/{source_key}/{entry.date}-{bulletin_type}-{index}.json"
        if not core.db_manager.has_bulletin_for_pdf(pdf_path):
            core.db_manager.insert_bulletin(
                entry.date,
                bulletin_type,
                file_path=pdf_path,
                title=f"Manual import {entry.date} {bulletin_type}",
            )
            inserted += 1

        payload_stations: List[dict] = []
        for station in entry.stations:
            name = (station.nom or "").strip()
            if not name:
                continue
            station_payload = {"name": name}
            block = {
                "tmin": station.tmin,
                "tmax": station.tmax,
                "weather_condition": station.weather_icon,
            }
            if bulletin_type == "observation":
                station_payload["observation"] = block
            else:
                station_payload["prevision"] = block
            payload_stations.append(station_payload)

        payload_dict = {
            "date_bulletin": entry.date,
            "type": bulletin_type,
            "source": entry.source or source,
            "stations": payload_stations,
        }
        core.db_manager.upsert_bulletin_payload(pdf_path, payload_dict)
        updated += 1

    return ManualMetricsIngestResponse(
        inserted_bulletins=inserted,
        updated_payloads=updated,
        skipped=skipped,
    )

@router.post("/scrape", response_model=ScrapeResponse)
async def trigger_scrape(request: ScrapeRequest):
    """Déclencher le scraping des bulletins avec des filtres facultatifs."""
    _ensure_services_ready()

    if request.month is not None and not 1 <= request.month <= 12:
        raise HTTPException(status_code=400, detail="Le mois doit être compris entre 1 et 12.")
    if request.day is not None and not 1 <= request.day <= 31:
        raise HTTPException(status_code=400, detail="Le jour doit être compris entre 1 et 31.")
    if request.year is not None and request.year < 1900:
        raise HTTPException(status_code=400, detail="L'année doit être valide.")

    output_dir = _resolve_scrape_output_dir(request.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    scrape_config = ScrapeConfig()
    if request.max_size_mb is not None:
        scrape_config.max_size_mb = request.max_size_mb
    if request.retries is not None:
        scrape_config.retries = request.retries
    if request.backoff is not None:
        scrape_config.backoff = request.backoff
    if request.connect_timeout is not None:
        scrape_config.connect_timeout = request.connect_timeout
    if request.read_timeout is not None:
        scrape_config.read_timeout = request.read_timeout
    if request.verify_ssl is not None:
        scrape_config.verify_ssl = request.verify_ssl

    scraper = MeteoBurkinaScraper(output_dir=str(output_dir), config=scrape_config)
    summary = await run_in_threadpool(
        scraper.scrape_all,
        request.use_pagination,
        request.year,
        request.month,
        request.day,
        request.max_pages,
        request.max_bulletins,
        request.delay,
    )
    return summary


@router.get("/scrape/manifest", response_model=ScrapeManifestResponse)
async def get_scrape_manifest(output_dir: Optional[str] = None):
    """Retourner le manifeste de scraping pour inspection."""
    manifest_dir = _resolve_scrape_output_dir(output_dir)
    manifest_path = manifest_dir / "scrape_manifest.json"
    if not manifest_path.exists():
        return {
            "output_dir": str(manifest_dir.resolve()),
            "exists": False,
            "manifest": {"version": 1, "items": {}},
        }
    try:
        store = ManifestStore(manifest_path)
        return {
            "output_dir": str(manifest_dir.resolve()),
            "exists": True,
            "manifest": store.data,
        }
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": ErrorCode.INTERNAL_SERVER_ERROR.value,
                "message": f"Unable to read manifest: {exc}",
            },
        )


def _save_extracted_data_to_db(pdf_entry: dict):
    """Sauvegarde automatique des résultats d'extraction en base de données."""
    if not core.db_manager: return
    
    pdf_path_str = str(pdf_entry.get("pdf_path", ""))
    if not pdf_path_str: return
    pdf_name = Path(pdf_path_str).name
    
    # Si c'est un bulletin déjà éclaté par l'interprète (date et type au top-level)
    is_exploded = "date" in pdf_entry and "type" in pdf_entry and "data" in pdf_entry
    
    conn = core.db_manager.get_connection()
    try:
        # On prépare une liste de bulletins à sauvegarder (un PDF peut en contenir plusieurs)
        bulletins_to_process = []
        
        if is_exploded:
            # Cas d'un bulletin déjà traité individuellement
            bulletins_to_process.append({
                "date": pdf_entry["date"],
                "type": pdf_entry["type"],
                "maps": pdf_entry.get("data", []),
                "interp_fr": pdf_entry.get("interpretation_francais"),
                "interp_mo": pdf_entry.get("interpretation_moore"),
                "interp_di": pdf_entry.get("interpretation_dioula"),
                "payload": pdf_entry
            })
        else:
            # Cas d'un résultat global de PDF qu'il faut éclater selon la règle ANAM
            j_date = extract_date_from_filename(pdf_name) or datetime.now()
            for idx, map_entry in enumerate(pdf_entry.get("data", [])):
                if idx == 0:
                    actual_date_obj = j_date - timedelta(days=1)
                    map_type = 'observation'
                elif idx == 1:
                    actual_date_obj = j_date + timedelta(days=1)
                    map_type = 'forecast'
                else:
                    actual_date_obj = j_date + timedelta(days=idx)
                    map_type = 'forecast'
                
                actual_date_str = actual_date_obj.strftime("%Y-%m-%d")
                bulletins_to_process.append({
                    "date": actual_date_str,
                    "type": map_type,
                    "maps": [map_entry],
                    "interp_fr": pdf_entry.get("interpretation_francais"),
                    "interp_mo": pdf_entry.get("interpretation_moore"),
                    "interp_di": pdf_entry.get("interpretation_dioula"),
                    "payload": pdf_entry
                })

        for b in bulletins_to_process:
            actual_date_str = b["date"]
            map_type = b["type"]
            payload_str = json.dumps(b["payload"])
            interp_fr = b["interp_fr"]
            interp_mo = b["interp_mo"]
            interp_di = b["interp_di"]

            # 1. Upsert Bulletin
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM bulletins WHERE date = %s AND type = %s AND file_path = %s", 
                           (actual_date_str, map_type, pdf_path_str))
                row = cur.fetchone()
                if row:
                    bulletin_id = row[0]
                    cur.execute('''
                       UPDATE bulletins SET 
                           processed_at = CURRENT_TIMESTAMP, 
                           payload_json = %s,
                           interpretation_francais = %s,
                           interpretation_moore = %s,
                           interpretation_dioula = %s
                       WHERE id = %s
                    ''', (payload_str, interp_fr, interp_mo, interp_di, bulletin_id))
                else:
                    cur.execute('''
                        INSERT INTO bulletins (date, type, file_path, title, processed_at, payload_json, interpretation_francais, interpretation_moore, interpretation_dioula)
                        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, %s, %s, %s, %s)
                        RETURNING id
                    ''', (actual_date_str, map_type, pdf_path_str, f"{pdf_name} - {map_type.capitalize()}", payload_str, interp_fr, interp_mo, interp_di))
                    bulletin_id = cur.fetchone()[0]
                conn.commit()
            
            # 2. Insert Weather Data
            for map_entry in b["maps"]:
                temps = map_entry.get("temperatures", [])
                for t in temps:
                    st_name = t.get("name")
                    if not st_name: continue
                    
                    st_id = core.db_manager.insert_station(st_name, None, None)
                    tmin = float(t.get("tmin")) if t.get("tmin") is not None else None
                    tmax = float(t.get("tmax")) if t.get("tmax") is not None else None
                    cond = t.get("weather_condition")
                    
                    with conn.cursor() as cur:
                        cur.execute("DELETE FROM weather_data WHERE bulletin_id = %s AND station_id = %s", (bulletin_id, st_id))
                        cur.execute('''
                           INSERT INTO weather_data (bulletin_id, station_id, tmin, tmax, weather_condition)
                           VALUES (%s, %s, %s, %s, %s)
                        ''', (bulletin_id, st_id, tmin, tmax, cond))
                    conn.commit()
                    
    except Exception as e:
        conn.rollback()
        logging.error(f"❌ Erreur auto-save pour {pdf_name}: {e}")

@router.post("/upload-bulletin", response_model=Union[UploadResponse, UploadJobResponse])
async def upload_bulletin(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    async_job: bool = Query(False, alias="async"),
):
    """Téléverser un PDF de bulletin et exécuter l'extraction de température."""
    _ensure_services_ready()

    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail={
                "code": ErrorCode.UPLOAD_INVALID.value,
                "message": "Nom de fichier manquant.",
            },
        )
    if file.content_type and "pdf" not in file.content_type.lower():
        raise HTTPException(
            status_code=400,
            detail={
                "code": ErrorCode.UPLOAD_INVALID.value,
                "message": "Le fichier doit être un PDF.",
            },
        )

    assert core.config is not None
    target_dir = core.config.pdf_directory
    target_dir.mkdir(parents=True, exist_ok=True)
    filename = _sanitize_filename(file.filename)
    target_path = target_dir / filename

    data = await file.read()
    if not data:
        raise HTTPException(
            status_code=400,
            detail={
                "code": ErrorCode.UPLOAD_EMPTY.value,
                "message": "Le fichier est vide.",
            },
        )

    try:
        with open(target_path, "wb") as buffer:
            buffer.write(data)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": ErrorCode.UPLOAD_FAILED.value,
                "message": f"Impossible de sauvegarder le PDF : {exc}",
            },
        )


    def _enqueue_job(job_id: str, filename_value: str, pdf_path_value: str):
        assert core.db_manager is not None
        ticker_stop = threading.Event()

        def progress_callback(current_results, *args, **kwargs):
            # Sérialisation et mise à jour DB pour affichage temps réel
            try:
                # Récupération flexible du message/progrès (2ème argument positionnel)
                message = args[0] if args else kwargs.get("message")
                
                # 1. Détermination du progrès
                current_progress = None
                if isinstance(current_results, (int, float)):
                    current_progress = int(current_results)
                    # Si on n'a que le progrès, on s'arrête là (pas de data à sérialiser)
                    core.db_manager.update_job(job_id, progress=min(99, current_progress))
                    return
                
                if isinstance(message, (int, float)):
                    current_progress = int(message)
                
                # 2. Sérialisation des data (si c'est une liste de résultats)
                if isinstance(current_results, list):
                    partial_serialized = _serialize_temperature_payload(current_results)
                    payload = {
                        "filename": filename_value,
                        "pdf_path": pdf_path_value,
                        "temperatures": partial_serialized,
                    }
                    
                    # 3. Calcul du progrès si non fourni
                    if current_progress is None:
                        done_maps = len(current_results[0].get("data", [])) if current_results and "data" in current_results[0] else 0
                        current_progress = 40 + (done_maps * 22)
                    
                    core.db_manager.update_job(job_id, status="running", result=payload, progress=min(99, current_progress))
            except Exception as e:
                logging.error(f"Error in single job progress callback: {e}")

        def job_runner():
            def job_ticker():
                while not ticker_stop.is_set():
                    for _ in range(20):
                        if ticker_stop.is_set(): return
                        time.sleep(1)
                    try:
                        job = core.db_manager.get_job(job_id)
                        if not job or job.get("status") != "running": break
                        curr_p = job.get("progress", 0)
                        if 40 <= curr_p < 84:
                            core.db_manager.update_job(job_id, progress=min(84, curr_p + 1))
                        elif 90 <= curr_p < 99:
                            core.db_manager.update_job(job_id, progress=min(99, curr_p + 1))
                    except: pass

            ticker_thread = threading.Thread(target=job_ticker, daemon=True)
            ticker_thread.start()

            try:
                core.db_manager.update_job(job_id, status="running", progress=10)
                pdf_extractor = PDFExtractor(core.config.pdf_directory, core.config.output_directory)
                pdf_result = pdf_extractor.process_single_pdf(target_path)
                if not pdf_result: raise RuntimeError("Traitement PDF impossible.")
                
                core.db_manager.update_job(job_id, progress=40)
                if os.getenv("AI_METHOD") == "QWEN":
                    ai_extractor = AIVLMExtractor()
                    temperatures_raw = ai_extractor.extract_temperatures([pdf_result], progress_callback=progress_callback)
                else:
                    temp_extractor = TemperatureExtractor(roi_config_path=core.config.roi_config_path)
                    temperatures_raw = temp_extractor.extract_temperatures([pdf_result])
                
                temperatures = _serialize_temperature_payload(temperatures_raw)
                core.db_manager.update_job(job_id, progress=85)
                try:
                    interpreter = LanguageInterpreter.get_shared(core.db_manager)
                    interpreted_results = interpreter.generate_interpretations(temperatures)
                    core.db_manager.update_job(job_id, progress=92)
                except Exception as interp_exc:
                    logging.error(f"Interpretation failed: {interp_exc}")
                    interpreted_results = temperatures

                try:
                    for pdf_res in interpreted_results:
                        _save_extracted_data_to_db(pdf_res)
                    try:
                        from backend.modules.forecast_evaluator import ForecastEvaluator
                        evaluator = ForecastEvaluator(core.db_manager)
                        evaluator.evaluate_forecasts()
                        evaluator.aggregate_monthly_metrics()
                        evaluator.calculate_monthly_metrics_direct()
                        evaluator.calculate_station_monthly_metrics()
                    except: pass
                except: pass

                result = {"filename": filename_value, "pdf_path": pdf_path_value, "temperatures": interpreted_results}
                core.db_manager.update_job(job_id, status="success", result=result, progress=100)
            except Exception as exc:
                core.db_manager.update_job(job_id, status="error", error_message=str(exc))
            finally:
                ticker_stop.set()

        background_tasks.add_task(run_in_threadpool, job_runner)

    if async_job:
        assert core.db_manager is not None
        job_id = str(uuid.uuid4())
        core.db_manager.create_job(
            job_id,
            "upload_bulletin",
            {"filename": filename, "pdf_path": str(target_path)},
        )
        _enqueue_job(job_id, filename, str(target_path))
        response = {
            "job_id": job_id,
            "status": "pending",
            "filename": filename,
            "pdf_path": str(target_path),
        }
        return JSONResponse(content=response, status_code=202)

    try:
        temperatures = await run_in_threadpool(extraction_task)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": ErrorCode.OCR_FAILED.value,
                "message": f"Échec de l'extraction : {exc}",
            },
        )

    return {
        "filename": filename,
        "pdf_path": str(target_path),
        "temperatures": temperatures,
    }


@router.post("/upload-bulletins", response_model=UploadBatchResponse)
async def upload_bulletins(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
):
    """Téléverser plusieurs bulletins (PDF ou ZIP) et les traiter de manière asynchrone."""
    _ensure_services_ready()
    assert core.config is not None and core.db_manager is not None

    batch_id = str(uuid.uuid4())
    jobs: List[UploadJobResponse] = []
    collected_paths: List[tuple[str, str]] = []

    def _save_bytes(filename_value: str, data: bytes) -> Optional[str]:
        if not data:
            return None
        target_dir = core.config.pdf_directory
        target_dir.mkdir(parents=True, exist_ok=True)
        filename_clean = _sanitize_filename(filename_value)
        target_path = target_dir / filename_clean
        try:
            with open(target_path, "wb") as buffer:
                buffer.write(data)
        except Exception:
            return None
        return str(target_path)

    for upload in files:
        if not upload.filename:
            continue
        raw = await upload.read()
        name_lower = upload.filename.lower()
        if name_lower.endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                    for member in archive.infolist():
                        if member.is_dir():
                            continue
                        member_name = Path(member.filename).name
                        if not member_name.lower().endswith(".pdf"):
                            continue
                        with archive.open(member) as handle:
                            content = handle.read()
                        saved = _save_bytes(member_name, content)
                        if saved:
                            collected_paths.append((member_name, saved))
            except Exception as exc:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "code": ErrorCode.UPLOAD_INVALID.value,
                        "message": f"Invalid zip archive: {exc}",
                    },
                )
        else:
            if upload.content_type and "pdf" not in upload.content_type.lower() and not name_lower.endswith(".pdf"):
                continue
            saved = _save_bytes(upload.filename, raw)
            if saved:
                collected_paths.append((upload.filename, saved))

    if not collected_paths:
        raise HTTPException(
            status_code=400,
            detail={
                "code": ErrorCode.UPLOAD_EMPTY.value,
                "message": "No PDF files to process.",
            },
        )

    # Create batch job first to avoid race condition with background tasks
    core.db_manager.create_job(
        batch_id,
        "upload_batch",
        {"job_ids": [], "total": 0}, 
    )

    job_ids: List[str] = []
    for original_name, pdf_path_value in collected_paths:
        job_id = str(uuid.uuid4())
        job_ids.append(job_id)
        filename_value = Path(pdf_path_value).name
        core.db_manager.create_job(
            job_id,
            "upload_bulletin",
            {"filename": filename_value, "pdf_path": pdf_path_value, "batch_id": batch_id},
        )
        def _make_job_runner(job_id_value: str, filename_value: str, pdf_path_value: str):
            ticker_stop = threading.Event()
            def _run():
                def job_ticker():
                    while not ticker_stop.is_set():
                        for _ in range(20):
                            if ticker_stop.is_set(): return
                            time.sleep(1)
                        try:
                            job = core.db_manager.get_job(job_id_value)
                            if not job or job.get("status") != "running": break
                            curr_p = job.get("progress", 0)
                            if 40 <= curr_p < 84:
                                core.db_manager.update_job(job_id_value, progress=min(84, curr_p + 1))
                            elif 90 <= curr_p < 99:
                                core.db_manager.update_job(job_id_value, progress=min(99, curr_p + 1))
                        except: pass
                
                ticker_thread = threading.Thread(target=job_ticker, daemon=True)
                ticker_thread.start()

                try:
                    batch_job = core.db_manager.get_job(batch_id) if batch_id else None
                    if batch_job and batch_job.get("status") == "canceled":
                        core.db_manager.update_job(job_id_value, status="canceled", error_message="Batch canceled.")
                        return
                    core.db_manager.update_job(job_id_value, status="running", progress=10)
                    pdf_extractor = PDFExtractor(core.config.pdf_directory, core.config.output_directory)
                    pdf_result = pdf_extractor.process_single_pdf(Path(pdf_path_value))
                    if not pdf_result: raise RuntimeError("Traitement PDF impossible.")
                    
                    core.db_manager.update_job(job_id_value, progress=40)
                    def _partial_progress_cb(current_results, *args, **kwargs):
                        try:
                            # L'extracteur envoie (results, overall_pct) ou (pct, message)
                            # Récupération du pourcentage depuis le 2ème argument
                            overall_pct = args[0] if args else kwargs.get("message")
                            
                            current_progress = None
                            
                            # Si le premier arg est un nombre, c'est le progrès direct
                            if isinstance(current_results, (int, float)):
                                current_progress = int(current_results)
                            # Si le second arg est un nombre (overall_pct), on l'utilise
                            elif isinstance(overall_pct, (int, float)):
                                # Mapper 0-100% de l'extracteur vers 40-84% du job global
                                current_progress = 40 + int(overall_pct * 0.44)
                            
                            if isinstance(current_results, list):
                                partial_serialized = _serialize_temperature_payload(current_results)
                                partial_result = {"filename": filename_value, "pdf_path": pdf_path_value, "temperatures": partial_serialized}
                                
                                if current_progress is None:
                                    # Fallback: calculer depuis le nombre d'éléments
                                    done_maps = len(current_results[0].get("data", [])) if current_results and "data" in current_results[0] else 0
                                    current_progress = 40 + (done_maps * 22)
                                
                                core.db_manager.update_job(job_id_value, result=partial_result, progress=min(84, current_progress))
                            elif current_progress is not None:
                                core.db_manager.update_job(job_id_value, progress=min(84, current_progress))
                        except Exception as e:
                            logging.error(f"Error in partial progress callback: {e}")


                    if os.getenv("AI_METHOD") == "QWEN":
                        ai_extractor = AIVLMExtractor()
                        temperatures = ai_extractor.extract_temperatures([pdf_result], progress_callback=_partial_progress_cb)
                    else:
                        temp_extractor = TemperatureExtractor(roi_config_path=core.config.roi_config_path)
                        temperatures = temp_extractor.extract_temperatures([pdf_result])
                    
                    core.db_manager.update_job(job_id_value, progress=85)
                    serialized_temps = _serialize_temperature_payload(temperatures)

                    try:
                        interpreter = LanguageInterpreter.get_shared(core.db_manager)
                        interpreted_results = interpreter.generate_interpretations(serialized_temps)
                        core.db_manager.update_job(job_id_value, progress=92)
                    except Exception as interp_exc:
                        logging.error(f"Interpretation failed: {interp_exc}")
                        interpreted_results = serialized_temps

                    try:
                        for pdf_res in interpreted_results:
                            _save_extracted_data_to_db(pdf_res)
                        try:
                            from backend.modules.forecast_evaluator import ForecastEvaluator
                            evaluator = ForecastEvaluator(core.db_manager)
                            evaluator.evaluate_forecasts()
                            evaluator.aggregate_monthly_metrics()
                            evaluator.calculate_monthly_metrics_direct()
                            evaluator.calculate_station_monthly_metrics()
                        except: pass
                    except: pass

                    result = {"filename": filename_value, "pdf_path": pdf_path_value, "temperatures": interpreted_results}
                    core.db_manager.update_job(job_id_value, status="success", result=result, progress=100)
                except Exception as exc:
                    core.db_manager.update_job(job_id_value, status="error", error_message=str(exc))
                finally:
                    ticker_stop.set()
            return _run

        background_tasks.add_task(
            run_in_threadpool,
            _make_job_runner(job_id, filename_value, pdf_path_value),
        )
        jobs.append(
            {
                "job_id": job_id,
                "status": "pending",
                "filename": filename_value,
                "pdf_path": pdf_path_value,
            }
        )

    core.db_manager.update_job(
        batch_id,
        payload={"job_ids": job_ids, "total": len(job_ids)},
    )

    def _batch_progress_runner():
        while True:
            time.sleep(5)
            try:
                sub_jobs = core.db_manager.get_jobs(job_ids)
                if not sub_jobs: break
                
                avg_progress = sum(j.get('progress', 0) for j in sub_jobs) // len(sub_jobs)
                status = "running"
                
                completed = [j for j in sub_jobs if j.get('status') in ('success', 'error', 'canceled')]
                if len(completed) == len(sub_jobs):
                    # Check if any error
                    has_error = any(j.get('status') == 'error' for j in sub_jobs)
                    core.db_manager.update_job(batch_id, status="success" if not has_error else "error", progress=100)
                    break
                
                core.db_manager.update_job(batch_id, status=status, progress=avg_progress)
            except:
                pass

    background_tasks.add_task(run_in_threadpool, _batch_progress_runner)

    return {
        "batch_id": batch_id,
        "total": len(jobs),
        "jobs": jobs,
    }


@router.get("/upload-bulletin/jobs/{job_id}", response_model=UploadJobStatus)
async def get_upload_job(job_id: str = ApiPath(..., min_length=1)):
    _ensure_db_ready()
    assert core.db_manager is not None
    job = core.db_manager.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=404,
            detail={
                "code": ErrorCode.RESOURCE_NOT_FOUND.value,
                "message": "Job not found.",
            },
        )
    payload = job.get("payload") or {}
    result = job.get("result")
    response = {
        "job_id": job.get("id"),
        "status": job.get("status"),
        "filename": payload.get("filename"),
        "pdf_path": payload.get("pdf_path"),
        "result": result,
        "progress": job.get("progress", 0),
        "error_message": job.get("error_message"),
        "created_at": job.get("created_at").isoformat() if job.get("created_at") else None,
        "updated_at": job.get("updated_at").isoformat() if job.get("updated_at") else None,
    }
    return response


@router.post("/upload-bulletin/jobs/{job_id}/retry", response_model=UploadJobStatus)
async def retry_upload_job(
    background_tasks: BackgroundTasks,
    job_id: str = ApiPath(..., min_length=1)
):
    """Relancer l'extraction pour les éléments échoués (NP) d'un job."""
    _ensure_db_ready()
    assert core.db_manager is not None
    job = core.db_manager.get_job(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    if job.get("status") not in ["success", "partial", "error"]:
         raise HTTPException(status_code=400, detail="Le job doit être terminé pour être relancé/réparé.")

    # On marque le job comme "running" TOUT DE SUITE pour éviter les race conditions avec le frontend
    core.db_manager.update_job(job_id, status="running")

    # On lance la réparation en background
    def repair_runner():
        try:
            # Récupération résultat actuel
            current_result = job.get("result")
            if not current_result or "temperatures" not in current_result:
                raise ValueError("Pas de résultats précédents à réparer.")

            temperatures = current_result["temperatures"]

            if os.getenv("AI_METHOD") == "QWEN":
                ai_extractor = AIVLMExtractor()
                
                # Correction des chemins d'images : le JSON stocké n'a que le nom de fichier
                # Il faut reconstruire le chemin absolu pour que cv2.imread puisse lire l'image.
                import copy
                temps_for_repair = copy.deepcopy(temperatures)
                
                output_root = core.config.output_directory if core.config else Path("bulletins_meteo")
                # Les images sont stockées dans temp/pdf_images par le PDFExtractor
                possible_dirs = [
                    output_root / "temp" / "pdf_images",
                    output_root,
                    output_root / "temp" / "maps"
                ]
                
                for pdf_entry in temps_for_repair:
                    for map_entry in pdf_entry.get("data", []):
                        img_name = map_entry.get("image_path")
                        if img_name:
                             found = False
                             # On cherche dans les dossiers possibles
                             for d in possible_dirs:
                                 candidate = d / img_name
                                 if candidate.exists():
                                     map_entry["image_path"] = str(candidate)
                                     found = True
                                     break
                             
                             if not found:
                                 # Cas extrême: chemin déjà absolu ou relatif courant ?
                                 if Path(img_name).exists():
                                      map_entry["image_path"] = str(Path(img_name).resolve())
                                 else:
                                      # On laisse tel quel, le logger de AIVLMExtractor signalera l'erreur
                                      pass

                # On tente de réparer (extraire les NPs)
                repaired_temps = ai_extractor.repair_results(temps_for_repair)
                
                # Mise à jour
                current_result["temperatures"] = _serialize_temperature_payload(repaired_temps)
                core.db_manager.update_job(job_id, status="success", result=current_result)
            else:
                # Pas de réparation supportée pour l'algo classique pour l'instant
                core.db_manager.update_job(job_id, status="success") # No-op

        except Exception as exc:
            core.db_manager.update_job(job_id, status="error", error_message=f"Echec réparation: {exc}")

    background_tasks.add_task(run_in_threadpool, repair_runner)

    return {
        "job_id": job_id,
        "status": "running"
    }


@router.post("/upload-bulletin/feedback")
async def submit_feedback(
    job_id: str = Body(..., embed=True),
    corrections: List[dict] = Body(..., embed=True) 
):
    """Enregistre les corrections utilisateur pour amélioration future ET mise à jour de la BDD."""
    # 1. Sauvegarde pour R&D (JSON)
    feedback_dir = core.config.project_root.parent / "datasets" / "feedback"
    feedback_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = int(time.time())
    filename = f"feedback_{timestamp}_{job_id}.json"
    
    path = feedback_dir / filename
    try:
        data = {
            "job_id": job_id,
            "timestamp": timestamp,
            "corrections": corrections
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"💾 Feedback utilisateur enregistré : {path}")

        # 2. Sauvegarde Opérationnelle (Postgres)
        _ensure_db_ready()
        conn = core.db_manager.get_connection()
        
        for pdf_entry in corrections:
            try:
                pdf_path_str = pdf_entry.get("pdf_path", "")
                if not pdf_path_str: continue
                
                pdf_name = Path(pdf_path_str).name
                j_date = extract_date_from_filename(pdf_name) or datetime.now()
                
                # --- Update each map with ANAM date rules ---
                for idx, map_entry in enumerate(pdf_entry.get("data", [])):
                     if idx == 0:
                         actual_date_obj = j_date - timedelta(days=1)
                         map_type = 'observation'
                     elif idx == 1:
                         actual_date_obj = j_date + timedelta(days=1)
                         map_type = 'forecast'
                     else:
                         actual_date_obj = j_date + timedelta(days=idx)
                         map_type = 'forecast'
                     
                     actual_date_str = actual_date_obj.strftime("%Y-%m-%d")
                
                     # --- Upsert Bulletin per card ---
                     bulletin_id = None
                     with conn.cursor() as cur:
                         cur.execute("SELECT id FROM bulletins WHERE date = %s AND type = %s AND file_path = %s", 
                                    (actual_date_str, map_type, pdf_path_str))
                         row = cur.fetchone()
                         if row:
                             bulletin_id = row[0]
                             cur.execute("UPDATE bulletins SET processed_at = CURRENT_TIMESTAMP WHERE id = %s", (bulletin_id,))
                         else:
                             cur.execute('''
                                 INSERT INTO bulletins (date, type, file_path, title, processed_at)
                                 VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                                 RETURNING id
                             ''', (actual_date_str, map_type, pdf_path_str, f"{pdf_name} - {map_type.capitalize()} (Feedback)"))
                             bulletin_id = cur.fetchone()[0]
                     conn.commit()
                     
                     # --- Insert Data for this card ---
                     temps = map_entry.get("temperatures", [])
                     for t in temps:
                         st_name = t.get("name")
                         if not st_name: continue
                         
                         st_id = core.db_manager.insert_station(st_name, None, None)
                         
                         tmin = t.get("tmin")
                         if tmin is not None: tmin = float(tmin)
                         tmax = t.get("tmax")
                         if tmax is not None: tmax = float(tmax)
                         cond = t.get("weather_condition")
                         
                         # Overwrite Weather Data
                         with conn.cursor() as cur:
                             cur.execute("DELETE FROM weather_data WHERE bulletin_id = %s AND station_id = %s", (bulletin_id, st_id))
                             cur.execute('''
                                INSERT INTO weather_data (bulletin_id, station_id, tmin, tmax, weather_condition)
                                VALUES (%s, %s, %s, %s, %s)
                             ''', (bulletin_id, st_id, tmin, tmax, cond))
                         conn.commit()

            except Exception as pdf_exc:
                logger.error(f"Erreur processing PDF feedback {pdf_entry.get('pdf_path')}: {pdf_exc}")
                conn.rollback()
                # On continue pour les autres PDFs

        return {"status": "success", "message": "Merci ! Données validées et sauvegardées."}

    except Exception as e:
        logger.error(f"❌ Erreur générale sauvegarde feedback: {e}")
        # On retourne une erreur explicite
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/upload-bulletins/batches/{batch_id}", response_model=UploadBatchStatus)
async def get_upload_batch(batch_id: str = ApiPath(..., min_length=1)):
    _ensure_db_ready()
    assert core.db_manager is not None
    batch = core.db_manager.get_job(batch_id)
    if not batch or batch.get("job_type") != "upload_batch":
        raise HTTPException(
            status_code=404,
            detail={
                "code": ErrorCode.RESOURCE_NOT_FOUND.value,
                "message": "Batch not found.",
            },
        )
    payload = batch.get("payload") or {}
    job_ids = payload.get("job_ids") or []
    jobs_raw = core.db_manager.get_jobs(job_ids)
    jobs_map = {job["id"]: job for job in jobs_raw}
    jobs: List[UploadJobStatus] = []
    counts = {"pending": 0, "running": 0, "success": 0, "error": 0, "canceled": 0}
    for job_id in job_ids:
        job = jobs_map.get(job_id)
        if not job:
            continue
        job_payload = job.get("payload") or {}
        status = job.get("status") or "pending"
        if status in counts:
            counts[status] += 1
        else:
            counts["pending"] += 1
        jobs.append(
            {
                "job_id": job_id,
                "status": status,
                "filename": job_payload.get("filename"),
                "pdf_path": job_payload.get("pdf_path"),
                "result": job.get("result"),
                "error_message": job.get("error_message"),
                "created_at": job.get("created_at").isoformat() if job.get("created_at") else None,
                "updated_at": job.get("updated_at").isoformat() if job.get("updated_at") else None,
            }
        )

    overall_status = "pending"
    batch_status = batch.get("status")
    if batch_status == "canceled":
        overall_status = "canceled"
    if counts["running"] > 0:
        overall_status = "running"
    elif counts["error"] > 0 and counts["success"] == 0:
        overall_status = "error"
    elif counts["success"] == len(job_ids):
        overall_status = "success"
    elif counts["error"] > 0:
        overall_status = "partial"

    return {
        "batch_id": batch_id,
        "status": overall_status,
        "total": len(job_ids),
        "pending": counts["pending"],
        "running": counts["running"],
        "success": counts["success"],
        "error": counts["error"],
        "canceled": counts["canceled"],
        "jobs": jobs,
    }


@router.get("/upload-bulletins/jobs")
async def list_upload_jobs(limit: int = 50, job_type: str = None):
    _ensure_db_ready()
    assert core.db_manager is not None
    jobs = core.db_manager.list_jobs(limit=limit, job_type=job_type)
    # Filter or format if needed
    formatted = []
    for j in jobs:
        formatted.append({
            "job_id": j["id"],
            "job_type": j["job_type"],
            "status": j["status"],
            "created_at": j["created_at"].isoformat() if j["created_at"] else None,
            "updated_at": j["updated_at"].isoformat() if j["updated_at"] else None,
            "error_message": j["error_message"],
            "progress": j.get("progress", 0),
            "filename": j.get("payload", {}).get("filename") if j.get("payload") else None,
            "result": j.get("result")
        })
    return formatted


@router.delete("/upload-bulletins/jobs/{job_id}")
async def delete_upload_job(job_id: str):
    _ensure_db_ready()
    assert core.db_manager is not None
    core.db_manager.delete_job(job_id)
    return {"status": "deleted", "job_id": job_id}


@router.post("/upload-bulletins/batches/{batch_id}/stop")
async def stop_upload_batch(batch_id: str = ApiPath(..., min_length=1)):
    _ensure_db_ready()
    assert core.db_manager is not None
    batch = core.db_manager.get_job(batch_id)
    if not batch or batch.get("job_type") != "upload_batch":
        raise HTTPException(
            status_code=404,
            detail={
                "code": ErrorCode.RESOURCE_NOT_FOUND.value,
                "message": "Batch not found.",
            },
        )
    core.db_manager.update_job(batch_id, status="canceled", error_message="Canceled by user.")
    payload = batch.get("payload") or {}
    job_ids = payload.get("job_ids") or []
    jobs = core.db_manager.get_jobs(job_ids)
    for job in jobs:
        if job.get("status") == "pending":
            core.db_manager.update_job(job.get("id"), status="canceled", error_message="Batch canceled.")
    return {"batch_id": batch_id, "status": "canceled"}


@router.get("/files/{category}/{filename}")
async def serve_file(category: str, filename: str):
    """Serve files from temp directories (maps, pdf_images)."""
    if not core.config:
        raise HTTPException(status_code=500, detail="Config not initialized")
    
    if ".." in filename or "/" in filename or "\\" in filename:
         raise HTTPException(status_code=400, detail="Invalid filename")

    base_path = core.config.output_directory / "temp"
    if category == "maps":
        file_path = base_path / "maps" / filename
    elif category == "pdf_images":
        file_path = base_path / "pdf_images" / filename
    else:
        raise HTTPException(status_code=400, detail="Invalid category")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(file_path)


@router.post("/maintenance/sync-history")
async def sync_job_history(background_tasks: BackgroundTasks):
    """Récupère les résultats des jobs passés pour peupler la base de données."""
    def _sync_task():
        _ensure_db_ready()
        conn = core.db_manager.get_connection()
        count = 0
        try:
            with conn.cursor() as cur:
                # Récupérer les jobs réussis avec un résultat
                cur.execute("SELECT result FROM jobs WHERE type = 'upload_bulletin' AND status = 'success'")
                rows = cur.fetchall()
                
                logger.info(f"Synchronisation: {len(rows)} jobs trouvés.")
                
                for row in rows:
                    result = row[0]
                    if not result: continue
                    
                    if isinstance(result, str):
                        try: result = json.loads(result)
                        except: continue
                    
                    temps = result.get("temperatures", [])
                    if not temps: continue
                    
                    for pdf_res in temps:
                        try:
                            _save_extracted_data_to_db(pdf_res)
                            count += 1
                        except Exception as e:
                           logger.error(f"Sync error for entry: {e}")
            logger.info(f"Historique synchronisé: {count} bulletins traités/mis à jour.")
        except Exception as e:
            logger.error(f"Global sync error: {e}")
    
    background_tasks.add_task(run_in_threadpool, _sync_task)
    return {"message": "Synchronisation de l'historique lancée en arrière-plan."}


@router.get("/json-metrics/files")
async def list_json_metrics_files():
    """Liste tous les fichiers JSON disponibles dans le dossier racine."""
    if not core.config:
         raise HTTPException(status_code=500, detail="Config not initialized")

    base_dir = core.config.output_directory
    if not base_dir.exists():
        return {"files": []}

    files = []
    for f in base_dir.glob("*.json"):
        if f.name in ["scrape_manifest.json", "rois.json"]:
            continue
        try:
            stat = f.stat()
            # Attempt to parse basic info
            date_bulletin = None
            map_type = None
            try:
                with open(f, "r", encoding="utf-8") as handle:
                    # Read only start to guess or whole if small
                    data = json.load(handle)
                    date_bulletin = data.get("date_bulletin")
                    map_type = data.get("map_type")
            except:
                pass

            files.append({
                "name": f.name,
                "path": f.name,
                "size": stat.st_size,
                "last_modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "date": date_bulletin,
                "map_type": map_type
            })
        except Exception as e:
            logger.warning(f"Error reading json file {f}: {e}")

    # Sort most recent first
    files.sort(key=lambda x: x["last_modified"], reverse=True)
    return {"files": files}


@router.get("/json-metrics/file")
async def get_json_metrics_file(path: str):
    """Récupère le contenu d'un fichier JSON spécifique."""
    if not core.config:
         raise HTTPException(status_code=500, detail="Config not initialized")

    if ".." in path or "/" in path or "\\" in path:
         raise HTTPException(status_code=400, detail="Invalid filename")

    target = core.config.output_directory / path
    if not target.exists():
        raise HTTPException(status_code=404, detail="File not found")

    try:
        with open(target, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {"path": path, "data": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {e}")
