import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ArrowLeft, Download } from 'lucide-react';

import ChartTimeseries from '../components/ChartTimeseries';
import ConfusionMatrix from '../components/ConfusionMatrix';
import { getStation, getStationReports } from '../services/api';

const buildTimeseries = (reports = []) =>
  reports
    .map((report) => ({
      date:
        report.date_bulletin ||
        (report.created_at
          ? new Date(report.created_at).toISOString().slice(0, 10)
          : `bulletin-${report.id}`),
      tmin_prev: report.Tmin_prev,
      tmin_obs: report.Tmin_obs,
      tmax_prev: report.Tmax_prev,
      tmax_obs: report.Tmax_obs,
      temps_obs: report.temps_obs,
      temps_prev: report.temps_prev,
      diff_percent:
        report.Tmax_prev != null && report.Tmax_obs != null
          ? Math.abs(report.Tmax_obs - report.Tmax_prev) /
              (Math.abs(report.Tmax_prev) || 1) *
              100
          : null,
    }))
    .sort((a, b) => new Date(a.date) - new Date(b.date));

const computeMetrics = (timeseries) => {
  const diffsTmin = timeseries
    .map((t) =>
      t.tmin_prev != null && t.tmin_obs != null
        ? Math.abs(t.tmin_obs - t.tmin_prev)
        : null,
    )
    .filter((val) => val != null);
  const diffsTmax = timeseries
    .map((t) =>
      t.tmax_prev != null && t.tmax_obs != null
        ? t.tmax_obs - t.tmax_prev
        : null,
    )
    .filter((val) => val != null);

  const mae_tmin =
    diffsTmin.length > 0
      ? diffsTmin.reduce((sum, diff) => sum + diff, 0) / diffsTmin.length
      : 0;

  const mae_tmax =
    diffsTmax.length > 0
      ? diffsTmax.reduce((sum, diff) => sum + Math.abs(diff), 0) /
        diffsTmax.length
      : 0;

  const rmse_tmax =
    diffsTmax.length > 0
      ? Math.sqrt(
          diffsTmax.reduce((sum, diff) => sum + diff * diff, 0) /
            diffsTmax.length,
        )
      : 0;

  const labels = Array.from(
    new Set(
      timeseries
        .flatMap((t) => [t.temps_obs, t.temps_prev])
        .filter((label) => !!label),
    ),
  );

  const matrix = labels.map(() => Array(labels.length).fill(0));
  timeseries.forEach((t) => {
    if (!t.temps_obs || !t.temps_prev) return;
    const obsIdx = labels.indexOf(t.temps_obs);
    const prevIdx = labels.indexOf(t.temps_prev);
    if (obsIdx >= 0 && prevIdx >= 0) {
      matrix[obsIdx][prevIdx] += 1;
    }
  });

  return {
    mae_tmin,
    mae_tmax,
    rmse_tmax,
    confusion_matrix: labels.length
      ? { labels, matrix }
      : { labels: ['n/a'], matrix: [[0]] },
  };
};

const getStationName = (station) =>
  station?.name || station?.nom || 'Station';

const StationDetail = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const [station, setStation] = useState(null);
  const [reports, setReports] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const loadStation = async () => {
      setLoading(true);
      setError('');
      try {
        const [stationRes, reportsRes] = await Promise.all([
          getStation(id),
          getStationReports(id, { limit: 500 }),
        ]);
        setStation(stationRes.data);
        setReports(reportsRes.data || []);
      } catch (err) {
        console.error(err);
        setError("Impossible de charger la station demandée.");
      } finally {
        setLoading(false);
      }
    };

    loadStation();
  }, [id]);

  const timeseries = useMemo(() => buildTimeseries(reports), [reports]);
  const metrics = useMemo(() => computeMetrics(timeseries), [timeseries]);

  const timeseriesData = [
    {
      name: 'Tmin Prévu',
      data: timeseries.map((t) => ({ x: t.date, y: t.tmin_prev })),
      color: '#60A5FA',
    },
    {
      name: 'Tmin Observé',
      data: timeseries.map((t) => ({ x: t.date, y: t.tmin_obs })),
      color: '#3B82F6',
    },
    {
      name: 'Tmax Prévu',
      data: timeseries.map((t) => ({ x: t.date, y: t.tmax_prev })),
      color: '#F87171',
    },
    {
      name: 'Tmax Observé',
      data: timeseries.map((t) => ({ x: t.date, y: t.tmax_obs })),
      color: '#EF4444',
    },
  ];

  const errorSeries = [
    {
      name: 'Erreur |Tmax_obs - Tmax_prev|',
      data: timeseries.map((t) => ({
        x: t.date,
        y:
          t.tmax_obs != null && t.tmax_prev != null
            ? Math.abs(t.tmax_obs - t.tmax_prev)
            : null,
      })),
      color: '#D41142',
    },
  ];

  const handleExport = () => {
    const header = ['date', 'tmin_prev', 'tmin_obs', 'tmax_prev', 'tmax_obs'];
    const rows = timeseries.map((t) =>
      [t.date, t.tmin_prev, t.tmin_obs, t.tmax_prev, t.tmax_obs].join(','),
    );
    const csv = [header.join(','), ...rows].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `station_${id}.csv`;
    anchor.click();
    URL.revokeObjectURL(url);
  };

  if (loading) {
    return <p className="text-gray-600">Chargement...</p>;
  }

  if (error) {
    return (
      <div className="space-y-4">
        <button
          onClick={() => navigate('/stations')}
          className="text-primary hover:underline"
        >
          Retour
        </button>
        <p className="text-red-600">{error}</p>
      </div>
    );
  }

  if (!station) {
    return <p className="text-gray-600">Station introuvable.</p>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <button
            onClick={() => navigate('/stations')}
            className="p-2 rounded-lg hover:bg-gray-100 transition-colors"
          >
            <ArrowLeft className="w-5 h-5 text-gray-700" />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              {getStationName(station)}
            </h1>
            <p className="text-sm text-gray-500">
              {station.latitude != null && station.longitude != null
                ? `${station.latitude.toFixed(3)}, ${station.longitude.toFixed(
                    3,
                  )}`
                : 'Coordonnées non définies'}
            </p>
          </div>
        </div>
        <button
          onClick={handleExport}
          className="flex items-center space-x-2 px-4 py-2 bg-primary text-white rounded-lg hover:bg-blue-700 transition-colors font-medium"
        >
          <Download className="w-4 h-4" />
          <span>Exporter les séries</span>
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
          <p className="text-sm text-gray-600 mb-1">MAE Tmin</p>
          <p className="text-2xl font-bold text-gray-900">
            {metrics.mae_tmin.toFixed(2)}°C
          </p>
        </div>
        <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
          <p className="text-sm text-gray-600 mb-1">MAE Tmax</p>
          <p className="text-2xl font-bold text-gray-900">
            {metrics.mae_tmax.toFixed(2)}°C
          </p>
        </div>
        <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
          <p className="text-sm text-gray-600 mb-1">RMSE Tmax</p>
          <p className="text-2xl font-bold text-gray-900">
            {metrics.rmse_tmax.toFixed(2)}°C
          </p>
        </div>
      </div>

      <ChartTimeseries
        series={timeseriesData}
        yLabel="Température (°C)"
        xLabel="Date"
        legend={true}
      />

      <ChartTimeseries
        series={errorSeries}
        yLabel="Erreur (°C)"
        xLabel="Date"
        legend={false}
      />

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
          <div className="p-6 border-b border-gray-200">
            <h2 className="text-lg font-semibold text-gray-900">
              Observations vs Prévisions
            </h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-700 uppercase">
                    Date
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-700 uppercase">
                    Tmin
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-700 uppercase">
                    Tmax
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-700 uppercase">
                    % Diff
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-700 uppercase">
                    Icônes
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {timeseries.map((t) => (
                  <tr key={t.date} className="hover:bg-gray-50">
                    <td className="px-4 py-3 text-sm text-gray-900">
                      {t.date}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">
                      {t.tmin_prev ?? '—'}°C / {t.tmin_obs ?? '—'}°C
                    </td>
                  <td className="px-4 py-3 text-sm text-gray-600">
                    {t.tmax_prev ?? '—'}°C / {t.tmax_obs ?? '—'}°C
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-900">
                    {t.diff_percent != null ? `${t.diff_percent.toFixed(1)}%` : '—'}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600">
                    {t.temps_prev || '—'} → {t.temps_obs || '—'}
                  </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <ConfusionMatrix
          labels={metrics.confusion_matrix.labels}
          matrix={metrics.confusion_matrix.matrix}
        />
      </div>
    </div>
  );
};

export default StationDetail;
