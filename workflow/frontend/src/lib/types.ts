export type ModelValue = "CLASSICS";

export type NodeTypeName =
  | "start"
  | "between"
  | "end"
  | "serial"
  | "parallel"
  | "inclusive";

export interface Definition {
  id: number;
  flow_code: string;
  flow_name: string;
  model_value: ModelValue;
  category: string | null;
  version: string;
  is_publish: number;
  publish_label?: string;
  form_custom: string;
  form_path: string | null;
  activity_status: number;
  listener_type: string | null;
  listener_path: string | null;
  ext: string | null;
  create_time: string | null;
  create_by: string;
  update_time: string | null;
  update_by: string;
  tenant_id: string;
  instance_count?: number;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}

export interface SkipJson {
  id?: number | null;
  nowNodeCode?: string | null;
  nowNodeType?: number | null;
  nextNodeCode?: string | null;
  nextNodeType?: number | null;
  skipName?: string | null;
  skipType?: string | null;
  skipCondition?: string | null;
  coordinate?: string | null;
  status?: number | null;
  expr?: string | null;
}

export interface NodeJson {
  id?: number | null;
  nodeType: number;
  nodeCode: string;
  nodeName?: string | null;
  permissionFlag?: string | null;
  nodeRatio?: string | null;
  coordinate?: string | null;
  anyNodeSkip?: string | null;
  listenerType?: string | null;
  listenerPath?: string | null;
  formCustom?: string;
  formPath?: string | null;
  ext?: string | null;
  version?: string | null;
  status?: number | null;
  handlerType?: string | null;
  handlerPath?: string | null;
  skipList: SkipJson[];
}

export interface DefJson {
  id?: number | null;
  flowCode: string;
  flowName: string;
  modelValue: ModelValue;
  category?: string | null;
  version?: string | null;
  isPublish?: number | null;
  formCustom?: string;
  formPath?: string | null;
  listenerType?: string | null;
  listenerPath?: string | null;
  ext?: string | null;
  extMap?: Record<string, unknown>;
  instance?: InstanceWire | null;
  chartStatusColor?: string[];
  topText?: string | null;
  topTextShow?: boolean;
  categoryList?: { value: string; label: string }[];
  formPathList?: { value: string; label: string; id: number }[];
  nodeList: NodeJson[];
}

export interface FormDefinition {
  id: number;
  form_code: string;
  form_name: string;
  version: string;
  is_publish: number;
  form_type: number;
  form_content: string | null;
  form_path: string | null;
  ext: string | null;
  create_time: string | null;
  create_by?: string;
  update_time: string | null;
}

export interface FormField {
  key: string;
  label: string;
  type?: "text" | "textarea" | "number" | "select" | "date" | "switch";
  required?: boolean;
  placeholder?: string;
  options?: string[];
  /** Columns occupied in a two-column form. */
  span?: 1 | 2;
}

export interface FormLayout {
  columns?: 1 | 2;
}

export interface FormSchema {
  layout?: FormLayout;
  fields: FormField[];
}

export interface InstanceWire {
  id: number;
  definition_id: number;
  business_id: string;
  node_type: number;
  node_code: string;
  node_name: string | null;
  flow_status: string;
  flow_status_label?: string;
  flow_status_tone?: string;
  activity_status: number;
  variable: Record<string, unknown>;
  def_json?: DefJson;
  create_time: string | null;
  create_by: string;
  update_time: string | null;
  flow_name?: string | null;
}

export interface Task {
  id: number;
  definition_id: number;
  instance_id: number;
  node_code: string;
  node_name: string | null;
  node_type: number;
  flow_status: string;
  flow_status_label?: string;
  form_custom: string;
  form_path: string | null;
  create_time: string | null;
  create_by?: string;
  flow_name?: string | null;
  business_id?: string | null;
  assignees?: string[];
  node?: NodeJson | null;
  instance?: InstanceWire;
  chart?: DefJson;
  variables?: Record<string, unknown>;
  form?: NodeJson | null;
}

export interface HisTask {
  id: number;
  definition_id: number;
  instance_id: number;
  task_id: number;
  node_code: string | null;
  node_name: string | null;
  node_type: number | null;
  target_node_code: string | null;
  target_node_name: string | null;
  approver: string | null;
  cooperate_type: number;
  cooperate_label?: string;
  collaborator: string | null;
  skip_type: string;
  flow_status: string;
  flow_status_label?: string;
  message: string | null;
  variable: Record<string, unknown>;
  create_time: string | null;
  update_time: string | null;
  form_custom?: string;
  form_path?: string | null;
  flow_name?: string | null;
}

export interface InstanceDetail {
  instance: InstanceWire;
  tasks: Task[];
  history: HisTask[];
  chart: DefJson;
}

export interface HandlerOption {
  handlerCode: string;
  handlerName: string;
  groupName: string;
  storageId: string;
  type?: string;
  dept?: string | null;
  roles?: string[];
}

export interface DemoUser {
  handler: string;
  name: string;
  group: string;
  roles: string[];
  dept?: string | null;
}

export interface AuthMe {
  handler: string;
  name: string;
  roles: string[];
  permissions: string[];
  dept: string;
  tenant_id: string;
  is_admin: boolean;
  auth_mode: "local" | "eai" | string;
}

export interface Enums {
  nodeTypes: Record<string, string>;
  flowStatus: Record<string, string>;
  flowStatusTone: Record<string, string>;
  cooperateTypes: Record<string, string>;
  chartColors: Record<string, string[]>;
  models: Record<string, string>;
  skipTypes: Record<string, string>;
  publishStatus: Record<string, string>;
}

export interface Stats {
  definitions: number;
  published: number;
  instances: number;
  running: number;
  tasks: number;
}

export interface LoadTaskResponse {
  id: number;
  formContent: string | null;
  form: {
    id?: number;
    formCode?: string;
    formName?: string;
    version?: string;
    formType?: number;
    formPath?: string;
    formContent?: string;
    schema?: FormSchema;
  };
  data: {
    task: Task;
    instance: InstanceWire;
    node: NodeJson | null;
    variables: Record<string, unknown>;
  };
}
