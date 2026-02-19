import { useEffect, useState, useRef } from "react";
import { Layout } from "../components/Layout";
import { API_BASE_URL, UPLOAD_BATCH_MAX_FILES } from "../config";
import { finishRequest, reportError, startRequest } from "../services/statusStore";
import {
  fetchUploadBatchStatus,
  stopUploadBatch,
  uploadBulletinsBatch,
  uploadBulletin,
  fetchUploadJobs,
  deleteUploadJob,
  fetchUploadJobStatus,
  retryUploadJob,
  submitFeedback,
  type UploadBatchStatus,
  type UploadJobStatus,
} from "../services/api";

type TemperatureValue = {
  name?: string | null;
  tmin: number | null;
  tmax: number | null;
  weather_condition?: string | null;
  tmin_raw?: string | null;
  tmax_raw?: string | null;
  bbox?: [number, number, number, number] | null;
  map_width?: number | null;
  map_height?: number | null;
};

type MapTemperatures = {
  type?: string;
  image_path?: string | null;
  temperatures: TemperatureValue[];
};

type TemperatureExtraction = {
  pdf_path: string | null;
  image_path: string | null;
  data: MapTemperatures[];
  interpretation_francais?: string | null;
  interpretation_moore?: string | null;
  interpretation_dioula?: string | null;
  type?: string;
  date?: string;
};

type UploadResponse = {
  filename: string;
  pdf_path: string;
  temperatures: TemperatureExtraction[];
};

function OCRVisualizer({
  imagePath,
  detections,
  title
}: {
  imagePath: string;
  detections: TemperatureValue[];
  title?: string
}) {
  const imageUrl = `${API_BASE_URL}/files/pdf_images/${imagePath}`;
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold text-ink">{title || "Visualisation OCR"}</p>
        <span className="text-xs text-muted">{detections?.length || 0} détections</span>
      </div>

      <div className="relative border border-[var(--border)] rounded-xl overflow-hidden bg-black/5">
        <img
          src={imageUrl}
          alt="Carte Météo"
          className="w-full h-auto block"
        />

        <div className="absolute top-0 left-0 w-full h-full overflow-hidden pointer-events-none">
          {detections?.map((det, idx) => {
            if (!det.bbox) return null;
            return (
              <OCRBox
                key={idx}
                bbox={det.bbox}
                label={det.name || `D${idx + 1}`}
                isHovered={hoveredIndex === idx}
                onHover={() => setHoveredIndex(idx)}
                onLeave={() => setHoveredIndex(null)}
                mapWidth={det.map_width}
                mapHeight={det.map_height}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}

function OCRBox({
  bbox,
  label,
  isHovered,
  onHover,
  onLeave,
  mapWidth,
  mapHeight
}: {
  bbox: [number, number, number, number];
  label: string;
  isHovered: boolean;
  onHover: () => void;
  onLeave: () => void;
  mapWidth?: number | null;
  mapHeight?: number | null;
}) {
  if (!mapWidth || !mapHeight) return null;

  const [x, y, w, h] = bbox;
  const left = (x / mapWidth) * 100;
  const top = (y / mapHeight) * 100;
  const width = (w / mapWidth) * 100;
  const height = (h / mapHeight) * 100;

  return (
    <div
      className={`absolute border-2 transition-all pointer-events-auto cursor-help ${isHovered
        ? "border-yellow-400 bg-yellow-400/20 z-20 scale-110"
        : "border-primary/60 bg-primary/5 z-10"
        }`}
      style={{
        left: `${left}%`,
        top: `${top}%`,
        width: `${width}%`,
        height: `${height}%`,
      }}
      onMouseEnter={onHover}
      onMouseLeave={onLeave}
      title={label}
    >
      <span className={`absolute -top-5 left-0 px-1 py-0.5 text-[10px] font-bold rounded whitespace-nowrap print:border print:border-primary print:text-primary print:bg-white ${isHovered ? "bg-yellow-400 text-black" : "bg-primary text-white"
        }`}>
        {label}
      </span>
    </div>
  );
}

function TemperatureRow({
  data,
  onSave
}: {
  data: TemperatureValue;
  onSave: (val: TemperatureValue) => void
}) {
  const [editing, setEditing] = useState(false);
  const [editValues, setEditValues] = useState(data);

  useEffect(() => {
    if (!editing) setEditValues(data);
  }, [data, editing]);

  const handleSave = () => {
    onSave(editValues);
    setEditing(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleSave();
    if (e.key === 'Escape') {
      setEditValues(data);
      setEditing(false);
    }
  };

  return (
    <tr className={`group transition-colors border-b border-[var(--border)] last:border-0 ${editing ? 'bg-primary-50/50 dark:bg-primary-900/10' : 'hover:bg-[var(--surface-hover)]'}`}>
      <td className="px-3 py-2 text-ink font-medium">{data.name ?? "-"}</td>
      <td className="px-3 py-2 text-ink">
        {editing ? (
          <input
            className="w-full min-w-[120px] rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            value={editValues.weather_condition || ""}
            onChange={e => setEditValues({ ...editValues, weather_condition: e.target.value })}
            onKeyDown={handleKeyDown}
            placeholder="Condition"
            autoFocus
          />
        ) : (
          <span className="text-xs">{data.weather_condition || "NP"}</span>
        )}
      </td>
      <td className="px-3 py-2 text-ink">
        {editing ? (
          <input
            type="number"
            className="w-16 rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            value={editValues.tmin ?? ""}
            onChange={e => setEditValues({ ...editValues, tmin: e.target.value === "" ? null : Number(e.target.value) })}
            onKeyDown={handleKeyDown}
          />
        ) : (
          <span>{data.tmin ?? data.tmin_raw ?? "-"}</span>
        )}
      </td>
      <td className="px-3 py-2 text-ink">
        {editing ? (
          <input
            type="number"
            className="w-16 rounded border border-[var(--border)] bg-[var(--surface)] px-2 py-1 text-sm focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
            value={editValues.tmax ?? ""}
            onChange={e => setEditValues({ ...editValues, tmax: e.target.value === "" ? null : Number(e.target.value) })}
            onKeyDown={handleKeyDown}
          />
        ) : (
          <span>{data.tmax ?? data.tmax_raw ?? "-"}</span>
        )}
      </td>
      <td className="px-3 py-2 text-right print:hidden">
        {editing ? (
          <div className="flex justify-end gap-1">
            <button onClick={handleSave} className="p-1 text-emerald-600 hover:bg-emerald-50 rounded"><span className="material-symbols-outlined text-sm">check</span></button>
            <button onClick={() => setEditing(false)} className="p-1 text-red-600 hover:bg-red-50 rounded"><span className="material-symbols-outlined text-sm">close</span></button>
          </div>
        ) : (
          <button onClick={() => setEditing(true)} className="invisible group-hover:visible p-1 text-muted hover:text-primary transition-all"><span className="material-symbols-outlined text-sm">edit</span></button>
        )}
      </td>
    </tr>
  );
}

export function UploadBulletinPage() {
  const [filesToProcess, setFilesToProcess] = useState<File[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<UploadResponse | null>(null);
  const [uploadJobId, setUploadJobId] = useState<string | null>(null);
  const [activeJobStatus, setActiveJobStatus] = useState<UploadJobStatus | null>(null);
  const [lastJobId, setLastJobId] = useState<string | null>(null);

  const [batchId, setBatchId] = useState<string | null>(null);
  const [batchStatus, setBatchStatus] = useState<UploadBatchStatus | null>(null);
  const [batchLoading, setBatchLoading] = useState(false);
  const [batchError, setBatchError] = useState<string | null>(null);

  const [history, setHistory] = useState<UploadJobStatus[]>([]);
  const [isDragging, setIsDragging] = useState(false);

  // Timer pour le temps écoulé
  const [startTime, setStartTime] = useState<number | null>(null);
  const [elapsedTime, setElapsedTime] = useState<number>(0);

  // Persistence LocalStorage pour éviter de perdre l'état au refresh/navigation
  useEffect(() => {
    const savedJobId = localStorage.getItem("anam_active_job_id");
    const savedBatchId = localStorage.getItem("anam_active_batch_id");

    if (savedJobId && !uploadJobId) {
      setUploadJobId(savedJobId);
      setUploading(true); // Re-trigger uploading state
    }
    if (savedBatchId && !batchId) {
      setBatchId(savedBatchId);
      setBatchLoading(true); // Re-trigger loading state
    }
  }, []);

  useEffect(() => {
    if (uploadJobId) {
      localStorage.setItem("anam_active_job_id", uploadJobId);
    } else if (uploading === false) {
      // Only clear if we explicitly finished, not just on component mount/remount
      // logic handled in polling effects
    }
  }, [uploadJobId, uploading]);

  useEffect(() => {
    if (batchId) localStorage.setItem("anam_active_batch_id", batchId);
    else localStorage.removeItem("anam_active_batch_id");
  }, [batchId]);

  // Timer effect - met à jour le temps écoulé chaque seconde
  useEffect(() => {
    if ((uploading || batchLoading) && startTime) {
      const interval = setInterval(() => {
        setElapsedTime(Math.floor((Date.now() - startTime) / 1000));
      }, 1000);
      return () => clearInterval(interval);
    }
  }, [uploading, batchLoading, startTime]);

  // Démarrer le timer quand le traitement commence
  useEffect(() => {
    if ((uploading || batchLoading) && !startTime) {
      setStartTime(Date.now());
      setElapsedTime(0);
    }
    if (!uploading && !batchLoading) {
      setStartTime(null);
    }
  }, [uploading, batchLoading]);

  // Formater le temps en mm:ss ou hh:mm:ss
  const formatElapsedTime = (seconds: number): string => {
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    if (hrs > 0) {
      return `${hrs}h ${mins.toString().padStart(2, '0')}m ${secs.toString().padStart(2, '0')}s`;
    }
    return `${mins}m ${secs.toString().padStart(2, '0')}s`;
  };

  // Estimation du temps restant basée sur la progression
  const estimateRemainingTime = (progress: number): string => {
    if (progress <= 0 || elapsedTime <= 0) return "Calcul...";

    const estimatedTotalTime = (elapsedTime / progress) * 100;
    const remaining = Math.max(0, Math.floor(estimatedTotalTime - elapsedTime));

    if (remaining === 0) return "Finalisation...";
    return `~${formatElapsedTime(remaining)}`;
  };

  const resultRef = useRef<HTMLDivElement>(null);
  const isInitialLoad = useRef(true);

  // Charger l'historique et reprendre l'état
  const loadHistoryAndResume = async () => {
    try {
      const jobs = await fetchUploadJobs(50);
      setHistory(jobs);

      if (isInitialLoad.current) {
        isInitialLoad.current = false;

        // 1. Chercher un job actif
        const activeJob = jobs.find(j => (j.status === 'running' || j.status === 'pending'));
        if (activeJob) {
          if (activeJob.job_type === 'upload_batch') {
            setBatchId(activeJob.job_id);
          } else {
            setUploadJobId(activeJob.job_id);
          }
          return;
        }

        // 2. Si aucun job actif, afficher le résultat du plus récent succès
        const latestSuccess = jobs.find(j => j.status === 'success' && j.result);
        if (latestSuccess) {
          setResult(latestSuccess.result as any);
          setLastJobId(latestSuccess.job_id);
        }
      }
    } catch (e) {
      console.error("Erreur historique", e);
    }
  };

  useEffect(() => {
    loadHistoryAndResume();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const getFilesFromEntry = async (entry: any): Promise<File[]> => {
    if (entry.isFile) {
      return new Promise((resolve) => entry.file((file: File) => resolve([file])));
    } else if (entry.isDirectory) {
      const dirReader = entry.createReader();
      const entries = await new Promise<any[]>((resolve) => dirReader.readEntries(resolve));
      const filesPromises = entries.map((e) => getFilesFromEntry(e));
      const filesArrays = await Promise.all(filesPromises);
      return filesArrays.flat().filter(f => f.name.toLowerCase().endsWith('.pdf') || f.name.toLowerCase().endsWith('.zip'));
    }
    return [];
  };

  const handleFileSelection = (files: FileList | File[] | null) => {
    if (!files) return;
    const next = Array.from(files).filter(f => f.name.toLowerCase().endsWith('.pdf') || f.name.toLowerCase().endsWith('.zip'));
    if (UPLOAD_BATCH_MAX_FILES > 0 && (filesToProcess.length + next.length) > UPLOAD_BATCH_MAX_FILES) {
      const message = `Limite atteinte: ${UPLOAD_BATCH_MAX_FILES} fichiers maximum.`;
      setError(message);
      reportError(message);
      setFilesToProcess(prev => [...prev, ...next].slice(0, UPLOAD_BATCH_MAX_FILES));
    } else {
      setFilesToProcess(prev => [...prev, ...next]);
      setError(null);
    }
    setResult(null);
    setBatchStatus(null);
    setBatchId(null);
  };

  const handleDrop = async (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    const items = e.dataTransfer.items;
    if (items && items.length > 0) {
      const promises: Promise<File[]>[] = [];
      for (let i = 0; i < items.length; i++) {
        if (items[i].kind === 'file') {
          const entry = items[i].webkitGetAsEntry();
          if (entry) promises.push(getFilesFromEntry(entry));
        }
      }
      const filesArrays = await Promise.all(promises);
      const allFiles = filesArrays.flat();
      if (allFiles.length > 0) handleFileSelection(allFiles);
    } else if (e.dataTransfer.files.length > 0) {
      handleFileSelection(e.dataTransfer.files);
    }
  };

  const clearQueue = () => {
    setFilesToProcess([]);
    setBatchId(null);
    setBatchStatus(null);
    setResult(null);
    setError(null);
  };

  const handleStartProcessing = async () => {
    if (filesToProcess.length === 0) return;
    if (filesToProcess.length === 1) {
      setUploading(true);
      setError(null);
      setResult(null);
      try {
        const response = await uploadBulletin(filesToProcess[0], { async: true });
        if ((response as any).job_id) setUploadJobId((response as any).job_id);
      } catch (err) {
        setError("Erreur d'upload");
        setUploading(false);
      }
    } else {
      setBatchLoading(true);
      try {
        const response = await uploadBulletinsBatch(filesToProcess);
        setBatchId(response.batch_id);
      } catch (err) {
        setBatchError("Erreur de batch");
      } finally {
        setBatchLoading(false);
      }
    }
  };

  // Polling Job Unique
  useEffect(() => {
    if (!uploadJobId) return;
    setUploading(true);
    let errorCount = 0;
    const interval = setInterval(async () => {
      try {
        const status = await fetchUploadJobStatus(uploadJobId);
        setActiveJobStatus(status);
        errorCount = 0; // Reset on success

        if (status.result) setResult(status.result as any);
        if (["success", "error", "partial"].includes(status.status)) {
          setUploading(false);
          setLastJobId(uploadJobId);
          setUploadJobId(null);
          localStorage.removeItem("anam_active_job_id");
          setActiveJobStatus(null);
          loadHistoryAndResume();
          clearInterval(interval);
        }
      } catch (e) {
        console.error("Polling job error:", e);
        errorCount++;
        // On ne coupe plus immédiatement au premier "Failed to fetch"
        // On attend 5 erreurs consécutives avant de lâcher prise
        if (errorCount > 5) {
          setUploadJobId(null);
          localStorage.removeItem("anam_active_job_id");
          setUploading(false);
          setActiveJobStatus(null);
          clearInterval(interval);
        }
      }
    }, 2500); // 2.5s instead of 1.2s to be more stable
    return () => clearInterval(interval);
  }, [uploadJobId]);

  // Polling Batch
  useEffect(() => {
    if (!batchId) return;
    setBatchLoading(true);
    let errorCount = 0;
    const interval = setInterval(async () => {
      try {
        const data = await fetchUploadBatchStatus(batchId);
        setBatchStatus(data);
        errorCount = 0;

        // Si on est dans un batch, on essaie d'afficher le résultat du plus récent succès
        const lastSuccess = [...(data.jobs || [])].reverse().find(j => j.status === 'success' && j.result);
        if (lastSuccess && !result) setResult(lastSuccess.result as any);

        if (["success", "error", "partial", "canceled"].includes(data.status)) {
          setBatchId(null);
          setBatchLoading(false);
          localStorage.removeItem("anam_active_batch_id");
          loadHistoryAndResume();
          clearInterval(interval);
        }
      } catch (e) {
        console.error("Polling batch error:", e);
        errorCount++;
        if (errorCount > 5) {
          setBatchId(null);
          setBatchLoading(false);
          localStorage.removeItem("anam_active_batch_id");
          clearInterval(interval);
        }
      }
    }, 3000); // 3s instead of 2s
    return () => clearInterval(interval);
  }, [batchId]);

  const handleTemperatureUpdate = (pIdx: number, mIdx: number, tIdx: number, val: TemperatureValue) => {
    setResult(prev => {
      if (!prev) return null;
      const next = { ...prev };
      next.temperatures[pIdx].data[mIdx].temperatures[tIdx] = val;
      return next;
    });
  };

  const handleRetry = async () => {
    const target = lastJobId || uploadJobId;
    if (!target) return;
    setUploading(true);
    setUploadJobId(target);
    await retryUploadJob(target);
  };

  const handleFeedback = async () => {
    const target = lastJobId || uploadJobId;
    if (!target || !result) return;
    await submitFeedback(target, result.temperatures);
    alert("Données validées !");
  };

  const handlePrint = () => {
    window.print();
  };

  const handleDeleteJob = async (jobId: string) => {
    if (!confirm("Supprimer ce job de l'historique ?")) return;
    try {
      await deleteUploadJob(jobId);
      setHistory(prev => prev.filter(j => j.job_id !== jobId));
      if (lastJobId === jobId) {
        setResult(null);
        setLastJobId(null);
      }
    } catch (e) {
      alert("Erreur suppression");
    }
  };

  const selectJobFromHistory = (job: UploadJobStatus) => {
    if (job.result) {
      setResult(job.result as any);
      setLastJobId(job.job_id);
      setUploadJobId(null);
      setBatchId(null);
    } else {
      if (["pending", "running"].includes(job.status)) {
        if (job.job_type === 'upload_batch') setBatchId(job.job_id);
        else setUploadJobId(job.job_id);
      } else {
        setResult(null);
      }
    }
  };

  const getStepLabel = (progress: number) => {
    if (progress < 40) return "Conversion PDF en images...";
    if (progress < 70) return "Extraction des données (AI)...";
    if (progress < 90) return "Interprétation linguistique...";
    if (progress < 100) return "Enregistrement en base...";
    return "Terminé !";
  };

  // Calcul du progrès basé sur les résultats visibles (fallback si backend ne met pas à jour)
  const calculateProgressFromResults = (): number => {
    if (!result || !uploading) return 0;

    // Compter le nombre total de détections dans les résultats
    let totalDetections = 0;
    let totalMaps = 0;

    result.temperatures?.forEach(entry => {
      entry.data?.forEach(map => {
        totalMaps++;
        totalDetections += map.temperatures?.length || 0;
      });
    });

    // Si on a des résultats, on est au moins à 40% (conversion terminée)
    // Chaque détection représente une portion du travail d'extraction (40-85%)
    if (totalDetections > 0) {
      // 10 villes par carte = 100%, mapper à 40-85%
      const expectedPerMap = 10; // Nombre attendu de villes par carte
      const extractionProgress = Math.min((totalDetections / (totalMaps * expectedPerMap)) * 100, 100);
      return 40 + (extractionProgress * 0.45); // 40% + jusqu'à 45% = 85% max
    }

    // Si on a des cartes mais pas encore de détections, on est en train de convertir
    if (totalMaps > 0) {
      return 35; // Conversion quasi terminée
    }

    // Si on a au moins un PDF entry, la conversion a commencé
    if (result.temperatures?.length > 0) {
      return 20;
    }

    return 5; // Démarrage
  };

  // Progrès effectif : prend le max entre backend et calcul local
  const effectiveProgress = batchStatus
    ? ((batchStatus.success + batchStatus.error) / batchStatus.total) * 100
    : Math.max(activeJobStatus?.progress || 0, calculateProgressFromResults());

  return (
    <Layout title="Importation Bulletins">
      <div className="max-w-7xl mx-auto space-y-8 pb-12 px-4 print:p-0">
        <div className="space-y-2 print:hidden">
          <h1 className="text-4xl font-black text-ink tracking-tight">Importation & Traitement</h1>
          <p className="text-muted text-base">Suivez en temps réel l'extraction de vos bulletins météorologiques.</p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          <div className="lg:col-span-2 space-y-6">
            <div
              onDrop={handleDrop}
              onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
              onDragLeave={() => setIsDragging(false)}
              className={`relative flex flex-col items-center justify-center p-12 border-2 border-dashed rounded-[2.5rem] transition-all duration-300 print:hidden ${isDragging ? "border-primary bg-primary/5 scale-[0.98]" : "border-[var(--border)] bg-[var(--surface)] hover:bg-[var(--surface-strong)]/30"
                }`}
            >
              <div className="size-20 rounded-full bg-gradient-to-br from-primary to-secondary text-white flex items-center justify-center shadow-lg mb-4">
                <span className="material-symbols-outlined text-4xl">{isDragging ? "download" : "cloud_upload"}</span>
              </div>
              <p className="text-xl font-bold text-ink mb-2">Glissez-déposez ici</p>
              <div className="flex gap-3">
                <label className="px-6 py-2 bg-[var(--surface-strong)] rounded-xl text-sm font-bold border border-[var(--border)] cursor-pointer hover:bg-muted transition-colors">
                  <input type="file" multiple accept=".pdf,.zip" onChange={(e) => handleFileSelection(e.target.files)} className="hidden" />
                  Fichiers
                </label>
                <label className="px-6 py-2 bg-[var(--surface-strong)] rounded-xl text-sm font-bold border border-[var(--border)] cursor-pointer hover:bg-muted transition-colors">
                  {/* @ts-ignore */}
                  <input type="file" webkitdirectory="" directory="" multiple onChange={(e) => handleFileSelection(e.target.files)} className="hidden" />
                  Dossier
                </label>
              </div>
            </div>

            {/* Barre de progression principale avec Pipeline Visuel */}
            {(uploading || batchId) && (
              <div className="bg-[var(--surface)] border-2 border-primary/20 rounded-[2.5rem] p-8 shadow-2xl space-y-8 animate-in fade-in zoom-in-95 duration-500 print:hidden relative overflow-hidden">
                {/* Effet de brillance animé en arrière-plan */}
                <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-transparent via-primary/40 to-transparent animate-shimmer" />

                <div className="flex items-center justify-between gap-4">
                  <div className="flex items-center gap-4">
                    <div className="size-12 rounded-2xl bg-primary/10 text-primary flex items-center justify-center relative">
                      <span className="material-symbols-outlined animate-spin">sync</span>
                      <div className="absolute -top-1 -right-1 size-3 bg-emerald-500 rounded-full border-2 border-[var(--surface)] animate-pulse" />
                    </div>
                    <div>
                      <h2 className="font-black text-xl text-ink tracking-tight">
                        {batchId ? "Pipeline Groupé" : "Pipeline d'Extraction"}
                      </h2>
                      <div className="flex items-center gap-2">
                        <span className="size-2 rounded-full bg-emerald-500 animate-pulse" />
                        <p className="text-xs font-bold text-emerald-600 uppercase tracking-widest">Traitement en direct</p>
                      </div>
                    </div>
                  </div>
                  <div className="text-right">
                    <span className="text-4xl font-black text-primary tabular-nums">
                      {Math.round(effectiveProgress)}%
                    </span>
                    <div className="mt-1 flex items-center justify-end gap-3 text-xs text-muted">
                      <span className="flex items-center gap-1">
                        <span className="material-symbols-outlined text-sm">timer</span>
                        {formatElapsedTime(elapsedTime)}
                      </span>
                      <span className="flex items-center gap-1 text-primary-600">
                        <span className="material-symbols-outlined text-sm">hourglass_top</span>
                        {estimateRemainingTime(effectiveProgress)}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Pipeline Steps Visuel */}
                <div className="grid grid-cols-3 gap-4 relative">
                  {/* Ligne de connexion en arrière-plan */}
                  <div className="absolute top-5 left-[15%] right-[15%] h-1 bg-[var(--surface-strong)] rounded-full z-0" />

                  {[
                    { label: "Conversion", icon: "picture_as_pdf", min: 0, max: 40 },
                    { label: "Extraction IA", icon: "psychology", min: 40, max: 85 },
                    { label: "Interprétation", icon: "translate", min: 85, max: 100 }
                  ].map((step, i) => {
                    const prog = effectiveProgress;

                    const isDone = prog >= step.max;
                    const isCurrent = prog >= step.min && prog < step.max;

                    return (
                      <div key={i} className="flex flex-col items-center gap-3 z-10">
                        <div className={`size-10 rounded-full flex items-center justify-center transition-all duration-500 border-2 ${isDone ? "bg-emerald-500 border-emerald-500 text-white shadow-lg shadow-emerald-500/20" :
                          isCurrent ? "bg-primary border-primary text-white shadow-lg shadow-primary/20 scale-110" :
                            "bg-[var(--surface-strong)] border-[var(--border)] text-muted"
                          }`}>
                          <span className="material-symbols-outlined text-xl">{isDone ? "check" : step.icon}</span>
                        </div>
                        <span className={`text-[10px] font-black uppercase tracking-widest ${isCurrent ? "text-primary" : "text-muted"}`}>
                          {step.label}
                        </span>
                      </div>
                    );
                  })}
                </div>

                <div className="space-y-3">
                  <div className="h-4 w-full bg-[var(--surface-strong)] rounded-full overflow-hidden p-1 shadow-inner relative">
                    <div
                      className="h-full bg-gradient-to-r from-primary via-secondary to-primary bg-[length:200%_100%] animate-gradient-x rounded-full transition-all duration-1000 shadow-sm"
                      style={{
                        width: `${Math.max(effectiveProgress, uploading ? 5 : 0)}%`
                      }}
                    />
                  </div>
                  <div className="flex justify-between items-center px-1">
                    <p className="text-[11px] font-medium text-muted">
                      {batchStatus
                        ? <><b className="text-ink">{batchStatus.success + batchStatus.error}</b> sur <b className="text-ink">{batchStatus.total}</b> fichiers terminés</>
                        : getStepLabel(effectiveProgress)
                      }
                    </p>
                    {batchId && (
                      <button onClick={() => stopUploadBatch(batchId)} className="group flex items-center gap-1.5 px-3 py-1.5 bg-red-50 hover:bg-red-100 text-red-600 rounded-lg transition-colors border border-red-100">
                        <span className="material-symbols-outlined text-sm">cancel</span>
                        <span className="text-[10px] font-black uppercase tracking-widest">Annuler</span>
                      </button>
                    )}
                  </div>
                </div>
              </div>
            )}

            {result && (
              <div id="extraction-result" ref={resultRef} className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-700">
                <div className="flex items-center justify-between border-b border-[var(--border)] pb-4 print:border-b-2">
                  <h2 className="text-2xl font-black text-ink">Résultats de l'extraction</h2>
                  <div className="flex gap-2 print:hidden">
                    <button onClick={handlePrint} className="flex items-center gap-2 px-4 py-2 bg-[var(--surface-strong)] rounded-xl text-xs font-bold hover:bg-muted border border-[var(--border)]">
                      <span className="material-symbols-outlined text-sm">print</span>
                      Imprimer / PDF
                    </button>
                    <button onClick={handleRetry} className="px-4 py-2 bg-orange-500/10 text-orange-600 rounded-xl text-xs font-bold hover:bg-orange-500/20">Réparer</button>
                    <button onClick={handleFeedback} className="px-4 py-2 bg-emerald-600 text-white rounded-xl text-xs font-bold hover:bg-emerald-700 shadow-lg">Valider</button>
                  </div>
                </div>

                {result.temperatures?.map((entry, pIdx) => (
                  <div key={pIdx} className="bg-[var(--surface)] border border-[var(--border)] rounded-3xl p-6 shadow-xl space-y-6 print:shadow-none print:border-2 print:rounded-none breakout-page break-inside-avoid">
                    <div className="flex items-center justify-between gap-4 border-b border-[var(--border)] pb-4 print:pb-2">
                      <div className="flex items-center gap-3">
                        <span className="material-symbols-outlined text-primary text-3xl print:text-2xl">picture_as_pdf</span>
                        <div className="flex-1 overflow-hidden">
                          <p className="text-sm font-bold truncate">{entry.pdf_path?.split(/[\\/]/).pop()}</p>
                          <div className="flex items-center gap-2">
                            <span className={`text-[9px] font-black uppercase px-2 py-0.5 rounded ${entry.type === 'observation' ? 'bg-sky-100 text-sky-700' : 'bg-purple-100 text-purple-700'}`}>
                              {entry.type}
                            </span>
                            <span className="text-[10px] text-muted font-bold font-mono">{entry.date}</span>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Section Interpretation */}
                    {(entry.interpretation_francais || entry.interpretation_moore || entry.interpretation_dioula) && (
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 bg-slate-50/50 p-5 rounded-3xl border border-slate-200/60">
                        <div className="space-y-2">
                          <div className="flex items-center gap-2">
                            <span className="size-1.5 rounded-full bg-blue-500"></span>
                            <p className="text-[10px] font-black uppercase text-slate-500 tracking-[0.2em]">Français</p>
                          </div>
                          <p className="text-xs text-ink leading-relaxed text-justify">{entry.interpretation_francais || "N/A"}</p>
                        </div>
                        <div className="space-y-2 border-t md:border-t-0 md:border-l border-slate-200 pt-4 md:pt-0 md:pl-6">
                          <div className="flex items-center gap-2">
                            <span className="size-1.5 rounded-full bg-amber-500"></span>
                            <p className="text-[10px] font-black uppercase text-slate-500 tracking-[0.2em]">Mòoré</p>
                          </div>
                          <p className="text-xs text-ink leading-relaxed font-medium italic text-justify">{entry.interpretation_moore || "En attente..."}</p>
                        </div>
                        <div className="space-y-2 border-t md:border-t-0 md:border-l border-slate-200 pt-4 md:pt-0 md:pl-6">
                          <div className="flex items-center gap-2">
                            <span className="size-1.5 rounded-full bg-emerald-500"></span>
                            <p className="text-[10px] font-black uppercase text-slate-500 tracking-[0.2em]">Dioula</p>
                          </div>
                          <p className="text-xs text-ink leading-relaxed font-medium italic text-justify">{entry.interpretation_dioula || "En attente..."}</p>
                        </div>
                      </div>
                    )}

                    {entry.data?.map((map, mIdx) => (
                      <div key={mIdx} className="space-y-4 pt-2">
                        <div className="flex items-center gap-2">
                          <span className="material-symbols-outlined text-muted text-base">map</span>
                          <h3 className="font-bold text-sm text-ink uppercase tracking-wider">Carte de Températures</h3>
                        </div>
                        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 print:grid-cols-1">
                          <div className="border border-[var(--border)] rounded-xl overflow-hidden bg-[var(--surface-strong)]/20 shadow-inner print:rounded-none">
                            <table className="w-full text-xs">
                              <thead className="bg-[var(--surface-strong)]/50 text-muted uppercase tracking-widest font-black print:bg-gray-100">
                                <tr>
                                  <th className="px-3 py-2 text-left">Station</th>
                                  <th className="px-3 py-2 text-left">Météo</th>
                                  <th className="px-3 py-2 text-left">Min</th>
                                  <th className="px-3 py-2 text-left">Max</th>
                                  <th className="px-3 py-2 print:hidden"></th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-[var(--border)]">
                                {map.temperatures?.map((t, tIdx) => (
                                  <TemperatureRow key={tIdx} data={t} onSave={(val) => handleTemperatureUpdate(pIdx, mIdx, tIdx, val)} />
                                ))}
                              </tbody>
                            </table>
                          </div>
                          <OCRVisualizer imagePath={map.image_path || entry.image_path || ""} detections={map.temperatures} />
                        </div>
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            )}

            {!result && !uploading && !batchId && (
              <div className="bg-[var(--surface)] p-12 rounded-3xl border border-[var(--border)] text-center space-y-4 print:hidden">
                <span className="material-symbols-outlined text-muted text-6xl">insights</span>
                <p className="text-muted font-medium">Les résultats de l'extraction s'afficheront ici une fois le traitement terminé.</p>
              </div>
            )}
          </div>

          <div className="space-y-6 print:hidden">
            <div className="bg-[var(--surface)] border border-[var(--border)] rounded-[2rem] shadow-xl overflow-hidden">
              <div className="p-5 border-b border-[var(--border)] bg-[var(--surface-strong)]/50 flex justify-between items-center">
                <h3 className="font-black text-sm uppercase tracking-widest">Attente ({filesToProcess.length})</h3>
                <button onClick={clearQueue} className="text-[10px] text-red-500 font-bold hover:underline">Vider</button>
              </div>
              <div className="p-4 space-y-3 max-h-[300px] overflow-y-auto">
                {filesToProcess?.map((f, i) => (
                  <div key={i} className="flex items-center gap-3 p-3 bg-[var(--surface-strong)]/30 rounded-2xl border border-[var(--border)] group">
                    <span className="material-symbols-outlined text-muted text-sm">{f.name.endsWith('.zip') ? 'archive' : 'description'}</span>
                    <div className="flex-1 min-w-0">
                      <p className="text-[11px] font-bold truncate">{f.name}</p>
                      <p className="text-[9px] text-muted">{(f.size / 1024).toFixed(0)} KB</p>
                    </div>
                    <button onClick={() => setFilesToProcess(prev => prev.filter((_, idx) => idx !== i))} className="opacity-0 group-hover:opacity-100 text-muted hover:text-red-500 transition-opacity">
                      <span className="material-symbols-outlined text-sm">close</span>
                    </button>
                  </div>
                ))}
                {filesToProcess.length > 0 && (
                  <button onClick={handleStartProcessing} disabled={uploading || batchLoading} className="w-full py-4 mt-2 bg-gradient-to-r from-primary to-secondary text-white font-bold rounded-2xl shadow-lg hover:shadow-primary/20 scale-[1] hover:scale-[1.02] transition-all disabled:opacity-50">
                    {uploading || batchLoading ? "Traitement..." : `Lancer l'extraction`}
                  </button>
                )}
                {filesToProcess.length === 0 && <p className="py-8 text-center text-xs text-muted font-medium italic">File d'attente vide</p>}
              </div>
            </div>

            <div className="bg-[var(--surface)] border border-[var(--border)] rounded-[2rem] shadow-xl overflow-hidden">
              <div className="p-5 border-b border-[var(--border)] bg-[var(--surface-strong)]/50 flex justify-between items-center">
                <h3 className="font-black text-sm uppercase tracking-widest">Historique</h3>
                <button onClick={loadHistoryAndResume} className="text-muted hover:text-primary transition-colors"><span className="material-symbols-outlined text-sm">refresh</span></button>
              </div>
              <div className="p-2 space-y-1 max-h-[400px] overflow-y-auto">
                {history.length === 0 && <p className="py-8 text-center text-xs text-muted italic">Aucun historique.</p>}
                {history?.map((job) => (
                  <div
                    key={job.job_id}
                    className={`flex items-center gap-3 p-3 rounded-2xl border transition-all group cursor-pointer ${lastJobId === job.job_id || uploadJobId === job.job_id || batchId === job.job_id ? "border-primary bg-primary/5" : "border-transparent hover:bg-[var(--surface-strong)]/30"
                      }`}
                    onClick={() => selectJobFromHistory(job)}
                  >
                    <div className={`size-8 rounded-full flex items-center justify-center shrink-0 ${job.status === 'success' ? 'bg-emerald-100 text-emerald-600' :
                      job.status === 'error' ? 'bg-red-100 text-red-600' :
                        'bg-primary/10 text-primary'
                      }`}>
                      {job.status === 'running' || job.status === 'pending' ? (
                        <span className="material-symbols-outlined text-base animate-spin">sync</span>
                      ) : (
                        <span className="material-symbols-outlined text-base">
                          {job.job_type === 'upload_batch' ? 'layers' : 'description'}
                        </span>
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-[11px] font-bold truncate text-ink">{job.filename || job.job_id.slice(0, 8)}</p>
                      <div className="flex items-center gap-2">
                        <span className={`text-[8px] font-black uppercase px-1.5 py-0.5 rounded-md ${job.status === 'success' ? 'bg-emerald-500/10 text-emerald-600' :
                          job.status === 'running' ? 'bg-primary/10 text-primary animate-pulse' :
                            'bg-slate-100 text-muted'
                          }`}>
                          {job.status}
                        </span>
                        <p className="text-[9px] text-muted">
                          {job.status === 'running' ? `${job.progress || 0}%` : new Date(job.created_at || '').toLocaleString('fr-FR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}
                        </p>
                      </div>
                    </div>
                    <button
                      onClick={(e) => { e.stopPropagation(); handleDeleteJob(job.job_id); }}
                      className="opacity-0 group-hover:opacity-100 p-1 text-muted hover:text-red-500 transition-opacity"
                    >
                      <span className="material-symbols-outlined text-sm">delete</span>
                    </button>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      <style>{`
        @media print {
          /* 1. Configuration de la Page */
          @page { 
            margin: 1cm; 
            size: a4 portrait; 
          }

          /* 2. Cacher TOUTE l'interface technique par IDs */
          #main-header, 
          #app-sidebar, 
          #global-status-indicator,
          nav, 
          aside, 
          header,
          button,
          .print\\:hidden,
          [aria-label="Ouvrir le menu"],
          .flex.h-20.items-center { 
            display: none !important; 
            visibility: hidden !important;
            height: 0 !important;
            width: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
          }

          /* 3. Libérer le conteneur principal */
          body, html {
            background: #f8fafc !important; /* Couleur slate-50 comme à l'écran */
            color: #0f172a !important; /* Couleur ink */
            height: auto !important;
            overflow: visible !important;
            -webkit-print-color-adjust: exact !important;
            print-color-adjust: exact !important;
          }

          /* Débloquer les parents */
          .h-screen, .flex-col, .lg\\:pl-64, main {
            display: block !important;
            position: static !important;
            height: auto !important;
            min-height: auto !important;
            overflow: visible !important;
            padding: 0 !important;
            margin: 0 !important;
            width: 100% !important;
            background: transparent !important;
          }

          /* 4. Formatage du Résultat "Fidèle" (Fiel) */
          #extraction-result {
            display: block !important;
            visibility: visible !important;
            width: 100% !important;
            margin: 0 !important;
            padding: 10px !important;
          }

          /* Chaque bulletin sur une nouvelle page si trop long */
          .bg-\\[var\\(--surface\\)\\].border.border-\\[var\\(--border\\)\\] {
            break-inside: avoid !important;
            page-break-inside: avoid !important;
            margin-bottom: 2rem !important;
            border: 1px solid #e2e8f0 !important;
            border-radius: 20px !important;
            box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1) !important;
            background: white !important;
            padding: 2rem !important;
          }

          /* Conservation des couleurs des badges */
          .bg-sky-100 { background-color: #e0f2fe !important; }
          .text-sky-700 { color: #0369a1 !important; }
          .bg-purple-100 { background-color: #f3e8ff !important; }
          .text-purple-700 { color: #7e22ce !important; }
          
          /* Force les maps à être visibles et bien rangées */
          .grid { 
            display: block !important; 
          }
          
          .grid > div {
            display: block !important;
            margin-bottom: 1.5rem !important;
            width: 100% !important;
          }

          /* Assurer que l'image de la map est visible */
          img {
            display: block !important;
            width: 100% !important;
            height: auto !important;
            max-height: 500px !important;
            object-fit: contain !important;
            margin: 10px 0 !important;
            border-radius: 12px !important;
          }

          /* Amélioration des tableaux */
          table {
            width: 100% !important;
            border-collapse: separate !important;
            border-spacing: 0 !important;
            border: 1px solid #e2e8f0 !important;
            border-radius: 12px !important;
            overflow: hidden !important;
          }
          
          th {
            background-color: #f1f5f9 !important;
            color: #64748b !important;
            font-weight: 800 !important;
            padding: 10px !important;
            border-bottom: 1px solid #e2e8f0 !important;
          }

          td {
            padding: 8px 12px !important;
            border-bottom: 1px solid #f1f5f9 !important;
          }

          /* Cacher les contrôles de ligne d'édition */
          .print\\:hidden { display: none !important; }
        }
      `}</style>
    </Layout>
  );
}
