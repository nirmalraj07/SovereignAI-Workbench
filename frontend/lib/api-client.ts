import axios, { AxiosInstance } from "axios";
import { useAuthStore } from "./store";

import type {
  LoginResponse,
  TaskSubmitResponse,
  TaskStatusResponse,
  KBQueryResponse,
  CodeRunResponse,
  GenerateAndRunResponse,
  SystemMetrics,
  SecurityDashboardData,
  AdminUser,
  ModelInfo,
  GeneratedFileResponse,
  NotificationItem,
} from "@/types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";


// =====================================================
// AXIOS CLIENT
// =====================================================

function client(): AxiosInstance {
  const instance = axios.create({
    baseURL: API_BASE,
  });

  // Automatically attach JWT token
  instance.interceptors.request.use((config) => {
    const token = useAuthStore.getState().token;

    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    return config;
  });

  // Automatically logout on unauthorized response
  instance.interceptors.response.use(
    (response) => response,

    (error) => {
      if (error?.response?.status === 401) {
        useAuthStore.getState().logout();
      }

      return Promise.reject(error);
    }
  );

  return instance;
}


// =====================================================
// API
// =====================================================

export const api = {

  // ===================================================
  // AUTH
  // ===================================================

  auth: {

    login: (
      username: string,
      password: string,
      mfa_code?: string
    ) =>
      client()
        .post<LoginResponse>(
          "/api/auth/login",
          {
            username,
            password,
            mfa_code,
          }
        )
        .then((response) => response.data),


    provisionMfa: () =>
      client()
        .get<{
          otpauth_url: string;
          secret: string;
        }>("/api/auth/mfa/provision")
        .then((response) => response.data),


    enableMfa: (code: string) =>
      client()
        .post<{
          mfa_enabled: boolean;
        }>(
          "/api/auth/mfa/enable",
          {
            code,
          }
        )
        .then((response) => response.data),


    disableMfa: () =>
      client()
        .post<{
          mfa_enabled: boolean;
        }>("/api/auth/mfa/disable")
        .then((response) => response.data),
  },


  // ===================================================
  // TASKS
  // ===================================================

  tasks: {

    /**
     * Submit a normal text-only agent task.
     *
     * IMPORTANT:
     * This sends JSON.
     *
     * Your backend must support JSON for this endpoint,
     * OR you should use submitWithImage/FormData for all tasks.
     */
    submit: (message: string) => {
      const form = new FormData();

      form.append("message", message);

      return client()
        .post<TaskSubmitResponse>(
          "/api/tasks/submit",
          form
        )
        .then((response) => response.data);
    },


    /**
     * Submit an agent task with an uploaded image or PDF.
     *
     * This matches FastAPI:
     *
     * message: str = Form(...)
     * image: UploadFile | None = File(None)
     */
    submitWithImage: (
      message: string,
      image: File
    ) => {
      const form = new FormData();

      form.append("message", message);
      form.append("image", image);

      return client()
        .post<TaskSubmitResponse>(
          "/api/tasks/submit",
          form
        )
        .then((response) => response.data);
    },


    /**
     * Get Celery task status.
     */
    status: (taskId: string) =>
      client()
        .get<TaskStatusResponse>(
          `/api/tasks/${taskId}`
        )
        .then((response) => response.data),
  },


  // ===================================================
  // KNOWLEDGE BASE
  // ===================================================

  kb: {

    query: (
      query: string,
      top_k = 5
    ) =>
      client()
        .post<KBQueryResponse>(
          "/api/kb/query",
          {
            query,
            top_k,
          }
        )
        .then((response) => response.data),


    ingest: (
      file: File,
      classification = "internal"
    ) => {
      const form = new FormData();

      form.append("file", file);
      form.append("classification", classification);

      return client()
        .post(
          "/api/kb/ingest",
          form
        )
        .then((response) => response.data);
    },
  },


  // ===================================================
  // CODE EXECUTION
  // ===================================================

  code: {

    run: (
      code: string,
      language: string
    ) =>
      client()
        .post<CodeRunResponse>(
          "/api/code/run",
          {
            code,
            language,
          }
        )
        .then((response) => response.data),


    generateAndRun: (
      instruction: string,
      language = "python"
    ) =>
      client()
        .post<GenerateAndRunResponse>(
          "/api/code/generate-and-run",
          {
            instruction,
            language,
          }
        )
        .then((response) => response.data),
  },


  // ===================================================
  // FILE GENERATION
  // ===================================================

  files: {

    generateDocx: (
      title: string,
      body_text: string
    ) =>
      client()
        .post<GeneratedFileResponse>(
          "/api/files/generate/docx",
          {
            title,
            body_text,
          }
        )
        .then((response) => response.data),


    generateXlsx: (
      title: string,
      headers: string[],
      rows: unknown[][]
    ) =>
      client()
        .post<GeneratedFileResponse>(
          "/api/files/generate/xlsx",
          {
            title,
            headers,
            rows,
          }
        )
        .then((response) => response.data),


    generatePptx: (
      title: string,
      slides: {
        title: string;
        bullets: string[];
      }[]
    ) =>
      client()
        .post<GeneratedFileResponse>(
          "/api/files/generate/pptx",
          {
            title,
            slides,
          }
        )
        .then((response) => response.data),


    downloadUrl: (path: string) =>
      `${API_BASE}/api/files/download?path=${encodeURIComponent(path)}`,
  },


  // ===================================================
  // MONITORING
  // ===================================================

  monitoring: {

    system: () =>
      client()
        .get<SystemMetrics>(
          "/api/monitoring/system"
        )
        .then((response) => response.data),
  },


  // ===================================================
  // SECURITY
  // ===================================================

  security: {

    dashboard: () =>
      client()
        .get<SecurityDashboardData>(
          "/api/security/dashboard"
        )
        .then((response) => response.data),
  },


  // ===================================================
  // ADMIN
  // ===================================================

  admin: {

    listUsers: () =>
      client()
        .get<AdminUser[]>(
          "/api/admin/users"
        )
        .then((response) => response.data),


    createUser: (
      username: string,
      password: string,
      role: string
    ) =>
      client()
        .post<AdminUser>(
          "/api/admin/users",
          {
            username,
            password,
            role,
          }
        )
        .then((response) => response.data),


    updateUserRole: (
      userId: string,
      role: string
    ) =>
      client()
        .patch<AdminUser>(
          `/api/admin/users/${userId}`,
          {
            role,
          }
        )
        .then((response) => response.data),


    deleteUser: (
      userId: string
    ) =>
      client()
        .delete(
          `/api/admin/users/${userId}`
        )
        .then((response) => response.data),


    disableUser: (
      userId: string
    ) =>
      client()
        .post<AdminUser>(
          `/api/admin/users/${userId}/disable`
        )
        .then((response) => response.data),


    enableUser: (
      userId: string
    ) =>
      client()
        .post<AdminUser>(
          `/api/admin/users/${userId}/enable`
        )
        .then((response) => response.data),


    resetPassword: (
      userId: string,
      newPassword: string
    ) =>
      client()
        .post(
          `/api/admin/users/${userId}/reset-password`,
          {
            new_password: newPassword,
          }
        )
        .then((response) => response.data),


    listModels: () =>
      client()
        .get<ModelInfo[]>(
          "/api/admin/models"
        )
        .then((response) => response.data),
  },


  // ===================================================
  // AUDIT
  // ===================================================

  audit: {

    list: (limit = 100) =>
      client()
        .get(
          `/api/security/dashboard?limit=${limit}`
        )
        .then(
          (response) =>
            response.data.audit_events as unknown[]
        ),
  },


  // ===================================================
  // NOTIFICATIONS
  // ===================================================

  notifications: {

    list: () =>
      client()
        .get<NotificationItem[]>(
          "/api/notifications"
        )
        .then((response) => response.data),


    markRead: (id: string) =>
      client()
        .post(
          `/api/notifications/${id}/read`
        )
        .then((response) => response.data),
  },
};


// =====================================================
// WEBSOCKET URL
// =====================================================

export function wsUrl(path: string): string {
  const wsBase =
    process.env.NEXT_PUBLIC_WS_BASE_URL ||
    "ws://localhost:8000";

  return `${wsBase}${path}`;
}