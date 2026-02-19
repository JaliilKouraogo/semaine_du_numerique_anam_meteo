#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import requests
import logging
import os
import re
import threading
import time
import unicodedata
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path
from typing import Optional
from backend.utils.date_utils import extract_date_from_filename, extraire_date_heure_nom_fichier

logger = logging.getLogger(__name__)

try:
    from gradio_client import Client
except ImportError:
    Client = None
    logger.warning("gradio_client not installed. Remote translation disabled.")

try:
    import torch
except (ImportError, OSError):
    torch = None
    logger.warning("Torch not available.")

try:
    from transformers import AutoModelForCausalLM, AutoModelForSeq2SeqLM, AutoTokenizer
except ImportError:
    AutoModelForCausalLM = None
    AutoModelForSeq2SeqLM = None
    AutoTokenizer = None
    logger.warning("Transformers not available.")

try:
    from huggingface_hub import snapshot_download
except ImportError:
    snapshot_download = None
    logger.warning("huggingface_hub not installed. Local model downloading disabled.")

from backend.utils.database import DatabaseManager

_INTERPRETER_LOCK = threading.Lock()
_INTERPRETER_INSTANCE = None


class TranslationCache:
    def __init__(self, db_manager: Optional[DatabaseManager]):
        self.db_manager = db_manager

    def get(self, language: str, source_text: str) -> Optional[str]:
        if not self.db_manager:
            return None
        try:
            return self.db_manager.get_translation_cache(language, source_text)
        except Exception as exc:
            logger.warning("Translation cache read failed: %s", exc)
            return None

    def store(self, language: str, source_text: str, translated_text: str, provider: str) -> None:
        if not self.db_manager:
            return
        try:
            self.db_manager.store_translation_cache(language, source_text, translated_text, provider)
        except Exception as exc:
            logger.warning("Translation cache write failed: %s", exc)


class InterpretationCache:
    def __init__(self, db_manager: Optional[DatabaseManager]):
        self.db_manager = db_manager

    def get(self, source_text: str) -> Optional[str]:
        if not self.db_manager:
            return None
        try:
            return self.db_manager.get_interpretation_cache(source_text)
        except Exception as exc:
            logger.warning("Interpretation cache read failed: %s", exc)
            return None

    def store(self, source_text: str, interpretation_text: str, provider: str) -> None:
        if not self.db_manager:
            return
        try:
            self.db_manager.store_interpretation_cache(source_text, interpretation_text, provider)
        except Exception as exc:
            logger.warning("Échec de l'écriture du cache d'interprétation : %s", exc)


def _log_json(level: int, event: str, **fields):
    payload = {
        "event": event,
        "level": logging.getLevelName(level),
        "ts": time.time(),
    }
    payload.update(fields)
    logger.log(level, json.dumps(payload, ensure_ascii=True))


import re
import unicodedata
import fitz  # PyMuPDF

# Utilise extraire_date_heure_nom_fichier importé

class LanguageInterpreter:
    """Extraire le texte des bulletins (PDF) et traduire via NLLB."""

    def __init__(self, _api_endpoint: Optional[str] = None, db_manager: Optional[DatabaseManager] = None):
        if not os.getenv("HF_TOKEN"):
            self._load_env_file()

        backend_root = Path(__file__).resolve().parents[1]
        project_root = Path(__file__).resolve().parents[2]
        
        models_root_env = os.getenv("LLM_MODELS_DIR")
        if models_root_env:
            models_root = Path(models_root_env)
            if not models_root.is_absolute():
                models_root = project_root / models_root
        else:
            models_root = backend_root / "models"

        # --- NLLB local ---
        auto_device = self._detect_optimal_device()
        logger.info(f"🖥️  Périphérique optimal détecté : {auto_device}")
        
        env_translation_device = os.getenv("TRANSLATION_DEVICE")
        self.translation_device = env_translation_device or auto_device
        
        if env_translation_device:
            logger.info(f"⚙️  Override manuel : TRANSLATION_DEVICE={env_translation_device}")
        self.translation_languages = {
            "moore": os.getenv("TRANSLATION_LANG_MOORE", "mos_Latn"),
            "dioula": os.getenv("TRANSLATION_LANG_DIOULA", "dyu_Latn"),
        }
        self.translation_source = os.getenv("TRANSLATION_SOURCE_LANG", "fra_Latn")
        self.translation_local_repo = os.getenv("TRANSLATION_LOCAL_REPO", "facebook/nllb-200-distilled-600M")
        self.translation_local_path = self._resolve_nllb_local_path(models_root)
        
        self.translation_model = None
        self.translation_tokenizer = None
        # self._init_translation_local() # Modèle chargé à la demande pour économiser la RAM

        self.translation_cache = TranslationCache(db_manager)
        self.interpretation_cache = InterpretationCache(db_manager)
        self.target_languages = list(self.translation_languages.keys())

        # --- Configuration Gradio / Remote (Correction crash) ---
        self.translation_client = None
        self.translation_source_label = self._resolve_lang_label(self.translation_source)
        self.translation_target_labels = {
            lang: self._resolve_lang_label(code)
            for lang, code in self.translation_languages.items()
        }
        self.translation_api_name = os.getenv("TRANSLATION_GRADIO_API_NAME", "/translate")

        remote_repo = os.getenv("TRANSLATION_GRADIO_REPO")
        if remote_repo and Client:
            try:
                self.translation_client = Client(remote_repo)
                logger.info(f"✅ Traduction distante activée via {remote_repo}")
            except Exception as exc:
                logger.warning(f"Impossible de connecter le client Gradio: {exc}")

    @classmethod
    def get_shared(cls, db_manager: Optional[DatabaseManager] = None) -> "LanguageInterpreter":
        global _INTERPRETER_INSTANCE
        with _INTERPRETER_LOCK:
            if _INTERPRETER_INSTANCE is None:
                _INTERPRETER_INSTANCE = cls(db_manager=db_manager)
            else:
                _INTERPRETER_INSTANCE._refresh_caches(db_manager)
            return _INTERPRETER_INSTANCE

    def _refresh_caches(self, db_manager: Optional[DatabaseManager]) -> None:
        if db_manager is None:
            return
        self.translation_cache = TranslationCache(db_manager)
        self.interpretation_cache = InterpretationCache(db_manager)

    def _init_translation_local(self):
        """Charge le modèle NLLB local en mémoire pour les traductions."""
        if not self.translation_local_path:
            logger.warning("Chemin local NLLB introuvable, traduction locale désactivée.")
            return
        
        try:
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
            
            logger.info(f"Chargement du modèle NLLB depuis {self.translation_local_path}...")
            
            self.translation_tokenizer = AutoTokenizer.from_pretrained(
                str(self.translation_local_path),
                local_files_only=True
            )
            
            # Chargement du modèle avec gestion intelligente du device et de la précision
            model_kwargs = {"local_files_only": True}
            
            if self.translation_device != "cpu" and torch.cuda.is_available():
                # GPU disponible : utiliser FP16 pour économiser la VRAM
                logger.info("🚀 Chargement en précision FP16 (GPU)...")
                model_kwargs["torch_dtype"] = torch.float16
                model_kwargs["device_map"] = "auto"  # Optimisation automatique de la distribution
            else:
                # CPU : garder FP32 pour la stabilité
                logger.info("💻 Chargement en précision FP32 (CPU)...")
            
            self.translation_model = AutoModelForSeq2SeqLM.from_pretrained(
                str(self.translation_local_path),
                **model_kwargs
            )
            
            # Forcer le CPU si nécessaire
            if self.translation_device == "cpu" or not torch.cuda.is_available():
                self.translation_model = self.translation_model.to("cpu")
            
            # Afficher les statistiques de mémoire post-chargement
            if self.translation_device != "cpu" and torch.cuda.is_available():
                gpu_memory_used = torch.cuda.memory_allocated(0) / (1024**3)
                logger.info(f"✅ Modèle NLLB chargé sur {self.translation_device}")
                logger.info(f"   Mémoire GPU utilisée : {gpu_memory_used:.2f} GB")
            else:
                logger.info(f"✅ Modèle NLLB chargé sur {self.translation_device}")
        
        except Exception as exc:
            logger.error(f"Erreur lors du chargement NLLB: {exc}")
            self.translation_model = None
            self.translation_tokenizer = None

    async def generate_interpretations_async(self, integrated_data):
        from fastapi.concurrency import run_in_threadpool
        return await run_in_threadpool(self.generate_interpretations, integrated_data)

    def _load_env_file(self):
        """Charge le fichier .env à la racine."""
        try:
            root_dir = Path(__file__).resolve().parents[2]
            env_path = root_dir / ".env"
            if env_path.exists():
                with open(env_path, "r", encoding="utf-8") as handle:
                    for line in handle:
                        line = line.strip()
                        if not line or line.startswith("#"): continue
                        if "=" in line:
                            if " #" in line: line = line.split(" #", 1)[0].strip()
                            key, value = line.split("=", 1)
                            os.environ[key.strip()] = value.strip().strip("'").strip('"')
        except Exception as exc:
            logger.warning("Failed to read .env: %s", exc)

    def _sync_env_paths(self):
        """Optionnel : synchronise les chemins des modèles dans .env."""
        pass

    def _detect_optimal_device(self) -> str:
        """
        Détecte automatiquement le meilleur périphérique d'exécution.
        
        Logique de décision :
        1. Vérifie la disponibilité de CUDA/GPU
        2. Vérifie la mémoire GPU disponible (si applicable)
        3. Vérifie la RAM système disponible
        4. Choisit CPU ou CUDA selon les ressources disponibles
        
        Returns:
            str: "cuda" ou "cpu"
        """
        # 1. Vérification de base : PyTorch et CUDA disponibles ?
        if torch is None:
            logger.info("⚠️  PyTorch non disponible, utilisation du CPU")
            return "cpu"
        
        if not torch.cuda.is_available():
            logger.info("💻 CPU sélectionné (CUDA non disponible)")
            return "cpu"
        
        # 2. CUDA disponible, vérifier les ressources GPU
        try:
            gpu_count = torch.cuda.device_count()
            if gpu_count == 0:
                logger.info("⚠️  Aucun GPU détecté, utilisation du CPU")
                return "cpu"
            
            # Récupérer les infos du GPU principal
            gpu_name = torch.cuda.get_device_name(0)
            gpu_memory_total = torch.cuda.get_device_properties(0).total_memory / (1024**3)  # GB
            gpu_memory_allocated = torch.cuda.memory_allocated(0) / (1024**3)  # GB
            gpu_memory_free = gpu_memory_total - gpu_memory_allocated
            
            logger.info(f"🎮 GPU détecté : {gpu_name}")
            logger.info(f"   Mémoire GPU : {gpu_memory_free:.2f} GB libre / {gpu_memory_total:.2f} GB total")
            
            # 3. Vérification de la RAM système
            try:
                import psutil
                ram_info = psutil.virtual_memory()
                ram_available_gb = ram_info.available / (1024**3)
                ram_total_gb = ram_info.total / (1024**3)
                logger.info(f"💾 RAM système : {ram_available_gb:.2f} GB libre / {ram_total_gb:.2f} GB total")
            except ImportError:
                logger.warning("⚠️  psutil non disponible, impossible de vérifier la RAM")
                ram_available_gb = 8.0  # Valeur par défaut conservatrice
            
            # 4. Décision intelligente
            # NLLB-3.3B nécessite environ 6-8 GB de VRAM en FP32, 3-4 GB en FP16
            # On privilégie le GPU si on a au moins 4 GB de VRAM libre
            MIN_GPU_MEMORY_GB = 4.0
            
            if gpu_memory_free >= MIN_GPU_MEMORY_GB:
                logger.info(f"✅ GPU sélectionné ({gpu_memory_free:.2f} GB VRAM disponible)")
                return "cuda"
            else:
                logger.warning(
                    f"⚠️  Mémoire GPU insuffisante ({gpu_memory_free:.2f} GB < {MIN_GPU_MEMORY_GB} GB requis)"
                )
                logger.info("💻 Fallback sur CPU")
                return "cpu"
        
        except Exception as exc:
            logger.error(f"❌ Erreur lors de la détection GPU : {exc}")
            logger.info("💻 Fallback sécurisé sur CPU")
            return "cpu"

    # --- LOGIQUE D'EXTRACTION PDF (Issue de text_extract.py) ---
    def _normaliser(self, texte):
        if not texte: return ""
        texte = texte.replace('’', "'").replace('–', '-').replace('—', '-')
        return "".join(c for c in unicodedata.normalize('NFD', texte)
                      if unicodedata.category(c) != 'Mn').lower()

    def _nettoyer_texte(self, texte):
        if not texte: return ""
        texte = texte.replace('\n', ' ')
        titres_a_virer = [
            r'^24 heures', r'^jusqu\'à demain 12 heures?', r'^jusqu\'à demain 12 heu',
            r'^demain 12 heures?', r'^demain 12 heu', r'^au cours de cette journee',
            r'^durant les dernieres 24 heures', r'^le temps des dernieres 24 heures'
        ]
        texte = re.sub(r'\s+', ' ', texte).strip()
        for pat in titres_a_virer:
            texte = re.sub(pat, '', texte, flags=re.IGNORECASE).strip()
        texte = re.sub(r'^[\s\.\,h0-9]+', '', texte).strip()
        if texte: texte = texte[0].upper() + texte[1:]
        return texte

    def _extraire_texte_pdf(self, pdf_path):
        """Extrait l'observation et la prévision depuis le PDF local."""
        try:
            doc = fitz.open(pdf_path)
            page = doc[0]
            # Zone gauche (50% de la page)
            x_limite = page.rect.width * 0.5
            rect = fitz.Rect(0, 0, x_limite, page.rect.height)
            texte_brut = page.get_text("text", clip=rect)
            if not texte_brut.strip():
                texte_brut = page.get_text("text")
            
            texte_norm = self._normaliser(texte_brut)
            
            # Balises de début et fin
            obs_starts = ["le temps des dernieres 24 heures", "le temps des dernieres", "dernieres 24 heures"]
            prev_starts = ["previsions valables jusqu'a demain 12 heures", "previsions valables jusqu'a", "previsions valables"]
            fin_pattern = "ci-contre, la carte des temperatures"

            # Extraction Observation
            obs_text = ""
            start_idx = -1
            for p in obs_starts:
                idx = texte_norm.find(p)
                if idx != -1:
                    start_idx = idx + len(p)
                    break
            if start_idx != -1:
                end_idx = len(texte_norm)
                for p in [fin_pattern] + prev_starts:
                    idx = texte_norm.find(p, start_idx)
                    if idx != -1 and idx < end_idx: end_idx = idx
                obs_text = self._nettoyer_texte(texte_brut[start_idx:end_idx])

            # Extraction Prévision
            prev_text = ""
            start_idx = -1
            for p in prev_starts:
                idx = texte_norm.find(p)
                if idx != -1:
                    start_idx = idx + len(p)
                    break
            if start_idx != -1:
                end_idx = len(texte_norm)
                for p in [fin_pattern, "information", "anam"]:
                    idx = texte_norm.find(p, start_idx)
                    if idx != -1 and idx < end_idx: end_idx = idx
                prev_text = self._nettoyer_texte(texte_brut[start_idx:end_idx])

            doc.close()
            return obs_text, prev_text
        except Exception as e:
            logger.error("Erreur extraction PDF %s: %s", pdf_path, e)
            return "", ""

    def generate_interpretations(self, integrated_data, progress_callback=None):
        """
        Génération des interprétations :
        1. AZEN (Agent BF) génère le texte français à partir des données des stations.
        2. L'API Moore traduit le texte d'AZEN.
        """
        all_bulletin_entries = []
        texts_to_translate_moore = set()
        texts_to_translate_dioula = set()
        
        # 1. GENERATION DU TEXTE FRANCAIS (QWEN)
        total_items = len(integrated_data)
        for i, entry in enumerate(integrated_data, 1):
            pdf_path = entry.get("pdf_path")
            maps = entry.get("data", [])
            
            if progress_callback:
                pct = (i - 1) / total_items * 100 * 0.5 # Qwen is the first 50%
                self._log_event("interpretation_progress", pct=pct, pdf=Path(pdf_path).name if pdf_path else "??")
                progress_callback(pct, f"Interprétation Qwen {i}/{total_items}: {Path(pdf_path).name if pdf_path else '??'}")

            # On garde l'OCR comme fallback au cas où AZEN échoue
            obs_fr_ocr, prev_fr_ocr = self._extraire_texte_pdf(pdf_path)
            
            nom_fichier = Path(pdf_path).name if pdf_path else "bulletin.pdf"
            date_file, heure_file = extraire_date_heure_nom_fichier(nom_fichier)
            ref_date_str = entry.get("date") or date_file
            
            try:
                ref_date = datetime.strptime(ref_date_str, "%Y-%m-%d")
            except:
                ref_date = datetime.now()

            # On itère sur les maps (Règle ANAM: Map 0 = Obs J, Map 1 = Prev J+1)
            for idx, map_entry in enumerate(maps):
                if idx == 0:
                    map_date = ref_date.strftime("%Y-%m-%d")
                    map_type = "observation"
                    fr_text_base = obs_fr_ocr
                elif idx == 1:
                    map_date = (ref_date + timedelta(days=1)).strftime("%Y-%m-%d")
                    map_type = "forecast"
                    fr_text_base = prev_fr_ocr
                else:
                    map_date = (ref_date + timedelta(days=idx)).strftime("%Y-%m-%d")
                    map_type = "forecast"
                    fr_text_base = prev_fr_ocr

                # --- GÉNÉRATION AZEN (Agent Météo BF) --- 
                # On utilise les données des stations de la map actuelle
                stations = map_entry.get("temperatures", [])
                fr_text = self._generate_qwen_french_interpretation(stations, map_type, map_date)
                
                # Fallback sur l'OCR si Qwen échoue
                if not fr_text:
                    fr_text = fr_text_base or ""
                
                if fr_text:
                    texts_to_translate_moore.add(fr_text)
                    texts_to_translate_dioula.add(fr_text)

                bulletin_entry = {
                    "pdf_path": str(pdf_path) if pdf_path else None,
                    "date": map_date,
                    "heure": entry.get("heure") or heure_file,
                    "type": map_type,
                    "interpretation_francais": fr_text,
                    "interpretation_moore": "", 
                    "interpretation_dioula": "",
                    "data": [
                        {
                            "type": map_type,
                            "image_path": map_entry.get("image_path"),
                            "temperatures": stations
                        }
                    ],
                    "stations": stations
                }
                all_bulletin_entries.append(bulletin_entry)

        # 2. TRADUCTION BATCH / CACHÉE
        moore_translations = {}
        dioula_translations = {}
        
        # On remplit d'abord depuis le cache pour optimiser
        for txt in list(texts_to_translate_moore):
            res_m = self.translation_cache.get("moore", txt)
            if res_m: moore_translations[txt] = res_m
            
            res_d = self.translation_cache.get("dioula", txt)
            if res_d: dioula_translations[txt] = res_d

        # Traduction Moore via API spécifiée si pas en cache
        to_translate_moore = [t for t in texts_to_translate_moore if t not in moore_translations]
        if to_translate_moore:
            def _on_moore_progress(pct, msg):
                if progress_callback:
                    # Moore translation is roughly the next 25% of the total interpretation time (after Qwen 50%)
                    overall_pct = 50 + (pct * 0.25)
                    progress_callback(overall_pct, f"Traduction Moore: {msg}")
            
            batch_results_moore = self._translate_batch_local(to_translate_moore, "moore", progress_callback=_on_moore_progress)
            for src, res in zip(to_translate_moore, batch_results_moore):
                if res:
                    moore_translations[src] = res
                    self.translation_cache.store("moore", src, res, "moore_api_cloud")

        # Traduction Dioula via NLLB (fallback batch)
        to_translate_dioula = [t for t in texts_to_translate_dioula if t not in dioula_translations]
        if to_translate_dioula:
            def _on_dioula_progress(pct, msg):
                if progress_callback:
                    # Dioula translation is roughly the last 25% of the total interpretation time (after Qwen 50% and Moore 25%)
                    overall_pct = 75 + (pct * 0.25)
                    progress_callback(overall_pct, f"Traduction Dioula: {msg}")

            batch_results_dioula = self._translate_batch_local(to_translate_dioula, "dioula", progress_callback=_on_dioula_progress)
            for src, res in zip(to_translate_dioula, batch_results_dioula):
                if res:
                    dioula_translations[src] = res
                    self.translation_cache.store("dioula", src, res, "local_nllb_batch")
        
        if progress_callback:
            progress_callback(100, "Interprétation terminée.")

        # 3. Finalisation des bulletins
        for b in all_bulletin_entries:
            fr = b["interpretation_francais"]
            if fr:
                b.setdefault("interpretation_moore", moore_translations.get(fr, ""))
                b.setdefault("interpretation_dioula", dioula_translations.get(fr, "") or "")
            
        return all_bulletin_entries

    def _generate_qwen_french_interpretation(self, stations, map_type, date):
        """
        Génère une petite interprétation en français basée sur les données des stations via Qwen.
        """
        if not stations:
            return None
            
        # 1. Préparer les données pour le prompt
        station_summary = []
        for s in stations:
            # Vérifier les différentes clés possibles selon l'étape du pipeline
            name = s.get("station") or s.get("name") or "Inconnue"
            tmin = s.get("tmin")
            tmax = s.get("tmax")
            weather = s.get("weather") or s.get("weather_condition") or "Non spécifiée"
            summary = f"- {name}: {tmin}°C/{tmax}°C, {weather}"
            station_summary.append(summary)
            
        data_text = "\n".join(station_summary)
        
        # 2. Construire le prompt
        type_str = "observation" if map_type == "observation" else "prévision"
        prompt = f"""Tu es Qwen, un agent expert de la météo nationale du Burkina Faso (ANAM).
Ton rôle est de transformer les données brutes des stations en un court texte informatif pour les citoyens.

Données de {type_str} pour le {date} :
{data_text}

Rédige une interprétation courte (2 à 4 phrases maximum) claire et professionnelle en français burkinabè. 
Commence par une synthèse de la température sur le pays (fraicheur ou chaleur) et termine par le temps qu'il fera ou qu'il a fait.
Sois direct, ne commence pas par une présentation.
"""

        # 3. Appeler Ollama
        ollama_base = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434").rstrip('/')
        ollama_url = f"{ollama_base}/api/generate"
        model = os.getenv("INTERPRETATION_MODEL", "qwen2:7b")
        
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.4, "num_predict": 250}
        }
        
        try:
            response = requests.post(ollama_url, json=payload, timeout=60)
            if response.status_code == 404:
                # Fallback : essayer des noms de modèles plus courants si le spécifié n'existe pas
                for alt_model in ["qwen2", "qwen", "llama3", "mistral"]:
                    logger.info(f"Tentative de fallback Qwen avec le modèle : {alt_model}")
                    payload["model"] = alt_model
                    try:
                        alt_resp = requests.post(ollama_url, json=payload, timeout=60)
                        if alt_resp.status_code == 200:
                            result = alt_resp.json().get("response", "").strip()
                            if result:
                                logger.info(f"✅ Qwen ({alt_model}) a généré une interprétation")
                                return result
                    except: continue
                logger.warning(f"⚠️ Aucun modèle Qwen/Ollama trouvé (404)")
            elif response.status_code == 200:
                result = response.json().get("response", "").strip()
                if result:
                    logger.info(f"✅ Qwen a généré une interprétation")
                    return result
            else:
                logger.warning(f"⚠️ Qwen (Ollama) erreur: {response.status_code}")
        except Exception as exc:
            logger.warning(f"⚠️ Qwen indisponible: {exc}")
            
        return None

    def _translate_moore_api(self, text):
        """Traduit du français vers le mooré via l'API spécifiée par l'utilisateur."""
        if not text:
            return None
            
        url = os.getenv("MOORE_TRANSLATOR_API_URL", "https://fr-mos-translator-314397473739.europe-west1.run.app/api/translate")
        
        # Sécurité : Si le texte est très long, on le découpe par phrases
        # car l'API Cloud peut avoir des limites de buffer provoquant des Erreurs 500.
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        translated_parts = []
        
        logger.info(f"☁️ Appel Moore API Cloud ({len(sentences)} phrases)")
        
        for sentence in sentences:
            if not sentence.strip(): continue
            payload = {
                "text": sentence.strip(),
                "source_lang": "french",
                "target_lang": "moore"
            }
            try:
                response = requests.post(url, json=payload, timeout=25)
                if response.status_code == 200:
                    data = response.json()
                    res = data.get("translation")
                    if res:
                        translated_parts.append(res.strip())
                else:
                    logger.warning(f"Moore API sentence error {response.status_code}")
                    return None # On abandonne si une phrase échoue pour basculer sur le fallback
            except Exception as exc:
                logger.warning(f"Moore API timeout/fail: {exc}")
                return None
                
        return " ".join(translated_parts) if translated_parts else None

    def _translate_qwen(self, text, language):
        """Traduction via Qwen (Ollama) en dernier recours avec fallbacks adaptés à l'utilisateur."""
        if not text:
            return None
            
        ollama_base = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434").rstrip('/')
        ollama_url = f"{ollama_base}/api/generate"
        # Utilisation du modèle présent chez l'utilisateur par défaut
        model = os.getenv("INTERPRETATION_MODEL", "qwen2.5:7b")
        
        target_lang_name = "Mooré (langue du Burkina Faso)" if language == "moore" else "Dioula (langue du Burkina Faso)"
        logger.info(f"🤖 Tentative de traduction {language} via Qwen (Ollama: {ollama_base})")
        
        prompt = f"""Tu es un traducteur expert polyglotte.
Traduits le texte météo suivant du Français vers le {target_lang_name}.
Assure-toi que la traduction est fluide et professionnelle.
Ne fournis QUE la traduction, sans commentaire, sans introduction, sans guillemets.

Texte à traduire :
{text}
"""
        
        # Liste des modèles détectés sur le système de l'utilisateur
        fallbacks = ["qwen2.5:7b", "qwen2.5", "qwen2", "mistral:7b", "llama3.1:8b", "llama3.2-vision:11b"]
        
        for current_model in [model] + fallbacks:
            payload = {
                "model": current_model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.2, "num_predict": 500}
            }
            try:
                response = requests.post(ollama_url, json=payload, timeout=90)
                if response.status_code == 200:
                    result = response.json().get("response", "").strip()
                    if result:
                        logger.info(f"✅ Traduction {language} réussie avec {current_model}")
                        return result
                elif response.status_code == 404:
                    logger.info(f"   └─ Modèle {current_model} non trouvé (404), changement...")
                    continue
                else:
                    logger.warning(f"⚠️ Erreur Ollama {current_model} ({response.status_code})")
            except Exception as e:
                logger.debug(f"      Fail {current_model}: {e}")
                continue
                
        logger.warning(f"❌ Impossible de traduire avec les modèles Ollama disponibles.")
        return None

    def _translate_batch_local(self, texts, language, progress_callback=None):
        """Traduction optimisée par lots pour NLLB (avec fallback API pour le mooré)."""
        if not texts:
            return []

        if language == "moore":
            results = []
            total = len(texts)
            for i, t in enumerate(texts, 1):
                if progress_callback:
                    progress_callback((i-1)/total*100, f"Traduction Moore API {i}/{total}")
                res = self._translate_moore_api(t)
                results.append(res)
            
            # If Moore API calls were successful, return them
            if any(r is not None for r in results):
                return results
            # Otherwise, fallback to NLLB
            logger.info("Fallback vers NLLB local pour le mooré car l'API a échoué.")

        if not self.translation_model or not self.translation_tokenizer:
            self._init_translation_local()

        if not self.translation_model or not self.translation_tokenizer:
            return [None] * len(texts)
            
        target_code = self.translation_languages.get(language)
        if not target_code: return [None] * len(texts)
        
        # Normalisation du code
        if "_" in target_code:
            parts = target_code.split("_")
            target_code = f"{parts[0].lower()}_{parts[1].capitalize()}"

        try:
            tokenizer = self.translation_tokenizer
            # Correction : On définit la langue source sur l'objet tokenizer lui-même
            tokenizer.src_lang = self.translation_source
            
            inputs = tokenizer(
                texts, 
                return_tensors="pt", 
                padding=True, 
                truncation=True
            ).to(self.translation_device)
            
            # Conversion du code de langue en token ID
            forced_bos_id = tokenizer.convert_tokens_to_ids(target_code)
            
            # DIAGNOSTIC : Vérifier si le token existe
            if forced_bos_id == tokenizer.unk_token_id or forced_bos_id == 0:
                logger.error(
                    f"⚠️  Batch: Code '{target_code}' non reconnu par NLLB (ID: {forced_bos_id})"
                )
                # Tentative de récupération
                base_lang = target_code.split("_")[0] if "_" in target_code else target_code
                for alt_code in [f"{base_lang}_Latn", f"{base_lang.lower()}_Latn", base_lang]:
                    alt_id = tokenizer.convert_tokens_to_ids(alt_code)
                    if alt_id != tokenizer.unk_token_id and alt_id != 0:
                        logger.info(f"✅ Batch: Code alternatif '{alt_code}' utilisé")
                        forced_bos_id = alt_id
                        break
                
                if forced_bos_id == tokenizer.unk_token_id or forced_bos_id == 0:
                    logger.error(f"❌ Batch: Impossible de traduire vers {language}")
                    return [None] * len(texts)
            
            generated = self.translation_model.generate(
                **inputs,
                forced_bos_token_id=forced_bos_id,
                max_length=256,
                repetition_penalty=1.5,
                no_repeat_ngram_size=3,
                num_beams=5,
                early_stopping=True,
            )
            results = tokenizer.batch_decode(generated, skip_special_tokens=True)
            return [r.strip() for r in results]
        except Exception as exc:
            logger.error(f"Erreur translation batch ({language}): {exc}")
            return [None] * len(texts)

    def _generate_french_bulletin(self, station_data):
        """Récupère ou génère le texte français global du bulletin."""
        pdf_path = station_data.get("pdf_path")
        if not pdf_path:
            return None
            
        path_obj = Path(pdf_path)
        if not path_obj.exists():
            # Fallback : chercher dans data/pdfs relative au dossier de travail (/app)
            # ou avec le préfixe backend si on est à la racine
            possible_fallbacks = [
                Path("/app/data/pdfs") / path_obj.name,
                Path("data/pdfs") / path_obj.name,
                Path("backend/data/pdfs") / path_obj.name
            ]
            for fb in possible_fallbacks:
                if fb.exists():
                    path_obj = fb
                    break
            
            if not path_obj.exists():
                logger.warning(f"Fichier PDF non trouvé: {pdf_path}")
        
        # 1. Tenter l'extraction OCR classique
        obs_fr, prev_fr = "", ""
        if path_obj.exists():
            obs_fr, prev_fr = self._extraire_texte_pdf(str(path_obj))
        
        is_forecast = "forecast" in str(path_obj).lower() or station_data.get("type") == "forecast"
        fr_text = prev_fr if is_forecast else obs_fr

        # 2. Fallback Qwen si l'OCR est vide (scanned PDF ou pas de texte)
        if not fr_text:
             # On essaie de régénérer via Qwen si on a les stations dans station_data
             stations = station_data.get("stations", [])
             map_type = "forecast" if is_forecast else "observation"
             map_date = station_data.get("date")
             if not stations and "name" in station_data:
                 # On a au moins la station cible
                 stations = [station_data]
                 
             if stations:
                 logger.info(f"🔄 Fallback Qwen pour le texte français car l'OCR est vide pour {path_obj.name}")
                 fr_text = self._generate_qwen_french_interpretation(stations, map_type, map_date)
        
        return fr_text

    def _generate_with_timeout(self, station_data, timeout_seconds):
        if timeout_seconds is None:
            return self._generate_french_bulletin(station_data), False
        remaining = max(0.0, timeout_seconds)
        if remaining == 0:
            return None, True
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self._generate_french_bulletin, station_data)
            try:
                return future.result(timeout=remaining), False
            except TimeoutError:
                future.cancel()
                return None, True

    def translate(self, text, language, force=False):
        if not text:
            return None

        if not force:
            cached = self.translation_cache.get(language, text)
            if cached:
                _log_json(
                    logging.INFO,
                    "translation_cache_hit",
                    language=language,
                )
                return cached

        # Priorité API pour le Mooré
        if language == "moore":
            translated = self._translate_moore_api(text)
            if translated:
                self.translation_cache.store(language, text, translated, "moore_api_cloud")
                _log_json(
                    logging.INFO,
                    "translation_success",
                    provider="moore_api_cloud",
                    language=language,
                )
                return translated

        target_label = self.translation_target_labels.get(language)
        if self.translation_client and target_label and self.translation_source_label:
            try:
                result = self.translation_client.predict(
                    text=text,
                    src_lang=self.translation_source_label,
                    tgt_lang=target_label,
                    api_name=self.translation_api_name,
                )
                if result:
                    translated = str(result).strip()
                    self.translation_cache.store(language, text, translated, "gradio_nllb")
                    _log_json(
                        logging.INFO,
                        "translation_success",
                        provider="gradio_nllb",
                        language=language,
                    )
                    return translated
            except Exception as exc:
                _log_json(
                    logging.WARNING,
                    "translation_error",
                    provider="gradio_nllb",
                    language=language,
                    error=str(exc),
                )

        translated = self._translate_local(text, language)
        if translated:
            self.translation_cache.store(language, text, translated, "local_nllb")
            _log_json(
                logging.INFO,
                "translation_success",
                provider="local_nllb",
                language=language,
            )
            return translated

        # --- FALLBACK ULTIME : Qwen (Ollama) ---
        translated = self._translate_qwen(text, language)
        if translated:
            self.translation_cache.store(language, text, translated, "qwen_ollama")
            _log_json(
                logging.INFO,
                "translation_success",
                provider="qwen_ollama",
                language=language,
            )
            return translated

        _log_json(
            logging.WARNING,
            "translation_failed",
            language=language,
        )
        return None

    def _translate_local(self, text, language):
        if not text:
            return None

        if not self.translation_model or not self.translation_tokenizer:
            self._init_translation_local()

        if not self.translation_model or not self.translation_tokenizer:
            return None
        target_code = self.translation_languages.get(language)
        if not target_code:
            return None
        
        # Normalisation du code de langue pour NLLB (ex: dyu_Latn)
        target_code = target_code.strip().replace("-", "_")
        # NLLB utilise souvent des codes comme 'dyu_Latn', on s'assure de la casse
        # mais attention, certains tokens spéciaux sont sensibles. 
        # Pour NLLB-200, c'est généralement minuscule_Majuscule (ex: fra_Latn)
        # On va essayer de corriger les erreurs communes.
        if "_" in target_code:
            parts = target_code.split("_")
            target_code = f"{parts[0].lower()}_{parts[1].capitalize()}"

        try:
            tokenizer = self.translation_tokenizer
            # Correction : On définit la langue source sur l'objet tokenizer lui-même
            tokenizer.src_lang = self.translation_source
            
            inputs = tokenizer(
                text, 
                return_tensors="pt", 
                padding=True, 
                truncation=True
            )
            if self.translation_device != "cpu" and torch.cuda.is_available():
                inputs = inputs.to(self.translation_device)
            
            # Conversion du code de langue en token ID
            forced_bos_id = tokenizer.convert_tokens_to_ids(target_code)
            
            # DIAGNOSTIC : Vérifier si le token existe dans le vocabulaire
            if forced_bos_id == tokenizer.unk_token_id or forced_bos_id == 0:
                logger.error(
                    f"⚠️  Code de langue '{target_code}' non reconnu par NLLB. "
                    f"Token ID retourné : {forced_bos_id}. "
                    f"Vérifiez que '{target_code}' est dans le vocabulaire NLLB-200."
                )
                # Tentative de récupération : essayer sans le script
                base_lang = target_code.split("_")[0] if "_" in target_code else target_code
                alternative_codes = [
                    f"{base_lang}_Latn",
                    f"{base_lang.lower()}_Latn",
                    base_lang
                ]
                for alt_code in alternative_codes:
                    alt_id = tokenizer.convert_tokens_to_ids(alt_code)
                    if alt_id != tokenizer.unk_token_id and alt_id != 0:
                        logger.info(f"✅ Code alternatif trouvé : '{alt_code}' (ID: {alt_id})")
                        forced_bos_id = alt_id
                        break
                
                if forced_bos_id == tokenizer.unk_token_id or forced_bos_id == 0:
                    logger.error(f"❌ Impossible de trouver un code valide pour la langue {language}")
                    return None
            
            generated = self.translation_model.generate(
                **inputs,
                forced_bos_token_id=forced_bos_id,
                max_length=200,
                repetition_penalty=1.5,
                no_repeat_ngram_size=3,
                num_beams=5,
                early_stopping=True,
            )
            result = tokenizer.batch_decode(generated, skip_special_tokens=True)[0]
            return result.strip()
        except Exception as exc:
            logger.error("Translation error via local NLLB (%s): %s", target_code, exc)
            return None

    def _resolve_lang_label(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        normalized = value.strip()
        if not normalized:
            return None

        label_map = {
            "fra_latn": "French",
            "fr": "French",
            "french": "French",
            "mos_latn": "Mossi",
            "mossi": "Mossi",
            "dyu_latn": "Dyula",
            "dyula": "Dyula",
        }
        key = normalized.lower().replace("-", "_")
        return label_map.get(key, normalized)

    def _resolve_torch_dtype(self, dtype_name: str):
        if torch is None:
            return None
        lookup = {
            "float32": torch.float32,
            "float16": torch.float16,
            "bfloat16": torch.bfloat16,
        }
        return lookup.get(dtype_name.lower(), torch.float32)

    def _format_env_path(self, path: Path) -> str:
        root_dir = Path(__file__).resolve().parents[2]
        try:
            rel = path.relative_to(root_dir)
            return str(rel).replace("\\", "/")
        except ValueError:
            return str(path)

    def _resolve_nllb_local_path(self, models_root: Path) -> Optional[Path]:
        env_path_str = os.getenv("TRANSLATION_LOCAL_PATH")
        candidates = []
        
        if env_path_str:
            env_path = Path(env_path_str)
            if not env_path.is_absolute():
                project_root = Path(__file__).resolve().parents[2]
                candidates.append(project_root / env_path)
            else:
                candidates.append(env_path)
        
        candidates.append(models_root / "nllb")
        candidates.append(models_root / "facebook__nllb-200-distilled-600M")

        for candidate in candidates:
            if candidate.exists():
                config_file = candidate / "config.json"
                if config_file.exists():
                    return candidate
                subdirs = [d for d in candidate.iterdir() if d.is_dir()]
                if len(subdirs) == 1 and (subdirs[0] / "config.json").exists():
                    return subdirs[0]
        return None
