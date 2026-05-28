"use client";

import React from "react";

import { ScraperContextProvider, useScraperContext } from "./components/scraper/ScraperContext";
import ScraperDraftBox from "./components/scraper/ScraperDraftBox";
import ScraperScrapeDialog from "./components/scraper/ScraperScrapeDialog";
import ScraperSourceManager from "./components/scraper/ScraperSourceManager";
import ScraperSubNav from "./components/scraper/ScraperSubNav";
import ScraperTaskCenter from "./components/scraper/ScraperTaskCenter";

const SUB_TAB_COMPONENTS: Record<string, React.ComponentType> = {
  "task-center": ScraperTaskCenter,
  "source-manager": ScraperSourceManager,
  "draft-box": ScraperDraftBox,
};

function ScraperPageInner() {
  const { activeSubTab } = useScraperContext();
  const ActiveComponent = SUB_TAB_COMPONENTS[activeSubTab] || ScraperTaskCenter;

  return (
    <div className="flex flex-col h-full">
      <ScraperSubNav />
      <div className="flex-1 overflow-hidden">
        <ActiveComponent />
      </div>
      <ScraperScrapeDialog />
    </div>
  );
}

export default function ScraperPage() {
  return (
    <ScraperContextProvider>
      <ScraperPageInner />
    </ScraperContextProvider>
  );
}
