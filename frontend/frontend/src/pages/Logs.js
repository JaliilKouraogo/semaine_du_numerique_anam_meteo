import React, { useEffect, useState } from 'react';
import { Clock, CheckCircle2, XCircle, AlertCircle } from 'lucide-react';
import { getBulletins } from '../services/api';

const Logs = () => {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    const loadLogs = async () => {
      setLoading(true);
      setError('');
      try {
        const response = await getBulletins({ limit: 50 });
        const bulletins = response.data || [];
        const transformed = bulletins.map((bulletin) => ({
          id: bulletin.id,
          job_type: 'ingestion',
          status: 'done',
          filename: bulletin.source_pdf || bulletin.map1_image || `Bulletin #${bulletin.id}`,
          started_at: bulletin.created_at || bulletin.date_bulletin,
          completed_at: bulletin.updated_at || bulletin.date_bulletin,
          logs: [
            {
              level: 'info',
              message: `${bulletin.station_count} station(s) détectée(s)`,
              timestamp: bulletin.date_bulletin,
            },
            {
              level: 'success',
              message: 'Données fusionnées et sauvegardées',
              timestamp: bulletin.updated_at || bulletin.date_bulletin,
            },
          ],
        }));
        setLogs(transformed);
      } catch (err) {
        console.error(err);
        setError("Impossible de charger l'historique.");
      } finally {
        setLoading(false);
      }
    };

    loadLogs();
  }, []);

  const getStatusIcon = (status) => {
    switch (status) {
      case 'done':
        return <CheckCircle2 className="w-5 h-5 text-success" />;
      case 'failed':
        return <XCircle className="w-5 h-5 text-danger" />;
      case 'processing':
        return <Clock className="w-5 h-5 text-primary animate-spin" />;
      default:
        return <AlertCircle className="w-5 h-5 text-gray-400" />;
    }
  };

  const getLogIcon = (level) => {
    switch (level) {
      case 'success':
        return <CheckCircle2 className="w-4 h-4 text-success" />;
      case 'error':
        return <XCircle className="w-4 h-4 text-danger" />;
      case 'warning':
        return <AlertCircle className="w-4 h-4 text-yellow-600" />;
      default:
        return <Clock className="w-4 h-4 text-gray-400" />;
    }
  };

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-gray-900">Logs et re-processing</h1>
      {error && (
        <div className="bg-red-50 text-red-700 px-4 py-3 rounded-lg border border-red-100">
          {error}
        </div>
      )}
      <div className="bg-white rounded-2xl shadow-sm border border-gray-100 overflow-hidden">
        <div className="p-6 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">Jobs d'ingestion</h2>
        </div>
        <div className="divide-y divide-gray-200">
          {loading && (
            <div className="p-6 text-sm text-gray-500">Chargement...</div>
          )}
          {!loading && logs.length === 0 && (
            <div className="p-6 text-sm text-gray-500">
              Aucun bulletin importé pour le moment.
            </div>
          )}
          {logs.map((log) => (
            <div key={log.id} className="p-6">
              <div className="flex items-start justify-between mb-4">
                <div className="flex items-center space-x-3">
                  {getStatusIcon(log.status)}
                  <div>
                    <p className="font-medium text-gray-900">{log.filename}</p>
                    <p className="text-sm text-gray-500">
                      {log.job_type} • {new Date(log.started_at).toLocaleString('fr-FR')}
                    </p>
                  </div>
                </div>
                <span
                  className={`px-3 py-1 rounded-full text-xs font-medium ${
                    log.status === 'done'
                      ? 'bg-green-100 text-green-700'
                      : log.status === 'failed'
                      ? 'bg-red-100 text-red-700'
                      : 'bg-yellow-100 text-yellow-700'
                  }`}
                >
                  {log.status}
                </span>
              </div>

              <div className="bg-gray-50 rounded-lg p-4 space-y-2 max-h-64 overflow-y-auto">
                {log.logs.map((entry, idx) => (
                  <div key={idx} className="flex items-start space-x-2 text-sm">
                    {getLogIcon(entry.level)}
                    <span className="text-gray-500">
                      {new Date(entry.timestamp).toLocaleTimeString('fr-FR')}
                    </span>
                    <span
                      className={`flex-1 ${
                        entry.level === 'error'
                          ? 'text-danger'
                          : entry.level === 'warning'
                          ? 'text-yellow-600'
                          : entry.level === 'success'
                          ? 'text-success'
                          : 'text-gray-700'
                      }`}
                    >
                      {entry.message}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default Logs;

