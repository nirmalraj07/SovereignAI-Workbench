"use client";
import { useRef, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { api } from "@/lib/api-client";
import { Eye } from "lucide-react";

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve((reader.result as string).split(",")[1]);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

export default function VisionPage() {
  const fileRef = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [imageB64, setImageB64] = useState<string | null>(null);
  const [instruction, setInstruction] = useState("Analyze this engineering drawing and identify components");
  const [taskId, setTaskId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onFileChange() {
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    setPreview(URL.createObjectURL(file));
    setImageB64(await fileToBase64(file));
  }

  async function handleSubmit() {
    setSubmitting(true);
    try {
      const res = await api.tasks.submit(instruction, imageB64 ?? undefined);
      setTaskId(res.task_id);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AppShell title="Vision Analysis Workspace">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card space-y-3">
          <h2 className="text-sm font-medium flex items-center gap-2"><Eye size={16} /> Upload drawing / photo</h2>
          <input ref={fileRef} type="file" accept="image/*" onChange={onFileChange} className="text-xs" />
          {preview && <img src={preview} alt="preview" className="rounded-lg border border-white/10 max-h-64 object-contain" />}
          <textarea
            className="input-field h-24 resize-none"
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
          />
          <button onClick={handleSubmit} className="btn-primary w-full" disabled={submitting || !imageB64}>
            {submitting ? "Submitting…" : "Analyze with Qwen2.5-VL"}
          </button>
          {taskId && (
            <p className="text-[11px] text-neutral-500">
              Task submitted: <code>{taskId.slice(0, 8)}</code>
            </p>
          )}
        </div>
        <div className="card">
          <h2 className="text-sm font-medium mb-2">Supported drawing types</h2>
          <ul className="text-xs text-neutral-400 space-y-1 list-disc list-inside">
            <li>P&amp;ID diagrams</li>
            <li>Process flow diagrams</li>
            <li>Equipment layouts</li>
            <li>General technical schematics</li>
          </ul>
        </div>
      </div>
    </AppShell>
  );
}
