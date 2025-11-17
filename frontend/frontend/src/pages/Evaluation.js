import React, { useEffect, useMemo, useState } from 'react';
import { Download } from 'lucide-react';

import MapStationMarker from '../components/MapStationMarker';
import ChartTimeseries from '../components/ChartTimeseries';
import ConfusionMatrix from '../components/ConfusionMatrix';
import {
  getAllMerged,
  getEvaluationMetrics,
} from '../services/api';
import { buildEvaluationDataset } from '../utils/dataTransforms';

const Evaluation = () => {
  const [evaluation, setEvaluation] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const loadEvaluation = async () => {
      setLoading(true);
      setError('');
      try {
        const [metricsRes, mergedRes] = await Promise.all([
          getEvaluationMetrics().catch(() => ({ data: {} })),
          getAllMerged().catch(() => ({ data: {} })),
        ]);

        const dataset = buildEvaluationDataset(mergedRes.data || {});
        const metrics = metricsRes.data || {};

        setEvaluation({
          global_mae_tmax:
            metrics.Tmax_MAE ?? dataset.global_mae_tmax ?? 0,
          global_rmse_tmax:
            metrics.Tmax_RMSE ?? dataset.global_rmse_tmax ?? 0,
          icon_accuracy:
            metrics.Icon_accuracy ?? dataset.icon_accuracy ?? 0,
          icon_macro_f1: metrics.Icon_macro_F1 ?? null,
          stations_heatmap: dataset.stations_heatmap,
          trend_mae: dataset.trend_mae,
          confusion_matrix: dataset.confusion_matrix,
        });
      } catch (err) {
        console.error(err);
        setError("Impossible de charger les métriques d'évaluation.");
      } finally {
        setLoading(false);
      }
    };

    loadEvaluation();
  }, []);

  const trendSeries = useMemo(() => {
    if (!evaluation) return [];
    return [
      {
        name: 'MAE Tmax',
        data: evaluation.trend_mae.map((t) => ({ x: t.date, y: t.mae })),
        color: '#2563EB',
      },
    ];
  }, [evaluation]);

  const handleExport = (format) => {
    if (!evaluation) return;
    if (format === 'json') {
      const blob = new Blob([JSON.stringify(evaluation, null, 2)], {
        type: 'application/json',
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = 'evaluation.json';
      anchor.click();
      URL.revokeObjectURL(url);
    } else {
      const csv = [
        ['Date', 'MAE Tmax'].join(','),
        ...evaluation.trend_mae.map((t) => [t.date, t.mae].join(',')),
      ].join('\n');
      const blob = new Blob([csv], { type: 'text/csv' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = 'evaluation.csv';
      anchor.click();
      URL.revokeObjectURL(url);
    }
  };

  if (loading) {
    return <p className="text-gray-600">Chargement...</p>;
  }

  if (error) {
    return <p className="text-red-600">{error}</p>;
  }

  if (!evaluation) {
    return <p className="text-gray-600">Aucune donnée pour le moment.</p>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Évaluation globale</h1>
        <div className="flex items-center space-x-2">
          <button
            onClick={() => handleExport('csv')}
            className="flex items-center space-x-2 px-4 py-2 bg-white border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 transition-colors font-medium"
          >
            <Download className="w-4 h-4" />
            <span>Exporter CSV</span>
          </button>
          <button
            onClick={() => handleExport('json')}
            className="flex items-center space-x-2 px-4 py-2 bg-primary text-white rounded-lg hover:bg-blue-700 transition-colors font-medium"
          >
            <Download className="w-4 h-4" />
            <span>Exporter JSON</span>
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
          <p className="text-sm text-gray-600 mb-1">MAE moyen Tmax (global)</p>
          <p className="text-3xl font-bold text-gray-900">
            {evaluation.global_mae_tmax?.toFixed(2) ?? '—'}°C
          </p>
        </div>
        <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
          <p className="text-sm text-gray-600 mb-1">RMSE moyen Tmax (global)</p>
          <p className="text-3xl font-bold text-gray-900">
            {evaluation.global_rmse_tmax?.toFixed(2) ?? '—'}°C
          </p>
        </div>
      </div>

      <div>
        <h2 className="text-xl font-semibold text-gray-900 mb-4">
          Carte heatmap des erreurs (MAE)
        </h2>
        <MapStationMarker stations={evaluation.stations_heatmap} />
      </div>

      <ChartTimeseries
        series={trendSeries}
        yLabel="MAE (°C)"
        xLabel="Date"
        legend={false}
      />

      <ConfusionMatrix
        labels={evaluation.confusion_matrix.labels}
        matrix={evaluation.confusion_matrix.matrix}
      />

      <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          Métriques d&apos;icônes météo
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="p-4 bg-gray-50 rounded-xl border border-gray-100">
            <p className="text-sm text-gray-600 mb-1">Accuracy</p>
            <p className="text-2xl font-semibold text-gray-900">
              {(evaluation.icon_accuracy * 100).toFixed(1)}%
            </p>
          </div>
          <div className="p-4 bg-gray-50 rounded-xl border border-gray-100">
            <p className="text-sm text-gray-600 mb-1">Macro F1-score</p>
            <p className="text-2xl font-semibold text-gray-900">
              {evaluation.icon_macro_f1
                ? (evaluation.icon_macro_f1 * 100).toFixed(1)
                : '—'}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Evaluation;
