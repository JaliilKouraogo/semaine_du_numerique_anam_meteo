import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Download, Search } from 'lucide-react';

import { getStations } from '../services/api';

const getStationName = (station) =>
  station?.name || station?.nom || 'Station';

const Stations = () => {
  const navigate = useNavigate();
  const [stations, setStations] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const loadStations = async () => {
      setLoading(true);
      setError('');
      try {
        const response = await getStations({ limit: 500 });
        setStations(response.data || []);
      } catch (err) {
        console.error(err);
        setError('Impossible de charger les stations.');
      } finally {
        setLoading(false);
      }
    };

    loadStations();
  }, []);

  const filteredStations = useMemo(() => {
    const term = searchTerm.trim().toLowerCase();
    if (!term) return stations;
    return stations.filter((station) => {
      const name = getStationName(station).toLowerCase();
      return name.includes(term);
    });
  }, [stations, searchTerm]);

  const handleExport = () => {
    const header = [
      'Nom',
      'Latitude',
      'Longitude',
      'Tmin_prev',
      'Tmax_prev',
      'Tmin_obs',
      'Tmax_obs',
      'Créé le',
    ].join(',');
    const rows = filteredStations.map((station) =>
      [
        getStationName(station),
        station.latitude ?? '',
        station.longitude ?? '',
        station.Tmin_prev ?? '',
        station.Tmax_prev ?? '',
        station.Tmin_obs ?? '',
        station.Tmax_obs ?? '',
        station.created_at ?? '',
      ].join(','),
    );
    const csv = [header, ...rows].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'stations.csv';
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">
          Stations météorologiques
        </h1>
        <button
          onClick={handleExport}
          className="flex items-center space-x-2 px-4 py-2 bg-primary text-white rounded-lg hover:bg-blue-700 transition-colors font-medium"
        >
          <Download className="w-4 h-4" />
          <span>Exporter CSV</span>
        </button>
      </div>

      {error && (
        <div className="bg-red-50 text-red-700 px-4 py-3 rounded-lg border border-red-100">
          {error}
        </div>
      )}

      <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
            <input
              type="text"
              placeholder="Rechercher une station..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary focus:border-transparent"
            />
          </div>
          <p className="text-sm text-gray-500 self-center">
            {filteredStations.length} station(s) affichée(s)
          </p>
        </div>
      </div>

      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase tracking-wider">
                  Station
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase tracking-wider">
                  Coordonnées
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase tracking-wider">
                  Prévisions (Tmin/Tmax)
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase tracking-wider">
                  Observations (Tmin/Tmax)
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase tracking-wider">
                  Dernière mise à jour
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {loading && (
                <tr>
                  <td
                    colSpan="4"
                    className="px-6 py-4 text-center text-sm text-gray-500"
                  >
                    Chargement...
                  </td>
                </tr>
              )}
              {!loading &&
                filteredStations.map((station) => (
                  <tr
                    key={station.id}
                    className="hover:bg-gray-50 transition-colors"
                  >
                    <td className="px-6 py-4 text-sm font-medium text-gray-900">
                      {getStationName(station)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                      {station.latitude != null && station.longitude != null
                        ? `${station.latitude.toFixed(3)}, ${station.longitude.toFixed(
                            3,
                          )}`
                        : 'N/A'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                      <div className="text-gray-500 text-xs uppercase">Prévisions</div>
                      <div>Tmin: {station.Tmin_prev ?? '—'}°C</div>
                      <div>Tmax: {station.Tmax_prev ?? '—'}°C</div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                      <div className="text-gray-500 text-xs uppercase">Observations</div>
                      <div>Tmin: {station.Tmin_obs ?? '—'}°C</div>
                      <div>Tmax: {station.Tmax_obs ?? '—'}°C</div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                      {station.updated_at
                        ? new Date(station.updated_at).toLocaleString('fr-FR')
                        : 'N/A'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm">
                      <button
                        onClick={() => navigate(`/station/${station.id}`)}
                        className="text-primary hover:text-blue-700 font-medium"
                      >
                        Voir détails
                      </button>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default Stations;
