import type { LayoutTemplate } from "./types";

export function transformTemplate(data: Record<string, unknown>): LayoutTemplate {
  return {
    id: data.id as string,
    name: data.name as string,
    reportType: data.report_type as string,
    pageSettings: data.page_settings as LayoutTemplate["pageSettings"],
    coverTemplate: (data.cover_template as LayoutTemplate["coverTemplate"]) ?? null,
    tocSettings: (data.toc_settings as LayoutTemplate["tocSettings"]) ?? null,
    bodyStyles: data.body_styles as LayoutTemplate["bodyStyles"],
    headingStyles: (data.heading_styles as LayoutTemplate["headingStyles"]) ?? [],
    tableStyles: (data.table_styles as LayoutTemplate["tableStyles"]) ?? null,
    figureStyles: (data.figure_styles as LayoutTemplate["figureStyles"]) ?? null,
    headerFooter: (data.header_footer as LayoutTemplate["headerFooter"]) ?? null,
    referenceStyle: (data.reference_style as string) ?? "gb7714",
    appendixRules: (data.appendix_rules as LayoutTemplate["appendixRules"]) ?? null,
    createdAt: data.created_at as string,
    updatedAt: data.updated_at as string,
  };
}
