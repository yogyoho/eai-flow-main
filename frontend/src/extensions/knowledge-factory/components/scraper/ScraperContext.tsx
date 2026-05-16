"use client";

import React, { createContext, useCallback, useContext, useState, type ReactNode } from "react";

export interface ScrapePrefill {
  url?: string;
  provider?: string;
  schema?: string;
  llm_model?: string;
}

interface ScraperContextValue {
  activeSubTab: string;
  setActiveSubTab: (tab: string) => void;
  scrapeDialogOpen: boolean;
  scrapePrefill: ScrapePrefill | null;
  openScrapeDialog: (prefill?: ScrapePrefill) => void;
  closeScrapeDialog: () => void;
  newlyCreatedTaskId: string | null;
  setNewlyCreatedTaskId: (id: string | null) => void;
  taskRefreshTrigger: number;
  triggerTaskRefresh: () => void;
  draftRefreshTrigger: number;
  triggerDraftRefresh: () => void;
}

const ScraperContext = createContext<ScraperContextValue | null>(null);

export function ScraperContextProvider({ children }: { children: ReactNode }) {
  const [activeSubTab, setActiveSubTab] = useState("task-center");
  const [scrapeDialogOpen, setScrapeDialogOpen] = useState(false);
  const [scrapePrefill, setScrapePrefill] = useState<ScrapePrefill | null>(null);
  const [newlyCreatedTaskId, setNewlyCreatedTaskId] = useState<string | null>(null);
  const [taskRefreshTrigger, setTaskRefreshTrigger] = useState(0);
  const [draftRefreshTrigger, setDraftRefreshTrigger] = useState(0);

  const openScrapeDialog = useCallback((prefill?: ScrapePrefill) => {
    setScrapePrefill(prefill || null);
    setScrapeDialogOpen(true);
  }, []);

  const closeScrapeDialog = useCallback(() => {
    setScrapeDialogOpen(false);
    setScrapePrefill(null);
  }, []);

  const triggerTaskRefresh = useCallback(() => setTaskRefreshTrigger((n) => n + 1), []);
  const triggerDraftRefresh = useCallback(() => setDraftRefreshTrigger((n) => n + 1), []);

  return (
    <ScraperContext.Provider
      value={{
        activeSubTab,
        setActiveSubTab,
        scrapeDialogOpen,
        scrapePrefill,
        openScrapeDialog,
        closeScrapeDialog,
        newlyCreatedTaskId,
        setNewlyCreatedTaskId,
        taskRefreshTrigger,
        triggerTaskRefresh,
        draftRefreshTrigger,
        triggerDraftRefresh,
      }}
    >
      {children}
    </ScraperContext.Provider>
  );
}

export function useScraperContext() {
  const ctx = useContext(ScraperContext);
  if (!ctx) throw new Error("useScraperContext must be used within ScraperContextProvider");
  return ctx;
}
