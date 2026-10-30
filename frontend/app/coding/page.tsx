"use client";

import { useState } from "react";
import { Play, Loader2, Code2 } from "lucide-react";
import { api } from "@/lib/api-client";
import type { GenerateAndRunResponse } from "@/types";

export default function CodingPage() {
  const [instruction, setInstruction] = useState("");
  const [language, setLanguage] = useState("python");
  const [result, setResult] = useState<GenerateAndRunResponse | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  async function handleRun() {
    if (!instruction.trim()) {
      setError("Please enter a coding instruction.");
      return;
    }

    setRunning(true);
    setError("");
    setResult(null);

    try {
      const response = await api.code.generateAndRun(
        instruction,
        language
      );

      setResult(response);
    } catch (err: any) {
      console.error(err);

      setError(
        err?.response?.data?.detail ||
          err?.message ||
          "Failed to connect to the backend."
      );
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="w-full min-h-screen p-6">

      {/* Page Header */}
      <div className="mb-6 flex items-center gap-3">
        <Code2 className="w-6 h-6 text-blue-400" />
        <div>
          <h1 className="text-2xl font-semibold">
            Coding Workspace
          </h1>
          <p className="text-sm text-neutral-400 mt-1">
            Describe the program you want to create and run it securely.
          </p>
        </div>
      </div>

      {/* Main Coding Card */}
      <div className="w-full max-w-6xl mx-auto rounded-xl border border-white/10 bg-surface p-6">

        {/* Language Selection */}
        <div className="mb-5">
          <label className="block text-sm font-medium mb-2 text-neutral-300">
            Programming Language
          </label>

          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            className="
              w-full
              max-w-md
              rounded-lg
              border
              border-white/10
              bg-black/20
              px-4
              py-3
              text-neutral-200
              outline-none
              focus:border-blue-500
            "
          >
            <option value="python">Python</option>
            <option value="javascript">JavaScript</option>
            <option value="java">Java</option>
            <option value="c">C</option>
            <option value="cpp">C++</option>
            <option value="sql">SQL</option>
          </select>
        </div>

        {/* Prompt Input */}
        <div className="mb-5">
          <label className="block text-sm font-medium mb-2 text-neutral-300">
            What would you like to build?
          </label>

          <textarea
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            placeholder={`Example:

Write a ${language} program that asks the user for two numbers and prints their sum.`}
            className="
              w-full
              min-h-[220px]
              resize-y
              rounded-xl
              border
              border-white/10
              bg-black/20
              p-5
              text-base
              text-neutral-100
              placeholder:text-neutral-500
              outline-none
              focus:border-blue-500
              focus:ring-1
              focus:ring-blue-500/30
            "
          />
        </div>

        {/* Button Area */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">

          <p className="text-sm text-neutral-500">
            The AI will generate the code and execute it in the sandbox.
          </p>

          <button
            onClick={handleRun}
            disabled={running || !instruction.trim()}
            className="
              flex
              items-center
              justify-center
              gap-2
              min-w-[180px]
              rounded-lg
              bg-blue-500
              px-6
              py-3
              font-semibold
              text-white
              transition
              hover:bg-blue-600
              disabled:cursor-not-allowed
              disabled:opacity-50
            "
          >
            {running ? (
              <>
                <Loader2 className="w-5 h-5 animate-spin" />
                Running...
              </>
            ) : (
              <>
                <Play className="w-5 h-5" />
                Generate & Run
              </>
            )}
          </button>

        </div>

        {/* Error */}
        {error && (
          <div className="mt-6 rounded-lg border border-red-500/30 bg-red-500/10 p-4 text-red-400">
            {error}
          </div>
        )}
      </div>

      {/* Results */}
      {result && (
        <div className="w-full max-w-6xl mx-auto mt-6 space-y-6">

          {/* Generated Code */}
          <div className="rounded-xl border border-white/10 bg-surface p-6">
            <h2 className="text-lg font-semibold mb-4">
              Generated Code
            </h2>

            <pre className="overflow-x-auto rounded-lg bg-black/30 p-5 text-sm text-green-300">
              <code>{result.final_code}</code>
            </pre>
          </div>

          {/* Execution Result */}
          <div className="rounded-xl border border-white/10 bg-surface p-6">

            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">
                Execution Result
              </h2>

              <span
                className={
                  result.success
                    ? "text-green-400 font-medium"
                    : "text-red-400 font-medium"
                }
              >
                {result.success ? "SUCCESS" : "FAILED"}
              </span>
            </div>

            {result.stdout && (
              <div className="mb-4">
                <h3 className="text-sm text-neutral-400 mb-2">
                  Output
                </h3>

                <pre className="overflow-x-auto rounded-lg bg-black/30 p-5 text-sm">
                  {result.stdout}
                </pre>
              </div>
            )}

            {result.stderr && (
              <div>
                <h3 className="text-sm text-red-400 mb-2">
                  Errors
                </h3>

                <pre className="overflow-x-auto rounded-lg bg-red-500/10 p-5 text-sm text-red-300">
                  {result.stderr}
                </pre>
              </div>
            )}

          </div>

        </div>
      )}

    </div>
  );
}