// ============== Knowledge Factory: Extraction ==============

export interface ExtractionDomain {
  id: string;
  name: string;
  description?: string;
  parent_domain?: string;
  standard_chapters?: Record<string, unknown>;
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
  source_report_ids: string[];
  target_template_name: string;
  config?: ExtractionConfig;
}

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

export interface EditorSection {
  id: string;
  title: string;
  level: number;
  required: boolean;
  purpose?: string;
  children?: EditorSection[];
  contentContract?: EditorContentContract;
  complianceRules?: string[];
  ragSources?: string[];
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
  root_sections_json?: { sections: EditorSection[] };
  cross_section_rules?: CrossSectionRule[];
  completeness_score?: number;
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
}

export const RULE_TYPES = [
  { value: "standard_check", label: "Standard Compliance Check" },
  { value: "requirement_check", label: "Requirement Check" },
  { value: "spatial_check", label: "Spatial Distance Check" },
  { value: "data_consistency", label: "Data Consistency Check" },
  { value: "reference_check", label: "Reference Standard Check" },
  { value: "engineering_check", label: "Engineering Check" },
  { value: "compliance_check", label: "Compliance Check" },
] as const;

export const SEVERITY_LEVELS = [
  { value: "critical", label: "Critical", color: "#dc2626" },
  { value: "warning", label: "Warning", color: "#f59e0b" },
  { value: "info", label: "Info", color: "#3b82f6" },
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
  ragSources?: string[];
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
  | "scraper";

export type LawViewType = "list" | "scraper";
