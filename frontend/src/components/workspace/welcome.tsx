"use client";

import { Bot } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { useI18n } from "@/core/i18n/hooks";
import { cn } from "@/lib/utils";

import { AuroraText } from "../ui/aurora-text";

let waved = false;

export function Welcome({
  className,
  mode,
  skill,
}: {
  className?: string;
  mode?: string;
  skill?: { displayName: string; description: string } | null;
}) {
  const { t } = useI18n();
  const searchParams = useSearchParams();
  const isUltra = useMemo(() => mode === "ultra", [mode]);
  const [isDark, setIsDark] = useState(false);

  useEffect(() => {
    const checkDark = () => {
      setIsDark(document.documentElement.classList.contains("dark"));
    };
    checkDark();
    const observer = new MutationObserver(checkDark);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });
    return () => observer.disconnect();
  }, []);

  const colors = useMemo(() => {
    if (isUltra) {
      return ["#fef3c7", "#fde68a", "#fcd34d"];
    }
    return isDark
      ? ["#ffffff", "#ffffff", "#ffffff"]
      : ["#151616", "#151616", "#151616"];
  }, [isUltra, isDark]);

  useEffect(() => {
    waved = true;
  }, []);

  return (
    <div
      className={cn(
        "mx-auto flex w-full flex-col items-center justify-center gap-2 px-8 py-4 text-center",
        className,
      )}
    >
      <div className="text-2xl font-bold">
        {searchParams.get("mode") === "skill" ? (
          `✨ ${t.welcome.createYourOwnSkill} ✨`
        ) : (
          <div className="flex items-center gap-2">
            <div className={cn("inline-block", !waved ? "animate-wave" : "")}>
              {isUltra ? "🚀" : <Bot className="size-7 text-primary" />}
            </div>
            <AuroraText className="font-normal" colors={colors}>{t.welcome.greeting}</AuroraText>
          </div>
        )}
      </div>
      {skill ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <p>{skill.description}</p>
        </div>
      ) : null}
    </div>
  );
}
