import React, { useEffect, useState } from 'react';
import { getBulletin, getBulletins, getMergedFilePreview } from '../services/api';

const Bulletin = () => {
  const [bulletins, setBulletins] = useState([]);
  const [selectedBulletin, setSelectedBulletin] = useState(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState('');

  const fetchBulletins = async () => {
    setLoading(true);
    setError('');
    try {
      const response = await getBulletins({ limit: 100 });
      setBulletins(response.data || []);
    } catch (err) {
      console.error(err);
      setError("Impossible de charger les bulletins.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBulletins();
  }, []);

  const handleSelectBulletin = async (id) => {
    setDetailLoading(true);
    setPreview(null);
    try {
      const response = await getBulletin(id);
      setSelectedBulletin(response.data);
      const sourcePath = response.data.source_pdf;
      if (sourcePath) {
        try {
          const previewResponse = await getMergedFilePreview(sourcePath);
          setPreview({
            path: previewResponse.data.path,
            raw: JSON.stringify(previewResponse.data.content, null, 2),
          });
        } catch (previewErr) {
          console.error(previewErr);
          setPreview(null);
        }
      } else {
        setPreview(null);
      }
    } catch (err) {
      console.error(err);
      setSelectedBulletin(null);
      setPreview(null);
    } finally {
      setDetailLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Bulletins ingérés</h1>

      <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
        <h2 className="text-lg font-semibold text-gray-900 mb-2">
          Ajouter de nouveaux bulletins
        </h2>
        <p className="text-gray-600">
          L&apos;ingestion se fait via le script{' '}
          <code className="bg-gray-100 px-2 py-1 rounded">automate_pipeline.py</code>.
          Une fois l&apos;extraction terminée et les fichiers fusionnés importés, ils apparaîtront
          automatiquement dans la liste ci-dessous.
        </p>
      </div>

      {error && (
        <div className="bg-red-50 text-red-700 px-4 py-3 rounded-lg border border-red-100">
          {error}
        </div>
      )}

      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="p-6 border-b border-gray-200 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-900">Liste des bulletins</h2>
          <button
            onClick={fetchBulletins}
            className="text-primary hover:underline text-sm font-medium"
          >
            Actualiser
          </button>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase">Date</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase">Stations</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase">Source</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-700 uppercase">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {loading && (
                <tr>
                  <td colSpan="4" className="px-6 py-4 text-center text-sm text-gray-500">
                    Chargement...
                  </td>
                </tr>
              )}
              {!loading &&
                bulletins.map((bulletin) => (
                  <tr key={bulletin.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 text-sm text-gray-900">
                      {new Date(bulletin.date_bulletin).toLocaleDateString('fr-FR')}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-600">{bulletin.station_count}</td>
                    <td className="px-6 py-4 text-sm text-gray-600 break-all">
                      {bulletin.source_pdf || 'N/A'}
                    </td>
                    <td className="px-6 py-4 text-sm">
                      <button
                        onClick={() => handleSelectBulletin(bulletin.id)}
                        className="text-primary hover:text-blue-700 font-medium"
                      >
                        Voir
                      </button>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </div>

      {selectedBulletin && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
          <div className="bg-white rounded-2xl shadow-xl max-w-4xl w-full max-h-[90vh] overflow-hidden">
            <div className="p-6 border-b border-gray-200 flex items-center justify-between">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">
                  Bulletin du {new Date(selectedBulletin.date_bulletin).toLocaleDateString('fr-FR')}
                </h2>
                <p className="text-sm text-gray-500">
                  {selectedBulletin.station_count} station(s) • Source: {selectedBulletin.source_pdf || 'N/A'}
                </p>
                {preview?.path && (
                  <p className="text-xs text-gray-400 mt-1">
                    {preview.path}
                  </p>
                )}
              </div>
              <div className="flex items-center space-x-3">
                {detailLoading && <span className="text-sm text-gray-500">Chargement...</span>}
                <button
                  onClick={() => {
                    setSelectedBulletin(null);
                    setPreview(null);
                  }}
                  className="text-sm px-4 py-2 rounded-lg border border-gray-300 hover:bg-gray-50"
                >
                  Fermer
                </button>
              </div>
            </div>
            <div className="max-h-[70vh] overflow-auto p-6">
              <h3 className="text-base font-semibold text-gray-900 mb-4">Stations</h3>
              <table className="w-full text-sm">
                <thead className="bg-gray-50 border-b border-gray-200 sticky top-0">
                  <tr>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-700 uppercase">Station</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-700 uppercase">Coordonnées</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-700 uppercase">Observations</th>
                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-700 uppercase">Prévisions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {selectedBulletin.stations?.map((station) => (
                    <tr key={`${station.station?.id}-${station.id}`}>
                      <td className="px-3 py-2 font-medium text-gray-900">
                        {station.station?.name || station.station?.nom || station.nom || 'Station'}
                      </td>
                      <td className="px-3 py-2 text-gray-600">
                        {station.station?.latitude != null && station.station?.longitude != null
                          ? `${station.station.latitude.toFixed(3)}, ${station.station.longitude.toFixed(3)}`
                          : 'N/A'}
                      </td>
                      <td className="px-3 py-2 text-gray-600">
                        <div>Tmin: {station.Tmin_obs ?? '—'}°C</div>
                        <div>Tmax: {station.Tmax_obs ?? '—'}°C</div>
                        <div>{station.temps_obs || '—'}</div>
                      </td>
                      <td className="px-3 py-2 text-gray-600">
                        <div>Tmin: {station.Tmin_prev ?? '—'}°C</div>
                        <div>Tmax: {station.Tmax_prev ?? '—'}°C</div>
                        <div>{station.temps_prev || '—'}</div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Bulletin;
