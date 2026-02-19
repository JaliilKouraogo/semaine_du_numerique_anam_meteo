import json
import logging


from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool

from backend.api_v1.models import (
    EvaluationMetrics,
    MetricsListResponse,
    MetricsRecalculateRequest
)
import backend.api_v1.core as core
from backend.api_v1.core import _ensure_db_ready, ErrorCode
from backend.api_v1.utils import _cache_get, _cache_set, _cache_clear
from backend.modules.forecast_evaluator import ForecastEvaluator

logger = logging.getLogger("anam.api")
router = APIRouter(tags=["metrics"])

@router.get("/metrics/{date}", response_model=EvaluationMetrics)
async def get_evaluation_metrics(date: str):
    """Retourner les métriques d'évaluation stockées dans la base de données pour une date donnée."""
    _ensure_db_ready()
    cache_key = f"metrics:detail:{date}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    
    assert core.db_manager is not None
    row = core.db_manager.get_evaluation_metrics_by_date(date)
    
    if not row:
        return {
            "date": date,
            "forecast_reference_date": None,
            "mae_tmin": None,
            "mae_tmax": None,
            "rmse_tmin": None,
            "rmse_tmax": None,
            "bias_tmin": None,
            "bias_tmax": None,
            "accuracy_weather": 0,
            "precision_weather": 0,
            "recall_weather": 0,
            "f1_score_weather": 0,
            "confusion_matrix": {},
            "sample_size": 0,
        }

    # confusion is expected to be a string in some DB versions, check if it needs parsing
    confusion = row.get("weather_confusion")
    if isinstance(confusion, str):
        confusion = json.loads(confusion)

    payload = {
        "id": row.get("id"),
        "date": row.get("bulletin_date"),
        "forecast_reference_date": row.get("forecast_reference_date"),
        "mae_tmin": row.get("mae_tmin"),
        "mae_tmax": row.get("mae_tmax"),
        "rmse_tmin": row.get("rmse_tmin"),
        "rmse_tmax": row.get("rmse_tmax"),
        "bias_tmin": row.get("bias_tmin"),
        "bias_tmax": row.get("bias_tmax"),
        "accuracy_weather": row.get("accuracy_weather"),
        "precision_weather": row.get("precision_weather"),
        "recall_weather": row.get("recall_weather"),
        "f1_score_weather": row.get("f1_score_weather"),
        "confusion_matrix": confusion,
        "sample_size": row.get("sample_size"),
        "observation_file_path": row.get("observation_file_path"),
        "forecast_file_path": row.get("forecast_file_path"),
        "observation_title": row.get("observation_title"),
        "forecast_title": row.get("forecast_title"),
        "calculated_at": row.get("calculated_at").isoformat() if hasattr(row.get("calculated_at"), 'isoformat') else row.get("calculated_at"),
    }
    _cache_set(cache_key, payload)
    return payload


@router.get("/metrics", response_model=MetricsListResponse)
async def list_evaluation_metrics(limit: int = Query(50, ge=1, le=500)):
    """List evaluation metrics stored in the database."""
    _ensure_db_ready()
    assert core.db_manager is not None
    
    # Force cleanup of duplicates before listing
    core.db_manager.cleanup_duplicate_metrics()
    
    cache_key = f"metrics:list:{limit}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    
    assert core.db_manager is not None
    rows = core.db_manager.list_evaluation_metrics(limit)
    
    items = []
    for row in rows:
        confusion = row.get("weather_confusion")
        if isinstance(confusion, str):
            confusion = json.loads(confusion)
            
        items.append(
            {
                "id": row.get("id"),
                "date": row.get("bulletin_date"),
                "forecast_reference_date": row.get("forecast_reference_date"),
                "mae_tmin": row.get("mae_tmin"),
                "mae_tmax": row.get("mae_tmax"),
                "rmse_tmin": row.get("rmse_tmin"),
                "rmse_tmax": row.get("rmse_tmax"),
                "bias_tmin": row.get("bias_tmin"),
                "bias_tmax": row.get("bias_tmax"),
                "accuracy_weather": row.get("accuracy_weather"),
                "precision_weather": row.get("precision_weather"),
                "recall_weather": row.get("recall_weather"),
                "f1_score_weather": row.get("f1_score_weather"),
                "confusion_matrix": confusion,
                "sample_size": row.get("sample_size"),
                "observation_file_path": row.get("observation_file_path"),
                "forecast_file_path": row.get("forecast_file_path"),
                "observation_title": row.get("observation_title"),
                "forecast_title": row.get("forecast_title"),
                "calculated_at": row.get("calculated_at").isoformat() if hasattr(row.get("calculated_at"), 'isoformat') else row.get("calculated_at"),
            }
        )
    payload = {"items": items, "total": len(items)}
    _cache_set(cache_key, payload)
    return payload


@router.post("/metrics/recalculate")
async def recalculate_metrics(payload: Optional[MetricsRecalculateRequest] = None):
    """Recalculate evaluation metrics for all bulletins."""
    _ensure_db_ready()
    assert core.db_manager is not None
    force = payload.force if payload else False

    def run_evaluation():
        evaluator = ForecastEvaluator(core.db_manager)
        # 1. Calculer les métriques quotidiennes
        daily_result = evaluator.evaluate_forecasts(force_recalculate=force)
        # 2a. Agréger les métriques mensuelles (legacy method for dashboard fallback)
        agg_result = evaluator.aggregate_monthly_metrics()
        # 2b. Calculer les métriques mensuelles (direct method)
        monthly_result = evaluator.calculate_monthly_metrics_direct()
        # 3. Calculer les métriques mensuelles par station
        station_result = evaluator.calculate_station_monthly_metrics()
        return {"daily": daily_result, "monthly_agg": agg_result, "monthly": monthly_result, "station": station_result}

    result = await run_in_threadpool(run_evaluation)
    
    # Invalider le cache après recalcul
    _cache_clear("metrics:")
    _cache_clear("monthly_metrics:")
    
    if not result.get("daily"):
        observation_count = len(core.db_manager.list_bulletin_dates("observation"))
        forecast_count = len(core.db_manager.list_bulletin_dates("forecast"))
        return {
            "status": "no_data",
            "message": "Aucune donnee observation/prevision disponible pour recalculer.",
            "observation_count": observation_count,
            "forecast_count": forecast_count,
        }
    
    return {
        "status": "done",
        "result": result,
    }


@router.get("/metrics/monthly/{year}/{month}")
async def get_monthly_metrics(year: int, month: int):
    """Récupère les métriques agrégées pour un mois donné."""
    _ensure_db_ready()
    assert core.db_manager is not None
    
    cache_key = f"monthly_metrics:{year}-{month:02d}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    
    metrics = core.db_manager.get_monthly_metrics(year, month)
    if not metrics:
        return {
            "year": year,
            "month": month,
            "mae_tmin": None,
            "mae_tmax": None,
            "rmse_tmin": None,
            "rmse_tmax": None,
            "accuracy_weather": 0,
            "sample_size": 0,
            "message": "Données mensuelles non disponibles."
        }
    
    _cache_set(cache_key, metrics)
    return metrics


@router.get("/metrics-monthly")
async def list_monthly_metrics(limit: int = Query(12, ge=1, le=60)):
    """Liste les métriques mensuelles récentes."""
    _ensure_db_ready()
    assert core.db_manager is not None
    
    cache_key = f"monthly_metrics:list:{limit}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    
    items = core.db_manager.list_monthly_metrics(limit)
    payload = {"items": items, "total": len(items)}
    
    _cache_set(cache_key, payload)
    return payload


@router.get("/metrics/stations")
async def list_stations_with_metrics():
    """Liste toutes les stations avec leurs métriques disponibles."""
    _ensure_db_ready()
    assert core.db_manager is not None
    
    stations = core.db_manager.list_all_stations_with_metrics()
    payload = {"stations": stations, "total": len(stations)}
    
    return payload


@router.get("/metrics/station/{station_id}/monthly/{year}/{month}")
async def get_station_monthly_metrics(station_id: int, year: int, month: int):
    """Récupère les métriques mensuelles pour une station donnée."""
    _ensure_db_ready()
    assert core.db_manager is not None
    
    cache_key = f"station_metrics:{station_id}:{year}-{month:02d}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    
    metrics = core.db_manager.get_station_monthly_metrics(station_id, year, month)
    if not metrics:
        raise HTTPException(
            status_code=404,
            detail={
                "code": ErrorCode.METRICS_NOT_FOUND.value,
                "message": f"Aucune métrique mensuelle pour la station {station_id} en {year}-{month:02d}.",
            },
        )
    
    _cache_set(cache_key, metrics)
    return metrics


@router.get("/metrics/station/{station_id}/monthly")
async def list_station_monthly_metrics(station_id: int, limit: int = Query(12, ge=1, le=60)):
    """Liste les métriques mensuelles récentes pour une station."""
    _ensure_db_ready()
    assert core.db_manager is not None
    
    cache_key = f"station_metrics_list:{station_id}:{limit}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    
    items = core.db_manager.list_station_monthly_metrics(station_id, limit)
    payload = {"items": items, "total": len(items)}
    
    if len(items) == 0:
        raise HTTPException(
            status_code=404,
            detail={
                "code": ErrorCode.METRICS_NOT_FOUND.value,
                "message": f"Aucune métrique mensuelle trouvée pour la station {station_id}.",
            },
        )
    
    _cache_set(cache_key, payload)
    return payload



@router.get("/metrics/comparison")
async def get_forecast_comparison(
    start_date: Optional[str] = Query(None, description="Date de début (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="Date de fin (YYYY-MM-DD)"),
    station_name: Optional[str] = Query(None, description="Filtrer par station")
):
    """
    Compare les prévisions J-1 avec les observations J.
    
    Retourne les métriques de précision:
    - Précision des icônes météo
    - MAE pour Tmin et Tmax
    - Détails par ville
    """
    _ensure_db_ready()
    assert core.db_manager is not None
    
    from backend.modules.forecast_comparison import ForecastComparisonEngine
    
    engine = ForecastComparisonEngine(tolerance_temp=2.0)
    
    try:
        conn = core.db_manager.get_connection()
        with conn.cursor() as cursor:
            # Récupérer les paires observation/prévision
            query = """
                SELECT 
                    ob.date as obs_date,
                    s.name as station_name,
                    o.tmin as tmin_obs,
                    o.tmax as tmax_obs,
                    o.weather_condition as weather_obs,
                    f.tmin as tmin_prev,
                    f.tmax as tmax_prev,
                    f.weather_condition as weather_prev
                FROM weather_data o
                JOIN bulletins ob ON o.bulletin_id = ob.id
                JOIN stations s ON o.station_id = s.id
                LEFT JOIN weather_data f ON f.station_id = o.station_id
                LEFT JOIN bulletins fb ON f.bulletin_id = fb.id AND
                    fb.date = (CAST(ob.date AS DATE) - INTERVAL '1 day')::text AND
                    fb.type = 'forecast'
                WHERE ob.type = 'observation'
            """
            
            params = []
            if start_date:
                query += " AND ob.date >= %s"
                params.append(start_date)
            if end_date:
                query += " AND ob.date <= %s"
                params.append(end_date)
            if station_name:
                query += " AND s.name ILIKE %s"
                params.append(f"%{station_name}%")
            
            query += " ORDER BY ob.date DESC, s.name"
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            comparisons = []
            for row in rows:
                obs_date, station, tmin_obs, tmax_obs, weather_obs, tmin_prev, tmax_prev, weather_prev = row
                
                if tmin_prev is None and tmax_prev is None and weather_prev is None:
                    continue  # Pas de prévision J-1
                
                comparison = engine.compare_single(
                    city_name=station,
                    date_obs=str(obs_date),
                    date_prev=str(obs_date - __import__('datetime').timedelta(days=1)),
                    forecast_data={
                        'tmin_prev': tmin_prev,
                        'tmax_prev': tmax_prev,
                        'weather_prev': weather_prev
                    },
                    observation_data={
                        'tmin_obs': tmin_obs,
                        'tmax_obs': tmax_obs,
                        'weather_obs': weather_obs
                    }
                )
                comparisons.append(comparison)
            
            # Calculer les métriques globales
            from dataclasses import asdict
            
            return {
                "total_comparisons": len(comparisons),
                "summary": engine.get_summary(),
                "comparisons": [asdict(c) for c in comparisons[:100]]  # Limiter à 100
            }
            
    except Exception as e:
        logger.error(f"Erreur lors de la comparaison forecast: {e}")
        raise HTTPException(status_code=500, detail=str(e))

