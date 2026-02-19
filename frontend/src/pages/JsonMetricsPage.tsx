import { useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import { Layout } from "../components/Layout";
import { ErrorPanel, LoadingPanel } from "../components/StatusPanel";
import {
    fetchJsonMetricsFile,
    fetchJsonMetricsFiles,
    type JsonMetricsFileInfo,
    type JsonMetricsFilePayload,
} from "../services/api";

type JsonStation = {
    nom?: string | null;
    tmin?: number | null;
    tmax?: number | null;
    weather_icon?: string | null;
};

type JsonEntry = {
    date: string;
    mapType: string;
    stations: JsonStation[];
    source: string;
};

type CsvRow = Record<string, string>;

type StationPair = {
    date: string;
    station: string;
    tminObs: number | null;
    tmaxObs: number | null;
    tminFore: number | null;
    tmaxFore: number | null;
    weatherObs: string | null;
    weatherFore: string | null;
};

type TemperatureMetrics = {
    mae_tmin?: number | null;
    mae_tmax?: number | null;
    rmse_tmin?: number | null;
    rmse_tmax?: number | null;
    bias_tmin?: number | null;
    bias_tmax?: number | null;
    temperature_sample_size?: number | null;
};

type WeatherMetrics = {
    accuracy_weather?: number | null;
    precision_weather?: number | null;
    recall_weather?: number | null;
    f1_score_weather?: number | null;
    weather_sample_size?: number | null;
    confusion_matrix?: {
        labels: string[];
        matrix: number[][];
    } | null;
};

type MetricsResult = TemperatureMetrics & WeatherMetrics;

type MetricsMode = "station" | "month" | "year";

const MODE_LABELS: Record<MetricsMode, string> = {
    station: "Par station",
    month: "Par mois",
    year: "Par année",
};

const formatNumber = (value?: number | null, decimals = 2) => {
    if (typeof value !== "number" || Number.isNaN(value)) return "--";
    return value.toFixed(decimals);
};

const formatScore = (value?: number | null, decimals = 3) => {
    if (typeof value !== "number" || Number.isNaN(value)) return "--";
    return value.toFixed(decimals);
};

const normalizeStation = (name?: string | null) => (name ?? "").trim();
const normalizeIconKey = (label?: string | null) =>
    (label ?? "")
        .normalize("NFD")
        .replace(/\p{Diacritic}/gu, "")
        .toLowerCase()
        .replace(/\s+/g, " ")
        .trim();

const ICON_NAME_TO_CODE: Record<string, string> = {
    // Pictogrammes météo standards
    "orages avec pluies isoles": "TSRA",
    "orages avec pluies isolés": "TSRA",
    "orages avec pluies": "TSRA",
    "pluies orageuses isolees": "TSRA",
    "pluies orageuses isolées": "TSRA",
    "pluie orageuse": "TSRA",
    "pluie": "RA",
    "pluies": "RA",
    "orage": "TS",
    "orages": "TS",
    "orages isoles": "TS",
    "orages isolés": "TS",
    "temps partiellement nuageux": "NSW",
    "temps nuageux": "NSW",
    "temps ensoleille": "NSW",
    "temps ensoleillé": "NSW",
    "ciel couvert": "NSW",
    "ciel dégagé": "NSW",
    "nuageux": "NSW",
    "ensoleillé": "NSW",
    "ensoleille": "NSW",
    "partiellement_nuageux": "NSW",

    // Pictogrammes avec poussière
    "orages avec pluies isoles avec poussiere": "DUTSRA",
    "orages avec pluies isolés avec poussière": "DUTSRA",
    "pluies avec poussiere": "DURA",
    "pluies avec poussière": "DURA",
    "orages isoles avec poussiere": "DUTS",
    "orages isolés avec poussière": "DUTS",
    "orages avec poussiere": "DUTS",
    "orages avec poussière": "DUTS",
    "temps partiellement nuageux avec poussiere": "DU",
    "temps partiellement nuageux avec poussière": "DU",
    "temps nuageux avec poussiere": "DU",
    "temps nuageux avec poussière": "DU",
    "temps ensoleille avec poussiere": "DU",
    "temps ensoleillé avec poussière": "DU",
    "poussiere": "DU",
    "poussière": "DU",
    "poussière en suspension": "DU",
    "ciel couvert avec poussière": "DU",
    "ciel nuageux avec poussière": "DU",
    "vent sable": "DU",
    "vent_sable": "DU",
};

const ICON_CODES = new Set([
    "TSRA",
    "RA",
    "TS",
    "NSW",
    "DUTSRA",
    "DURA",
    "DUTS",
    "DU",
]);
const ICON_CODE_ALIASES: Record<string, string> = {
    DUFUTSRA: "DUTSRA",
    DUFURA: "DURA",
};
const ICON_CODE_LIST = Array.from(ICON_CODES).sort();

const toIconCode = (label?: string | null) => {
    const trimmed = (label ?? "").trim();
    if (!trimmed) return "";
    const upper = trimmed.toUpperCase();
    if (ICON_CODE_ALIASES[upper]) {
        return ICON_CODE_ALIASES[upper];
    }
    if (ICON_CODES.has(upper)) {
        return upper;
    }
    const normalized = normalizeIconKey(trimmed);
    return ICON_NAME_TO_CODE[normalized] ?? "UNK";
};

const toCsvIconCode = (label?: string | null) => {
    const trimmed = (label ?? "").trim();
    if (!trimmed) return "";
    const upper = trimmed.toUpperCase();
    if (ICON_CODE_ALIASES[upper]) {
        return ICON_CODE_ALIASES[upper];
    }
    return ICON_CODES.has(upper) ? upper : "UNK";
};

const extractDateFromPayload = (payload: JsonMetricsFilePayload["data"]) => {
    const raw = payload?.date_bulletin ?? "";
    const match = raw.match(/Bulletin_du_(\d{2})_([A-Za-zÀ-ÿ]+)_(\d{4})/);
    if (!match) return null;
    const [, day, monthName, year] = match;
    const month = monthName
        .normalize("NFD")
        .replace(/\p{Diacritic}/gu, "")
        .toLowerCase();
    const months: Record<string, string> = {
        janvier: "01",
        fevrier: "02",
        mars: "03",
        avril: "04",
        mai: "05",
        juin: "06",
        juillet: "07",
        aout: "08",
        septembre: "09",
        octobre: "10",
        novembre: "11",
        decembre: "12",
    };
    const monthValue = months[month];
    if (!monthValue) return null;
    return `${year}-${monthValue}-${day}`;
};

const parseCsvLine = (line: string, delimiter: string) => {
    const values: string[] = [];
    let current = "";
    let inQuotes = false;
    for (let i = 0; i < line.length; i += 1) {
        const char = line[i];
        if (char === "\"") {
            if (inQuotes && line[i + 1] === "\"") {
                current += "\"";
                i += 1;
            } else {
                inQuotes = !inQuotes;
            }
            continue;
        }
        if (char === delimiter && !inQuotes) {
            values.push(current);
            current = "";
            continue;
        }
        current += char;
    }
    values.push(current);
    return values.map((value) => value.trim());
};

const parseCsvContent = (content: string): CsvRow[] => {
    const lines = content
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter((line) => line.length > 0);
    if (lines.length === 0) return [];
    const delimiter = lines[0].includes(";") ? ";" : ",";
    const headers = parseCsvLine(lines[0], delimiter).map((h) => h.toLowerCase());
    return lines.slice(1).map((line) => {
        const values = parseCsvLine(line, delimiter);
        const row: CsvRow = {};
        headers.forEach((header, idx) => {
            row[header] = values[idx] ?? "";
        });
        return row;
    });
};

const toNumber = (value: string) => {
    const normalized = value.replace(",", ".").trim();
    if (!normalized) return null;
    const parsed = Number(normalized);
    return Number.isNaN(parsed) ? null : parsed;
};

const parseMonthToken = (value: string) => {
    const trimmed = value.trim();
    if (!trimmed) return "";
    const numeric = Number(trimmed);
    if (!Number.isNaN(numeric) && numeric >= 1 && numeric <= 12) {
        return String(Math.trunc(numeric)).padStart(2, "0");
    }
    const normalized = trimmed
        .normalize("NFD")
        .replace(/\p{Diacritic}/gu, "")
        .toLowerCase();
    const monthMap: Record<string, string> = {
        janvier: "01",
        fevrier: "02",
        mars: "03",
        avril: "04",
        mai: "05",
        juin: "06",
        juillet: "07",
        aout: "08",
        septembre: "09",
        octobre: "10",
        novembre: "11",
        decembre: "12",
    };
    return monthMap[normalized] ?? "";
};

const csvRowsToEntries = (rows: CsvRow[], source: string): JsonEntry[] => {
    const grouped = new Map<string, JsonEntry>();
    rows.forEach((row) => {
        const year = row.annee || row.year || "";
        const monthToken = row.mois || row.month || "";
        const month = parseMonthToken(monthToken);
        const day = row.jour || row.day || "";
        const date =
            row.date ||
            row.bulletin_date ||
            row.date_bulletin ||
            (year && month && day
                ? `${year}-${month}-${String(day).padStart(2, "0")}`
                : "");
        const station =
            row.localites ||
            row.station ||
            row.nom ||
            row.name ||
            row.station_name ||
            row.stationnom ||
            "";

        const hasForecast = Boolean(row.previsions || row.tmin_prev || row.tmax_prev);
        const hasObserved = Boolean(row.observations || row.tmin_obs || row.tmax_obs);

        if (date && station && (hasForecast || hasObserved)) {
            if (hasObserved) {
                const keyObs = `${date}::observed`;
                const entryObs =
                    grouped.get(keyObs) ??
                    ({
                        date,
                        mapType: "observed",
                        stations: [],
                        source,
                    } as JsonEntry);
                entryObs.stations.push({
                    nom: station,
                    tmin: toNumber(row.tmin_obs || row.tmin || row.t_min || ""),
                    tmax: toNumber(row.tmax_obs || row.tmax || row.t_max || ""),
                    weather_icon: toCsvIconCode(
                        row.observations || row.weather_obs || row.weather_icon || "",
                    ),
                });
                grouped.set(keyObs, entryObs);
            }
            if (hasForecast) {
                const keyPrev = `${date}::forecast`;
                const entryPrev =
                    grouped.get(keyPrev) ??
                    ({
                        date,
                        mapType: "forecast",
                        stations: [],
                        source,
                    } as JsonEntry);
                entryPrev.stations.push({
                    nom: station,
                    tmin: toNumber(row.tmin_prev || row.tmin_fore || ""),
                    tmax: toNumber(row.tmax_prev || row.tmax_fore || ""),
                    weather_icon: toCsvIconCode(
                        row.previsions || row.weather_fore || row.weather_icon || "",
                    ),
                });
                grouped.set(keyPrev, entryPrev);
            }
            return;
        }

        const mapTypeRaw =
            row.map_type || row.type || row.map || row.mode || row.maptype || "";
        if (!date || !mapTypeRaw || !station) return;
        const mapType = mapTypeRaw.toLowerCase().trim();
        const key = `${date}::${mapType}`;
        const entry =
            grouped.get(key) ??
            ({
                date,
                mapType,
                stations: [],
                source,
            } as JsonEntry);
        entry.stations.push({
            nom: station,
            tmin: toNumber(row.tmin || row.t_min || row.min || ""),
            tmax: toNumber(row.tmax || row.t_max || row.max || ""),
            weather_icon: toCsvIconCode(
                row.weather_icon || row.icon || row.picto || row.weather || "",
            ),
        });
        grouped.set(key, entry);
    });
    return Array.from(grouped.values());
};

const shiftDate = (dateStr: string, days: number) => {
    const [yearStr, monthStr, dayStr] = dateStr.split("-");
    const year = Number(yearStr);
    const month = Number(monthStr);
    const day = Number(dayStr);
    if (!year || !month || !day) return null;
    const base = new Date(Date.UTC(year, month - 1, day));
    base.setUTCDate(base.getUTCDate() + days);
    const yyyy = base.getUTCFullYear();
    const mm = String(base.getUTCMonth() + 1).padStart(2, "0");
    const dd = String(base.getUTCDate()).padStart(2, "0");
    return `${yyyy}-${mm}-${dd}`;
};

const buildPairs = (entries: JsonEntry[], usePrevDay: boolean) => {
    const observedByDate = new Map<string, Map<string, JsonStation>>();
    const forecastByDate = new Map<string, Map<string, JsonStation>>();

    entries.forEach((entry) => {
        const dateKey = entry.date;
        if (!dateKey) return;
        const stationsMap = new Map<string, JsonStation>();
        entry.stations.forEach((station) => {
            const key = normalizeStation(station.nom);
            if (!key) return;
            stationsMap.set(key, station);
        });
        if (entry.mapType === "observed") {
            observedByDate.set(dateKey, stationsMap);
        } else if (entry.mapType === "forecast") {
            forecastByDate.set(dateKey, stationsMap);
        }
    });

    const pairs: StationPair[] = [];
    const skippedDates: Array<{ date: string; reason: string }> = [];
    observedByDate.forEach((observedStations, obsDate) => {
        const forecastDate = usePrevDay ? shiftDate(obsDate, -1) : obsDate;
        if (!forecastDate) {
            skippedDates.push({ date: obsDate, reason: "Date invalide" });
            return;
        }
        const forecastStations = forecastByDate.get(forecastDate);
        if (!forecastStations) {
            skippedDates.push({
                date: obsDate,
                reason: usePrevDay
                    ? `Prévision manquante (J-1: ${forecastDate})`
                    : "Prévision manquante (même jour)",
            });
            return;
        }
        observedStations.forEach((obs, station) => {
            const fore = forecastStations.get(station);
            if (!fore) return;
            pairs.push({
                date: obsDate,
                station,
                tminObs: typeof obs.tmin === "number" ? obs.tmin : null,
                tmaxObs: typeof obs.tmax === "number" ? obs.tmax : null,
                tminFore: typeof fore.tmin === "number" ? fore.tmin : null,
                tmaxFore: typeof fore.tmax === "number" ? fore.tmax : null,
                weatherObs: obs.weather_icon ?? null,
                weatherFore: fore.weather_icon ?? null,
            });
        });
    });

    return { pairs, skippedDates };
};

const computeTemperatureMetrics = (pairs: StationPair[]): TemperatureMetrics => {
    const tminPairs = pairs.filter((p) => p.tminObs !== null && p.tminFore !== null);
    const tmaxPairs = pairs.filter((p) => p.tmaxObs !== null && p.tmaxFore !== null);

    const mae = (values: number[]) => values.reduce((sum, val) => sum + val, 0) / values.length;
    const rmse = (values: number[]) =>
        Math.sqrt(values.reduce((sum, val) => sum + val * val, 0) / values.length);

    const metrics: TemperatureMetrics = {};

    if (tminPairs.length) {
        const errors = tminPairs.map((p) => (p.tminFore ?? 0) - (p.tminObs ?? 0));
        metrics.mae_tmin = mae(errors.map((e) => Math.abs(e)));
        metrics.rmse_tmin = rmse(errors);
        metrics.bias_tmin = mae(errors);
    }

    if (tmaxPairs.length) {
        const errors = tmaxPairs.map((p) => (p.tmaxFore ?? 0) - (p.tmaxObs ?? 0));
        metrics.mae_tmax = mae(errors.map((e) => Math.abs(e)));
        metrics.rmse_tmax = rmse(errors);
        metrics.bias_tmax = mae(errors);
    }

    metrics.temperature_sample_size = Math.min(
        tminPairs.length || tmaxPairs.length,
        tmaxPairs.length || tminPairs.length,
    );

    return metrics;
};

const computeWeatherMetrics = (pairs: StationPair[]): WeatherMetrics => {
    const filtered = pairs.filter((p) => p.weatherObs && p.weatherFore);
    if (!filtered.length) return {};

    const yTrueRaw = filtered.map((p) => toIconCode(p.weatherObs));
    const yPredRaw = filtered.map((p) => toIconCode(p.weatherFore));
    const validIndices = yTrueRaw
        .map((value, idx) => (value !== "UNK" && yPredRaw[idx] !== "UNK" ? idx : -1))
        .filter((idx) => idx >= 0);
    const yTrue = validIndices.map((idx) => yTrueRaw[idx]);
    const yPred = validIndices.map((idx) => yPredRaw[idx]);
    const hasUnknown = yTrueRaw.includes("UNK") || yPredRaw.includes("UNK");
    const labels = hasUnknown ? [...ICON_CODE_LIST, "UNK"] : [...ICON_CODE_LIST];
    const labelIndex = new Map(labels.map((label, idx) => [label, idx]));
    const matrix = Array.from({ length: labels.length }, () =>
        Array.from({ length: labels.length }, () => 0),
    );

    yTrue.forEach((label, idx) => {
        const row = labelIndex.get(label);
        const col = labelIndex.get(yPred[idx]);
        if (row === undefined || col === undefined) return;
        matrix[row][col] += 1;
    });

    const total = yTrue.length;
    let correct = 0;
    labels.forEach((_, idx) => {
        correct += matrix[idx][idx];
    });

    const support = labels.map(
        (label) => yTrue.filter((value) => value === label).length,
    );

    const precisionPerLabel = labels.map((_, idx) => {
        const colSum = matrix.reduce((sum, row) => sum + row[idx], 0);
        const tp = matrix[idx][idx];
        return colSum ? tp / colSum : 0;
    });

    const recallPerLabel = labels.map((_, idx) => {
        const rowSum = matrix[idx].reduce((sum, val) => sum + val, 0);
        const tp = matrix[idx][idx];
        return rowSum ? tp / rowSum : 0;
    });

    const f1PerLabel = precisionPerLabel.map((prec, idx) => {
        const rec = recallPerLabel[idx];
        return prec + rec === 0 ? 0 : (2 * prec * rec) / (prec + rec);
    });

    const weighted = (values: number[]) =>
        values.reduce((sum, value, idx) => sum + value * support[idx], 0) / total;

    return {
        accuracy_weather: correct / total,
        precision_weather: weighted(precisionPerLabel),
        recall_weather: weighted(recallPerLabel),
        f1_score_weather: weighted(f1PerLabel),
        weather_sample_size: total,
        confusion_matrix: {
            labels,
            matrix,
        },
    };
};

const computeMetrics = (pairs: StationPair[]): MetricsResult => {
    return {
        ...computeTemperatureMetrics(pairs),
        ...computeWeatherMetrics(pairs),
    };
};

type ContingencyScoreRow = {
    code: string;
    pod: number | null;
    far: number | null;
};

const computeContingencyScores = (pairs: StationPair[]) => {
    const filtered = pairs.filter((p) => p.weatherObs && p.weatherFore);
    if (!filtered.length) {
        return { pc: null as number | null, rows: [] as ContingencyScoreRow[] };
    }
    const yTrueRaw = filtered.map((p) => toIconCode(p.weatherObs));
    const yPredRaw = filtered.map((p) => toIconCode(p.weatherFore));
    const validIndices = yTrueRaw
        .map((value, idx) => (value !== "UNK" && yPredRaw[idx] !== "UNK" ? idx : -1))
        .filter((idx) => idx >= 0);
    const yTrue = validIndices.map((idx) => yTrueRaw[idx]);
    const yPred = validIndices.map((idx) => yPredRaw[idx]);
    if (!yTrue.length) {
        return { pc: null as number | null, rows: [] as ContingencyScoreRow[] };
    }

    const labels = [...ICON_CODE_LIST];
    const labelIndex = new Map(labels.map((label, idx) => [label, idx]));
    const matrix = Array.from({ length: labels.length }, () =>
        Array.from({ length: labels.length }, () => 0),
    );

    yTrue.forEach((label, idx) => {
        const row = labelIndex.get(label);
        const col = labelIndex.get(yPred[idx]);
        if (row === undefined || col === undefined) return;
        matrix[row][col] += 1;
    });

    const total = matrix.reduce(
        (sum, row) => sum + row.reduce((rowSum, value) => rowSum + value, 0),
        0,
    );
    const diag = labels.reduce((sum, _, i) => sum + (matrix[i]?.[i] ?? 0), 0);
    const pc = total > 0 ? (diag / total) * 100 : null;

    const rows = labels.map((label, idx) => {
        const oi = matrix[idx].reduce((sum, value) => sum + value, 0);
        const pi = matrix.reduce((sum, row) => sum + (row[idx] ?? 0), 0);
        const nii = matrix[idx]?.[idx] ?? 0;
        const pod = oi > 0 ? nii / oi : null;
        const rel = pi > 0 ? nii / pi : null;
        const far = rel !== null ? 1 - rel : null;
        return { code: label, pod, far };
    });

    return { pc, rows };
};

export function JsonMetricsPage() {
    const [files, setFiles] = useState<JsonMetricsFileInfo[]>([]);
    const [selectedPaths, setSelectedPaths] = useState<string[]>([]);
    const [fileFilter, setFileFilter] = useState("");
    const [loadingFiles, setLoadingFiles] = useState(false);
    const [loadingData, setLoadingData] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [jsonEntries, setJsonEntries] = useState<JsonEntry[]>([]);
    const [csvEntries, setCsvEntries] = useState<JsonEntry[]>([]);
    const [dataSource, setDataSource] = useState<"json" | "csv">("json");
    const [metricsMode, setMetricsMode] = useState<MetricsMode>("station");
    const [selectedStation, setSelectedStation] = useState<string>("");
    const [selectedMonth, setSelectedMonth] = useState<string>("");
    const [selectedYear, setSelectedYear] = useState<string>("");
    const [showSkippedDates, setShowSkippedDates] = useState<boolean>(false);
    const [csvArranged, setCsvArranged] = useState<boolean>(false);
    const [csvReadyEntries, setCsvReadyEntries] = useState<JsonEntry[]>([]);
    const [exporting, setExporting] = useState<boolean>(false);
    const tablesRef = useRef<HTMLDivElement | null>(null);
    const temperatureRef = useRef<HTMLDivElement | null>(null);
    const contingencyRef = useRef<HTMLDivElement | null>(null);
    const scoresRef = useRef<HTMLDivElement | null>(null);

    useEffect(() => {
        const loadFiles = async () => {
            try {
                setLoadingFiles(true);
                const payload = await fetchJsonMetricsFiles();
                setFiles(payload.files ?? []);
                setError(null);
            } catch (err) {
                console.error("Echec du chargement des fichiers JSON:", err);
                setError("Echec du chargement des fichiers JSON.");
            } finally {
                setLoadingFiles(false);
            }
        };
        loadFiles();
    }, []);

    const filteredFiles = useMemo(() => {
        const term = fileFilter.trim().toLowerCase();
        if (!term) return files;
        return files.filter((file) =>
            [file.name, file.path, file.date, file.map_type]
                .filter(Boolean)
                .some((value) => String(value).toLowerCase().includes(term)),
        );
    }, [files, fileFilter]);

    const allSelected =
        filteredFiles.length > 0 &&
        filteredFiles.every((file) => selectedPaths.includes(file.path));

    const handleToggleAll = () => {
        if (allSelected) {
            const remaining = selectedPaths.filter(
                (path) => !filteredFiles.find((file) => file.path === path),
            );
            setSelectedPaths(remaining);
        } else {
            const merged = new Set(selectedPaths);
            filteredFiles.forEach((file) => merged.add(file.path));
            setSelectedPaths(Array.from(merged));
        }
    };

    const handleToggleFile = (path: string) => {
        setSelectedPaths((prev) =>
            prev.includes(path) ? prev.filter((item) => item !== path) : [...prev, path],
        );
    };

    const handleLoadData = async () => {
        if (!selectedPaths.length) {
            setError("Sélectionnez au moins un fichier JSON.");
            return;
        }
        try {
            setLoadingData(true);
            const payloads = await Promise.all(
                selectedPaths.map((path) => fetchJsonMetricsFile(path)),
            );
            const normalized: JsonEntry[] = payloads
                .map((payload) => {
                    const data = payload.data ?? {};
                    const date = payload.data?.date_bulletin
                        ? extractDateFromPayload(payload.data)
                        : null;
                    const fallbackDate = files.find((file) => file.path === payload.path)?.date ?? null;
                    const normalizedDate = date ?? fallbackDate;
                    return {
                        date: normalizedDate ?? "",
                        mapType: (data.map_type ?? "").toLowerCase(),
                        stations: Array.isArray(data.stations) ? data.stations : [],
                        source: payload.path,
                    };
                })
                .filter((entry) => entry.date && entry.mapType);
            setJsonEntries(normalized);
            setError(null);
        } catch (err) {
            console.error("Echec du chargement des données JSON:", err);
            setError("Echec du chargement des données JSON.");
            setJsonEntries([]);
        } finally {
            setLoadingData(false);
        }
    };

    const processJsonFiles = async (filesList: FileList | File[]) => {
        if (!filesList || filesList.length === 0) return;
        const readers = Array.from(filesList).map(
            (file) =>
                new Promise<JsonMetricsFilePayload>((resolve, reject) => {
                    const reader = new FileReader();
                    reader.onload = () => {
                        try {
                            const payload = JSON.parse(String(reader.result ?? "{}"));
                            resolve({ path: `local:${file.name}`, data: payload });
                        } catch (err) {
                            reject(err);
                        }
                    };
                    reader.onerror = () => reject(reader.error);
                    reader.readAsText(file);
                }),
        );

        try {
            setLoadingData(true);
            const payloads = await Promise.all(readers);
            const normalized: JsonEntry[] = payloads
                .map((payload) => {
                    const data = payload.data ?? {};
                    const date = extractDateFromPayload(data);
                    return {
                        date: date ?? "",
                        mapType: (data.map_type ?? "").toLowerCase(),
                        stations: Array.isArray(data.stations) ? data.stations : [],
                        source: payload.path,
                    };
                })
                .filter((entry) => entry.date && entry.mapType);
            setJsonEntries((prev) => [...prev, ...normalized]);
            setError(null);
        } catch (err) {
            console.error("Echec du chargement local:", err);
            setError("Impossible de lire certains fichiers JSON locaux.");
        } finally {
            setLoadingData(false);
        }
    };

    const handleLocalUpload = async (event: ChangeEvent<HTMLInputElement>) => {
        await processJsonFiles(event.target.files ?? []);
        event.target.value = "";
    };

    const processCsvFiles = async (filesList: FileList | File[]) => {
        if (!filesList || filesList.length === 0) return;
        try {
            setLoadingData(true);
            const parsedEntries: JsonEntry[] = [];
            for (const file of Array.from(filesList)) {
                const content = await file.text();
                const rows = parseCsvContent(content);
                const entriesFromCsv = csvRowsToEntries(rows, `local:${file.name}`);
                parsedEntries.push(...entriesFromCsv);
            }
            if (parsedEntries.length === 0) {
                setError("Aucune donnée exploitable trouvée dans le CSV.");
            } else {
                setCsvEntries((prev) => [...prev, ...parsedEntries]);
                setSelectedStation("");
                setSelectedMonth("");
                setSelectedYear("");
                setError(null);
            }
        } catch (err) {
            console.error("Echec du chargement CSV:", err);
            setError("Impossible de lire certains fichiers CSV.");
        } finally {
            setLoadingData(false);
        }
    };

    const handleApplyCsv = () => {
        setCsvReadyEntries(csvEntries);
        setCsvArranged(true);
    };

    const handleExportCsv = () => {
        if (!tablesRef.current) return;
        setExporting(true);
        setTimeout(() => {
            // Implement logic for generating and downloading PDF/XLS
            // Currently just a placeholder to finish the state
            setExporting(false);
        }, 1000);
    };

    const activeEntries = dataSource === "json" ? jsonEntries : csvReadyEntries;

    const { pairs, skippedDates } = useMemo(() => {
        return buildPairs(activeEntries, dataSource === "json" || csvArranged);
    }, [activeEntries, dataSource, csvArranged]);

    const stations = useMemo(() => {
        return Array.from(new Set(pairs.map((p) => p.station))).sort();
    }, [pairs]);

    const years = useMemo(() => {
        const allYears = new Set(pairs.map((p) => p.date.substring(0, 4)));
        return Array.from(allYears).sort().reverse();
    }, [pairs]);

    const months = useMemo(() => {
        const allMonths = new Set(pairs.map((p) => p.date.substring(0, 7)));
        return Array.from(allMonths).sort().reverse();
    }, [pairs]);

    const filteredPairs = useMemo(() => {
        let current = pairs;
        if (metricsMode === "station" && selectedStation) {
            current = current.filter((p) => p.station === selectedStation);
        }
        if (metricsMode === "month" && selectedMonth) {
            current = current.filter((p) => p.date.startsWith(selectedMonth));
        }
        if (metricsMode === "year" && selectedYear) {
            current = current.filter((p) => p.date.startsWith(selectedYear));
        }
        return current;
    }, [pairs, metricsMode, selectedStation, selectedMonth, selectedYear]);

    const metrics = useMemo(() => computeMetrics(filteredPairs), [filteredPairs]);
    const contingency = useMemo(
        () => computeContingencyScores(filteredPairs),
        [filteredPairs],
    );

    return (
        <Layout title="Métriques JSON/CSV">
            <div className="max-w-7xl mx-auto space-y-6 pb-12 px-4">
                <div>
                    <h1 className="text-3xl font-black text-ink mb-2">
                        Analyse comparative (JSON / CSV)
                    </h1>
                    <p className="text-muted">
                        Chargez des fichiers JSON ou CSV pour comparer Observations vs Prévisions.
                    </p>
                </div>

                {/* --- Source Switcher --- */}
                <div className="p-4 rounded-xl border border-[var(--border)] bg-[var(--surface)] shadow-sm space-y-4">
                    <div className="flex items-center gap-4 border-b border-[var(--border)] pb-4">
                        <button
                            onClick={() => setDataSource("json")}
                            className={`px-4 py-2 rounded-lg font-bold text-sm transition-colors ${dataSource === "json"
                                    ? "bg-primary text-white shadow-md"
                                    : "bg-[var(--surface-strong)] text-muted hover:text-ink"
                                }`}
                        >
                            Mode JSON (ANAM)
                        </button>
                        <button
                            onClick={() => setDataSource("csv")}
                            className={`px-4 py-2 rounded-lg font-bold text-sm transition-colors ${dataSource === "csv"
                                    ? "bg-primary text-white shadow-md"
                                    : "bg-[var(--surface-strong)] text-muted hover:text-ink"
                                }`}
                        >
                            Mode CSV
                        </button>
                    </div>

                    {/* Source JSON */}
                    {dataSource === "json" && (
                        <div className="space-y-4 animate-in fade-in">
                            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                                <div className="flex gap-2 items-center text-sm">
                                    <span className="font-medium text-ink">Fichier JSON local :</span>
                                    <input
                                        type="file"
                                        accept=".json"
                                        multiple
                                        className="file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-primary/10 file:text-primary hover:file:bg-primary/20 block w-full text-sm text-muted"
                                        onChange={handleLocalUpload}
                                    />
                                </div>
                                <div className="flex items-center gap-2">
                                    <input
                                        type="text"
                                        placeholder="Filtrer les fichiers distants..."
                                        className="px-3 py-2 rounded-lg border border-[var(--border)] bg-[var(--surface)] text-sm focus:border-primary focus:outline-none w-64"
                                        value={fileFilter}
                                        onChange={(e) => setFileFilter(e.target.value)}
                                    />
                                </div>
                            </div>

                            {loadingFiles ? (
                                <div className="flex justify-center py-8">
                                    <span className="material-symbols-outlined animate-spin text-3xl text-primary">
                                        sync
                                    </span>
                                </div>
                            ) : (
                                <div className="border border-[var(--border)] rounded-lg overflow-hidden max-h-64 overflow-y-auto bg-[var(--surface-strong)]/20">
                                    <table className="w-full text-sm text-left">
                                        <thead className="bg-[var(--surface-strong)] text-muted text-xs uppercase font-bold sticky top-0">
                                            <tr>
                                                <th className="px-4 py-3 w-10 text-center">
                                                    <input
                                                        type="checkbox"
                                                        className="rounded border-gray-300 text-primary focus:ring-primary"
                                                        checked={allSelected}
                                                        onChange={handleToggleAll}
                                                    />
                                                </th>
                                                <th className="px-4 py-3">Fichier</th>
                                                <th className="px-4 py-3">Date</th>
                                                <th className="px-4 py-3">Type</th>
                                            </tr>
                                        </thead>
                                        <tbody className="divide-y divide-[var(--border)]">
                                            {filteredFiles.map((file) => (
                                                <tr
                                                    key={file.path}
                                                    className="hover:bg-[var(--surface-hover)] bg-[var(--surface)] cursor-pointer"
                                                    onClick={() => handleToggleFile(file.path)}
                                                >
                                                    <td className="px-4 py-2 text-center">
                                                        <input
                                                            type="checkbox"
                                                            className="rounded border-gray-300 text-primary focus:ring-primary"
                                                            checked={selectedPaths.includes(file.path)}
                                                            readOnly
                                                        />
                                                    </td>
                                                    <td className="px-4 py-2 font-medium text-ink truncate max-w-xs">
                                                        {file.name}
                                                    </td>
                                                    <td className="px-4 py-2 text-muted whitespace-nowrap">
                                                        {file.date || "-"}
                                                    </td>
                                                    <td className="px-4 py-2 text-muted whitespace-nowrap">
                                                        <span
                                                            className={`px-2 py-0.5 rounded text-[10px] uppercase font-bold tracking-wider ${file.map_type?.toLowerCase().includes("obs")
                                                                    ? "bg-sky-100 text-sky-700"
                                                                    : "bg-purple-100 text-purple-700"
                                                                }`}
                                                        >
                                                            {file.map_type || "INCONNU"}
                                                        </span>
                                                    </td>
                                                </tr>
                                            ))}
                                            {filteredFiles.length === 0 && (
                                                <tr>
                                                    <td colSpan={4} className="px-4 py-8 text-center text-muted">
                                                        Aucun fichier trouvé.
                                                    </td>
                                                </tr>
                                            )}
                                        </tbody>
                                    </table>
                                </div>
                            )}

                            <div className="flex justify-end pt-2">
                                <button
                                    disabled={loadingData || selectedPaths.length === 0}
                                    onClick={handleLoadData}
                                    className="px-6 py-2 bg-primary text-white rounded-lg font-bold shadow-lg hover:bg-primary-600 disabled:opacity-50 transition-all flex items-center gap-2"
                                >
                                    {loadingData ? (
                                        <>
                                            <span className="material-symbols-outlined animate-spin text-lg">
                                                sync
                                            </span>
                                            Chargement...
                                        </>
                                    ) : (
                                        <>
                                            <span className="material-symbols-outlined text-lg">
                                                analytics
                                            </span>
                                            Analyser {selectedPaths.length} fichier(s)
                                        </>
                                    )}
                                </button>
                            </div>
                        </div>
                    )}

                    {/* Source CSV */}
                    {dataSource === "csv" && (
                        <div className="space-y-4 animate-in fade-in">
                            <div className="p-8 border-2 border-dashed border-[var(--border)] rounded-xl bg-[var(--surface-strong)]/20 flex flex-col items-center justify-center text-center">
                                <span className="material-symbols-outlined text-4xl text-muted mb-2">
                                    description
                                </span>
                                <p className="font-bold text-ink mb-1">
                                    Glissez un ou plusieurs fichiers CSV
                                </p>
                                <p className="text-xs text-muted mb-4">
                                    Colonnes attendues : date, station, tmin_obs, tmax_obs, weather_obs,
                                    tmin_prev, tmax_prev, weather_prev...
                                </p>
                                <input
                                    type="file"
                                    accept=".csv"
                                    multiple
                                    className="block w-full text-sm text-slate-500
                    file:mr-4 file:py-2 file:px-4
                    file:rounded-full file:border-0
                    file:text-sm file:font-semibold
                    file:bg-primary file:text-white
                    hover:file:bg-primary-700
                    cursor-pointer w-auto"
                                    onChange={(e) => processCsvFiles(e.target.files ?? [])}
                                />
                            </div>

                            {csvEntries.length > 0 && (
                                <div className="flex items-center justify-between bg-emerald-50 border border-emerald-100 p-4 rounded-lg">
                                    <div className="flex items-center gap-3">
                                        <span className="material-symbols-outlined text-emerald-600">
                                            check_circle
                                        </span>
                                        <div>
                                            <p className="font-bold text-emerald-900">
                                                {csvEntries.length} lignes chargées
                                            </p>
                                            <p className="text-xs text-emerald-700">
                                                Cliquez sur "Valider & Organiser" pour traiter les paires.
                                            </p>
                                        </div>
                                    </div>
                                    <button
                                        onClick={handleApplyCsv}
                                        className="px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm font-bold shadow hover:bg-emerald-700"
                                    >
                                        Valider & Organiser
                                    </button>
                                </div>
                            )}
                        </div>
                    )}
                </div>

                {error && <ErrorPanel title="Erreur" message={error} />}

                {/* --- Metrics Dashboard --- */}
                {(pairs.length > 0 || skippedDates.length > 0) && (
                    <div className="space-y-8 animate-in slide-in-from-bottom-4 duration-500">
                        {/* Filters */}
                        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-4 shadow-sm flex flex-wrap gap-4 items-center justify-between">
                            <div className="flex items-center gap-4">
                                <div className="flex items-center gap-2">
                                    <span className="text-sm font-bold text-muted uppercase tracking-wider">
                                        Mode :
                                    </span>
                                    <div className="flex bg-[var(--surface-strong)] rounded-lg p-1">
                                        {(["station", "month", "year"] as MetricsMode[]).map((m) => (
                                            <button
                                                key={m}
                                                onClick={() => {
                                                    setMetricsMode(m);
                                                    setSelectedStation("");
                                                    setSelectedMonth("");
                                                    setSelectedYear("");
                                                }}
                                                className={`px-3 py-1 text-xs font-bold rounded-md transition-all ${metricsMode === m
                                                        ? "bg-white text-primary shadow-sm"
                                                        : "text-muted hover:text-ink"
                                                    }`}
                                            >
                                                {MODE_LABELS[m]}
                                            </button>
                                        ))}
                                    </div>
                                </div>

                                {metricsMode === "station" && (
                                    <select
                                        className="px-3 py-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface)] text-sm font-medium focus:ring-1 focus:ring-primary"
                                        value={selectedStation}
                                        onChange={(e) => setSelectedStation(e.target.value)}
                                    >
                                        <option value="">Toutes les stations</option>
                                        {stations.map((s) => (
                                            <option key={s} value={s}>
                                                {s}
                                            </option>
                                        ))}
                                    </select>
                                )}

                                {metricsMode === "month" && (
                                    <select
                                        className="px-3 py-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface)] text-sm font-medium focus:ring-1 focus:ring-primary"
                                        value={selectedMonth}
                                        onChange={(e) => setSelectedMonth(e.target.value)}
                                    >
                                        <option value="">Tous les mois</option>
                                        {months.map((m) => (
                                            <option key={m} value={m}>
                                                {m}
                                            </option>
                                        ))}
                                    </select>
                                )}

                                {metricsMode === "year" && (
                                    <select
                                        className="px-3 py-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface)] text-sm font-medium focus:ring-1 focus:ring-primary"
                                        value={selectedYear}
                                        onChange={(e) => setSelectedYear(e.target.value)}
                                    >
                                        <option value="">Toutes les années</option>
                                        {years.map((y) => (
                                            <option key={y} value={y}>
                                                {y}
                                            </option>
                                        ))}
                                    </select>
                                )}
                            </div>

                            <div className="flex items-center gap-2">
                                <p className="text-xs font-bold text-muted">
                                    {filteredPairs.length} paires analysées
                                </p>
                                <button
                                    onClick={handleExportCsv}
                                    className="p-2 hover:bg-[var(--surface-strong)] rounded-lg text-primary transition-colors"
                                    title="Exporter le rapport"
                                >
                                    <span className="material-symbols-outlined">download</span>
                                </button>
                            </div>
                        </div>

                        {/* Warning Skipped */}
                        {skippedDates.length > 0 && (
                            <div className="bg-orange-50 border border-orange-100 rounded-xl p-4">
                                <div className="flex items-start gap-3">
                                    <span className="material-symbols-outlined text-orange-500 mt-0.5">
                                        warning
                                    </span>
                                    <div className="flex-1">
                                        <p className="font-bold text-orange-900 text-sm mb-1">
                                            Certaines dates ont été ignorées ({skippedDates.length})
                                        </p>
                                        <button
                                            onClick={() => setShowSkippedDates(!showSkippedDates)}
                                            className="text-xs font-bold text-orange-700 underline decoration-dotted"
                                        >
                                            {showSkippedDates ? "Masquer les détails" : "Voir les détails"}
                                        </button>
                                        {showSkippedDates && (
                                            <ul className="mt-3 space-y-1 max-h-40 overflow-y-auto pr-2">
                                                {skippedDates.map((d, i) => (
                                                    <li key={i} className="text-xs text-orange-800/80 font-mono">
                                                        {d.date} : {d.reason}
                                                    </li>
                                                ))}
                                            </ul>
                                        )}
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* Metrics Content */}
                        <div ref={tablesRef} className="space-y-8 print:space-y-4">
                            {/* Temperature */}
                            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6" ref={temperatureRef}>
                                <div className="bg-[var(--surface)] border border-[var(--border)] rounded-2xl p-6 shadow-sm">
                                    <div className="flex items-center gap-3 mb-6">
                                        <div className="p-2 bg-rose-100 text-rose-600 rounded-lg">
                                            <span className="material-symbols-outlined">thermostat</span>
                                        </div>
                                        <h3 className="text-lg font-bold text-ink">Températures</h3>
                                    </div>

                                    <div className="space-y-6">
                                        <div>
                                            <h4 className="text-xs font-black text-muted uppercase tracking-widest mb-3">
                                                Température Minimale (Tmin)
                                            </h4>
                                            <div className="grid grid-cols-3 gap-4">
                                                <MetricBox
                                                    label="MAE"
                                                    value={metrics.mae_tmin}
                                                    unit="°C"
                                                    tooltip="Erreur Absolue Moyenne"
                                                />
                                                <MetricBox
                                                    label="RMSE"
                                                    value={metrics.rmse_tmin}
                                                    unit="°C"
                                                    tooltip="Racine de l'Erreur Quadratique Moyenne"
                                                />
                                                <MetricBox label="Biais" value={metrics.bias_tmin} unit="°C" />
                                            </div>
                                        </div>

                                        <div className="border-t border-[var(--border)] pt-6">
                                            <h4 className="text-xs font-black text-muted uppercase tracking-widest mb-3">
                                                Température Maximale (Tmax)
                                            </h4>
                                            <div className="grid grid-cols-3 gap-4">
                                                <MetricBox
                                                    label="MAE"
                                                    value={metrics.mae_tmax}
                                                    unit="°C"
                                                    tooltip="Erreur Absolue Moyenne"
                                                />
                                                <MetricBox
                                                    label="RMSE"
                                                    value={metrics.rmse_tmax}
                                                    unit="°C"
                                                    tooltip="Racine de l'Erreur Quadratique Moyenne"
                                                />
                                                <MetricBox label="Biais" value={metrics.bias_tmax} unit="°C" />
                                            </div>
                                        </div>
                                    </div>
                                </div>

                                {/* Weather Scores */}
                                <div
                                    className="bg-[var(--surface)] border border-[var(--border)] rounded-2xl p-6 shadow-sm"
                                    ref={scoresRef}
                                >
                                    <div className="flex items-center gap-3 mb-6">
                                        <div className="p-2 bg-sky-100 text-sky-600 rounded-lg">
                                            <span className="material-symbols-outlined">cloud</span>
                                        </div>
                                        <h3 className="text-lg font-bold text-ink">Phénomènes Météo</h3>
                                    </div>

                                    <div className="grid grid-cols-2 gap-4 mb-6">
                                        <div className="bg-sky-50 rounded-xl p-4 border border-sky-100">
                                            <p className="text-xs font-bold text-sky-700/60 uppercase tracking-wider mb-1">
                                                Précision Globale
                                            </p>
                                            <p className="text-3xl font-black text-sky-700">
                                                {formatNumber((metrics.accuracy_weather ?? 0) * 100, 1)}
                                                <span className="text-sm font-bold opacity-60 ml-0.5">%</span>
                                            </p>
                                        </div>
                                        <div className="bg-violet-50 rounded-xl p-4 border border-violet-100">
                                            <p className="text-xs font-bold text-violet-700/60 uppercase tracking-wider mb-1">
                                                F1-Score Pondéré
                                            </p>
                                            <p className="text-3xl font-black text-violet-700">
                                                {formatScore(metrics.f1_score_weather)}
                                            </p>
                                        </div>
                                    </div>

                                    <div className="grid grid-cols-2 gap-4">
                                        <MetricBox label="Précision (pondérée)" value={metrics.precision_weather} />
                                        <MetricBox label="Rappel (pondéré)" value={metrics.recall_weather} />
                                    </div>

                                    {contingency.pc !== null && (
                                        <div className="mt-6 pt-6 border-t border-[var(--border)]">
                                            <h4 className="text-xs font-black text-muted uppercase tracking-widest mb-3">
                                                Scores de Contingence
                                            </h4>
                                            <div className="bg-[var(--surface-strong)]/30 rounded-lg p-3 flex items-center justify-between">
                                                <span className="text-sm font-bold text-ink">Proportion Correcte (PC)</span>
                                                <span className="font-mono font-bold text-primary">
                                                    {formatNumber(contingency.pc, 1)}%
                                                </span>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </div>

                            {/* Contingency Table */}
                            {contingency.rows.length > 0 && (
                                <div
                                    className="bg-[var(--surface)] border border-[var(--border)] rounded-2xl overflow-hidden shadow-sm"
                                    ref={contingencyRef}
                                >
                                    <div className="px-6 py-4 border-b border-[var(--border)] bg-[var(--surface-strong)]/30">
                                        <h3 className="text-sm font-bold text-ink uppercase tracking-widest">
                                            Détails par Phénomène (Table de Contingence)
                                        </h3>
                                    </div>
                                    <div className="overflow-x-auto">
                                        <table className="w-full text-sm text-left">
                                            <thead className="bg-[var(--surface-strong)]/50 text-muted border-b border-[var(--border)]">
                                                <tr>
                                                    <th className="px-6 py-3 font-bold w-1/4">Phénomène</th>
                                                    <th className="px-6 py-3 font-bold text-right">POD (Détection)</th>
                                                    <th className="px-6 py-3 font-bold text-right">FAR (Fausses Alarmes)</th>
                                                    <th className="px-6 py-3 font-bold text-right">Performance</th>
                                                </tr>
                                            </thead>
                                            <tbody className="divide-y divide-[var(--border)]">
                                                {contingency.rows.map((row) => (
                                                    <tr key={row.code} className="hover:bg-[var(--surface-hover)]">
                                                        <td className="px-6 py-3 font-bold font-mono text-ink">
                                                            {row.code}
                                                        </td>
                                                        <td className="px-6 py-3 text-right tabular-nums">
                                                            {formatScore(row.pod)}
                                                        </td>
                                                        <td className="px-6 py-3 text-right tabular-nums">
                                                            {formatScore(row.far)}
                                                        </td>
                                                        <td className="px-6 py-3 text-right">
                                                            <div className="flex justify-end gap-1">
                                                                <div
                                                                    className="h-1.5 rounded-full bg-emerald-500"
                                                                    style={{ width: `${(row.pod ?? 0) * 50}px` }}
                                                                />
                                                                <div
                                                                    className="h-1.5 rounded-full bg-red-400"
                                                                    style={{ width: `${(row.far ?? 0) * 50}px` }}
                                                                />
                                                            </div>
                                                        </td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                    <div className="px-6 py-3 bg-[var(--surface-strong)]/30 border-t border-[var(--border)] flex gap-6 text-xs text-muted">
                                        <div className="flex items-center gap-2">
                                            <div className="size-2 rounded-full bg-emerald-500" />
                                            <span>POD: Probability of Detection (Idéal: 1.0)</span>
                                        </div>
                                        <div className="flex items-center gap-2">
                                            <div className="size-2 rounded-full bg-red-400" />
                                            <span>FAR: False Alarm Ratio (Idéal: 0.0)</span>
                                        </div>
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </div>
        </Layout>
    );
}

function MetricBox({
    label,
    value,
    unit = "",
    tooltip,
}: {
    label: string;
    value?: number | null;
    unit?: string;
    tooltip?: string;
}) {
    return (
        <div className="bg-[var(--surface-strong)]/30 rounded-xl p-3 border border-[var(--border)] flex flex-col items-center justify-center text-center group relative cursor-help">
            <p className="text-[10px] font-bold text-muted uppercase tracking-wider mb-1">
                {label}
            </p>
            <p className="text-xl font-black text-ink">
                {formatNumber(value)}
                {unit && <span className="text-xs font-bold text-muted ml-0.5">{unit}</span>}
            </p>
            {tooltip && (
                <div className="absolute bottom-full mb-2 bg-gray-900 text-white text-xs px-2 py-1 rounded shadow-lg opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none whitespace-nowrap z-10">
                    {tooltip}
                </div>
            )}
        </div>
    );
}
