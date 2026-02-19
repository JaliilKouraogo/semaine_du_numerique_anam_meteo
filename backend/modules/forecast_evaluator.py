#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Evaluation des previsions meteo pour le systeme ANAM-METEO-EVAL."""

import logging
from datetime import datetime, timedelta
from typing import Dict

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    recall_score,
)

logger = logging.getLogger(__name__)


class ForecastEvaluator:
    """Calcule les metriques servant a juger la qualite des bulletins."""

    def __init__(self, db_manager):
        self.db_manager = db_manager

    def calculate_temperature_metrics(self, tmin_obs, tmax_obs, tmin_fore, tmax_fore):
        """Retourne MAE/RMSE/biais pour les temperatures mini/maxi."""
        tmin_pairs = [(o, f) for o, f in zip(tmin_obs, tmin_fore) if o is not None and f is not None]
        tmax_pairs = [(o, f) for o, f in zip(tmax_obs, tmax_fore) if o is not None and f is not None]
        if not tmin_pairs and not tmax_pairs:
            return {}

        metrics = {}

        if tmin_pairs:
            tmin_obs_arr = np.array([p[0] for p in tmin_pairs], dtype=float)
            tmin_fore_arr = np.array([p[1] for p in tmin_pairs], dtype=float)
            metrics["mae_tmin"] = mean_absolute_error(tmin_obs_arr, tmin_fore_arr)
            metrics["rmse_tmin"] = float(np.sqrt(mean_squared_error(tmin_obs_arr, tmin_fore_arr)))
            metrics["bias_tmin"] = float(np.mean(tmin_fore_arr - tmin_obs_arr))
            metrics["tmin_sample_size"] = len(tmin_pairs)

        if tmax_pairs:
            tmax_obs_arr = np.array([p[0] for p in tmax_pairs], dtype=float)
            tmax_fore_arr = np.array([p[1] for p in tmax_pairs], dtype=float)
            metrics["mae_tmax"] = mean_absolute_error(tmax_obs_arr, tmax_fore_arr)
            metrics["rmse_tmax"] = float(np.sqrt(mean_squared_error(tmax_obs_arr, tmax_fore_arr)))
            metrics["bias_tmax"] = float(np.mean(tmax_fore_arr - tmax_obs_arr))
            metrics["tmax_sample_size"] = len(tmax_pairs)

        sample_size = metrics.get("tmin_sample_size") or metrics.get("tmax_sample_size")
        if metrics.get("tmin_sample_size") and metrics.get("tmax_sample_size"):
            sample_size = min(metrics["tmin_sample_size"], metrics["tmax_sample_size"])
        metrics["temperature_sample_size"] = sample_size

        return metrics

    def calculate_weather_metrics(self, weather_obs, weather_fore):
        """Calcule accuracy, precision, rappel, F1 et matrice de confusion."""
        if not weather_obs or not weather_fore:
            return {}

        pairs = [
            (observed, forecasted)
            for observed, forecasted in zip(weather_obs, weather_fore)
            if observed is not None and forecasted is not None
        ]
        if not pairs:
            return {}

        y_true = [item[0] for item in pairs]
        y_pred = [item[1] for item in pairs]

        labels = sorted(set(y_true) | set(y_pred))
        matrix = confusion_matrix(y_true, y_pred, labels=labels)

        accuracy = accuracy_score(y_true, y_pred)
        precision = precision_score(y_true, y_pred, average="weighted", zero_division=0)
        recall = recall_score(y_true, y_pred, average="weighted", zero_division=0)
        f1 = f1_score(y_true, y_pred, average="weighted", zero_division=0)

        return {
            "accuracy_weather": accuracy,
            "precision_weather": precision,
            "recall_weather": recall,
            "f1_score_weather": f1,
            "confusion_matrix": {
                "labels": labels,
                "matrix": matrix.tolist(),
            },
            "sample_size": len(y_true),
        }

    def evaluate_forecasts(self, force_recalculate: bool = False):
        """Calcule les metriques pour tous les bulletins exploitables."""
        import re
        import unicodedata
        from pathlib import Path
        # Nettoyage des anciennes metriques invalides (meme jour)
        self.db_manager.cleanup_invalid_metrics()
        
        # 1. Récupérer tous les bulletins avec leurs dates et types
        conn = self.db_manager.get_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT id, type, date, file_path FROM bulletins")
            all_bulletins = cursor.fetchall()
        
        if not all_bulletins:
            logger.warning("Aucun bulletin trouve dans la base pour evaluation.")
            return {}

        # 2. Indexer par Date Cible
        # Prev(Jour J) -> Vise Jour J+1 (Date Cible)
        # Obs(Jour J)  -> Vise Jour J   (Date Cible)
        forecasts_by_target = {} # Key: Target Date (YYYY-MM-DD), Value: List of (BulletinID, RefDate)
        observations_by_target = {} # Key: Target Date, Value: BulletinID
        
        pdf_date_regex = re.compile(r"(\d{1,2})[a-zA-Z\u00C0-\u00FF\s_\-]+?([a-zA-Z\u00C0-\u00FF]+)[_\- ]+(\d{4})", re.IGNORECASE)
        month_map = {
            "janvier": 1, "fevrier": 2, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
            "juillet": 7, "aout": 8, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12, "décembre": 12
        }

        def normalize_month(m):
            t = unicodedata.normalize("NFKD", m.lower())
            return "".join(ch for ch in t if not unicodedata.combining(ch))

        for b_id, b_type, b_date, b_path in all_bulletins:
            # Essayer d'extraire la date du nom de fichier pour plus de précision (fiel)
            file_date = None
            if b_path:
                match = pdf_date_regex.search(Path(b_path).stem)
                if match:
                    try:
                        day = int(match.group(1))
                        month_str = normalize_month(match.group(2))
                        year = int(match.group(3))
                        month = month_map.get(month_str)
                        if month:
                            file_date = datetime(year, month, day)
                    except (ValueError, TypeError):
                        pass
            
            # Fallback sur la date en base si le fichier ne matche pas
            if file_date is None:
                try:
                    if isinstance(b_date, datetime):
                        file_date = b_date
                    else:
                        file_date = datetime.strptime(b_date, "%Y-%m-%d")
                except (ValueError, TypeError):
                    continue
            
            if not file_date:
                continue
                
            ref_date_str = file_date.strftime("%Y-%m-%d")
            
            if b_type == 'forecast':
                target_date = (file_date + timedelta(days=1)).strftime("%Y-%m-%d")
                # On stocke l'ID et la date de référence (le jour où la prévision a été faite)
                forecasts_by_target[target_date] = (b_id, ref_date_str)
            elif b_type == 'observation':
                target_date = ref_date_str
                observations_by_target[target_date] = b_id

        # 3. Identifier les couples à évaluer
        # On cherche l'intersection des dates cibles disponibles en observation et prévision
        target_dates = sorted(set(observations_by_target.keys()) & set(forecasts_by_target.keys()))
        
        evaluations = []
        for target_date in target_dates:
            obs_bid = observations_by_target[target_date]
            fore_bid, fore_ref_date = forecasts_by_target[target_date]
            
            # Vérifier si l'évaluation existe déjà
            existing_metric = None
            if not force_recalculate:
                existing_metric = self.db_manager.get_evaluation_metrics_by_date(target_date)
                # Si l'évaluation existe et a des données (sample_size > 0), on passe
                if existing_metric and existing_metric.get('sample_size', 0) > 0:
                    continue
            
            # Calculer les métriques
            pairs = self._get_pairs_by_bulletin_ids(obs_bid, fore_bid)

            if not pairs:
                # On ne logue que si on a vraiment rien trouvé
                logger.debug("Aucune station commune pour Obs(%s) et Prev(%s)", target_date, fore_ref_date)
                continue

            tmin_obs, tmax_obs, tmin_fore, tmax_fore = [], [], [], []
            weather_obs, weather_fore = [], []

            for _, tmin_o, tmax_o, w_o, tmin_f, tmax_f, w_f in pairs:
                tmin_obs.append(tmin_o)
                tmax_obs.append(tmax_o)
                weather_obs.append(w_o)
                tmin_fore.append(tmin_f)
                tmax_fore.append(tmax_f)
                weather_fore.append(w_f)

            temp_metrics = self.calculate_temperature_metrics(
                tmin_obs, tmax_obs, tmin_fore, tmax_fore
            )
            weather_metrics = self.calculate_weather_metrics(weather_obs, weather_fore)

            all_metrics = {**temp_metrics, **weather_metrics}
            all_metrics["observation_date"] = target_date
            all_metrics["forecast_reference_date"] = fore_ref_date

            try:
                self.db_manager.save_evaluation_metrics(
                    target_date,
                    fore_ref_date,
                    all_metrics
                )
                evaluations.append(all_metrics)
                logger.info("Evaluation reussie : %s (prev %s) -> %d stations", 
                            target_date, fore_ref_date, len(pairs))
            except Exception as exc:
                logger.error("Erreur lors de la sauvegarde pour %s: %s", target_date, exc)
                continue

        # 4. Finalisation
        self.db_manager.cleanup_duplicate_metrics()
        
        if not evaluations:
            logger.info("Recalcul termine. Aucune nouvelle evaluation necessaire.")
            return {"evaluated": 0, "message": "Déjà à jour."}

        return {
            "status": "success",
            "evaluated": len(evaluations),
            "dates": [e["observation_date"] for e in evaluations],
            "details": evaluations,
        }

    def calculate_monthly_metrics_direct(self) -> Dict:
        """Calcule directement les métriques mensuelles à partir des données brutes."""
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()
        
        # Récupérer tous les mois ayant des observations
        cursor.execute(
            """
            SELECT DISTINCT EXTRACT(YEAR FROM CAST(date AS DATE))::text as year,
                            TO_CHAR(CAST(date AS DATE), 'MM') as month
            FROM bulletins
            WHERE type = 'observation'
            ORDER BY year DESC, month DESC
            """
        )
        months = cursor.fetchall()
        
        calculated_count = 0
        
        for year_str, month_str in months:
            year = int(year_str)
            month = int(month_str)
            
            # Récupérer toutes les paires observation/prévision pour ce mois
            cursor.execute(
                """
                SELECT 
                    o.tmin as obs_tmin,
                    o.tmax as obs_tmax,
                    o.weather_condition as obs_weather,
                    f.tmin as fore_tmin,
                    f.tmax as fore_tmax,
                    f.weather_condition as fore_weather
                FROM weather_data o
                JOIN bulletins ob ON o.bulletin_id = ob.id
                JOIN weather_data f ON o.station_id = f.station_id
                JOIN bulletins fb ON f.bulletin_id = fb.id
                WHERE ob.type = 'observation'
                  AND fb.type = 'forecast'
                  AND TO_CHAR(CAST(ob.date AS DATE), 'YYYY-MM') = %s
                  AND fb.date = (CAST(ob.date AS DATE) - INTERVAL '1 day')::text
                """,
                (f"{year_str}-{month_str}",)
            )
            
            rows = cursor.fetchall()
            
            if not rows:
                logger.info(f"Aucune donnée pour {year}-{month:02d}")
                continue
            
            # Extraire les valeurs
            tmin_obs = []
            tmax_obs = []
            tmin_fore = []
            tmax_fore = []
            weather_obs = []
            weather_fore = []
            
            for row in rows:
                if row[0] is not None and row[3] is not None:  # tmin
                    tmin_obs.append(float(row[0]))
                    tmin_fore.append(float(row[3]))
                
                if row[1] is not None and row[4] is not None:  # tmax
                    tmax_obs.append(float(row[1]))
                    tmax_fore.append(float(row[4]))
                
                if row[2] is not None and row[5] is not None:  # weather
                    weather_obs.append(row[2])
                    weather_fore.append(row[5])
            
            # Calculer les métriques
            temp_metrics = self.calculate_temperature_metrics(
                tmin_obs, tmax_obs, tmin_fore, tmax_fore
            )
            weather_metrics = self.calculate_weather_metrics(weather_obs, weather_fore)
            
            # Combiner les métriques
            all_metrics = {**temp_metrics, **weather_metrics}
            all_metrics["sample_size"] = len(rows)
            cursor.execute(
                """
                SELECT DISTINCT ob.date
                FROM weather_data o
                JOIN bulletins ob ON o.bulletin_id = ob.id
                JOIN weather_data f ON o.station_id = f.station_id
                JOIN bulletins fb ON f.bulletin_id = fb.id
                WHERE ob.type = 'observation'
                  AND fb.type = 'forecast'
                  AND TO_CHAR(CAST(ob.date AS DATE), 'YYYY-MM') = %s
                  AND fb.date = (CAST(ob.date AS DATE) - INTERVAL '1 day')::text
                """,
                (f"{year_str}-{month_str}",)
            )
            all_metrics["days_evaluated"] = len(set(r[0] for r in cursor.fetchall()))
            
            # Sauvegarder
            self.db_manager.save_monthly_metrics(year, month, all_metrics)
            calculated_count += 1
            logger.info(f"Métriques mensuelles calculées pour {year}-{month:02d} : {all_metrics['days_evaluated']} jours, {all_metrics['sample_size']} échantillons")
        
        return {
            "status": "done",
            "months_calculated": calculated_count,
        }

    def aggregate_monthly_metrics(self) -> Dict:
        """Agrège les métriques d'évaluation par mois (méthode legacy)."""
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()
        
        # Récupérer tous les mois distincts avec des métriques
        cursor.execute(
            """
            SELECT DISTINCT EXTRACT(YEAR FROM CAST(bulletin_date AS DATE))::text as year,
                            TO_CHAR(CAST(bulletin_date AS DATE), 'MM') as month
            FROM evaluation_metrics
            ORDER BY year DESC, month DESC
            """
        )
        months = cursor.fetchall()
        
        aggregated_count = 0
        for year_str, month_str in months:
            year = int(year_str)
            month = int(month_str)
            
            # Agréger les métriques pour ce mois
            cursor.execute(
                """
                SELECT 
                    AVG(mae_tmin) as avg_mae_tmin,
                    AVG(mae_tmax) as avg_mae_tmax,
                    AVG(rmse_tmin) as avg_rmse_tmin,
                    AVG(rmse_tmax) as avg_rmse_tmax,
                    AVG(bias_tmin) as avg_bias_tmin,
                    AVG(bias_tmax) as avg_bias_tmax,
                    AVG(accuracy_weather) as avg_accuracy_weather,
                    AVG(precision_weather) as avg_precision_weather,
                    AVG(recall_weather) as avg_recall_weather,
                    AVG(f1_score_weather) as avg_f1_score_weather,
                    SUM(sample_size) as total_sample_size,
                    COUNT(*) as days_count
                FROM evaluation_metrics
                WHERE EXTRACT(YEAR FROM CAST(bulletin_date AS DATE))::text = %s 
                  AND TO_CHAR(CAST(bulletin_date AS DATE), 'MM') = %s
                """,
                (year_str, month_str),
            )
            row = cursor.fetchone()
            
            if row and row[0] is not None:  # Au moins une métrique valide
                monthly_metrics = {
                    "mae_tmin": row[0],
                    "mae_tmax": row[1],
                    "rmse_tmin": row[2],
                    "rmse_tmax": row[3],
                    "bias_tmin": row[4],
                    "bias_tmax": row[5],
                    "accuracy_weather": row[6],
                    "precision_weather": row[7],
                    "recall_weather": row[8],
                    "f1_score_weather": row[9],
                    "sample_size": row[10] or 0,
                    "days_evaluated": row[11] or 0,
                }
                
                self.db_manager.save_monthly_metrics(year, month, monthly_metrics)
                aggregated_count += 1
                logger.info(f"Métriques mensuelles agrégées pour {year}-{month:02d} : {row[11]} jours")
        
        return {
            "status": "done",
            "months_aggregated": aggregated_count,
        }

    def calculate_station_monthly_metrics(self) -> Dict:
        """Calcule les métriques mensuelles pour chaque station individuellement."""
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()
        
        # Récupérer toutes les stations
        cursor.execute("SELECT id, name FROM stations ORDER BY name")
        stations = cursor.fetchall()
        
        calculated_count = 0
        
        for station_id, station_name in stations:
            # Récupérer tous les mois ayant des observations pour cette station
            cursor.execute(
                """
                SELECT DISTINCT EXTRACT(YEAR FROM CAST(ob.date AS DATE))::text as year,
                                TO_CHAR(CAST(ob.date AS DATE), 'MM') as month
                FROM weather_data wd
                JOIN bulletins ob ON wd.bulletin_id = ob.id
                WHERE ob.type = 'observation'
                  AND wd.station_id = %s
                ORDER BY year DESC, month DESC
                """,
                (station_id,)
            )
            months = cursor.fetchall()
            
            station_calculated = 0
            
            for year_str, month_str in months:
                year = int(year_str)
                month = int(month_str)
                
                # Récupérer toutes les paires observation/prévision pour cette station et ce mois
                cursor.execute(
                    """
                    SELECT 
                        o.tmin as obs_tmin,
                        o.tmax as obs_tmax,
                        o.weather_condition as obs_weather,
                        f.tmin as fore_tmin,
                        f.tmax as fore_tmax,
                        f.weather_condition as fore_weather
                    FROM weather_data o
                    JOIN bulletins ob ON o.bulletin_id = ob.id
                    JOIN weather_data f ON o.station_id = f.station_id
                    JOIN bulletins fb ON f.bulletin_id = fb.id
                    WHERE ob.type = 'observation'
                      AND fb.type = 'forecast'
                      AND o.station_id = %s
                      AND TO_CHAR(CAST(ob.date AS DATE), 'YYYY-MM') = %s
                      AND fb.date = (CAST(ob.date AS DATE) - INTERVAL '1 day')::text
                    """,
                    (station_id, f"{year_str}-{month_str}"),
                )
                
                rows = cursor.fetchall()
                
                if not rows:
                    continue
                
                # Extraire les valeurs
                tmin_obs = []
                tmax_obs = []
                tmin_fore = []
                tmax_fore = []
                weather_obs = []
                weather_fore = []
                
                for row in rows:
                    if row[0] is not None and row[3] is not None:  # tmin
                        tmin_obs.append(float(row[0]))
                        tmin_fore.append(float(row[3]))
                    
                    if row[1] is not None and row[4] is not None:  # tmax
                        tmax_obs.append(float(row[1]))
                        tmax_fore.append(float(row[4]))
                    
                    if row[2] is not None and row[5] is not None:  # weather
                        weather_obs.append(row[2])
                        weather_fore.append(row[5])
                
                # Calculer les métriques
                temp_metrics = self.calculate_temperature_metrics(
                    tmin_obs, tmax_obs, tmin_fore, tmax_fore
                )
                weather_metrics = self.calculate_weather_metrics(weather_obs, weather_fore)
                
                # Combiner les métriques
                all_metrics = {**temp_metrics, **weather_metrics}
                all_metrics["sample_size"] = len(rows)
                cursor.execute(
                    """
                    SELECT DISTINCT ob.date
                    FROM weather_data o
                    JOIN bulletins ob ON o.bulletin_id = ob.id
                    JOIN weather_data f ON o.station_id = f.station_id
                    JOIN bulletins fb ON f.bulletin_id = fb.id
                    WHERE ob.type = 'observation'
                      AND fb.type = 'forecast'
                      AND o.station_id = %s
                      AND TO_CHAR(CAST(ob.date AS DATE), 'YYYY-MM') = %s
                      AND fb.date = (CAST(ob.date AS DATE) - INTERVAL '1 day')::text
                    """,
                    (station_id, f"{year_str}-{month_str}"),
                )
                all_metrics["days_evaluated"] = len(set(r[0] for r in cursor.fetchall()))
                
                # Sauvegarder
                self.db_manager.save_station_monthly_metrics(station_id, year, month, all_metrics)
                station_calculated += 1
                logger.info(f"Métriques mensuelles calculées pour {station_name} - {year}-{month:02d} : {all_metrics['days_evaluated']} jours, {all_metrics['sample_size']} échantillons")
            
            if station_calculated > 0:
                calculated_count += 1
                logger.info(f"Station {station_name}: {station_calculated} mois calculés")
        
        return {
            "status": "done",
            "stations_processed": calculated_count,
        }

    def _get_pairs_by_bulletin_ids(self, obs_bid, fore_bid):
        """Récupère les paires de données météo pour deux bulletins donnés en joignant sur l'ID de station."""
        conn = self.db_manager.get_connection()
        with conn.cursor() as cursor:
            query = '''
                SELECT 
                    s.name,
                    o.tmin as obs_tmin, o.tmax as obs_tmax, o.weather_condition as obs_weather,
                    f.tmin as fore_tmin, f.tmax as fore_tmax, f.weather_condition as fore_weather
                FROM weather_data o
                JOIN stations s ON o.station_id = s.id
                JOIN weather_data f ON o.station_id = f.station_id
                WHERE o.bulletin_id = %s AND f.bulletin_id = %s
            '''
            cursor.execute(query, (obs_bid, fore_bid))
            return cursor.fetchall()
