import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..sandbox import executor as sandbox
from ..router.router import router as model_router
from ..security.auth import get_current_user
from ..security.audit import record_event


router = APIRouter(prefix="/api/code", tags=["code"])


# ============================================================
# REQUEST MODELS
# ============================================================

class RunRequest(BaseModel):
    code: str
    language: str


class GenerateAndRunRequest(BaseModel):
    instruction: str
    language: str = "python"
    max_repair_attempts: int = 3


# ============================================================
# CODE CLEANING
# ============================================================

def clean_generated_code(text: str, language: str) -> str:
    """
    Extract executable source code from an AI response.

    Handles:
    - Markdown code blocks
    - ```python
    - ```javascript
    - ```java
    - ```c
    - ```cpp
    - ```sql
    - Explanations before code
    - Explanations after code
    """

    if not text:
        return ""

    text = text.strip()

    # --------------------------------------------------------
    # STEP 1: Extract Markdown fenced code blocks
    # --------------------------------------------------------

    pattern = r"```(?:[a-zA-Z0-9_+\-]*)?\s*\n?(.*?)```"

    matches = re.findall(
        pattern,
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )

    if matches:
        # Use the largest code block.
        # Usually this is the actual complete program.
        code = max(matches, key=len).strip()

        return code

    # --------------------------------------------------------
    # STEP 2: Remove accidental Markdown opening fence
    # --------------------------------------------------------

    text = re.sub(
        r"^```(?:python|javascript|java|c|cpp|sql)?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # --------------------------------------------------------
    # STEP 3: Remove accidental Markdown closing fence
    # --------------------------------------------------------

    text = re.sub(
        r"\s*```$",
        "",
        text,
    )

    return text.strip()


# ============================================================
# RUN EXISTING CODE
# ============================================================

@router.post("/run")
async def run(
    req: RunRequest,
    user: dict = Depends(get_current_user),
):
    try:
        print("\n=== CODE RUN START ===")
        print(f"Language: {req.language}")

        result = await sandbox.execute(
            req.code,
            req.language,
        )

        record_event(
            user=user["username"],
            action="code_run",
            resource=req.language,
        )

        print("=== CODE RUN COMPLETE ===")
        print(f"Exit Code: {result.exit_code}")

        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_code,
            "duration_ms": result.duration_ms,
            "timed_out": result.timed_out,
        }

    except Exception as exc:
        import traceback

        print("\n========== CODE RUN ERROR ==========")
        traceback.print_exc()
        print("====================================\n")

        return {
            "stdout": "",
            "stderr": str(exc),
            "exit_code": -1,
            "duration_ms": 0,
            "timed_out": False,
        }


# ============================================================
# GENERATE AND RUN CODE
# ============================================================

@router.post("/generate-and-run")
async def generate_and_run(
    req: GenerateAndRunRequest,
    user: dict = Depends(get_current_user),
):
    """
    Coding Workspace workflow:

    1. Generate code using AI
    2. Extract executable code
    3. Execute code
    4. If execution fails, ask AI to repair it
    5. Execute repaired code
    6. Return final result
    """

    print("\n========================================")
    print("=== CODING WORKSPACE START ===")
    print("========================================")

    print(f"Instruction: {req.instruction}")
    print(f"Language: {req.language}")

    try:

        # ====================================================
        # STEP 1: GENERATE CODE
        # ====================================================

        print("\n=== GENERATING CODE ===")

        prompt = f"""
You are an expert programming assistant.

Write a complete and executable {req.language} program.

USER REQUEST:
{req.instruction}

STRICT RULES:

1. Return ONLY the source code.
2. Do NOT explain the code.
3. Do NOT say "Here is the code".
4. Do NOT use Markdown.
5. Do NOT use triple backticks.
6. Do NOT add text before the program.
7. Do NOT add text after the program.
8. The result must be directly executable.
"""

        gen = await model_router.generate(
            prompt,
            explicit_modality="code",
        )

        # Extract only executable source code
        generated_code = clean_generated_code(
            gen.text,
            req.language,
        )

        if not generated_code:
            raise RuntimeError(
                "The AI did not return any executable code."
            )

        print("\n=== GENERATED CODE ===")
        print(generated_code)

        # ====================================================
        # STEP 2: REPAIR FUNCTION
        # ====================================================

        async def repair(code: str, stderr: str) -> str:

            print("\n=== REPAIRING CODE ===")

            repair_prompt = f"""
You are an expert {req.language} debugging assistant.

The following program failed.

ERROR:
{stderr}

PROGRAM:
{code}

Fix the program.

STRICT RULES:

1. Return ONLY corrected source code.
2. Do NOT explain the problem.
3. Do NOT explain the solution.
4. Do NOT use Markdown.
5. Do NOT use triple backticks.
6. Do NOT add text before the code.
7. Do NOT add text after the code.
8. Return a complete executable program.
"""

            fix = await model_router.generate(
                repair_prompt,
                explicit_modality="code",
            )

            fixed_code = clean_generated_code(
                fix.text,
                req.language,
            )

            if not fixed_code:
                raise RuntimeError(
                    "The AI repair process did not return executable code."
                )

            print("\n=== REPAIRED CODE ===")
            print(fixed_code)

            return fixed_code

        # ====================================================
        # STEP 3: EXECUTE + AUTO REPAIR
        # ====================================================

        print("\n=== EXECUTING CODE ===")

        result, final_code, attempts = (
            await sandbox.execute_with_repair(
                generated_code,
                req.language,
                repair,
                max_attempts=req.max_repair_attempts,
            )
        )

        # ====================================================
        # STEP 4: RECORD AUDIT EVENT
        # ====================================================

        record_event(
            user=user["username"],
            action="code_generate_and_run",
            resource=req.language,
        )

        success = result.exit_code == 0

        print("\n========================================")
        print("=== CODING WORKSPACE COMPLETE ===")
        print("========================================")

        print(f"Success: {success}")
        print(f"Attempts: {attempts}")
        print(f"Exit Code: {result.exit_code}")

        # ====================================================
        # STEP 5: RETURN RESULT
        # ====================================================

        return {
            "final_code": final_code,
            "attempts": attempts,
            "success": success,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    except Exception as exc:
        import traceback

        print("\n========================================")
        print("========== CODING WORKSPACE ERROR ==========")
        print("========================================")

        traceback.print_exc()

        print("========================================\n")

        # Return JSON so frontend does not receive
        # an Axios Network Error.

        return {
            "final_code": "",
            "attempts": 0,
            "success": False,
            "stdout": "",
            "stderr": str(exc),
        }