import { useMemo } from "react";

// EAI-CUSTOM: 按客户品牌化（构建期注入，见 brand.ts）
import { BRAND_FOOTER } from "@/brand";
import { cn } from "@/lib/utils";

export type FooterProps = {
  className?: string;
};

export function Footer({ className }: FooterProps) {
  const year = useMemo(() => new Date().getFullYear(), []);
  return (
    <footer
      className={cn(
        "container-md mx-auto mt-32 flex flex-col items-center justify-center",
        className,
      )}
    >
      <hr className="from-border/0 to-border/0 m-0 h-px w-full border-none bg-linear-to-r via-white/20" />
      <div className="text-muted-foreground container flex h-20 flex-col items-center justify-center text-sm">
        <p className="text-center font-serif text-lg md:text-xl">
          &quot;Originated from Open Source, give back to Open Source.&quot;
        </p>
      </div>
      <div className="text-muted-foreground container mb-8 flex flex-col items-center justify-center text-xs">
        {/* EAI-CUSTOM: 按客户品牌化 —— 设了 BRAND_FOOTER 就显示客户页脚，否则保留默认 */}
        {BRAND_FOOTER ? (
          <p>{BRAND_FOOTER}</p>
        ) : (
          <>
            <p>Licensed under MIT License</p>
            <p>&copy; {year} </p>
          </>
        )}
      </div>
    </footer>
  );
}
