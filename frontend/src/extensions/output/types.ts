export type OutputFormat = "docx" | "pdf" | "preview";
export type WatermarkType = "draft" | "review" | "final";
export type GenerateSource = "project" | "markdown";

export interface LayoutTemplate {
  id: string;
  name: string;
  reportType: string;
  isBuiltin: boolean;
  pageSettings: PageSettings;
  coverTemplate: CoverTemplate | null;
  coverMaster: CoverMaster | null;
  tocSettings: TocSettings | null;
  bodyStyles: BodyStyles;
  headingStyles: HeadingStyle[];
  tableStyles: TableStyles | null;
  figureStyles: FigureStyles | null;
  headerFooter: HeaderFooter | null;
  referenceStyle: string;
  appendixRules: AppendixRules | null;
  createdAt: string;
  updatedAt: string;
}

export interface PageSettings {
  paperSize: "A4" | "A3" | "B5" | "letter";
  orientation: "portrait" | "landscape";
  marginTop: number;
  marginBottom: number;
  marginLeft: number;
  marginRight: number;
}

export interface CoverTemplate {
  showLogo: boolean;
  logoPosition: "left" | "center" | "right";
  showTitle: boolean;
  showClient: boolean;
  showDate: boolean;
  showProjectNumber: boolean;
}

export interface CoverSlot {
  id: string;
  label: string;
  kind: "variable" | "literal";
  sampleValue: string;
  defaultFrom?: string | null;
  /** Exact OOXML substring to find at generation (label-inclusive for colon fields
   * so duplicate values like XX don't collide). Absent → sampleValue. */
  target?: string | null;
}

export interface CoverMasterImage {
  origRid: string;
  ext: string;
  b64: string;
}

export interface CoverMaster {
  mode: "master";
  /** Full OOXML fragment — only present on detail responses (getTemplate /
   * create / update / duplicate). List responses omit it (L1) → optional. */
  xml?: string;
  images?: CoverMasterImage[];
  slots: CoverSlot[];
  sourceFile: string;
  boundary: string;
}

export interface TocSettings {
  maxDepth: number;
  showPageNumbers: boolean;
  leaderDots: boolean;
}

export interface BodyStyles {
  fontFamily: string;
  fontSize: number;
  lineHeight: number;
  paragraphSpacing: number;
  firstLineIndent: number;
}

export interface HeadingStyle {
  level: number;
  fontFamily: string;
  fontSize: number;
  fontWeight: number;
  color: string;
  numbering: "decimal" | "chinese" | "none";
}

export interface TableStyles {
  headerBg: string;
  headerColor: string;
  borderColor: string;
  stripeRows: boolean;
}

export interface FigureStyles {
  captionPosition: "above" | "below";
  numbering: "chapter" | "continuous";
  showSource: boolean;
}

export interface HeaderFooter {
  headerText: string;
  footerText: string;
  showPageNumber: boolean;
  showLogo: boolean;
}

export interface AppendixRules {
  numbering: "A-B-C" | "I-II-III" | "1-2-3";
  separateToc: boolean;
}

export interface GenerateOutputRequest {
  source: GenerateSource;
  projectId?: string;
  markdownFile?: File;
  format: OutputFormat;
  layoutTemplateId: string;
  watermark?: WatermarkType;
  chapterIds?: string[];
}

export interface GenerateOutputResult {
  taskId: string;
  status: "queued" | "processing" | "completed" | "failed";
  downloadUrl?: string;
  fileName?: string;
}

export interface HistoryEntry {
  taskId: string;
  projectId: string;
  format: string;
  status: GenerateOutputResult["status"];
  fileName?: string;
  downloadUrl?: string;
  createdAt: string;
}

export const WATERMARK_LABELS: Record<WatermarkType, string> = {
  draft: "初稿",
  review: "送审稿",
  final: "正式稿",
};
