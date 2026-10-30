"use client";
import { useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { api } from "@/lib/api-client";
import type { GeneratedFileResponse } from "@/types";
import { FileText, Table, Presentation } from "lucide-react";

export default function FilesPage() {
  const [title, setTitle] = useState("Untitled Report");
  const [body, setBody] = useState("");
  const [generated, setGenerated] = useState<{ kind: string; file: GeneratedFileResponse }[]>([]);
  const [busy, setBusy] = useState<string | null>(null);

  async function generate(kind: "docx" | "xlsx" | "pptx") {
    setBusy(kind);
    try {
      let file: GeneratedFileResponse;
      if (kind === "docx") file = await api.files.generateDocx(title, body);
      else if (kind === "xlsx") file = await api.files.generateXlsx(title, ["Item", "Value"], [["Sample", "123"]]);
      else file = await api.files.generatePptx(title, [{ title: "Summary", bullets: body.split("\n").filter(Boolean) }]);
      setGenerated((g) => [{ kind, file }, ...g]);
    } finally {
      setBusy(null);
    }
  }

  return (
    <AppShell title="File Generation Workspace">
      <div className="card space-y-3 mb-6">
        <input className="input-field" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Document title" />
        <textarea className="input-field h-32 resize-none" value={body} onChange={(e) => setBody(e.target.value)}
                  placeholder="Body text / bullet points (one per line for presentations)" />
        <div className="flex gap-3">
          <button onClick={() => generate("docx")} disabled={busy !== null} className="btn-secondary flex items-center gap-1">
            <FileText size={14} /> {busy === "docx" ? "Generating…" : "Generate DOCX"}
          </button>
          <button onClick={() => generate("xlsx")} disabled={busy !== null} className="btn-secondary flex items-center gap-1">
            <Table size={14} /> {busy === "xlsx" ? "Generating…" : "Generate XLSX"}
          </button>
          <button onClick={() => generate("pptx")} disabled={busy !== null} className="btn-secondary flex items-center gap-1">
            <Presentation size={14} /> {busy === "pptx" ? "Generating…" : "Generate PPTX"}
          </button>
        </div>
      </div>

      <div className="card">
        <h2 className="text-sm font-medium mb-3">Generated files</h2>
        {generated.length === 0 && <p className="text-xs text-neutral-500">Nothing generated yet.</p>}
        <div className="space-y-2">
          {generated.map((g, i) => (
            <div key={i} className="flex justify-between items-center text-sm border-b border-white/5 pb-2">
              <span>{g.file.file_path.split("/").pop()}</span>
              <a href={api.files.downloadUrl(g.file.file_path)} className="text-accent text-xs hover:underline">
                Download
              </a>
            </div>
          ))}
        </div>
      </div>
    </AppShell>
  );
}
