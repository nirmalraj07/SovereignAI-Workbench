"""
Sandbox executor.

For Windows/local development, generated code is executed using local
subprocesses.

WARNING:
This is intended for local development. Production deployments should use
Docker or another properly isolated sandbox.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

from dataclasses import dataclass
from pathlib import Path


# ============================================================
# LANGUAGE CONFIGURATION
# ============================================================

_LANGUAGE_RUNNERS = {
    "python": {
        "filename": "main.py",
        "command": lambda path: [
            sys.executable,
            str(path),
        ],
        "required": None,
    },

    "javascript": {
        "filename": "main.js",
        "command": lambda path: [
            "node",
            str(path),
        ],
        "required": "node",
    },

    "c": {
        "filename": "main.c",
        "compile_command": lambda path: [
            "gcc",
            str(path),
            "-o",
            str(path.parent / "main.exe"),
        ],
        "run_command": lambda path: [
            str(path.parent / "main.exe"),
        ],
        "required": "gcc",
    },

    "cpp": {
        "filename": "main.cpp",
        "compile_command": lambda path: [
            "g++",
            str(path),
            "-o",
            str(path.parent / "main.exe"),
        ],
        "run_command": lambda path: [
            str(path.parent / "main.exe"),
        ],
        "required": "g++",
    },

    "java": {
        "filename": "Main.java",
        "compile_command": lambda path: [
            "javac",
            str(path),
        ],
        "run_command": lambda path: [
            "java",
            "-cp",
            str(path.parent),
            "Main",
        ],
        "required": "javac",
    },
}


@dataclass
class ExecutionResult:
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: float
    timed_out: bool = False


# ============================================================
# LOCAL PROCESS EXECUTION
# ============================================================

def run_local_process(
    command: list[str],
    working_directory: str,
    timeout: int,
):
    """
    Run a process synchronously.

    Called through asyncio.to_thread() so Windows does not encounter
    asyncio.create_subprocess_exec() NotImplementedError.
    """

    try:
        completed = subprocess.run(
            command,
            cwd=working_directory,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        return {
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "exit_code": completed.returncode,
            "timed_out": False,
        }

    except subprocess.TimeoutExpired as exc:

        stdout = exc.stdout or ""
        stderr = exc.stderr or "Execution timed out"

        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")

        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")

        return {
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": -1,
            "timed_out": True,
        }

    except FileNotFoundError as exc:

        return {
            "stdout": "",
            "stderr": (
                f"Required program was not found: {exc.filename}. "
                "Please install the required language runtime/compiler "
                "and make sure it is available in PATH."
            ),
            "exit_code": -1,
            "timed_out": False,
        }

    except Exception as exc:

        return {
            "stdout": "",
            "stderr": str(exc),
            "exit_code": -1,
            "timed_out": False,
        }


# ============================================================
# EXECUTE CODE
# ============================================================

async def execute(code: str, language: str) -> ExecutionResult:
    """
    Execute generated code locally on Windows.
    """

    start = time.time()

    language = language.lower().strip()

    if language not in _LANGUAGE_RUNNERS:

        return ExecutionResult(
            stdout="",
            stderr=(
                f"Unsupported language: {language}. "
                f"Supported languages: {', '.join(_LANGUAGE_RUNNERS.keys())}"
            ),
            exit_code=-1,
            duration_ms=0,
        )

    runner = _LANGUAGE_RUNNERS[language]

    # --------------------------------------------------------
    # CHECK REQUIRED RUNTIME / COMPILER
    # --------------------------------------------------------

    required = runner.get("required")

    if required and shutil.which(required) is None:

        return ExecutionResult(
            stdout="",
            stderr=(
                f"{required} is not installed or is not available in PATH. "
                f"Please install the required runtime/compiler for {language}."
            ),
            exit_code=-1,
            duration_ms=(time.time() - start) * 1000,
        )

    run_id = uuid.uuid4().hex[:12]

    try:

        with tempfile.TemporaryDirectory(
            prefix=f"sovereignai-sandbox-{run_id}-"
        ) as tmpdir:

            working_directory = Path(tmpdir)

            # ------------------------------------------------
            # CREATE SOURCE FILE
            # ------------------------------------------------

            source_path = (
                working_directory /
                runner["filename"]
            )

            source_path.write_text(
                code,
                encoding="utf-8",
            )

            print("\n================================")
            print("=== LOCAL SANDBOX START ===")
            print("================================")
            print(f"Language: {language}")
            print(f"Source: {source_path}")

            # ------------------------------------------------
            # COMPILED LANGUAGES
            # ------------------------------------------------

            if "compile_command" in runner:

                compile_command = runner["compile_command"](
                    source_path
                )

                print("\n=== COMPILING ===")
                print("Command:", " ".join(compile_command))

                compile_result = await asyncio.to_thread(
                    run_local_process,
                    compile_command,
                    str(working_directory),
                    20,
                )

                if compile_result["exit_code"] != 0:

                    return ExecutionResult(
                        stdout=compile_result["stdout"],
                        stderr=compile_result["stderr"],
                        exit_code=compile_result["exit_code"],
                        duration_ms=(
                            time.time() - start
                        ) * 1000,
                        timed_out=compile_result["timed_out"],
                    )

                command = runner["run_command"](source_path)

            # ------------------------------------------------
            # INTERPRETED LANGUAGES
            # ------------------------------------------------

            else:

                command = runner["command"](
                    source_path
                )

            # ------------------------------------------------
            # RUN PROGRAM
            # ------------------------------------------------

            print("\n=== EXECUTING ===")
            print("Command:", " ".join(command))

            process_result = await asyncio.to_thread(
                run_local_process,
                command,
                str(working_directory),
                10,
            )

            duration_ms = (
                time.time() - start
            ) * 1000

            print("\n=== EXECUTION COMPLETE ===")
            print(
                f"Exit Code: {process_result['exit_code']}"
            )

            return ExecutionResult(
                stdout=process_result["stdout"],
                stderr=process_result["stderr"],
                exit_code=process_result["exit_code"],
                duration_ms=duration_ms,
                timed_out=process_result["timed_out"],
            )

    except Exception as exc:

        return ExecutionResult(
            stdout="",
            stderr=str(exc),
            exit_code=-1,
            duration_ms=(time.time() - start) * 1000,
        )


# ============================================================
# EXECUTE WITH AI REPAIR
# ============================================================

async def execute_with_repair(
    initial_code: str,
    language: str,
    repair_fn,
    max_attempts: int = 3,
):
    """
    Execute generated code and automatically request AI repairs when
    execution fails.
    """

    code = initial_code

    for attempt in range(1, max_attempts + 1):

        print(f"\n=== EXECUTION ATTEMPT {attempt} ===")

        result = await execute(
            code,
            language,
        )

        # SUCCESS
        if result.exit_code == 0:

            print("=== EXECUTION SUCCESS ===")

            return result, code, attempt

        # FAILURE
        print("=== EXECUTION FAILED ===")
        print(result.stderr)

        # Ask AI to repair the code
        code = await repair_fn(
            code,
            result.stderr,
        )

    # --------------------------------------------------------
    # FINAL EXECUTION
    # --------------------------------------------------------

    print("\n=== FINAL EXECUTION ===")

    result = await execute(
        code,
        language,
    )

    return result, code, max_attempts