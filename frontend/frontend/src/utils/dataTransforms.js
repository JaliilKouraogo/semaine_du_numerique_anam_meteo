const MONTHS_FR = {
  janvier: '01',
  fevrier: '02',
  février: '02',
  mars: '03',
  avril: '04',
  mai: '05',
  juin: '06',
  juillet: '07',
  aout: '08',
  août: '08',
  septembre: '09',
  octobre: '10',
  novembre: '11',
  decembre: '12',
  décembre: '12',
};

const normalizeLabel = (label) =>
  typeof label === 'string'
    ? label.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
    : label;

export const parseBulletinDate = (label) => {
  if (!label) return null;
  const isoMatch = label.match(/(20\d{2}-\d{2}-\d{2})/);
  if (isoMatch) return isoMatch[1];

  const frMatch = label
    .normalize('NFD')
    .match(/(\d{1,2})\s*([a-zA-Zéèêûôîïùà]+)\s*(20\d{2})/i);
  if (frMatch) {
    const day = frMatch[1].padStart(2, '0');
    const month = MONTHS_FR[frMatch[2].toLowerCase()] || '01';
    const year = frMatch[3];
    return `${year}-${month}-${day}`;
  }
  return label;
};

const ensureNumber = (value) => {
  if (value === null || value === undefined) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

export const buildEvaluationDataset = (payload = {}) => {
  const bulletins = payload.bulletins || [];
  const stationStats = new Map();
  const trend = [];
  const iconPairs = [];
  let totalDiff = 0;
  let totalSq = 0;
  let totalCount = 0;

  bulletins.forEach((bulletin, idx) => {
    const dateKey = parseBulletinDate(bulletin.date_bulletin) || `bulletin-${idx + 1}`;
    let sum = 0;
    let count = 0;

    (bulletin.stations || []).forEach((station) => {
      const tmaxObs = ensureNumber(station.Tmax_obs);
      const tmaxPrev = ensureNumber(station.Tmax_prev);
      const key = station.nom?.trim().toUpperCase();

      if (tmaxObs !== null && tmaxPrev !== null) {
        const diff = tmaxObs - tmaxPrev;
        sum += Math.abs(diff);
        count += 1;
        totalDiff += Math.abs(diff);
        totalSq += diff * diff;
        totalCount += 1;

        if (!stationStats.has(key)) {
          stationStats.set(key, {
            name: station.nom,
            lat: station.latitude,
            lon: station.longitude,
            sum: 0,
            count: 0,
          });
        }
        const current = stationStats.get(key);
        current.sum += Math.abs(diff);
        current.count += 1;
      }

      const tempsObs = normalizeLabel(station.temps_obs);
      const tempsPrev = normalizeLabel(station.temps_prev);
      if (tempsObs && tempsPrev) {
        iconPairs.push([tempsObs, tempsPrev]);
      }
    });

    if (count > 0) {
      trend.push({
        date: dateKey,
        mae: sum / count,
      });
    }
  });

  const heatmap = Array.from(stationStats.values()).map((st, idx) => ({
    id: idx + 1,
    name: st.name,
    latitude: st.lat,
    longitude: st.lon,
    mae: st.count ? st.sum / st.count : null,
    mae_tmax: st.count ? st.sum / st.count : null,
    count: st.count,
  }));

  const labels = Array.from(
    new Set(iconPairs.flat().map((label) => label || 'n/a')),
  );
  const matrix = labels.map(() => Array(labels.length).fill(0));
  let iconMatches = 0;

  iconPairs.forEach(([obs, prev]) => {
    const obsIdx = labels.indexOf(obs || 'n/a');
    const prevIdx = labels.indexOf(prev || 'n/a');
    if (obsIdx >= 0 && prevIdx >= 0) {
      matrix[obsIdx][prevIdx] += 1;
    }
    if (obs && prev && obs === prev) {
      iconMatches += 1;
    }
  });

  return {
    stations_heatmap: heatmap,
    trend_mae: trend,
    confusion_matrix: {
      labels: labels.length ? labels : ['n/a'],
      matrix: labels.length ? matrix : [[0]],
    },
    global_mae_tmax: totalCount ? totalDiff / totalCount : null,
    global_rmse_tmax: totalCount ? Math.sqrt(totalSq / totalCount) : null,
    icon_accuracy: iconPairs.length ? iconMatches / iconPairs.length : null,
  };
};
