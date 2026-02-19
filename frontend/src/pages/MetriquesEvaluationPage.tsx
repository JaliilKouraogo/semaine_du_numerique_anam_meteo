import { useEffect, useState } from "react";
import { Layout } from "../components/Layout";
import { ErrorPanel, LoadingPanel } from "../components/StatusPanel";
import { formatFrenchMonth } from "../services/api";
import {
  fetchMonthlyMetricsList,
  fetchMetricsList,
  recalculateMetrics,
  type MonthlyMetricsResponse,
  type MetricsResponse,
} from "../services/api";

export function MetriquesEvaluationPage() {
  const [monthlyMetrics, setMonthlyMetrics] = useState<MonthlyMetricsResponse[]>([]);
  const [dailyMetrics, setDailyMetrics] = useState<MetricsResponse[]>([]);
  const [selectedDailyMetric, setSelectedDailyMetric] = useState<MetricsResponse | null>(null);
  const [selectedMonthlyMetric, setSelectedMonthlyMetric] = useState<MonthlyMetricsResponse | null>(null);
  const [viewMode, setViewMode] = useState<"daily" | "monthly">("daily");
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [recalcLoading, setRecalcLoading] = useState<boolean>(false);
  const [recalcMessage, setRecalcMessage] = useState<string | null>(null);

  const loadMetrics = async () => {
    try {
      setLoading(true);
      setError(null);

      // Load daily first
      const dailyPayload = await fetchMetricsList(100);
      const dailies = dailyPayload.items ?? [];
      setDailyMetrics(dailies);
      if (dailies.length > 0 && !selectedDailyMetric) {
        setSelectedDailyMetric(dailies[0]);
      }

      // Load monthly
      const monthlyPayload = await fetchMonthlyMetricsList(24);
      const monthlies = monthlyPayload.items ?? [];
      setMonthlyMetrics(monthlies);
      if (monthlies.length > 0 && !selectedMonthlyMetric) {
        setSelectedMonthlyMetric(monthlies[0]);
      }

    } catch (err) {
      console.error("Échec du chargement des métriques:", err);
      setError("Échec du chargement des métriques.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadMetrics();
  }, []);

  const handleRecalculate = async () => {
    try {
      setRecalcLoading(true);
      setRecalcMessage(null);
      const result = await recalculateMetrics(true);
      if (result.status === "no_data") {
        setRecalcMessage(result.message ?? "Aucune donnée pour recalculer.");
      } else {
        const dailyCount = (result.result?.daily as any)?.evaluated ?? 0;
        setRecalcMessage(`Recalcul terminé : ${dailyCount} jours évalués.`);
        await loadMetrics();
      }
    } catch (err) {
      console.error("Échec du recalcul:", err);
      setRecalcMessage("Échec du recalcul des métriques.");
    } finally {
      setRecalcLoading(false);
    }
  };

  const getMetricColor = (value: number, type: "mae" | "rmse" | "bias" | "accuracy") => {
    if (type === "accuracy") {
      if (value >= 0.9) return "text-green-600 dark:text-green-400";
      if (value >= 0.7) return "text-yellow-600 dark:text-yellow-400";
      return "text-red-600 dark:text-red-400";
    }
    if (type === "bias") {
      if (Math.abs(value) <= 0.5) return "text-green-600 dark:text-green-400";
      if (Math.abs(value) <= 1.0) return "text-yellow-600 dark:text-yellow-400";
      return "text-red-600 dark:text-red-400";
    }
    if (value <= 1.0) return "text-green-600 dark:text-green-400";
    if (value <= 2.0) return "text-yellow-600 dark:text-yellow-400";
    return "text-red-600 dark:text-red-400";
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString("fr-FR", {
      day: "numeric",
      month: "long",
      year: "numeric",
    });
  };

  const selectedMetric = viewMode === "daily" ? selectedDailyMetric : selectedMonthlyMetric;

  return (
    <Layout title="Métriques d'Évaluation">
      <div className="space-y-6">
        {/* Header & Mode Switcher */}
        <div className="bg-[var(--surface)] rounded-2xl border border-[var(--border)] p-6 shadow-lg">
          <div className="flex flex-wrap items-center justify-between gap-6">
            <div className="flex bg-[var(--canvas-strong)] p-1 rounded-xl border border-[var(--border)]">
              <button
                onClick={() => setViewMode("daily")}
                className={`flex items-center gap-2 px-6 py-2.5 rounded-lg text-sm font-bold transition-all ${viewMode === "daily"
                  ? "bg-white dark:bg-[var(--surface)] shadow-md text-primary-600"
                  : "text-muted hover:text-ink"
                  }`}
              >
                <span className="material-symbols-outlined text-base">today</span>
                Par Jour (Précis)
              </button>
              <button
                onClick={() => setViewMode("monthly")}
                className={`flex items-center gap-2 px-6 py-2.5 rounded-lg text-sm font-bold transition-all ${viewMode === "monthly"
                  ? "bg-white dark:bg-[var(--surface)] shadow-md text-primary-600"
                  : "text-muted hover:text-ink"
                  }`}
              >
                <span className="material-symbols-outlined text-base">calendar_view_month</span>
                Mensuel (Global)
              </button>
            </div>

            <div className="flex items-center gap-6">
              {viewMode === "daily" ? (
                <div className="flex items-center gap-3">
                  <div className="size-10 rounded-xl bg-blue-500/10 flex items-center justify-center">
                    <span className="material-symbols-outlined text-primary-500">event</span>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-muted">Date du bulletin</label>
                    <select
                      value={selectedDailyMetric?.date ?? ""}
                      onChange={(e) => {
                        const m = dailyMetrics.find((dm) => dm.date === e.target.value);
                        if (m) setSelectedDailyMetric(m);
                      }}
                      className="rounded-lg border-none bg-transparent font-bold text-ink p-0 focus:ring-0 cursor-pointer"
                    >
                      {dailyMetrics.map((dm) => (
                        <option key={dm.date} value={dm.date}>
                          {formatDate(dm.date)}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              ) : (
                <div className="flex items-center gap-3">
                  <div className="size-10 rounded-xl bg-green-500/10 flex items-center justify-center">
                    <span className="material-symbols-outlined text-green-500">grid_view</span>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-muted">Période mensuelle</label>
                    <select
                      value={selectedMonthlyMetric ? `${selectedMonthlyMetric.year}-${selectedMonthlyMetric.month}` : ""}
                      onChange={(e) => {
                        const [y, m] = e.target.value.split("-");
                        const found = monthlyMetrics.find((mm) => mm.year === Number(y) && mm.month === Number(m));
                        if (found) setSelectedMonthlyMetric(found);
                      }}
                      className="rounded-lg border-none bg-transparent font-bold text-ink p-0 focus:ring-0 cursor-pointer"
                    >
                      {monthlyMetrics.map((mm) => (
                        <option key={`${mm.year}-${mm.month}`} value={`${mm.year}-${mm.month}`}>
                          {formatFrenchMonth(mm.year, mm.month)}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              )}

              <button
                type="button"
                onClick={handleRecalculate}
                disabled={recalcLoading}
                className="inline-flex items-center gap-2 rounded-xl border border-primary-200 bg-primary-50 px-4 py-2.5 text-sm font-bold text-primary-700 transition hover:bg-primary-100 disabled:opacity-50 shadow-sm"
              >
                <span className={`material-symbols-outlined text-base ${recalcLoading ? "animate-spin" : ""}`}>
                  refresh
                </span>
                {recalcLoading ? "Calcul..." : "Mettre à jour"}
              </button>
            </div>
          </div>
          {recalcMessage && (
            <div className="mt-4 p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-xl flex items-center gap-2 text-blue-700 dark:text-blue-300 text-sm">
              <span className="material-symbols-outlined text-base">info</span>
              {recalcMessage}
            </div>
          )}
        </div>

        {loading ? (
          <LoadingPanel message="Analyse des performances..." />
        ) : error ? (
          <ErrorPanel message={error} />
        ) : !selectedMetric ? (
          <div className="p-12 text-center bg-[var(--surface)] rounded-2xl border border-[var(--border)]">
            <span className="material-symbols-outlined text-6xl text-muted/30 mb-4">analytics</span>
            <p className="text-muted">Aucune donnée d'évaluation disponible pour le moment.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
            {/* Main Stats (Top Left) */}
            <div className="xl:col-span-8 space-y-6">
              {/* Informations sur les bulletins sources */}
              {viewMode === "daily" && (selectedMetric as MetricsResponse).observation_file_path && (
                <div className="bg-[var(--surface)] rounded-2xl border border-[var(--border)] p-5 shadow-sm">
                  <div className="flex items-center gap-4">
                    <div className="size-12 rounded-2xl bg-primary-500/10 flex items-center justify-center shrink-0">
                      <span className="material-symbols-outlined text-primary-600">article</span>
                    </div>
                    <div className="min-w-0 flex-1">
                      <h4 className="text-[10px] font-black uppercase tracking-widest text-muted mb-2">Bulletins utilisés pour cette évaluation</h4>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div className="bg-[var(--canvas-strong)] p-2 px-3 rounded-xl border border-[var(--border)] flex items-center gap-3 min-w-0">
                          <span className="material-symbols-outlined text-sm text-green-600">check_circle</span>
                          <div className="min-w-0">
                            <p className="text-[9px] font-bold text-muted uppercase">Observation du {new Date((selectedMetric as MetricsResponse).date).toLocaleDateString()}</p>
                            <p className="text-xs font-mono text-ink truncate" title={(selectedMetric as MetricsResponse).observation_file_path || ''}>
                              {(selectedMetric as MetricsResponse).observation_file_path?.split(/[\\/]/).pop()}
                            </p>
                          </div>
                        </div>
                        <div className="bg-[var(--canvas-strong)] p-2 px-3 rounded-xl border border-[var(--border)] flex items-center gap-3 min-w-0">
                          <span className="material-symbols-outlined text-sm text-blue-600">history</span>
                          <div className="min-w-0">
                            <p className="text-[9px] font-bold text-muted uppercase">Prévision du {(selectedMetric as MetricsResponse).forecast_reference_date}</p>
                            <p className="text-xs font-mono text-ink truncate" title={(selectedMetric as MetricsResponse).forecast_file_path || ''}>
                              {(selectedMetric as MetricsResponse).forecast_file_path?.split(/[\\/]/).pop() || 'Fichier inconnu'}
                            </p>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              )}
              {/* Temperature Metrics Card */}
              <div className="bg-[var(--surface)] rounded-2xl border border-[var(--border)] shadow-sm overflow-hidden">
                <div className="px-6 py-4 border-b border-[var(--border)] bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-[var(--surface-strong)] dark:to-[var(--canvas-strong)] flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="size-10 rounded-xl bg-blue-500 flex items-center justify-center shadow-lg shadow-blue-500/30">
                      <span className="material-symbols-outlined text-white">thermostat</span>
                    </div>
                    <div>
                      <h3 className="font-bold text-ink">Ecarts de Température</h3>
                      <p className="text-xs text-muted">Comparaison Forecast vs Observation</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <span className="text-2xl font-black text-ink">
                      {selectedMetric.sample_size}
                    </span>
                    <span className="text-xs text-muted ml-2">stations analysées</span>
                  </div>
                </div>
                <div className="p-8">
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                    {/* MAE Group */}
                    <div className="space-y-4">
                      <div className="flex items-center gap-2 text-muted">
                        <span className="material-symbols-outlined text-sm font-bold">trending_up</span>
                        <span className="text-xs font-black uppercase tracking-widest">Erreur Absolue (MAE)</span>
                      </div>
                      <div className="grid grid-cols-1 gap-3">
                        <div className="bg-[var(--surface-strong)] p-4 rounded-2xl border border-[var(--border)] relative overflow-hidden group">
                          <div className="absolute top-0 right-0 p-2 opacity-10 group-hover:opacity-20 transition-opacity">
                            <span className="material-symbols-outlined text-4xl">thermometer_minus</span>
                          </div>
                          <p className="text-xs text-muted mb-1">Tmin</p>
                          <p className={`text-2xl font-black ${getMetricColor(selectedMetric.mae_tmin ?? 0, 'mae')}`}>
                            {(selectedMetric.mae_tmin ?? 0).toFixed(2)}°C
                          </p>
                        </div>
                        <div className="bg-[var(--surface-strong)] p-4 rounded-2xl border border-[var(--border)] relative overflow-hidden group">
                          <div className="absolute top-0 right-0 p-2 opacity-10 group-hover:opacity-20 transition-opacity">
                            <span className="material-symbols-outlined text-4xl">thermometer_add</span>
                          </div>
                          <p className="text-xs text-muted mb-1">Tmax</p>
                          <p className={`text-2xl font-black ${getMetricColor(selectedMetric.mae_tmax ?? 0, 'mae')}`}>
                            {(selectedMetric.mae_tmax ?? 0).toFixed(2)}°C
                          </p>
                        </div>
                      </div>
                    </div>

                    {/* RMSE Group */}
                    <div className="space-y-4">
                      <div className="flex items-center gap-2 text-muted">
                        <span className="material-symbols-outlined text-sm font-bold">calculate</span>
                        <span className="text-xs font-black uppercase tracking-widest">Ecart Quadratique (RMSE)</span>
                      </div>
                      <div className="p-4 rounded-2xl border border-[var(--border)] space-y-4">
                        <div>
                          <p className="flex justify-between text-xs mb-1">
                            <span className="text-muted">Tmin:</span>
                            <span className={`font-bold ${getMetricColor(selectedMetric.rmse_tmin ?? 0, 'rmse')}`}>
                              {(selectedMetric.rmse_tmin ?? 0).toFixed(2)}°C
                            </span>
                          </p>
                          <div className="h-1.5 w-full bg-[var(--canvas-strong)] rounded-full overflow-hidden">
                            <div
                              className="h-full bg-blue-500 rounded-full"
                              style={{ width: `${Math.min(100, (selectedMetric.rmse_tmin ?? 0) * 30)}%` }}
                            />
                          </div>
                        </div>
                        <div>
                          <p className="flex justify-between text-xs mb-1">
                            <span className="text-muted">Tmax:</span>
                            <span className={`font-bold ${getMetricColor(selectedMetric.rmse_tmax ?? 0, 'rmse')}`}>
                              {(selectedMetric.rmse_tmax ?? 0).toFixed(2)}°C
                            </span>
                          </p>
                          <div className="h-1.5 w-full bg-[var(--canvas-strong)] rounded-full overflow-hidden">
                            <div
                              className="h-full bg-indigo-500 rounded-full"
                              style={{ width: `${Math.min(100, (selectedMetric.rmse_tmax ?? 0) * 30)}%` }}
                            />
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Bias Group */}
                    <div className="space-y-4">
                      <div className="flex items-center gap-2 text-muted">
                        <span className="material-symbols-outlined text-sm font-bold">balance</span>
                        <span className="text-xs font-black uppercase tracking-widest">Biais Système</span>
                      </div>
                      <div className="space-y-3">
                        <div className="flex items-center justify-between p-3 rounded-xl bg-orange-500/5 border border-orange-500/10">
                          <div>
                            <p className="text-[10px] uppercase font-bold text-orange-600/60">Tmin Bias</p>
                            <p className={`font-mono text-lg font-bold ${getMetricColor(selectedMetric.bias_tmin ?? 0, 'bias')}`}>
                              {(selectedMetric.bias_tmin ?? 0) > 0 ? '+' : ''}{(selectedMetric.bias_tmin ?? 0).toFixed(2)}°C
                            </p>
                          </div>
                          <span className="text-xs text-muted max-w-[100px]">
                            {(selectedMetric.bias_tmin ?? 0) > 0 ? "Prév. trop chaude" : "Prév. trop froide"}
                          </span>
                        </div>
                        <div className="flex items-center justify-between p-3 rounded-xl bg-amber-500/5 border border-amber-500/10">
                          <div>
                            <p className="text-[10px] uppercase font-bold text-amber-600/60">Tmax Bias</p>
                            <p className={`font-mono text-lg font-bold ${getMetricColor(selectedMetric.bias_tmax ?? 0, 'bias')}`}>
                              {(selectedMetric.bias_tmax ?? 0) > 0 ? '+' : ''}{(selectedMetric.bias_tmax ?? 0).toFixed(2)}°C
                            </p>
                          </div>
                          <span className="text-xs text-muted max-w-[100px]">
                            {(selectedMetric.bias_tmax ?? 0) > 0 ? "Prév. trop chaude" : "Prév. trop froide"}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Weather Classification Card */}
              <div className="bg-[var(--surface)] rounded-2xl border border-[var(--border)] shadow-sm">
                <div className="px-6 py-4 border-b border-[var(--border)] flex items-center gap-3">
                  <div className="size-10 rounded-xl bg-purple-500 flex items-center justify-center shadow-lg shadow-purple-500/30">
                    <span className="material-symbols-outlined text-white">filter_drama</span>
                  </div>
                  <div>
                    <h3 className="font-bold text-ink">Classification Météorologique</h3>
                    <p className="text-xs text-muted">Précision des icônes du bulletin</p>
                  </div>
                </div>
                <div className="p-8">
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
                    <div className="text-center p-4 bg-[var(--surface-strong)] rounded-2xl border border-[var(--border)]">
                      <p className="text-[10px] uppercase font-black text-muted mb-2">Accuracy</p>
                      <p className={`text-3xl font-black ${getMetricColor(selectedMetric.accuracy_weather ?? 0, 'accuracy')}`}>
                        {((selectedMetric.accuracy_weather ?? 0) * 100).toFixed(1)}%
                      </p>
                    </div>
                    <div className="text-center p-4 bg-[var(--surface-strong)] rounded-2xl border border-[var(--border)]">
                      <p className="text-[10px] uppercase font-black text-muted mb-2">Precision</p>
                      <p className={`text-3xl font-black ${getMetricColor(selectedMetric.precision_weather ?? 0, 'accuracy')}`}>
                        {((selectedMetric.precision_weather ?? 0) * 100).toFixed(1)}%
                      </p>
                    </div>
                    <div className="text-center p-4 bg-[var(--surface-strong)] rounded-2xl border border-[var(--border)]">
                      <p className="text-[10px] uppercase font-black text-muted mb-2">Recall</p>
                      <p className={`text-3xl font-black ${getMetricColor(selectedMetric.recall_weather ?? 0, 'accuracy')}`}>
                        {((selectedMetric.recall_weather ?? 0) * 100).toFixed(1)}%
                      </p>
                    </div>
                    <div className="text-center p-4 bg-[var(--surface-strong)] rounded-2xl border border-[var(--border)]">
                      <p className="text-[10px] uppercase font-black text-muted mb-2">F1 Score</p>
                      <p className={`text-3xl font-black ${getMetricColor(selectedMetric.f1_score_weather ?? 0, 'accuracy')}`}>
                        {((selectedMetric.f1_score_weather ?? 0) * 100).toFixed(1)}%
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Sidebar List (Right) */}
            <div className="xl:col-span-4 space-y-6">
              {/* History List */}
              <div className="bg-[var(--surface)] rounded-2xl border border-[var(--border)] shadow-sm flex flex-col h-[580px]">
                <div className="p-4 border-b border-[var(--border)] flex items-center justify-between">
                  <h4 className="font-black text-xs uppercase tracking-widest text-muted">Historique des {viewMode === "daily" ? "Jours" : "Mois"}</h4>
                  <span className="px-2 py-0.5 rounded-full bg-primary-100 text-primary-700 text-[10px] font-black uppercase">
                    {viewMode === "daily" ? dailyMetrics.length : monthlyMetrics.length} entrées
                  </span>
                </div>
                <div className="flex-1 overflow-y-auto p-2 space-y-1">
                  {viewMode === "daily" ? (
                    dailyMetrics.map((dm, idx) => (
                      <button
                        key={dm.id || `${dm.date}-${dm.forecast_reference_date}-${idx}`}
                        onClick={() => setSelectedDailyMetric(dm)}
                        className={`w-full flex items-center justify-between p-3 rounded-xl transition-all ${selectedDailyMetric?.id === dm.id
                          ? "bg-primary-500 text-white shadow-lg shadow-primary-500/20"
                          : "hover:bg-[var(--canvas-strong)] text-ink"
                          }`}
                      >
                        <div className="text-left flex-1 min-w-0 pr-2">
                          <p className="text-sm font-bold leading-tight">
                            {new Date(dm.date).toLocaleDateString("fr-FR", { day: 'numeric', month: 'short' })}
                          </p>
                          <p className={`text-[10px] font-medium ${selectedDailyMetric?.id === dm.id ? "text-white/70" : "text-muted"}`}>
                            Réf: {dm.forecast_reference_date ? new Date(dm.forecast_reference_date).toLocaleDateString("fr-FR", { day: 'numeric', month: 'short' }) : 'N/A'}
                          </p>

                          {/* Affichage des noms de fichiers - Style "Exploration" */}
                          <div className={`mt-2 pt-2 border-t space-y-2 ${selectedDailyMetric?.id === dm.id ? "border-white/15" : "border-black/5"}`}>
                            <div className="space-y-1">
                              <div className="flex items-center gap-1.5 min-w-0">
                                <span className={`material-symbols-outlined text-[14px] ${selectedDailyMetric?.id === dm.id ? "text-white/60" : "text-blue-500"}`}>
                                  description
                                </span>
                                <span className={`text-[10px] font-bold uppercase tracking-tight ${selectedDailyMetric?.id === dm.id ? "text-white/60" : "text-muted"}`}>
                                  Observation
                                </span>
                              </div>
                              <p
                                className={`text-[11px] font-medium leading-tight truncate pl-5 ${selectedDailyMetric?.id === dm.id ? "text-white" : "text-ink"}`}
                                title={dm.observation_title || dm.observation_file_path || ''}
                              >
                                {dm.observation_title || dm.observation_file_path?.split(/[\\/]/).pop() || "Bulletin_Obs_Inconnu.pdf"}
                              </p>
                            </div>

                            <div className="space-y-1">
                              <div className="flex items-center gap-1.5 min-w-0">
                                <span className={`material-symbols-outlined text-[14px] ${selectedDailyMetric?.id === dm.id ? "text-white/60" : "text-emerald-500"}`}>
                                  online_prediction
                                </span>
                                <span className={`text-[10px] font-bold uppercase tracking-tight ${selectedDailyMetric?.id === dm.id ? "text-white/60" : "text-muted"}`}>
                                  Prévision (J-1)
                                </span>
                              </div>
                              <p
                                className={`text-[11px] font-medium leading-tight truncate pl-5 ${selectedDailyMetric?.id === dm.id ? "text-white" : "text-ink"}`}
                                title={dm.forecast_title || dm.forecast_file_path || ''}
                              >
                                {dm.forecast_title || dm.forecast_file_path?.split(/[\\/]/).pop() || "Bulletin_Prev_Inconnu.pdf"}
                              </p>
                            </div>
                          </div>
                        </div>
                        <div className="text-right shrink-0 self-start pt-1">
                          <p className={`text-sm font-black ${selectedDailyMetric?.id === dm.id ? "text-white" : getMetricColor(dm.accuracy_weather ?? 0, 'accuracy')}`}>
                            {((dm.accuracy_weather ?? 0) * 100).toFixed(0)}%
                          </p>
                          <span className={`text-[10px] font-bold ${selectedDailyMetric?.id === dm.id ? "text-white/70" : "text-muted"}`}>MAE {dm.mae_tmax?.toFixed(1)}°</span>
                        </div>
                      </button>
                    ))
                  ) : (
                    monthlyMetrics.map((mm) => (
                      <button
                        key={`${mm.year}-${mm.month}`}
                        onClick={() => setSelectedMonthlyMetric(mm)}
                        className={`w-full flex items-center justify-between p-3 rounded-xl transition-all ${selectedMonthlyMetric?.year === mm.year && selectedMonthlyMetric.month === mm.month
                          ? "bg-primary-500 text-white shadow-lg shadow-primary-500/20"
                          : "hover:bg-[var(--canvas-strong)] text-ink"
                          }`}
                      >
                        <div className="text-left">
                          <p className="text-sm font-bold leading-tight">
                            {formatFrenchMonth(mm.year, mm.month)}
                          </p>
                          <p className={`text-[10px] font-medium ${selectedMonthlyMetric?.year === mm.year ? "text-white/70" : "text-muted"}`}>
                            {mm.days_evaluated} jours analysés
                          </p>
                        </div>
                        <div className="text-right">
                          <p className={`text-sm font-black ${selectedMonthlyMetric?.year === mm.year ? "text-white" : getMetricColor(mm.accuracy_weather ?? 0, 'accuracy')}`}>
                            {((mm.accuracy_weather ?? 0) * 100).toFixed(0)}%
                          </p>
                          <span className={`text-[9px] font-bold ${selectedMonthlyMetric?.year === mm.year ? "text-white/60" : "text-muted"}`}>MAE: {mm.mae_tmax?.toFixed(1)}°</span>
                        </div>
                      </button>
                    ))
                  )}
                </div>
              </div>

              {/* Technical Legend */}
              <div className="bg-gradient-to-br from-indigo-900 to-slate-900 rounded-2xl p-6 text-white shadow-xl">
                <h4 className="flex items-center gap-2 text-xs font-black uppercase tracking-widest text-indigo-400 mb-4">
                  <span className="material-symbols-outlined text-sm">info</span> Commprendre les calculs
                </h4>
                <div className="space-y-4 text-xs">
                  <div>
                    <p className="font-bold text-indigo-200 mb-1">Logique de comparaison</p>
                    <p className="text-indigo-100/70">Nous comparons les bulletins de <b>Prévision (J-1)</b> avec les bulletins d'<b>Observation (J+1)</b> du même jour.</p>
                  </div>
                  <div>
                    <p className="font-bold text-indigo-200 mb-1">MAE vs RMSE</p>
                    <p className="text-indigo-100/70">La <span className="text-indigo-300">MAE</span> est l'erreur moyenne. La <span className="text-indigo-300">RMSE</span> est plus sensible aux gros écarts ponctuels de température.</p>
                  </div>
                  <div>
                    <p className="font-bold text-indigo-200 mb-1">Interprétation du Biais</p>
                    <p className="text-indigo-100/70">Un biais positif signifie que le système à tendance à prédire des températures plus élevées que la réalité.</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </Layout>
  );
}
