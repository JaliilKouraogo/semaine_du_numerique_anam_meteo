import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Eye } from 'lucide-react';

import KPICard from '../components/KPICard';
import MapStationMarker from '../components/MapStationMarker';
import {
  getAllMerged,
  getBulletins,
  getEvaluationMetrics,
  getStations,
  getStatsOverview,
} from '../services/api';
import { buildEvaluationDataset } from '../utils/dataTransforms';

const Dashboard = () => {
  const navigate = useNavigate();
  const [kpis, setKpis] = useState(null);
  const [bulletins, setBulletins] = useState([]);
  const [stations, setStations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const loadData = async () => {
      setLoading(true);
      setError('');
      try {
        const [statsRes, bulletinsRes, stationsRes, mergedRes, evalRes] =
          await Promise.all([
            getStatsOverview(),
            getBulletins({ limit: 6 }),
            getStations({ limit: 100 }),
            getAllMerged().catch(() => ({ data: {} })),
            getEvaluationMetrics().catch(() => ({ data: {} })),
          ]);

        const stats = statsRes.data || {};
        const evalMetrics = evalRes.data || {};
        const derivedMetrics = buildEvaluationDataset(mergedRes.data || {});

        setKpis({
          bulletinsIngeres24h: stats.bulletins || 0,
          stationsCouvertes: stats.stations || 0,
          maeMoyenTmax:
            evalMetrics.Tmax_MAE ?? derivedMetrics.global_mae_tmax ?? 0,
          accuracyTempsSensible:
            evalMetrics.Icon_accuracy ?? derivedMetrics.icon_accuracy ?? 0,
          delaiMoyenIngestion: stats.latest_bulletin ? 0 : 0,
        });

        setBulletins(bulletinsRes.data || []);
        setStations(stationsRes.data || []);
      } catch (err) {
        console.error(err);
        setError("Impossible de charger les données du dashboard.");
      } finally {
        setLoading(false);
      }
    };

    loadData();
  }, []);

  const resolvedKpis = kpis || {
    bulletinsIngeres24h: 0,
    stationsCouvertes: 0,
    maeMoyenTmax: 0,
    accuracyTempsSensible: 0,
    delaiMoyenIngestion: 0,
  };

  return (
    <div className="space-y-6">
      {error && (
        <div className="bg-red-50 text-red-700 px-4 py-3 rounded-lg border border-red-100">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
        <KPICard
          title="Bulletins ingérés (base)"
          value={resolvedKpis.bulletinsIngeres24h}
          delta24h={0}
          unit=""
        />
        <KPICard
          title="Stations couvertes"
          value={resolvedKpis.stationsCouvertes}
          delta24h={0}
          unit=""
        />
        <KPICard
          title="MAE moyen (Tmax)"
          value={resolvedKpis.maeMoyenTmax.toFixed(2)}
          delta24h={0}
          unit="°C"
        />
        <KPICard
          title="Accuracy temps sensible"
          value={(resolvedKpis.accuracyTempsSensible * 100 || 0).toFixed(0)}
          delta24h={0}
          unit="%"
        />
        <KPICard
          title="Délai moyen d'ingestion"
          value={resolvedKpis.delaiMoyenIngestion}
          delta24h={0}
          unit=""
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div>
          <h2 className="text-xl font-semibold text-gray-900 mb-4">
            Carte des stations
          </h2>
          <MapStationMarker
            stations={stations}
            onMarkerClick={(station) =>
              navigate(`/station/${station.id ?? station.name}`)
            }
          />
        </div>

        <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
          <h2 className="text-xl font-semibold text-gray-900 mb-4">
            Bulletins récents
          </h2>
          <div className="space-y-3">
            {loading && bulletins.length === 0 && (
              <p className="text-sm text-gray-500">
                Chargement des bulletins...
              </p>
            )}
            {bulletins.map((bulletin) => (
              <div
                key={bulletin.id}
                className="flex items-center justify-between p-3 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
              >
                <div>
                  <p className="font-medium text-gray-900">
                    {bulletin.source_pdf ||
                      bulletin.map1_image ||
                      `Bulletin #${bulletin.id}`}
                  </p>
                  <p className="text-sm text-gray-500">
                    {new Date(bulletin.date_bulletin).toLocaleDateString(
                      'fr-FR',
                    )}{' '}
                    • {bulletin.station_count} station(s)
                  </p>
                </div>
                <button
                  onClick={() => navigate(`/bulletin?id=${bulletin.id}`)}
                  className="p-2 text-primary hover:bg-primary/10 rounded-lg transition-colors"
                >
                  <Eye className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="bg-white rounded-2xl p-6 shadow-sm border border-gray-100">
        <h2 className="text-xl font-semibold text-gray-900 mb-4">
          Automatisation de la collecte
        </h2>
        <p className="text-gray-600 mb-4">
          Pour intégrer de nouveaux bulletins, lancez le script
          d&apos;automatisation côté serveur&nbsp;:
        </p>
        <pre className="bg-gray-900 text-gray-100 rounded-xl p-4 text-sm overflow-auto">
python automate_pipeline.py --api-url http://127.0.0.1:8000
        </pre>
        <p className="text-gray-600 mt-4">
          Ce script enchaîne le scraping, la conversion, l&apos;extraction Qwen /
          OCR et l&apos;import dans l&apos;API. Le dashboard se met ensuite à jour
          automatiquement en lisant les données persistées en SQLite.
        </p>
      </div>
    </div>
  );
};

export default Dashboard;
