"""
Modules du backend ANAM-METEO-EVAL.

Modules disponibles:
- forecast_evaluator: Évaluation des prévisions météo
- forecast_comparison: Comparaison prévisions vs observations
- vlm_icon_engine: Moteur VLM pour extraction d'icônes
- pdf_extractor: Extraction de données PDF
- temperature_extractor: Extraction de températures
- icon_classifier: Classification d'icônes météo
- language_interpreter: Interprétation multilingue
- data_integrator: Intégration des données
- data_validator: Validation des données
- pipeline_runner: Exécution du pipeline
"""

# Exports des nouveaux modules
from .vlm_icon_engine import VLMIconEngine, get_vlm_engine, recognize_weather_icons
from .forecast_comparison import (
    ForecastComparisonEngine,
    ComparisonMetrics,
    CityComparison,
    get_comparison_engine,
    compare_forecast_vs_observation
)
