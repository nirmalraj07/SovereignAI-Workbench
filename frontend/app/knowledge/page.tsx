"use client";
import { useRef, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { api } from "@/lib/api-client";
import type { KBQueryResponse } from "@/types";
import { Upload, Search } from "lucide-react";

export default function KnowledgePage() {
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<KBQueryResponse | null>(null);
  const [searching, setSearching] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    setSearching(true);
    try {
      setResult(await api.kb.query(query));
    } finally {
      setSearching(false);
    }
  }

  async function handleUpload() {
    const file = fileRef.current?.files?.[0];
    if (!file) return;
    setUploadStatus("Ingesting…");
    try {
      const res = await api.kb.ingest(file);
      setUploadStatus(`Indexed ${res.filename} (${res.characters_extracted} chars extracted)`);
    } catch {
      setUploadStatus("Ingestion failed");
    }
  }

  return (
    <AppShell title="Knowledge Search Workspace">
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="card space-y-3">
          <h2 className="text-sm font-medium flex items-center gap-2"><Upload size={16} /> Ingest document</h2>
          <input ref={fileRef} type="file" accept=".pdf,.docx,.txt,.csv,.xlsx" className="text-xs" />
          <button onClick={handleUpload} className="btn-secondary w-full">Upload &amp; index</button>
          {uploadStatus && <p className="text-[11px] text-neutral-500">{uploadStatus}</p>}
        </div>

        <form onSubmit={handleSearch} className="card lg:col-span-2 space-y-3">
          <h2 className="text-sm font-medium flex items-center gap-2"><Search size={16} /> Search SOPs &amp; manuals</h2>
          <div className="flex gap-2">
            <input className="input-field" value={query} onChange={(e) => setQuery(e.target.value)}
                   placeholder="Ask a question grounded in the knowledge base…" />
            <button type="submit" className="btn-primary" disabled={searching}>
              {searching ? "Searching…" : "Search"}
            </button>
          </div>
        </form>
      </div>

      {result && (
        <div className="card mt-6">
          <h2 className="text-sm font-medium mb-3">Retrieved sources</h2>
          <div className="space-y-3">
            {result.chunks.length === 0 && <p className="text-xs text-neutral-500">No matching chunks found.</p>}
            {result.chunks.map((chunk, i) => (
              <div key={i} className="border-b border-white/5 pb-3">
                <div className="flex justify-between text-xs text-neutral-500 mb-1">
                  <span>{chunk.filename} — p.{chunk.page}</span>
                  <span>relevance {chunk.score.toFixed(2)}</span>
                </div>
                <p className="text-sm text-neutral-300">{chunk.text}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </AppShell>
  );
}
