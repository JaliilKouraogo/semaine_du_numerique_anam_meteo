import React, { useEffect, useState } from "react";
import { Sidebar } from "./Sidebar";
import { NAV_ITEMS, type NavItem } from "../navigation";
import { GlobalStatusIndicator } from "./GlobalStatusIndicator";
import { DEBUG_MODE, BACKEND_DEBUG_MODE } from "../config";
import { setPipelineRunning, statusStore } from "../services/statusStore";
import { fetchMe, fetchPipelineRuns, logout, type MeResponse } from "../services/api";
import { useNavigate } from "react-router-dom";

const THEME_KEY = "anam-theme";

const getStoredTheme = () => {
  if (typeof window === "undefined") {
    return null;
  }
  const stored = window.localStorage.getItem(THEME_KEY);
  if (stored === "dark" || stored === "light") {
    return stored;
  }
  return null;
};

const getInitialTheme = () => {
  if (typeof window === "undefined") {
    return false;
  }
  const stored = getStoredTheme();
  if (stored === "dark") return true;
  if (stored === "light") return false;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
};

type LayoutProps = {
  children: React.ReactNode;
  title?: string;
  navItems?: NavItem[];
  fixed?: boolean;
  fullWidth?: boolean;
};

export function Layout({ children, title, navItems = NAV_ITEMS, fixed = false, fullWidth = false }: LayoutProps) {
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [isDesktopSidebarOpen, setIsDesktopSidebarOpen] = useState(true);
  const [isDarkMode, setIsDarkMode] = useState(getInitialTheme);
  const [isThemeLocked, setIsThemeLocked] = useState(() => getStoredTheme() !== null);
  const [isPipelineRunning, setIsPipelineRunning] = useState(
    () => statusStore.getState().pipelineRunning
  );
  const [user, setUser] = useState<MeResponse | null>(null);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", isDarkMode);
    if (isThemeLocked) {
      window.localStorage.setItem(THEME_KEY, isDarkMode ? "dark" : "light");
    }
  }, [isDarkMode, isThemeLocked]);

  useEffect(() => {
    const unsubscribe = statusStore.subscribe(() => {
      setIsPipelineRunning(statusStore.getState().pipelineRunning);
    });
    return () => {
      unsubscribe();
    };
  }, []);

  useEffect(() => {
    const loadUser = async () => {
      try {
        const data = await fetchMe();
        setUser(data);
      } catch {
        // user not logged in or token expired
      }
    };
    loadUser();
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (isThemeLocked) return;
    const media = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!media) return;
    const handler = (event: MediaQueryListEvent) => {
      setIsDarkMode(event.matches);
    };
    media.addEventListener?.("change", handler);
    return () => {
      media.removeEventListener?.("change", handler);
    };
  }, [isThemeLocked]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const handler = (event: StorageEvent) => {
      if (event.key !== THEME_KEY) return;
      const stored = getStoredTheme();
      if (!stored) {
        setIsThemeLocked(false);
        setIsDarkMode(window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false);
        return;
      }
      setIsThemeLocked(true);
      setIsDarkMode(stored === "dark");
    };
    window.addEventListener("storage", handler);
    return () => window.removeEventListener("storage", handler);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const data = await fetchPipelineRuns();
        const latest = data.runs?.[0];
        if (!cancelled) {
          setPipelineRunning(latest?.status === "running");
        }
      } catch {
        // ignore polling errors
      }
    };

    poll();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!isPipelineRunning) {
      return;
    }
    let cancelled = false;
    const poll = async () => {
      try {
        const data = await fetchPipelineRuns();
        const latest = data.runs?.[0];
        if (!cancelled) {
          setPipelineRunning(latest?.status === "running");
        }
      } catch {
        // ignore polling errors
      }
    };

    poll();
    const interval = setInterval(poll, 60000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [isPipelineRunning]);


  const mainPadding = title ? "pt-24" : "pt-6";
  const mainOverflow = fixed ? "overflow-hidden" : "overflow-y-auto";
  const mainPaddingBottom = fixed ? "pb-0" : "pb-6";
  const desktopPadding = isDesktopSidebarOpen ? "lg:pl-64" : "lg:pl-0";
  const debugLabel = DEBUG_MODE && BACKEND_DEBUG_MODE
    ? "Debug UI/API"
    : DEBUG_MODE
      ? "Debug UI"
      : BACKEND_DEBUG_MODE
        ? "Debug API"
        : null;

  return (
    <div className="h-screen overflow-hidden bg-transparent">
      <Sidebar
        navItems={navItems}
        isMobileOpen={isSidebarOpen}
        isDesktopOpen={isDesktopSidebarOpen}
        onClose={() => setIsSidebarOpen(false)}
        onDesktopToggle={() => setIsDesktopSidebarOpen((prev: boolean) => !prev)}
      />
      <div className={`flex h-full flex-col bg-transparent ${desktopPadding}`}>
        {title && (
          <header
            id="main-header"
            className={`fixed top-0 left-0 right-0 z-20 flex h-20 items-center justify-between border-b border-[var(--border)] bg-[var(--surface)]/85 px-4 backdrop-blur sm:px-6 ${isDesktopSidebarOpen ? "lg:left-64" : "lg:left-0"
              }`}
          >
            <div className="flex items-center gap-3">
              <button
                type="button"
                className="lg:hidden size-10 rounded-xl border border-[var(--border)] flex items-center justify-center text-muted"
                onClick={() => setIsSidebarOpen(true)}
                aria-label="Ouvrir le menu"
              >
                <span className="material-symbols-outlined">menu</span>
              </button>
              <button
                type="button"
                className="hidden lg:flex size-10 rounded-xl border border-[var(--border)] items-center justify-center text-muted hover:bg-[var(--canvas-strong)] transition-colors"
                onClick={() => setIsDesktopSidebarOpen((prev: boolean) => !prev)}
                aria-label="Afficher ou masquer la navigation"
              >
                <span className="material-symbols-outlined">
                  {isDesktopSidebarOpen ? "left_panel_close" : "left_panel_open"}
                </span>
              </button>
              <div className="size-10 rounded-2xl bg-gradient-to-br from-primary-500 to-secondary-600 hidden sm:flex items-center justify-center shadow-lg">
                <span className="material-symbols-outlined text-white text-xl">insights</span>
              </div>
              <div>
                <h2 className="text-ink text-xl font-semibold leading-tight font-display">{title}</h2>
                <p className="text-xs text-muted uppercase tracking-[0.3em]">Console technique</p>
              </div>
            </div>
            <div className="flex items-center gap-3 max-w-full">
              {debugLabel && (
                <span className="rounded-full border border-red-300/60 bg-red-500/15 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-red-700">
                  {debugLabel}
                </span>
              )}
              <div className="relative hidden md:flex">
                <input
                  type="text"
                  placeholder="Rechercher station, date, alerte"
                  className="w-64 px-4 py-2 pl-10 rounded-full border border-[var(--border)] bg-[var(--surface)]/70 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/30"
                />
                <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-muted text-lg">
                  search
                </span>
              </div>
              <button className="relative flex items-center justify-center rounded-xl h-10 w-10 text-muted hover:bg-[var(--canvas-strong)] transition-colors">
                <span className="material-symbols-outlined">notifications</span>
                <span className="absolute top-1 right-1 size-2 bg-primary-500 rounded-full"></span>
              </button>
              <button
                type="button"
                onClick={() => {
                  setIsThemeLocked(true);
                  setIsDarkMode((prev: boolean) => !prev);
                }}
                className="flex h-10 w-10 items-center justify-center rounded-full bg-[var(--canvas-strong)] text-ink hover:bg-[var(--canvas-strong)] transition-colors"
                aria-label="Basculer le th&egrave;me"
              >
                <span className="material-symbols-outlined">{isDarkMode ? "light_mode" : "dark_mode"}</span>
              </button>
              <div className="hidden sm:flex items-center gap-2 pl-4 border-l border-[var(--border)]">
                <div className="text-right">
                  <p className="text-sm font-medium text-ink">{user?.username || "Chargement..."}</p>
                  <button
                    onClick={() => logout()}
                    className="text-[10px] text-red-500 hover:text-red-400 font-bold uppercase tracking-widest text-left"
                  >
                    Déconnexion
                  </button>
                </div>
                <div className="bg-gradient-to-br from-primary-500 to-secondary-600 rounded-full size-10 flex items-center justify-center shadow-md">
                  <span className="material-symbols-outlined text-white text-sm">person</span>
                </div>
              </div>
            </div>
          </header>

        )}
        <main
          className={`flex-1 ${mainOverflow} overflow-x-hidden bg-transparent ${fullWidth ? "px-1" : "px-4 sm:px-6"} ${mainPaddingBottom} ${mainPadding}`}
          style={{ scrollbarGutter: "stable" }}
        >
          <div className={fullWidth ? "" : "mx-auto max-w-7xl"}>{children}</div>
        </main>
        <GlobalStatusIndicator />
      </div>
    </div>
  );
}
