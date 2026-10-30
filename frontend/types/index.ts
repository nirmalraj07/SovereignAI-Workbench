export type Role = "viewer" | "auditor" | "engineer" | "admin";

export interface AuthUser {
  username: string;
  role: Role;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export interface TaskNode {
  id: string;
  agent: string;
  status: "pending" | "running" | "done" | "failed";
}

export interface ChatResult {
  plan: TaskNode[];
  results: Record<string, unknown>;
}

export interface TaskSubmitResponse {
  task_id: string;
  status: string;
}

export interface TaskStatusResponse {
  task_id: string;
  state: "PENDING" | "STARTED" | "SUCCESS" | "FAILURE";
  result?: ChatResult;
  error?: string;
}

export interface KBChunk {
  text: string;
  filename: string;
  page: number;
  score: number;
}

export interface KBQueryResponse {
  chunks: KBChunk[];
  citations: { source: string; page: number; document_id: string; relevance: number }[];
}

export interface CodeRunResponse {
  stdout: string;
  stderr: string;
  exit_code: number;
  duration_ms: number;
  timed_out: boolean;
}

export interface GenerateAndRunResponse {
  final_code: string;
  attempts: number;
  success: boolean;
  stdout: string;
  stderr: string;
}

export interface SystemMetrics {
  cpu_percent: number;
  memory_percent: number;
  memory_used_gb: number;
  memory_total_gb: number;
  disk_used_gb: number;
  disk_total_gb: number;
  disk_percent: number;
  gpus: { index: number; name: string; utilization_pct: number; memory_used_mb: number; memory_total_mb: number }[];
}

export interface SecurityDashboardData {
  external_connections: number;
  external_api_calls: number;
  network_egress_allowed: boolean;
  audit_events: AuditEvent[];
}

export interface AuditEvent {
  action: string;
  resource: string;
  ip: string;
  created_at: string;
}

export interface AdminUser {
  id: string;
  username: string;
  role: Role;
  is_active: boolean;
  created_at: string;
}

export interface ModelInfo {
  name: string;
  backend_type: string;
  modality: string;
  status: "online" | "offline" | "unknown";
  good_for: string[];
}

export interface GeneratedFileResponse {
  file_path: string;
  download_url: string;
}

export interface NotificationItem {
  id: string;
  title: string;
  message: string;
  level: "info" | "warning" | "error" | "success";
  created_at: string;
  read: boolean;
}
