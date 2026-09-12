"use client";

/**
 * Registry 面板 (EAI-CUSTOM, plan 2026-09-12 ontology-ui Task 3 Step 3.3).
 *
 * 对象类型卡片（display_name / api_name / 属性数）+ stub 链接卡（enabled:false + note，
 * 虚线边框 + "⛔ traverse 拒绝"）。数据：fetchObjectTypes + fetchRegistryMeta。
 */
import { useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";

import {
  fetchObjectTypes,
  fetchRegistryMeta,
} from "@/extensions/ontology/api/ontology-graph-api";

export function RegistryPanel() {
  const metaQuery = useQuery({
    queryKey: ["ontology", "registry"],
    queryFn: fetchRegistryMeta,
  });
  const schemaQuery = useQuery({
    queryKey: ["ontology", "object-types"],
    queryFn: fetchObjectTypes,
  });

  if (schemaQuery.isLoading || metaQuery.isLoading) {
    return (
      <div className="text-muted-foreground flex items-center justify-center gap-2 py-10 text-xs">
        <Loader2 className="h-4 w-4 animate-spin" />
        加载注册表…
      </div>
    );
  }

  if (schemaQuery.isError) {
    return (
      <div className="text-muted-foreground py-10 text-center text-xs">
        注册表加载失败：{String(schemaQuery.error)}
      </div>
    );
  }

  const schema = schemaQuery.data;
  if (!schema) {
    return null;
  }

  const stubLinks = schema.link_types.filter((lt) => !lt.enabled);

  return (
    <div className="flex flex-col gap-4">
      <section>
        <h3 className="text-muted-foreground mb-2 text-[10.5px] font-medium tracking-widest">
          对象类型（{schema.object_types.length}）
        </h3>
        <div className="flex flex-col gap-2">
          {schema.object_types.map((obj) => (
            <div key={obj.name} className="border-border rounded-lg border px-2.5 py-2">
              <div className="flex items-center gap-2">
                <b className="text-foreground text-[12.5px] font-semibold">{obj.display_name}</b>
                <span className="text-muted-foreground font-mono text-[10px]">{obj.name}</span>
                <span className="text-muted-foreground ml-auto text-[11px] tabular-nums">
                  {obj.properties.length} 属性
                </span>
              </div>
              {obj.description ? (
                <p className="text-muted-foreground mt-1 text-[11px] leading-relaxed">{obj.description}</p>
              ) : null}
            </div>
          ))}
        </div>
      </section>

      {stubLinks.length > 0 ? (
        <section>
          <h3 className="text-muted-foreground mb-2 text-[10.5px] font-medium tracking-widest">
            stub 链接（enabled:false，{stubLinks.length}）
          </h3>
          <div className="flex flex-col gap-2">
            {stubLinks.map((lt) => (
              <div
                key={lt.name}
                className="border-border rounded-lg border border-dashed px-2.5 py-2"
              >
                <div className="flex items-center gap-2">
                  <b className="text-foreground font-mono text-[11.5px]">{lt.name}</b>
                  <span className="ml-auto text-[10.5px] text-amber-600 dark:text-amber-400">
                    ⛔ traverse 拒绝
                  </span>
                </div>
                <p className="text-muted-foreground mt-1 text-[11px] leading-relaxed">
                  {lt.note ?? `${lt.source} → ${lt.target}`}
                </p>
              </div>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}
