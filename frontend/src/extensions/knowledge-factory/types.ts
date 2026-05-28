// ============== Knowledge Factory: Extraction ==============

export interface ExtractionDomain {
  id: string;
  name: string;
  description?: string;
  parent_domain?: string;
  standard_chapters?: Record<string, unknown>;
  industry?: string;
  report_type?: string;
  created_at: string;
}

export interface DictItemResponse {
  id: string;
  category: string;
  label: string;
  sort_order: number;
  enabled: boolean;
  created_at: string;
}

export interface ExtractionConfig {
  llm_model: string;
  chunk_strategy: "semantic" | "fixed" | "section";
  merge_threshold: number;
  min_section_length: number;
}

export interface StepStatus {
  name: string;
  status: "waiting" | "running" | "completed" | "failed";
  duration?: string;
  detail: string;
}

export interface TemplateResult {
  template_id: string;
  name: string;
  version: string;
  chapters: number;
  sections: number;
  completeness_score: number;
  domain: string;
}

export interface ExtractionTaskResponse {
  id: string;
  name?: string;
  domain?: string;
  industry?: string;
  report_type?: string;
  source_reports: string[];
  status: "pending" | "running" | "completed" | "failed" | "paused";
  progress: number;
  steps: StepStatus[];
  result?: TemplateResult;
  error?: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
}

export interface ExtractionTaskListResponse {
  tasks: ExtractionTaskResponse[];
  total: number;
}

export interface ExtractionTaskCreate {
  name: string;
  domain: string;
  industry?: string;
  report_type?: string;
  source_report_ids: string[];
  target_template_name: string;
  /** 已有模板 ID，填写则向已有模板合并，不填则创建新模板 */
  target_template_id?: string;
  /** 合并模式：overwrite=覆盖替换，merge=合并差分，append=内容追加 */
  merge_mode?: MergeMode;
  config?: ExtractionConfig;
}

/** 模板合并模式 */
export type MergeMode = "overwrite" | "merge" | "append";

export const MERGE_MODE_OPTIONS: { value: MergeMode; label: string; description: string }[] = [
  { value: "overwrite", label: "覆盖替换", description: "用提取结果完全替换目标模板的所有章节和内容" },
  { value: "merge", label: "合并差分", description: "逐章节对比，同标题章节合并内容，新增章节追加，已有章节保留" },
  { value: "append", label: "内容追加", description: "仅追加目标模板中不存在的章节，已有章节不受影响" },
];

// ============== Template Editor Types ==============

export interface ContentContract {
  key_elements: string[];
  structure_type: "narrative_text" | "table" | "formula" | "diagram" | "mixed";
  style_rules?: string;
  min_word_count?: number;
  forbidden_phrases: string[];
}

export interface CrossSectionRule {
  rule_id: string;
  description: string;
  source_sections: string[];
  target_sections: string[];
  validation_type: string;
  fields: string[];
}

export interface TemplateSection {
  id: string;
  title: string;
  level: number;
  required: boolean;
  purpose?: string;
  children?: TemplateSection[];
  content_contract?: ContentContract;
  compliance_rules?: string[];
  rag_sources?: string[];
  generation_hint?: string;
  example_snippet?: string;
  completeness_score?: number;
}

export interface TemplateDocument {
  template_id: string;
  name: string;
  version: string;
  domain: string;
  status: "draft" | "published" | "deprecated";
  completeness_score: number;
  root_sections: TemplateSection[];
  cross_section_rules: CrossSectionRule[];
  created_at: string;
}

export interface TemplateListItem {
  id: string;
  domain: string;
  name: string;
  version: string;
  status: "draft" | "published" | "deprecated";
  completeness_score: number;
  source_report_count: number;
  created_by?: string;
  created_at: string;
  updated_at: string;
}

export interface TemplateListResponse {
  templates: TemplateListItem[];
  total: number;
}

export interface TemplateVersionResponse {
  id: string;
  version: string;
  changelog?: string;
  published_by?: string;
  published_at: string;
}

// ============== Template Editor Frontend Types ==============

export interface QualityAssessmentDimension {
  score: number;
  strengths: string[];
  issues: string[];
}

export interface QualityAssessmentResult {
  overall_score: number;
  dimensions: Record<string, QualityAssessmentDimension>;
  suggestions: string[];
  quality_grade: string;
}

export interface VersionDiffSection {
  section_id: string;
  title: string;
  level: number;
  status: "added" | "removed" | "modified" | "unchanged";
}

export interface VersionCompareResult {
  version_a: string;
  version_b: string;
  added_count: number;
  removed_count: number;
  modified_count: number;
  unchanged_count: number;
  sections: VersionDiffSection[];
}

export interface TemplateRollbackResponse {
  success: boolean;
  message: string;
  template_id: string;
  new_version: string;
  restored_version: string;
}

export interface EditorSection {
  id: string;
  title: string;
  level: number;
  required: boolean;
  purpose?: string;
  children?: EditorSection[];
  contentContract?: EditorContentContract;
  complianceRules?: string[];
  ragSources?: RAGSourceConfig[];
  generationHint?: string;
  exampleSnippet?: string;
  completenessScore?: number;
}

export interface EditorContentContract {
  keyElements: string[];
  structureType: "narrative_text" | "table" | "formula" | "diagram" | "mixed";
  styleRules: string;
  minWordCount: number;
  forbiddenPhrases: string[];
}

export interface EditorTemplate {
  id: string;
  name: string;
  version: string;
  domain: string;
  status: "draft" | "published" | "deprecated";
  completenessScore: number;
  sections: EditorSection[];
  isDirty: boolean;
  lastSaved?: string;
}

export interface TemplateUpdatePayload {
  name?: string;
  root_sections_json?: { sections: Record<string, unknown>[] };
  cross_section_rules?: CrossSectionRule[];
  completeness_score?: number;
  rag_sources?: RAGSourceConfig[];
}

export interface RAGSourceConfig {
  kb_id: string;
  kb_name: string;
  ragflow_dataset_id?: string;
  retrieval_strategy: "semantic" | "keyword" | "hybrid";
  top_k: number;
  similarity_threshold: number;
  vector_similarity_weight: number;
}

export const RETRIEVAL_STRATEGIES: { value: RAGSourceConfig["retrieval_strategy"]; label: string; description: string }[] = [
  { value: "hybrid", label: "混合检索", description: "语义+关键词混合，推荐" },
  { value: "semantic", label: "语义检索", description: "基于语义相似度匹配" },
  { value: "keyword", label: "关键词检索", description: "基于关键词精确匹配" },
];

export function normalizeRagSources(raw: unknown[] | undefined): RAGSourceConfig[] {
  if (!raw || !Array.isArray(raw)) return [];
  return raw.map((item) => {
    if (typeof item === "object" && item !== null && "kb_id" in item) {
      return item as RAGSourceConfig;
    }
    const obj = item as Record<string, unknown>;
    return {
      kb_id: String(obj.kb_id ?? obj.id ?? ""),
      kb_name: String(obj.kb_name ?? obj.name ?? ""),
      ragflow_dataset_id: obj.ragflow_dataset_id ? String(obj.ragflow_dataset_id) : undefined,
      retrieval_strategy: (obj.retrieval_strategy as RAGSourceConfig["retrieval_strategy"]) ?? "hybrid",
      top_k: Number(obj.top_k ?? 5),
      similarity_threshold: Number(obj.similarity_threshold ?? 0.2),
      vector_similarity_weight: Number(obj.vector_similarity_weight ?? 0.3),
    };
  });
}

export type SectionOperation =
  | { type: "add"; parentId: string | null; level: number }
  | { type: "delete"; sectionId: string }
  | { type: "move"; sectionId: string; targetParentId: string | null; index: number }
  | { type: "update"; sectionId: string; changes: Partial<EditorSection> };

// ============== Law / Regulation Types ==============

export type LawType =
  | "law"
  | "regulation"
  | "rule"
  | "national"
  | "industry"
  | "local"
  | "technical";

export interface LawItem {
  id: string;
  title: string;
  law_number?: string;
  law_type: LawType;
  status: "active" | "deprecated" | "updating";
  department?: string;
  effective_date?: string;
  update_date?: string;
  ref_count: number;
  view_count?: number;
  content?: string;
  summary?: string;
  ragflow_dataset_id?: string;
  ragflow_document_id?: string;
  is_synced: "pending" | "synced" | "failed";
  last_sync_at?: string;
  keywords?: string[];
  referred_laws?: string[];
  sector?: string;
  version?: string;
  supersedes?: string;
  superseded_by?: string;
  source_url?: string;
  linked_templates?: string[];
  created_at: string;
  updated_at?: string;
}

export interface LawListResponse {
  laws: LawItem[];
  total: number;
  by_type: Record<LawType, number>;
  by_status: Record<string, number>;
}

export interface LawStatistics {
  total_count: number;
  active_count: number;
  deprecated_count: number;
  synced_count: number;
  pending_sync_count: number;
  failed_sync_count: number;
}

export interface RAGFlowKBStatus {
  type: string;
  kb_name: string;
  exists: boolean;
  dataset_id?: string;
  document_count: number;
  status: "healthy" | "missing" | "error";
  error_message?: string;
  last_sync_time?: string;
}

export interface RAGFlowStatusResponse {
  statuses: RAGFlowKBStatus[];
  total_kbs: number;
  healthy_kbs: number;
  missing_kbs: number;
  error_kbs: number;
}

// ============== Compliance Rule Types ==============

export interface ComplianceRule {
  id: string;
  ruleId: string;
  name: string;
  type: string;
  typeName: string;
  severity: string;
  severityName: string;
  enabled: boolean;
  description?: string;
  industry: string;
  industryName: string;
  reportTypes: string[];
  applicableRegions: string[];
  nationalLevel: boolean;
  sourceSections: string[];
  targetSections: string[];
  validationConfig: ValidationConfig;
  errorMessage?: string;
  autoFixSuggestion?: string;
  seedVersion?: string;
  createdAt: string;
  updatedAt: string;
}

export interface ValidationConfig {
  fields: ValidationField[];
  comparisonType: string;
  checkRules?: string[];
}

export interface ValidationField {
  fieldName: string;
  limit?: number;
  min?: number;
  max?: number;
  unit?: string;
  standard?: string;
  required?: boolean;
  allowed?: boolean;
  comparison?: string;
  value?: string;
}

export interface ComplianceRuleListResponse {
  rules: ComplianceRule[];
  total: number;
  page: number;
  limit: number;
}

export interface ComplianceRuleCreate {
  ruleId: string;
  name: string;
  type: string;
  typeName: string;
  severity: string;
  severityName: string;
  enabled: boolean;
  description?: string;
  industry: string;
  industryName: string;
  reportTypes: string[];
  applicableRegions: string[];
  nationalLevel: boolean;
  sourceSections: string[];
  targetSections: string[];
  validationConfig: ValidationConfig;
  errorMessage?: string;
  autoFixSuggestion?: string;
}

export interface ComplianceRuleUpdate {
  name?: string;
  type?: string;
  typeName?: string;
  severity?: string;
  severityName?: string;
  enabled?: boolean;
  description?: string;
  industry?: string;
  industryName?: string;
  reportTypes?: string[];
  applicableRegions?: string[];
  nationalLevel?: boolean;
  sourceSections?: string[];
  targetSections?: string[];
  validationConfig?: ValidationConfig;
  errorMessage?: string;
  autoFixSuggestion?: string;
}

export interface ComplianceRuleImportResponse {
  success: boolean;
  total: number;
  created: number;
  updated: number;
  skipped: number;
  errors: number;
  errorMessages: string[];
}

export interface ComplianceRuleStatus {
  seedVersion: string;
  seedTotal: number;
  dbTotal: number;
  dbEnabled: number;
  dbDisabled: number;
  inSeedNotInDb: string[];
  inDbNotInSeed: string[];
  upToDate: boolean;
}

export interface ComplianceRuleStatistics {
  total: number;
  enabled: number;
  disabled: number;
  fromSeed: number;
  typeDistribution: Record<string, number>;
  severityDistribution: Record<string, number>;
  industryDistribution: Record<string, number>;
}

export interface ComplianceRuleOverview {
  statistics: ComplianceRuleStatistics;
  seedStatus: ComplianceRuleStatus;
  triggerStatistics: {
    totalTriggers: number;
    blockedTriggers: number;
    monthTriggers: number;
    monthBlocked: number;
    passRate: number;
  };
}

export interface RuleFilterParams {
  keyword?: string;
  industry?: string;
  reportType?: string;
  region?: string;
  type?: string;
  severity?: string;
  enabled?: boolean;
  page?: number;
  limit?: number;
}

export interface RuleDictionaryOption {
  value: string;
  label: string;
}

export interface RuleDictionaries {
  industries: RuleDictionaryOption[];
  reportTypes: RuleDictionaryOption[];
  regions: RuleDictionaryOption[];
  ruleTypes: RuleDictionaryOption[];
  severityLevels: RuleDictionaryOption[];
}

export const RULE_TYPES = [
  { value: "standard_check", label: "标准合规检查" },
  { value: "requirement_check", label: "要求符合性检查" },
  { value: "spatial_check", label: "空间距离检查" },
  { value: "data_consistency", label: "数据一致性检查" },
  { value: "reference_check", label: "引用标准检查" },
  { value: "engineering_check", label: "工程规范检查" },
  { value: "compliance_check", label: "合规性检查" },
] as const;

export const SEVERITY_LEVELS = [
  { value: "critical", label: "严重", color: "var(--error-500)" },
  { value: "warning", label: "警告", color: "var(--warning-500)" },
  { value: "info", label: "提示", color: "var(--info-500)" },
] as const;

export const INDUSTRIES = [
  { value: "environmental", label: "Environmental Protection" },
  { value: "safety_assessment", label: "Safety Assessment" },
  { value: "energy_assessment", label: "Energy Assessment" },
  { value: "fire_safety", label: "Fire Safety" },
  { value: "occupational_health", label: "Occupational Health" },
] as const;

export const REPORT_TYPES = [
  { value: "coal_mining_planning_eia", label: "Coal Mining Planning EIA" },
  { value: "coal_mining_project_eia", label: "Coal Mining Project EIA" },
  { value: "industrial_planning_eia", label: "Industrial Planning EIA" },
  { value: "construction_project_eia", label: "Construction Project EIA" },
  { value: "retrospective_evaluation", label: "Retrospective Evaluation" },
] as const;

export const REGIONS = [
  { value: "nationwide", label: "Nationwide" },
  { value: "jilin", label: "Jilin" },
  { value: "heilongjiang", label: "Heilongjiang" },
] as const;

export const DEFAULT_RULE_DICTIONARIES: RuleDictionaries = {
  industries: [...INDUSTRIES],
  reportTypes: [...REPORT_TYPES],
  regions: [...REGIONS],
  ruleTypes: [...RULE_TYPES],
  severityLevels: [...SEVERITY_LEVELS],
};

// ============== Compliance Check Types ==============

export interface ValidationIssue {
  ruleId: string;
  ruleName: string;
  severity: "critical" | "warning" | "info" | string;
  checkResult: "pass" | "fail" | "warning" | "error" | "skip";
  message: string;
  fieldName?: string;
  sourceValue?: string;
  targetValue?: string;
  location?: string[];
  suggestion?: string;
  details?: Record<string, unknown>;
}

export interface ComplianceCheckRequest {
  reportData?: Record<string, unknown>;
  rawText?: string;
  extractedFields?: Record<string, unknown>;
  reportType?: string;
  industry?: string;
  region?: string;
  ruleIds?: string[];
  checkAll?: boolean;
  stopOnFirstFail?: boolean;
  threadId?: string;
}

export interface ComplianceCheckResponse {
  success: boolean;
  totalRules: number;
  passed: number;
  failed: number;
  warnings: number;
  errors: number;
  skipped: number;
  hasCriticalIssues: boolean;
  durationMs: number;
  issues: ValidationIssue[];
}

export interface CheckStatistics {
  total: number;
  passed: number;
  failed: number;
  critical: number;
  warning: number;
  info: number;
}

// ============== Sample Reports (Knowledge Factory) ==============

export interface SampleReport {
  id: string;
  name: string;
  knowledge_base_id?: string;
  knowledge_base_name?: string;
  uploadTime: string;
  size: string;
  pages: number;
  status: "parsing" | "completed" | "pending";
  progress?: number;
  qualityScore?: number;
  chapters?: number;
  sections?: number;
  templateVersion?: string;
}

export interface ExtractionTask {
  id: string;
  sourceReports: string[];
  progress: number;
  status: "running" | "completed" | "paused";
  steps: {
    name: string;
    status: "completed" | "running" | "waiting";
    duration: string;
    detail: string;
  }[];
  result?: {
    version: string;
    chapters: number;
    sections: number;
  };
}

export interface VersionHistory {
  version: string;
  date: string;
  author: string;
  comment: string;
  changes: string;
  isHead?: boolean;
  isStable?: boolean;
}

export interface LawTemplateSection {
  id: string;
  title: string;
  level: number;
  required: boolean;
  purpose?: string;
  children?: LawTemplateSection[];
  contentContract?: {
    keyElements: string[];
    structureType: "narrative_text" | "table" | "formula" | "diagram" | "mixed";
    styleRules: string;
    minWordCount: number;
    forbiddenPhrases: string[];
  };
  complianceRules?: string[];
  ragSources?: RAGSourceConfig[];
  generationHint?: string;
  exampleSnippet?: string;
}

export type TabId =
  | "reports"
  | "extraction"
  | "editor"
  | "law"
  | "rules"
  | "version"
  | "quality"
  | "scraper"
  | "dictionaries";

export type LawViewType = "list" | "scraper";

// ==================== Scraper Sub-Tab Types ====================

export type ScraperSubTab = "task-center" | "new-scrape" | "source-manager" | "draft-box";

export interface ScrapTaskItem {
  task_id: string;
  url: string;
  provider: string;
  schema_name?: string;
  status: "pending" | "running" | "completed" | "failed" | "cancelled";
  error?: string;
  provider_used?: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
}

export interface ScrapTaskDetail extends ScrapTaskItem {
  prompt?: string;
  result?: string;
  structured_data?: Record<string, unknown>;
  logs: ScrapLogEntry[];
  draft_id?: string;
}

export interface ScrapLogEntry {
  type: "log" | "result" | "error" | "heartbeat" | "cancelled";
  level?: "info" | "success" | "error" | "warning";
  message?: string;
  content?: string;
  provider_used?: string;
}

export interface TaskListResponse {
  tasks: ScrapTaskItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface ScrapSource {
  id: string;
  name: string;
  url_pattern: string;
  category?: string;
  default_schema?: string;
  default_provider?: string;
  is_enabled: boolean;
  last_scraped_at?: string;
  created_at: string;
  updated_at: string;
}

export interface ScrapSourceDetail extends ScrapSource {
  description?: string;
  auth_config?: Record<string, unknown>;
  proxy_config?: Record<string, unknown>;
  cron_expression?: string;
}

export interface ScrapSourceCreate {
  name: string;
  description?: string;
  url_pattern: string;
  category?: string;
  default_schema?: string;
  default_provider?: string;
  auth_config?: Record<string, unknown>;
  proxy_config?: Record<string, unknown>;
  cron_expression?: string;
  is_enabled?: boolean;
}

export type ScrapSourceUpdate = Partial<ScrapSourceCreate>;

export interface ScrapSourceListResponse {
  sources: ScrapSource[];
  total: number;
  page: number;
  page_size: number;
}
