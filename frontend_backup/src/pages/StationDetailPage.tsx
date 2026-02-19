import React, { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  MapPin,
  Thermometer,
  TrendingUp,
  TrendingDown,
  Calendar,
  CloudRain,
  Sun,
  Wind,
  AlertTriangle,
  CheckCircle,
  XCircle,
  BarChart3,
  Download,
  RefreshCcw,
} from 'lucide-react';
import { API_BASE_URL } from '../config';

interface StationReport {
  id: number;
  date_bulletin: string;
  tmin_obs: number | null;
  tmax_obs: number | null;
  weather_obs: string | null;
  tmin_prev: number | null;
  tmax_prev: number | null;
  weather_prev: string | null;
  interpretation_moore: string | null;
  interpretation_dioula: string | null;
  interpretation_francais: string | null;
}

interface StationDetail {
  id: number;
  name: string;
  latitude: number | null;
  longitude: number | null;
  x_rel: number | null;
  y_rel: number | null;
  reports: StationReport[];
  metrics: {
    total_reports: number;
    avg_tmin: number | null;
    avg_tmax: number | null;
    icon_accuracy: number | null;
    tmin_mae: number | null;
    tmax_mae: number | null;
  };
}

const WeatherIcon: React.FC<{ weather: string | null }> = ({ weather }) => {
  const w = (weather || '').toUpperCase();
  if (w.includes('TSRA') || w.includes('PLUIE') || w.includes('ORAGE')) {
    return <CloudRain className="w-5 h-5 text-blue-500" />;
  }
  if (w.includes('DUFU') || w.includes('POUSSIERE')) {
    return <Wind className="w-5 h-5 text-yellow-600" />;
  }
  return <Sun className="w-5 h-5 text-yellow-400" />;
};

const AccuracyBadge: React.FC<{ value: number | null }> = ({ value }) => {
  if (value === null) return <span className="text-gray-400">N/A</span>;
  
  const color = value >= 80 ? 'bg-green-100 text-green-700' :
                value >= 60 ? 'bg-yellow-100 text-yellow-700' :
                'bg-red-100 text-red-700';
  
  return (
    <span className={`px-2 py-1 rounded-full text-sm font-medium ${color}`}>
      {value.toFixed(1)}%
    </span>
  );
};

const StatCard: React.FC<{
  title: string;
  value: string | number;
  subtitle?: string;
  icon: React.ReactNode;
  trend?: 'up' | 'down' | null;
}> = ({ title, value, subtitle, icon, trend }) => (
  <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5 hover:shadow-md transition-shadow">
    <div className="flex items-start justify-between">
      <div>
        <p className="text-sm text-gray-500 mb-1">{title}</p>
        <p className="text-2xl font-bold text-gray-900">{value}</p>
        {subtitle && <p className="text-xs text-gray-400 mt-1">{subtitle}</p>}
      </div>
      <div className="p-3 rounded-lg bg-gradient-to-br from-blue-50 to-indigo-50">
        {icon}
      </div>
    </div>
    {trend && (
      <div className={`mt-3 flex items-center text-sm ${trend === 'up' ? 'text-green-600' : 'text-red-600'}`}>
        {trend === 'up' ? <TrendingUp className="w-4 h-4 mr-1" /> : <TrendingDown className="w-4 h-4 mr-1" />}
        <span>{trend === 'up' ? 'En amélioration' : 'En baisse'}</span>
      </div>
    )}
  </div>
);

const StationDetailPage: React.FC = () => {
  const { stationId } = useParams<{ stationId: string }>();
  const navigate = useNavigate();
  const [station, setStation] = useState<StationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedPeriod, setSelectedPeriod] = useState<'7d' | '30d' | 'all'>('30d');

  useEffect(() => {
    fetchStationDetail();
  }, [stationId]);

  const fetchStationDetail = async () => {
    try {
      setLoading(true);
      setError(null);
      
      // Fetch station info
      const stationRes = await fetch(`${API_BASE_URL}/api/v1/stations/${stationId}`);
      if (!stationRes.ok) throw new Error('Station non trouvée');
      const stationData = await stationRes.json();
      
      // Fetch station reports
      const reportsRes = await fetch(`${API_BASE_URL}/api/v1/stations/${stationId}/reports?limit=100`);
      const reportsData = reportsRes.ok ? await reportsRes.json() : { items: [] };
      
      // Calculate metrics
      const reports = reportsData.items || [];
      const validTmin = reports.filter((r: StationReport) => r.tmin_obs !== null);
      const validTmax = reports.filter((r: StationReport) => r.tmax_obs !== null);
      
      const metrics = {
        total_reports: reports.length,
        avg_tmin: validTmin.length > 0 
          ? validTmin.reduce((sum: number, r: StationReport) => sum + (r.tmin_obs || 0), 0) / validTmin.length 
          : null,
        avg_tmax: validTmax.length > 0 
          ? validTmax.reduce((sum: number, r: StationReport) => sum + (r.tmax_obs || 0), 0) / validTmax.length 
          : null,
        icon_accuracy: calculateIconAccuracy(reports),
        tmin_mae: calculateMAE(reports, 'tmin'),
        tmax_mae: calculateMAE(reports, 'tmax'),
      };
      
      setStation({
        ...stationData,
        reports,
        metrics,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erreur de chargement');
    } finally {
      setLoading(false);
    }
  };

  const calculateIconAccuracy = (reports: StationReport[]): number | null => {
    const validReports = reports.filter(r => r.weather_obs && r.weather_prev);
    if (validReports.length === 0) return null;
    
    const correct = validReports.filter(r => {
      const obs = normalizeWeather(r.weather_obs);
      const prev = normalizeWeather(r.weather_prev);
      return obs === prev;
    }).length;
    
    return (correct / validReports.length) * 100;
  };

  const calculateMAE = (reports: StationReport[], type: 'tmin' | 'tmax'): number | null => {
    const validReports = reports.filter(r => {
      const obs = type === 'tmin' ? r.tmin_obs : r.tmax_obs;
      const prev = type === 'tmin' ? r.tmin_prev : r.tmax_prev;
      return obs !== null && prev !== null;
    });
    
    if (validReports.length === 0) return null;
    
    const totalError = validReports.reduce((sum, r) => {
      const obs = type === 'tmin' ? r.tmin_obs! : r.tmax_obs!;
      const prev = type === 'tmin' ? r.tmin_prev! : r.tmax_prev!;
      return sum + Math.abs(obs - prev);
    }, 0);
    
    return totalError / validReports.length;
  };

  const normalizeWeather = (weather: string | null): string => {
    if (!weather) return 'NSW';
    const w = weather.toUpperCase();
    if (w.includes('TSRA') || w.includes('PLUIE') || w.includes('ORAGE')) return 'TSRA';
    if (w.includes('DUFU') || w.includes('POUSSIERE')) return 'DUFU';
    return 'NSW';
  };

  const filteredReports = useMemo(() => {
    if (!station?.reports) return [];
    
    const now = new Date();
    const reports = [...station.reports].sort((a, b) => 
      new Date(b.date_bulletin).getTime() - new Date(a.date_bulletin).getTime()
    );
    
    if (selectedPeriod === '7d') {
      const cutoff = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
      return reports.filter(r => new Date(r.date_bulletin) >= cutoff);
    }
    if (selectedPeriod === '30d') {
      const cutoff = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
      return reports.filter(r => new Date(r.date_bulletin) >= cutoff);
    }
    return reports;
  }, [station?.reports, selectedPeriod]);

  const exportCSV = () => {
    if (!station?.reports) return;
    
    const headers = ['Date', 'Tmin Obs', 'Tmax Obs', 'Météo Obs', 'Tmin Prévu', 'Tmax Prévu', 'Météo Prévue'];
    const rows = station.reports.map(r => [
      r.date_bulletin,
      r.tmin_obs ?? '',
      r.tmax_obs ?? '',
      r.weather_obs ?? '',
      r.tmin_prev ?? '',
      r.tmax_prev ?? '',
      r.weather_prev ?? '',
    ]);
    
    const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `station_${station.name.replace(/\s+/g, '_')}_reports.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (error || !station) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <AlertTriangle className="w-16 h-16 text-red-400 mx-auto mb-4" />
          <h2 className="text-xl font-semibold text-gray-700 mb-2">Erreur</h2>
          <p className="text-gray-500 mb-4">{error || 'Station non trouvée'}</p>
          <button
            onClick={() => navigate(-1)}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
          >
            Retour
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-blue-50/30">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <button
                onClick={() => navigate(-1)}
                className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
              >
                <ArrowLeft className="w-5 h-5 text-gray-600" />
              </button>
              <div>
                <h1 className="text-2xl font-bold text-gray-900">{station.name}</h1>
                {station.latitude && station.longitude && (
                  <p className="text-sm text-gray-500 flex items-center gap-1">
                    <MapPin className="w-4 h-4" />
                    {station.latitude.toFixed(4)}°N, {station.longitude.toFixed(4)}°W
                  </p>
                )}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={fetchStationDetail}
                className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
                title="Actualiser"
              >
                <RefreshCcw className="w-5 h-5 text-gray-600" />
              </button>
              <button
                onClick={exportCSV}
                className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors"
              >
                <Download className="w-4 h-4" />
                Export CSV
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Metrics Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <StatCard
            title="Total Relevés"
            value={station.metrics.total_reports}
            subtitle="Bulletins analysés"
            icon={<BarChart3 className="w-6 h-6 text-blue-600" />}
          />
          <StatCard
            title="Température Min Moyenne"
            value={station.metrics.avg_tmin !== null ? `${station.metrics.avg_tmin.toFixed(1)}°C` : 'N/A'}
            subtitle="Sur la période"
            icon={<TrendingDown className="w-6 h-6 text-blue-600" />}
          />
          <StatCard
            title="Température Max Moyenne"
            value={station.metrics.avg_tmax !== null ? `${station.metrics.avg_tmax.toFixed(1)}°C` : 'N/A'}
            subtitle="Sur la période"
            icon={<TrendingUp className="w-6 h-6 text-red-600" />}
          />
          <StatCard
            title="Précision Icônes"
            value={station.metrics.icon_accuracy !== null ? `${station.metrics.icon_accuracy.toFixed(1)}%` : 'N/A'}
            subtitle="Prévision vs Observation"
            icon={<CheckCircle className="w-6 h-6 text-green-600" />}
          />
        </div>

        {/* MAE Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
            <h3 className="text-sm font-medium text-gray-500 mb-3">Erreur Absolue Moyenne (MAE)</h3>
            <div className="grid grid-cols-2 gap-4">
              <div className="p-4 bg-blue-50 rounded-lg">
                <p className="text-sm text-blue-600 mb-1">Tmin</p>
                <p className="text-2xl font-bold text-blue-700">
                  {station.metrics.tmin_mae !== null ? `±${station.metrics.tmin_mae.toFixed(2)}°C` : 'N/A'}
                </p>
              </div>
              <div className="p-4 bg-red-50 rounded-lg">
                <p className="text-sm text-red-600 mb-1">Tmax</p>
                <p className="text-2xl font-bold text-red-700">
                  {station.metrics.tmax_mae !== null ? `±${station.metrics.tmax_mae.toFixed(2)}°C` : 'N/A'}
                </p>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
            <h3 className="text-sm font-medium text-gray-500 mb-3">Coordonnées sur Carte</h3>
            <div className="grid grid-cols-2 gap-4">
              <div className="p-4 bg-gray-50 rounded-lg">
                <p className="text-sm text-gray-600 mb-1">Position X (relative)</p>
                <p className="text-xl font-semibold text-gray-800">
                  {station.x_rel !== null ? `${(station.x_rel * 100).toFixed(1)}%` : 'Non défini'}
                </p>
              </div>
              <div className="p-4 bg-gray-50 rounded-lg">
                <p className="text-sm text-gray-600 mb-1">Position Y (relative)</p>
                <p className="text-xl font-semibold text-gray-800">
                  {station.y_rel !== null ? `${(station.y_rel * 100).toFixed(1)}%` : 'Non défini'}
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Reports Table */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
          <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-900">Historique des Relevés</h2>
            <div className="flex items-center gap-2">
              {(['7d', '30d', 'all'] as const).map((period) => (
                <button
                  key={period}
                  onClick={() => setSelectedPeriod(period)}
                  className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${
                    selectedPeriod === period
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  }`}
                >
                  {period === '7d' ? '7 jours' : period === '30d' ? '30 jours' : 'Tout'}
                </button>
              ))}
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Date</th>
                  <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">Tmin Obs</th>
                  <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">Tmax Obs</th>
                  <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">Météo Obs</th>
                  <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">Tmin Prévu</th>
                  <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">Tmax Prévu</th>
                  <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">Météo Prévue</th>
                  <th className="px-6 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">Précision</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filteredReports.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="px-6 py-8 text-center text-gray-500">
                      Aucun relevé pour cette période
                    </td>
                  </tr>
                ) : (
                  filteredReports.map((report, index) => {
                    const weatherMatch = normalizeWeather(report.weather_obs) === normalizeWeather(report.weather_prev);
                    
                    return (
                      <tr key={report.id || index} className="hover:bg-gray-50">
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="flex items-center gap-2">
                            <Calendar className="w-4 h-4 text-gray-400" />
                            <span className="text-sm font-medium text-gray-900">
                              {new Date(report.date_bulletin).toLocaleDateString('fr-FR')}
                            </span>
                          </div>
                        </td>
                        <td className="px-6 py-4 text-center">
                          <span className="text-sm text-blue-600 font-medium">
                            {report.tmin_obs !== null ? `${report.tmin_obs}°C` : '-'}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-center">
                          <span className="text-sm text-red-600 font-medium">
                            {report.tmax_obs !== null ? `${report.tmax_obs}°C` : '-'}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-center">
                          <div className="flex items-center justify-center gap-1">
                            <WeatherIcon weather={report.weather_obs} />
                            <span className="text-xs text-gray-500">{report.weather_obs || '-'}</span>
                          </div>
                        </td>
                        <td className="px-6 py-4 text-center">
                          <span className="text-sm text-blue-400">
                            {report.tmin_prev !== null ? `${report.tmin_prev}°C` : '-'}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-center">
                          <span className="text-sm text-red-400">
                            {report.tmax_prev !== null ? `${report.tmax_prev}°C` : '-'}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-center">
                          <div className="flex items-center justify-center gap-1">
                            <WeatherIcon weather={report.weather_prev} />
                            <span className="text-xs text-gray-500">{report.weather_prev || '-'}</span>
                          </div>
                        </td>
                        <td className="px-6 py-4 text-center">
                          {report.weather_obs && report.weather_prev ? (
                            weatherMatch ? (
                              <CheckCircle className="w-5 h-5 text-green-500 mx-auto" />
                            ) : (
                              <XCircle className="w-5 h-5 text-red-400 mx-auto" />
                            )
                          ) : (
                            <span className="text-gray-300">-</span>
                          )}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          {filteredReports.length > 0 && (
            <div className="px-6 py-4 bg-gray-50 border-t border-gray-100">
              <p className="text-sm text-gray-500">
                Affichage de {filteredReports.length} relevé(s) sur {station.metrics.total_reports} au total
              </p>
            </div>
          )}
        </div>

        {/* Interpretations Section */}
        {filteredReports.length > 0 && filteredReports[0].interpretation_francais && (
          <div className="mt-6 bg-white rounded-xl shadow-sm border border-gray-100 p-6">
            <h3 className="text-lg font-semibold text-gray-900 mb-4">Dernière Interprétation</h3>
            <div className="space-y-3">
              {filteredReports[0].interpretation_francais && (
                <div className="p-4 bg-blue-50 rounded-lg">
                  <p className="text-sm font-medium text-blue-600 mb-1">Français</p>
                  <p className="text-gray-700">{filteredReports[0].interpretation_francais}</p>
                </div>
              )}
              {filteredReports[0].interpretation_moore && (
                <div className="p-4 bg-green-50 rounded-lg">
                  <p className="text-sm font-medium text-green-600 mb-1">Mooré</p>
                  <p className="text-gray-700">{filteredReports[0].interpretation_moore}</p>
                </div>
              )}
              {filteredReports[0].interpretation_dioula && (
                <div className="p-4 bg-yellow-50 rounded-lg">
                  <p className="text-sm font-medium text-yellow-600 mb-1">Dioula</p>
                  <p className="text-gray-700">{filteredReports[0].interpretation_dioula}</p>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default StationDetailPage;
