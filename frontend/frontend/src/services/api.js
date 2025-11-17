import axios from 'axios';

const resolveApiBaseUrl = () => {
  const candidates = [];

  const envVal = (process.env.REACT_APP_API_URL || '').trim();
  if (envVal) {
    candidates.push(envVal);
  }

  if (typeof window !== 'undefined') {
    const { protocol, hostname } = window.location;
    const defaultPort = protocol === 'https:' ? 8443 : 8000;
    candidates.push(`${protocol}//${hostname}:${defaultPort}`);
    candidates.push(`${protocol}//${hostname}`);
  }

  candidates.push('http://localhost:8000');

  for (const candidate of candidates) {
    if (!candidate) continue;
    try {
      const normalized = new URL(candidate).toString().replace(/\/$/, '');
      return normalized;
    } catch (_) {
      // continue
    }
  }

  return 'http://localhost:8000';
};

const API_BASE_URL = resolveApiBaseUrl();

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Santé
export const pingHealth = () => api.get('/health');

// Statistiques globales
export const getStatsOverview = () => api.get('/stats/overview');

// Bulletins
export const getBulletins = (params = {}) =>
  api.get('/bulletins', { params });

export const getBulletin = (id) => api.get(`/bulletins/${id}`);

export const deleteBulletin = (id) => api.delete(`/bulletins/${id}`);

export const getBulletinStations = (id) =>
  api.get(`/bulletins/${id}/stations`);

export const importBulletin = (payload) =>
  api.post('/bulletins/import', payload);

// Stations
export const getStations = (params = {}) =>
  api.get('/stations', { params });

export const getStation = (id) => api.get(`/stations/${id}`);

export const updateStation = (id, payload) =>
  api.patch(`/stations/${id}`, payload);

export const getStationReports = (id, params = {}) =>
  api.get(`/stations/${id}/reports`, { params });

// Exports / évaluation
export const getAllMerged = () => api.get('/exports/all-merged');

export const getEvaluationMetrics = () => api.get('/evaluation/metrics');
export const getMergedFilePreview = (path) =>
  api.get('/exports/merged-file', { params: { path } });


export default api;

