"use client";

import { useEffect, useRef, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { ScanText, FileText, Loader2, X } from "lucide-react";
import { useAuthStore } from "@/lib/store";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  "http://localhost:8000";

export default function OcrPage() {
  const fileRef = useRef<HTMLInputElement>(null);

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);

  const [instruction, setInstruction] = useState(
    "Extract findings from this scanned inspection report"
  );

  const [taskId, setTaskId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const token = useAuthStore((state) => state.token);

  useEffect(() => {
    return () => {
      if (preview) {
        URL.revokeObjectURL(preview);
      }
    };
  }, [preview]);

  function onFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] || null;

    if (preview) {
      URL.revokeObjectURL(preview);
    }

    setPreview(null);
    setSelectedFile(file);
    setError(null);
    setTaskId(null);

    if (!file) {
      return;
    }

    const isImage = file.type.startsWith("image/");

    const isPdf =
      file.type === "application/pdf" ||
      file.name.toLowerCase().endsWith(".pdf");

    if (!isImage && !isPdf) {
      setSelectedFile(null);

      setError(
        "Please select a supported image or PDF file."
      );

      if (fileRef.current) {
        fileRef.current.value = "";
      }

      return;
    }

    if (isImage) {
      const previewUrl = URL.createObjectURL(file);
      setPreview(previewUrl);
    }
  }

  function clearSelectedFile() {
    if (preview) {
      URL.revokeObjectURL(preview);
    }

    setSelectedFile(null);
    setPreview(null);
    setError(null);
    setTaskId(null);

    if (fileRef.current) {
      fileRef.current.value = "";
    }
  }

  async function handleSubmit() {
    if (!selectedFile) {
      setError("Please choose an image or PDF file.");
      return;
    }

    if (!instruction.trim()) {
      setError("Please enter an OCR instruction.");
      return;
    }

    setSubmitting(true);
    setError(null);
    setTaskId(null);

    try {
      const formData = new FormData();

      formData.append(
        "message",
        instruction.trim()
      );

      formData.append(
        "image",
        selectedFile
      );

      const response = await fetch(
        `${API_BASE}/api/tasks/submit`,
        {
          method: "POST",

          headers: token
            ? {
                Authorization: `Bearer ${token}`,
              }
            : {},

          body: formData,
        }
      );

      let data: unknown;

      try {
        data = await response.json();
      } catch {
        throw new Error(
          "The server returned an invalid response."
        );
      }

      if (!response.ok) {
        const detail =
          typeof data === "object" &&
          data !== null &&
          "detail" in data
            ? String(data.detail)
            : "Failed to submit OCR task.";

        throw new Error(detail);
      }

      const responseData = data as {
        task_id?: string;
      };

      if (!responseData.task_id) {
        throw new Error(
          "Backend did not return a task ID."
        );
      }

      setTaskId(responseData.task_id);
    } catch (err) {
      console.error(
        "OCR submission error:",
        err
      );

      setError(
        err instanceof Error
          ? err.message
          : "Failed to submit OCR task."
      );
    } finally {
      setSubmitting(false);
    }
  }

  const isPdf =
    selectedFile?.type === "application/pdf" ||
    selectedFile?.name.toLowerCase().endsWith(".pdf");

  return (
    <AppShell title="OCR Upload Workspace">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

        {/* Upload Card */}
        <div className="card space-y-4">

          <h2 className="text-sm font-medium flex items-center gap-2">
            <ScanText size={16} />
            Upload Scan
          </h2>

          {/* File Input */}
          <input
            ref={fileRef}
            type="file"
            accept="image/*,.pdf"
            onChange={onFileChange}
            disabled={submitting}
            className="text-xs"
          />

          {/* Image Preview */}
          {preview && selectedFile && (
            <div className="relative">
              <img
                src={preview}
                alt="Uploaded document preview"
                className="
                  rounded-lg
                  border
                  border-white/10
                  max-h-80
                  w-full
                  object-contain
                "
              />

              <button
                type="button"
                onClick={clearSelectedFile}
                disabled={submitting}
                className="
                  absolute
                  top-2
                  right-2
                  rounded-full
                  border
                  border-white/20
                  bg-black/70
                  p-2
                  text-white
                  hover:bg-black
                "
                title="Remove selected file"
              >
                <X size={16} />
              </button>
            </div>
          )}

          {/* PDF Preview */}
          {selectedFile && isPdf && !preview && (
            <div
              className="
                relative
                border
                border-white/10
                rounded-lg
                p-6
                flex
                items-center
                gap-3
                text-sm
                text-neutral-400
              "
            >
              <FileText size={28} />

              <div className="min-w-0">
                <p className="text-xs text-neutral-500">
                  PDF selected
                </p>

                <p className="truncate">
                  {selectedFile.name}
                </p>
              </div>

              <button
                type="button"
                onClick={clearSelectedFile}
                disabled={submitting}
                className="
                  ml-auto
                  rounded-md
                  border
                  border-white/10
                  p-2
                  hover:bg-white/10
                "
                title="Remove selected file"
              >
                <X size={16} />
              </button>
            </div>
          )}

          {/* Selected Image Name */}
          {selectedFile && preview && (
            <div className="text-xs text-neutral-500">
              Selected file:{" "}
              <span className="text-neutral-300">
                {selectedFile.name}
              </span>
            </div>
          )}

          {/* Instruction */}
          <div>
            <label className="block text-xs text-neutral-400 mb-2">
              OCR Instruction
            </label>

            <textarea
              className="
                input-field
                h-24
                resize-none
                w-full
              "
              value={instruction}
              disabled={submitting}
              onChange={(event) =>
                setInstruction(event.target.value)
              }
              placeholder="Describe what you want the OCR workflow to do..."
            />
          </div>

          {/* Error */}
          {error && (
            <div
              className="
                rounded-lg
                border
                border-red-500/30
                bg-red-500/10
                p-3
                text-xs
                text-red-400
              "
            >
              {error}
            </div>
          )}

          {/* Submit Button */}
          <button
            type="button"
            onClick={handleSubmit}
            className="btn-primary w-full"
            disabled={submitting || !selectedFile}
          >
            {submitting ? (
              <span className="flex items-center justify-center gap-2">
                <Loader2
                  size={16}
                  className="animate-spin"
                />

                Uploading and starting workflow...
              </span>
            ) : (
              "Run OCR → Approval Note Workflow"
            )}
          </button>

          {/* Success / Task ID */}
          {taskId && (
            <div
              className="
                rounded-lg
                border
                border-green-500/30
                bg-green-500/10
                p-3
                text-xs
                text-green-400
              "
            >
              <p className="font-medium">
                Task submitted successfully.
              </p>

              <p className="mt-2 text-neutral-400">
                Task ID:
              </p>

              <code className="block mt-1 break-all text-neutral-300">
                {taskId}
              </code>

              <p className="mt-3 text-neutral-500">
                You can track this workflow in the AI Chat workspace
                or Agent Monitor.
              </p>
            </div>
          )}
        </div>

        {/* Engine Information */}
        <div className="card">

          <h2 className="text-sm font-medium mb-3 flex items-center gap-2">
            <ScanText size={16} />
            OCR Engine
          </h2>

          <p className="text-xs text-neutral-400 leading-6">
            Tesseract runs first for fast offline OCR. If the OCR
            confidence is below the configured threshold, the pipeline
            can retry using PaddleOCR for more complex layouts, tables,
            and scanned documents.
          </p>

          <div className="mt-6 border-t border-white/10 pt-4">

            <h3 className="text-xs font-medium mb-3">
              Workflow
            </h3>

            <ol
              className="
                text-xs
                text-neutral-400
                space-y-3
                list-decimal
                list-inside
              "
            >
              <li>
                Upload an image or PDF document.
              </li>

              <li>
                The frontend sends the file as multipart form data.
              </li>

              <li>
                FastAPI reads the uploaded file.
              </li>

              <li>
                The backend converts the file to Base64.
              </li>

              <li>
                Celery starts the multi-agent workflow.
              </li>

              <li>
                The OCR Agent creates a temporary file and extracts text.
              </li>

              <li>
                Extracted content is indexed into the knowledge base.
              </li>

              <li>
                Additional planning, research, validation, and approval
                agents can process the workflow.
              </li>
            </ol>
          </div>

          <div className="mt-6 border-t border-white/10 pt-4">

            <h3 className="text-xs font-medium mb-2">
              Supported Uploads
            </h3>

            <div className="text-xs text-neutral-400 space-y-1">
              <p>• JPG / JPEG</p>
              <p>• PNG</p>
              <p>• Other browser-supported image formats</p>
              <p>• PDF</p>
            </div>
          </div>

        </div>

      </div>
    </AppShell>
  );
}