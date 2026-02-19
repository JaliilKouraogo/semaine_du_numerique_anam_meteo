#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Database manager for ANAM-METEO-EVAL system - PostgreSQL version
"""

import os
import json
import logging
import threading
import psycopg2
from psycopg2.extras import RealDictCursor
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger("anam.database")

class DatabaseManager:
    """Manages database operations for meteorological data using PostgreSQL"""
    
    def __init__(self, db_url=None):
        self.db_url = db_url or os.getenv("DATABASE_URL", "postgresql://anam_user:anam_password@db:5432/anam_db")
        self._local = threading.local()
    
    def get_connection(self):
        """Get database connection, create if not exists"""
        conn = getattr(self._local, "connection", None)
        if conn is None or conn.closed:
            conn = psycopg2.connect(self.db_url)
            self._local.connection = conn
        return conn
    
    def initialize_database(self):
        """Initialize the database with required tables (PostgreSQL syntax)"""
        conn = self.get_connection()
        with conn.cursor() as cursor:
                    # Table des stations
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS stations (
                            id SERIAL PRIMARY KEY,
                            name TEXT UNIQUE NOT NULL,
                            latitude REAL,
                            longitude REAL
                        )
                    ''')
            
                    # Table des bulletins
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS bulletins (
                            id SERIAL PRIMARY KEY,
                            date TEXT NOT NULL,
                            type TEXT NOT NULL CHECK(type IN ('observation', 'forecast')),
                            file_path TEXT,
                            title TEXT,
                            interpretation_francais TEXT,
                            interpretation_moore TEXT,
                            interpretation_dioula TEXT,
                            payload_json TEXT,
                            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            UNIQUE(date, type)
                        )
                    ''')
            
                    # Table des données météo
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS weather_data (
                            id SERIAL PRIMARY KEY,
                            bulletin_id INTEGER REFERENCES bulletins(id) ON DELETE CASCADE,
                            station_id INTEGER REFERENCES stations(id),
                            tmin REAL,
                            tmax REAL,
                            tmin_raw TEXT,
                            tmax_raw TEXT,
                            weather_condition TEXT,
                            interpretation_francais TEXT,
                            interpretation_moore TEXT,
                            interpretation_dioula TEXT,
                            quality_score REAL,
                            payload_json TEXT
                        )
                    ''')
            
                    # Migration: add quality_score if it doesn't exist
                    try:
                        cursor.execute("ALTER TABLE weather_data ADD COLUMN IF NOT EXISTS quality_score REAL")
                    except:
                        pass
            
                    # Table des métriques d'évaluation
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS evaluation_metrics (
                            id SERIAL PRIMARY KEY,
                            bulletin_date TEXT NOT NULL,
                            forecast_reference_date TEXT,
                            mae_tmin REAL,
                            mae_tmax REAL,
                            rmse_tmin REAL,
                            rmse_tmax REAL,
                            bias_tmin REAL,
                            bias_tmax REAL,
                            accuracy_weather REAL,
                            precision_weather REAL,
                            recall_weather REAL,
                            f1_score_weather REAL,
                            weather_confusion TEXT,
                            sample_size INTEGER,
                            calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    ''')

                    # Migration: add unique constraint to evaluation_metrics
                    try:
                        cursor.execute("SAVEPOINT migration_unique_eval")
                        cursor.execute("ALTER TABLE evaluation_metrics ADD CONSTRAINT unique_evaluation UNIQUE (bulletin_date, forecast_reference_date)")
                        cursor.execute("RELEASE SAVEPOINT migration_unique_eval")
                    except:
                        cursor.execute("ROLLBACK TO SAVEPOINT migration_unique_eval")

                    # Table des runs de pipeline
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS pipeline_runs (
                            id SERIAL PRIMARY KEY,
                            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            finished_at TIMESTAMP,
                            status TEXT NOT NULL DEFAULT 'running',
                            steps_json TEXT,
                            error_message TEXT,
                            metadata TEXT,
                            last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    ''')

                    # Table des problèmes de données (data_issues)
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS data_issues (
                            id SERIAL PRIMARY KEY,
                            bulletin_id INTEGER REFERENCES bulletins(id) ON DELETE CASCADE,
                            station_id INTEGER REFERENCES stations(id),
                            bulletin_date TEXT,
                            map_type TEXT,
                            code TEXT,
                            message TEXT,
                            severity TEXT,
                            status TEXT DEFAULT 'open',
                            resolved_at TIMESTAMP,
                            resolution_note TEXT,
                            details TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    ''')

                    # Cache de traduction
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS translation_cache (
                            id SERIAL PRIMARY KEY,
                            language TEXT NOT NULL,
                            source_text TEXT NOT NULL,
                            translated_text TEXT NOT NULL,
                            provider TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            UNIQUE(language, source_text)
                        )
                    ''')

        # Cache d'interprétation
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS interpretation_cache (
                            id SERIAL PRIMARY KEY,
                            source_text TEXT UNIQUE NOT NULL,
                            interpretation_text TEXT NOT NULL,
                            provider TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    ''')

                    # Métriques mensuelles
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS monthly_metrics (
                            id SERIAL PRIMARY KEY,
                            year INTEGER NOT NULL,
                            month INTEGER NOT NULL,
                            metrics_json TEXT NOT NULL,
                            calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            UNIQUE(year, month)
                        )
                    ''')

                    # Métriques mensuelles par station
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS station_monthly_metrics (
                            id SERIAL PRIMARY KEY,
                            station_id INTEGER REFERENCES stations(id) ON DELETE CASCADE,
                            year INTEGER NOT NULL,
                            month INTEGER NOT NULL,
                            metrics_json TEXT NOT NULL,
                            calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            UNIQUE(station_id, year, month)
                        )
                    ''')

                    # Table des jobs
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS jobs (
                            id TEXT PRIMARY KEY,
                            job_type TEXT NOT NULL,
                            status TEXT NOT NULL DEFAULT 'pending',
                            progress INTEGER DEFAULT 0,
                            payload_json TEXT,
                            result_json TEXT,
                            error_message TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    ''')

                    # État de l'application
                    cursor.execute('''
                        CREATE TABLE IF NOT EXISTS app_state (
                            key TEXT PRIMARY KEY,
                            value TEXT,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    ''')

                    # Création des index
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_bulletins_date ON bulletins(date)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_weather_station ON weather_data(station_id)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_trans_source ON translation_cache(source_text)")
            
                    conn.commit()
    
    # --- Stations ---
    def insert_station(self, name, latitude, longitude):
        conn = self.get_connection()
        with conn.cursor() as cursor:
            cursor.execute('''
                INSERT INTO stations (name, latitude, longitude)
                VALUES (%s, %s, %s)
                ON CONFLICT (name) DO UPDATE SET 
                latitude = EXCLUDED.latitude, longitude = EXCLUDED.longitude
                RETURNING id
            ''', (name, latitude, longitude))
            station_id = cursor.fetchone()[0]
            conn.commit()
            return station_id

    # --- Bulletins ---
    def insert_bulletin(self, date, bulletin_type, file_path=None, title=None, interpretations=None):
        conn = self.get_connection()
        with conn.cursor() as cursor:
            interp_fr = (interpretations or {}).get("fr")
            interp_moore = (interpretations or {}).get("moore")
            interp_dioula = (interpretations or {}).get("dioula")
            cursor.execute('''
                INSERT INTO bulletins (date, type, file_path, title, interpretation_francais, interpretation_moore, interpretation_dioula)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (date, type) DO UPDATE SET
                    file_path = EXCLUDED.file_path,
                    title = EXCLUDED.title,
                    interpretation_francais = COALESCE(EXCLUDED.interpretation_francais, bulletins.interpretation_francais),
                    interpretation_moore = COALESCE(EXCLUDED.interpretation_moore, bulletins.interpretation_moore),
                    interpretation_dioula = COALESCE(EXCLUDED.interpretation_dioula, bulletins.interpretation_dioula)
                RETURNING id
            ''', (date, bulletin_type, file_path, title, interp_fr, interp_moore, interp_dioula))
            bulletin_id = cursor.fetchone()[0]
            conn.commit()
            return bulletin_id

    def update_bulletin_interpretations(self, date, bulletin_type, interpretations):
        conn = self.get_connection()
        with conn.cursor() as cursor:
            # Construire dynamiquement la requête pour ne pas écraser les champs non fournis par du NULL
            updates = []
            params = []
            
            field_map = {
                "fr": "interpretation_francais",
                "moore": "interpretation_moore",
                "dioula": "interpretation_dioula"
            }
            
            for key, db_field in field_map.items():
                if key in interpretations and interpretations[key]:
                    updates.append(f"{db_field} = %s")
                    params.append(interpretations[key])
            
            if not updates:
                return 0
                
            sql = f"UPDATE bulletins SET {', '.join(updates)} WHERE date = %s AND type = %s"
            params.extend([date, bulletin_type])
            
            cursor.execute(sql, tuple(params))
            count = cursor.rowcount
            conn.commit()
            return count

    def list_bulletin_summaries(self, limit=50, offset=0):
        conn = self.get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT b.id, b.date, b.type, b.title, b.file_path, 
                b.processed_at::text as processed_at,
                (SELECT COUNT(*) FROM weather_data wd WHERE wd.bulletin_id = b.id) as stations_count,
                b.interpretation_francais, b.interpretation_moore, b.interpretation_dioula
                FROM bulletins b
                ORDER BY b.date DESC, b.processed_at DESC
                LIMIT %s OFFSET %s
            ''', (limit, offset))
            return list(cursor.fetchall())

    def count_bulletin_summaries(self):
        conn = self.get_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(1) FROM bulletins")
            return cursor.fetchone()[0]

    def list_bulletin_payloads_by_date(self, date):
        conn = self.get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("""
                SELECT payload_json, interpretation_francais, interpretation_moore, interpretation_dioula 
                FROM bulletins 
                WHERE date = %s
            """, (date,))
            rows = cursor.fetchall()
            results = []
            for row in rows:
                p = json.loads(row['payload_json']) if row['payload_json'] else {}
                if row['interpretation_francais']: p['interpretation_francais'] = row['interpretation_francais']
                if row['interpretation_moore']: p['interpretation_moore'] = row['interpretation_moore']
                if row['interpretation_dioula']: p['interpretation_dioula'] = row['interpretation_dioula']
                results.append(p)
            return results

    def upsert_bulletin_payload(self, file_path, payload):
        conn = self.get_connection()
        with conn.cursor() as cursor:
            cursor.execute('''
                UPDATE bulletins SET payload_json = %s WHERE file_path = %s
            ''', (json.dumps(payload), str(file_path)))
            conn.commit()

    # --- Weather Data ---
    def insert_weather_data(self, bulletin_id, station_id, tmin, tmax, weather_condition, tmin_raw=None, tmax_raw=None, quality_score=None):
        conn = self.get_connection()
        with conn.cursor() as cursor:
            cursor.execute('''
                INSERT INTO weather_data (bulletin_id, station_id, tmin, tmax, tmin_raw, tmax_raw, weather_condition, quality_score)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ''', (bulletin_id, station_id, tmin, tmax, tmin_raw, tmax_raw, weather_condition, quality_score))
            conn.commit()

    def upsert_station_snapshot(self, file_path, station_payload):
        conn = self.get_connection()
        with conn.cursor() as cursor:
            # On cherche le bulletin_id correspondant au file_path
            cursor.execute("SELECT id FROM bulletins WHERE file_path = %s", (str(file_path),))
            res = cursor.fetchone()
            if not res: return
            bulletin_id = res[0]
            
            # On cherche le station_id
            cursor.execute("SELECT id FROM stations WHERE name = %s", (station_payload.get("name"),))
            res = cursor.fetchone()
            if not res: return
            station_id = res[0]
            
            cursor.execute('''
                UPDATE weather_data SET payload_json = %s
                WHERE bulletin_id = %s AND station_id = %s
            ''', (json.dumps(station_payload), bulletin_id, station_id))
            conn.commit()

    def update_station_interpretations(self, file_path, station_name, bulletin_type, interpretations):
        conn = self.get_connection()
        with conn.cursor() as cursor:
            query = '''
                UPDATE weather_data
                SET interpretation_francais = %s, interpretation_moore = %s, interpretation_dioula = %s
                WHERE bulletin_id IN (SELECT id FROM bulletins WHERE file_path = %s)
                AND station_id IN (SELECT id FROM stations WHERE name = %s)
            '''
            cursor.execute(query, (
                interpretations.get("fr"),
                interpretations.get("moore"),
                interpretations.get("dioula"),
                str(file_path),
                station_name
            ))
            conn.commit()

    # --- Data Issues ---
    def insert_data_issue(self, bulletin_id, station_id, bulletin_date, map_type, code, message, severity, details=None):
        conn = self.get_connection()
        with conn.cursor() as cursor:
            cursor.execute('''
                INSERT INTO data_issues (bulletin_id, station_id, bulletin_date, map_type, code, message, severity, details)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ''', (bulletin_id, station_id, bulletin_date, map_type, code, message, severity, json.dumps(details or {})))
            conn.commit()

    def list_data_issues(self, date=None, station_name=None, severity=None, status=None, limit=100, offset=0):
        conn = self.get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            query = """
                SELECT di.*, s.name as station_name 
                FROM data_issues di
                LEFT JOIN stations s ON di.station_id = s.id
                WHERE 1=1
            """
            params = []
            if date:
                query += " AND di.bulletin_date = %s"
                params.append(date)
            if station_name:
                query += " AND s.name ILIKE %s"
                params.append(f"%{station_name}%")
            if severity:
                query += " AND di.severity = %s"
                params.append(severity)
            if status:
                query += " AND di.status = %s"
                params.append(status)
            
            query += " ORDER BY di.created_at DESC LIMIT %s OFFSET %s"
            params.extend([limit, offset])
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            for row in rows:
                if row.get('details'):
                    try:
                        row['details'] = json.loads(row['details'])
                    except:
                        pass
            return list(rows)

    def count_data_issues(self, date=None, station_name=None, severity=None, status=None):
        conn = self.get_connection()
        with conn.cursor() as cursor:
            query = """
                SELECT COUNT(*) 
                FROM data_issues di
                LEFT JOIN stations s ON di.station_id = s.id
                WHERE 1=1
            """
            params = []
            if date:
                query += " AND di.bulletin_date = %s"
                params.append(date)
            if station_name:
                query += " AND s.name ILIKE %s"
                params.append(f"%{station_name}%")
            if severity:
                query += " AND di.severity = %s"
                params.append(severity)
            if status:
                query += " AND di.status = %s"
                params.append(status)
            
            cursor.execute(query, params)
            return cursor.fetchone()[0]

    def update_data_issue_status(self, issue_id, status, note=None):
        conn = self.get_connection()
        with conn.cursor() as cursor:
            if status == "fixed" or status == "ignored":
                cursor.execute('''
                    UPDATE data_issues 
                    SET status = %s, resolution_note = %s, resolved_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                ''', (status, note, issue_id))
            else:
                cursor.execute('''
                    UPDATE data_issues 
                    SET status = %s, resolution_note = %s
                    WHERE id = %s
                ''', (status, note, issue_id))
            conn.commit()

    def get_average_quality_score(self, date=None):
        conn = self.get_connection()
        with conn.cursor() as cursor:
            query = "SELECT AVG(wd.quality_score) FROM weather_data wd"
            params = []
            if date:
                query += " JOIN bulletins b ON wd.bulletin_id = b.id WHERE b.date = %s"
                params.append(date)
            else:
                query += " WHERE wd.quality_score IS NOT NULL"
                
            cursor.execute(query, params)
            res = cursor.fetchone()
            return res[0] if res and res[0] is not None else 0.0

    def count_quality_scores(self, date=None):
        conn = self.get_connection()
        with conn.cursor() as cursor:
            query = "SELECT COUNT(*) FROM weather_data wd"
            params = []
            if date:
                query += " JOIN bulletins b ON wd.bulletin_id = b.id WHERE b.date = %s AND wd.quality_score IS NOT NULL"
                params.append(date)
            else:
                query += " WHERE wd.quality_score IS NOT NULL"
                
            cursor.execute(query, params)
            return cursor.fetchone()[0]

    def update_temperatures_for_station(self, date, station_name, map_type, tmin=None, tmax=None):
        conn = self.get_connection()
        with conn.cursor() as cursor:
            # First find the station_id and bulletin_id
            cursor.execute('''
                SELECT wd.id FROM weather_data wd
                JOIN bulletins b ON wd.bulletin_id = b.id
                JOIN stations s ON wd.station_id = s.id
                WHERE b.date = %s AND s.name = %s AND b.type = %s
            ''', (date, station_name, map_type))
            row = cursor.fetchone()
            if not row:
                return 0
            
            wd_id = row[0]
            updates = []
            params = []
            if tmin is not None:
                updates.append("tmin = %s")
                params.append(tmin)
            if tmax is not None:
                updates.append("tmax = %s")
                params.append(tmax)
            
            if not updates:
                return 0
            
            params.append(wd_id)
            query = f"UPDATE weather_data SET {', '.join(updates)} WHERE id = %s"
            cursor.execute(query, params)
            conn.commit()
            return 1

    # --- Pipeline Runs ---
    def create_pipeline_run(self, steps_template, metadata=None):
        conn = self.get_connection()
        with conn.cursor() as cursor:
            cursor.execute('''
                INSERT INTO pipeline_runs (status, steps_json, metadata)
                VALUES (%s, %s, %s)
                RETURNING id
            ''', ("running", json.dumps(steps_template), json.dumps(metadata or {})))
            run_id = cursor.fetchone()[0]
            conn.commit()
            return run_id

    def update_pipeline_run(self, run_id, status=None, steps=None, error_message=None, metadata=None, finished=False):
        conn = self.get_connection()
        with conn.cursor() as cursor:
            updates = []
            params = []
            if status:
                updates.append("status = %s")
                params.append(status)
            if steps:
                updates.append("steps_json = %s")
                params.append(json.dumps(steps))
            if error_message:
                updates.append("error_message = %s")
                params.append(error_message)
            if metadata:
                updates.append("metadata = %s")
                params.append(json.dumps(metadata))
            if finished:
                updates.append("finished_at = CURRENT_TIMESTAMP")
            
            updates.append("last_update = CURRENT_TIMESTAMP")
            params.append(run_id)
            
            query = f"UPDATE pipeline_runs SET {', '.join(updates)} WHERE id = %s"
            cursor.execute(query, params)
            conn.commit()

    def get_pipeline_run(self, run_id):
        conn = self.get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT * FROM pipeline_runs WHERE id = %s", (run_id,))
            row = cursor.fetchone()
            if row:
                if row['steps_json']: row['steps'] = json.loads(row['steps_json'])
                if row['metadata']: row['metadata'] = json.loads(row['metadata'])
            return row

    def list_pipeline_runs(self, limit=20):
        conn = self.get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT %s", (limit,))
            rows = cursor.fetchall()
            for row in rows:
                if row['steps_json']: row['steps'] = json.loads(row['steps_json'])
                if row['metadata']: row['metadata'] = json.loads(row['metadata'])
            return rows

    def has_active_pipeline_run(self):
        conn = self.get_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(1) FROM pipeline_runs WHERE status = 'running'")
            return cursor.fetchone()[0] > 0

    # --- Caches (Translation & Interpretation) ---
    def get_translation_cache(self, language, source_text):
        conn = self.get_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT translated_text FROM translation_cache WHERE language = %s AND source_text = %s", (language, source_text))
            res = cursor.fetchone()
            return res[0] if res else None

    def store_translation_cache(self, language, source_text, translated_text, provider):
        conn = self.get_connection()
        with conn.cursor() as cursor:
            cursor.execute('''
                INSERT INTO translation_cache (language, source_text, translated_text, provider)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (language, source_text) DO UPDATE SET translated_text = EXCLUDED.translated_text
            ''', (language, source_text, translated_text, provider))
            conn.commit()

    def get_interpretation_cache(self, source_text):
        conn = self.get_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT interpretation_text FROM interpretation_cache WHERE source_text = %s", (source_text,))
            res = cursor.fetchone()
            return res[0] if res else None

    def store_interpretation_cache(self, source_text, interpretation_text, provider):
        conn = self.get_connection()
        with conn.cursor() as cursor:
            cursor.execute('''
                INSERT INTO interpretation_cache (source_text, interpretation_text, provider)
                VALUES (%s, %s, %s)
                ON CONFLICT (source_text) DO UPDATE SET interpretation_text = EXCLUDED.interpretation_text
            ''', (source_text, interpretation_text, provider))
            conn.commit()

    # --- Evaluation ---
    def cleanup_invalid_metrics(self):
        # Pour une implémentation simple, on peut supprimer les métriques très anciennes ou corrompues si besoin
        pass

    def list_bulletin_dates(self, bulletin_type):
        conn = self.get_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT DISTINCT date FROM bulletins WHERE type = %s ORDER BY date DESC", (bulletin_type,))
            return [row[0] for row in cursor.fetchall()]

    def has_evaluation(self, observation_date, forecast_date):
        conn = self.get_connection()
        with conn.cursor() as cursor:
            cursor.execute('''
                SELECT COUNT(1) FROM evaluation_metrics 
                WHERE bulletin_date = %s AND forecast_reference_date = %s
            ''', (observation_date, forecast_date))
            return cursor.fetchone()[0] > 0

    def get_observation_forecast_pairs(self, observation_date, forecast_date):
        conn = self.get_connection()
        with conn.cursor() as cursor:
            query = '''
                SELECT 
                    s.name,
                    o.tmin as obs_tmin, o.tmax as obs_tmax, o.weather_condition as obs_weather,
                    f.tmin as fore_tmin, f.tmax as fore_tmax, f.weather_condition as fore_weather
                FROM weather_data o
                JOIN bulletins ob ON o.bulletin_id = ob.id
                JOIN stations s ON o.station_id = s.id
                JOIN weather_data f ON o.station_id = f.station_id
                JOIN bulletins fb ON f.bulletin_id = fb.id
                WHERE ob.type = 'observation' AND ob.date = %s
                AND fb.type = 'forecast' AND fb.date = %s
            '''
            cursor.execute(query, (observation_date, forecast_date))
            return cursor.fetchall()

    def save_evaluation_metrics(self, bulletin_date, forecast_ref_date, metrics):
        """Sauvegarde ou met à jour les métriques d'évaluation pour un couple de dates."""
        conn = self.get_connection()
        with conn.cursor() as cursor:
            # On utilise ON CONFLICT pour écraser les anciennes métriques si elles existent
            cursor.execute('''
                INSERT INTO evaluation_metrics (
                    bulletin_date, forecast_reference_date, 
                    mae_tmin, mae_tmax, rmse_tmin, rmse_tmax, 
                    bias_tmin, bias_tmax, accuracy_weather, 
                    precision_weather, recall_weather, f1_score_weather, 
                    weather_confusion, sample_size, calculated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (bulletin_date, forecast_reference_date) 
                DO UPDATE SET
                    mae_tmin = EXCLUDED.mae_tmin,
                    mae_tmax = EXCLUDED.mae_tmax,
                    rmse_tmin = EXCLUDED.rmse_tmin,
                    rmse_tmax = EXCLUDED.rmse_tmax,
                    bias_tmin = EXCLUDED.bias_tmin,
                    bias_tmax = EXCLUDED.bias_tmax,
                    accuracy_weather = EXCLUDED.accuracy_weather,
                    precision_weather = EXCLUDED.precision_weather,
                    recall_weather = EXCLUDED.recall_weather,
                    f1_score_weather = EXCLUDED.f1_score_weather,
                    weather_confusion = EXCLUDED.weather_confusion,
                    sample_size = EXCLUDED.sample_size,
                    calculated_at = CURRENT_TIMESTAMP
            ''', (
                bulletin_date, forecast_ref_date,
                metrics.get("mae_tmin"), metrics.get("mae_tmax"),
                metrics.get("rmse_tmin"), metrics.get("rmse_tmax"),
                metrics.get("bias_tmin"), metrics.get("bias_tmax"),
                metrics.get("accuracy_weather"), metrics.get("precision_weather"),
                metrics.get("recall_weather"), metrics.get("f1_score_weather"),
                json.dumps(metrics.get("confusion_matrix") or {}),
                metrics.get("sample_size")
            ))
            conn.commit()

    def cleanup_duplicate_metrics(self):
        """Supprime les doublons de métriques d'évaluation en ne gardant que la version la plus récente."""
        conn = self.get_connection()
        with conn.cursor() as cursor:
            cursor.execute('''
                DELETE FROM evaluation_metrics
                WHERE id NOT IN (
                    SELECT MAX(id)
                    FROM evaluation_metrics
                    GROUP BY bulletin_date, forecast_reference_date
                )
            ''')
            conn.commit()
            return cursor.rowcount

    def save_monthly_metrics(self, year, month, metrics):
        conn = self.get_connection()
        with conn.cursor() as cursor:
            cursor.execute('''
                INSERT INTO monthly_metrics (year, month, metrics_json)
                VALUES (%s, %s, %s)
                ON CONFLICT (year, month) DO UPDATE SET 
                metrics_json = EXCLUDED.metrics_json, calculated_at = CURRENT_TIMESTAMP
            ''', (year, month, json.dumps(metrics)))
            conn.commit()

    def save_station_monthly_metrics(self, station_id, year, month, metrics):
        conn = self.get_connection()
        with conn.cursor() as cursor:
            cursor.execute('''
                INSERT INTO station_monthly_metrics (station_id, year, month, metrics_json)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (station_id, year, month) DO UPDATE SET 
                metrics_json = EXCLUDED.metrics_json, calculated_at = CURRENT_TIMESTAMP
            ''', (station_id, year, month, json.dumps(metrics)))
            conn.commit()

    def get_evaluation_metrics_by_date(self, date):
        conn = self.get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT * FROM evaluation_metrics
                WHERE bulletin_date = %s
                ORDER BY calculated_at DESC
                LIMIT 1
            ''', (date,))
            return cursor.fetchone()

    def list_evaluation_metrics(self, limit=50):
        conn = self.get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT 
                    em.*,
                    b_obs.file_path as observation_file_path,
                    b_fc.file_path as forecast_file_path,
                    b_obs.title as observation_title,
                    b_fc.title as forecast_title
                FROM evaluation_metrics em
                LEFT JOIN bulletins b_obs ON em.bulletin_date = b_obs.date AND b_obs.type = 'observation'
                LEFT JOIN bulletins b_fc ON em.forecast_reference_date = b_fc.date AND b_fc.type = 'forecast'
                ORDER BY em.bulletin_date DESC
                LIMIT %s
            ''', (limit,))
            return list(cursor.fetchall())

    def get_monthly_metrics(self, year, month):
        conn = self.get_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT metrics_json FROM monthly_metrics WHERE year = %s AND month = %s", (year, month))
            row = cursor.fetchone()
            return json.loads(row[0]) if row else None

    def list_monthly_metrics(self, limit=12):
        conn = self.get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT year, month, metrics_json, calculated_at 
                FROM monthly_metrics 
                ORDER BY year DESC, month DESC 
                LIMIT %s
            ''', (limit,))
            rows = cursor.fetchall()
            for row in rows:
                if row['metrics_json']:
                    row.update(json.loads(row['metrics_json']))
                    del row['metrics_json']
            return list(rows)

    def list_all_stations_with_metrics(self):
        conn = self.get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # On retourne les stations qui ont au moins une métrique mensuelle
            cursor.execute('''
                SELECT DISTINCT s.id, s.name, s.latitude, s.longitude
                FROM stations s
                JOIN station_monthly_metrics smm ON s.id = smm.station_id
                ORDER BY s.name
            ''')
            return list(cursor.fetchall())

    def get_station_monthly_metrics(self, station_id, year, month):
        conn = self.get_connection()
        with conn.cursor() as cursor:
            cursor.execute('''
                SELECT metrics_json FROM station_monthly_metrics 
                WHERE station_id = %s AND year = %s AND month = %s
            ''', (station_id, year, month))
            row = cursor.fetchone()
            return json.loads(row[0]) if row else None

    def list_station_monthly_metrics(self, station_id, limit=12):
        conn = self.get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute('''
                SELECT year, month, metrics_json, calculated_at 
                FROM station_monthly_metrics 
                WHERE station_id = %s
                ORDER BY year DESC, month DESC 
                LIMIT %s
            ''', (station_id, limit))
            rows = cursor.fetchall()
            for row in rows:
                if row['metrics_json']:
                    row.update(json.loads(row['metrics_json']))
                    del row['metrics_json']
            return list(rows)

    # --- Jobs ---
    def create_job(self, job_id, job_type, payload=None):
        conn = self.get_connection()
        with conn.cursor() as cursor:
            cursor.execute('''
                INSERT INTO jobs (id, job_type, payload_json)
                VALUES (%s, %s, %s)
            ''', (job_id, job_type, json.dumps(payload or {})))
            conn.commit()

    def update_job(self, job_id, status=None, result=None, error_message=None, progress=None, payload=None):
        conn = self.get_connection()
        with conn.cursor() as cursor:
            updates = []
            params = []
            if status:
                updates.append("status = %s")
                params.append(status)
            if result:
                updates.append("result_json = %s")
                params.append(json.dumps(result))
            if error_message:
                updates.append("error_message = %s")
                params.append(error_message)
            if progress is not None:
                updates.append("progress = %s")
                params.append(progress)
            if payload is not None:
                updates.append("payload_json = %s")
                params.append(json.dumps(payload))
            
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(job_id)
            
            query = f"UPDATE jobs SET {', '.join(updates)} WHERE id = %s"
            cursor.execute(query, params)
            conn.commit()

    def get_job(self, job_id):
        conn = self.get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT * FROM jobs WHERE id = %s", (job_id,))
            row = cursor.fetchone()
            if row:
                if row['payload_json']: row['payload'] = json.loads(row['payload_json'])
                if row['result_json']: row['result'] = json.loads(row['result_json'])
            return row

    def get_jobs(self, job_ids):
        if not job_ids: return []
        conn = self.get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Use tuple if more than 1, else special case for IN
            if len(job_ids) == 1:
                cursor.execute("SELECT * FROM jobs WHERE id = %s", (job_ids[0],))
            else:
                cursor.execute("SELECT * FROM jobs WHERE id IN %s", (tuple(job_ids),))
            rows = cursor.fetchall()
            for row in rows:
                if row['payload_json']: row['payload'] = json.loads(row['payload_json'])
                if row['result_json']: row['result'] = json.loads(row['result_json'])
            return list(rows)

    def list_jobs(self, limit=50, job_type=None):
        conn = self.get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            if job_type:
                cursor.execute("SELECT * FROM jobs WHERE job_type = %s ORDER BY created_at DESC LIMIT %s", (job_type, limit))
            else:
                cursor.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT %s", (limit,))
            rows = cursor.fetchall()
            for row in rows:
                if row['payload_json']: row['payload'] = json.loads(row['payload_json'])
                if row['result_json']: row['result'] = json.loads(row['result_json'])
            return list(rows)

    def delete_job(self, job_id):
        conn = self.get_connection()
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM jobs WHERE id = %s", (job_id,))
            conn.commit()

    def delete_bulletin(self, bulletin_id):
        conn = self.get_connection()
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM bulletins WHERE id = %s", (bulletin_id,))
            conn.commit()

    # --- App State ---
    def get_app_state(self, key):
        conn = self.get_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT value FROM app_state WHERE key = %s", (key,))
            res = cursor.fetchone()
            return res[0] if res else None

    def set_app_state(self, key, value):
        conn = self.get_connection()
        with conn.cursor() as cursor:
            cursor.execute('''
                INSERT INTO app_state (key, value)
                VALUES (%s, %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = CURRENT_TIMESTAMP
            ''', (key, str(value)))
            conn.commit()

    # --- Misc ---
    def list_processed_pdf_paths(self):
        conn = self.get_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT DISTINCT file_path FROM bulletins WHERE file_path IS NOT NULL")
            return [row[0] for row in cursor.fetchall()]

    def close(self):
        """Close connection"""
        conn = getattr(self._local, "connection", None)
        if conn:
            conn.close()
            self._local.connection = None
