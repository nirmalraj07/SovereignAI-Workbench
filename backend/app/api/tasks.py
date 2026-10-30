import asyncio
import base64

from celery.result import AsyncResult
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from jose import JWTError, jwt
from pydantic import BaseModel

from ..core.config import settings
from ..security.auth import get_current_user
from ..workers.celery_app import celery_app, run_agent_task
from ..workers.task_ownership import can_access, record_owner


router = APIRouter(
    prefix="/api/tasks",
    tags=["tasks"],
)


# ============================================================
# REQUEST MODELS
# ============================================================

class SubmitTaskRequest(BaseModel):
    """
    JSON request format for normal text/image-base64 submissions.
    """

    message: str
    image_b64: str | None = None
    filename: str | None = None


# ============================================================
# SUBMIT TASK
# ============================================================

@router.post("/submit")
async def submit_task(
    message: str = Form(...),
    image: UploadFile | None = File(None),
    user: dict = Depends(get_current_user),
):
    """
    Submit a long-running agent workflow.

    Supports multipart/form-data:

        message=<instruction>
        image=<uploaded image or PDF>

    The uploaded file is converted to base64 so it can safely travel
    through Celery/Redis JSON serialization.
    """

    image_b64 = None
    filename = None

    if image is not None:

        filename = image.filename or "uploaded_file"

        contents = await image.read()

        if not contents:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty",
            )

        image_b64 = base64.b64encode(contents).decode("utf-8")

    # --------------------------------------------------------
    # Send task to Celery
    # --------------------------------------------------------

    task = run_agent_task.delay(
        message,
        image_b64,
        filename,
    )

    # --------------------------------------------------------
    # Record task ownership
    # --------------------------------------------------------

    record_owner(
        task.id,
        user["username"],
    )

    return {
        "task_id": task.id,
    }


# ============================================================
# OPTIONAL JSON SUBMISSION ENDPOINT
# ============================================================

@router.post("/submit-json")
async def submit_task_json(
    payload: SubmitTaskRequest,
    user: dict = Depends(get_current_user),
):
    """
    Alternative endpoint for normal frontend chat submissions where
    JSON is preferred instead of multipart/form-data.
    """

    task = run_agent_task.delay(
        payload.message,
        payload.image_b64,
        payload.filename,
    )

    record_owner(
        task.id,
        user["username"],
    )

    return {
        "task_id": task.id,
    }


# ============================================================
# TASK STATUS
# ============================================================

@router.get("/{task_id}")
async def task_status(
    task_id: str,
    user: dict = Depends(get_current_user),
):
    """
    Returns Celery task status and result.

    Ownership is checked before exposing task information.
    """

    if not can_access(
        task_id,
        user["username"],
        user["role"],
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    result = AsyncResult(
        task_id,
        app=celery_app,
    )

    payload = {
        "task_id": task_id,
        "state": result.state,
    }

    if result.state == "SUCCESS":
        payload["result"] = result.result

    elif result.state == "FAILURE":
        payload["error"] = str(result.result)

    return payload


# ============================================================
# WEBSOCKET AUTHENTICATION
# ============================================================

def _authenticate_websocket_token(
    token: str | None,
) -> dict | None:
    """
    Authenticate a browser WebSocket connection.

    Browser WebSockets cannot normally send an Authorization header,
    so the JWT is supplied through the token query parameter.
    """

    if not token:
        return None

    try:

        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )

        username = payload.get("sub")
        role = payload.get("role")

        if not username or not role:
            return None

        return {
            "username": username,
            "role": role,
        }

    except JWTError:
        return None


# ============================================================
# TASK PROGRESS WEBSOCKET
# ============================================================

@router.websocket("/ws/{task_id}")
async def task_progress_ws(
    websocket: WebSocket,
    task_id: str,
    token: str | None = None,
):
    """
    Streams Celery task progress to the frontend.

    Example:

        ws://localhost:8000/api/tasks/ws/<task_id>?token=<JWT>
    """

    from ..observability.metrics import (
        active_websocket_connections,
    )

    # --------------------------------------------------------
    # Authenticate
    # --------------------------------------------------------

    user = _authenticate_websocket_token(token)

    if user is None:

        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Authentication required",
        )

        return

    # --------------------------------------------------------
    # Check ownership
    # --------------------------------------------------------

    if not can_access(
        task_id,
        user["username"],
        user["role"],
    ):

        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Task not found",
        )

        return

    # --------------------------------------------------------
    # Accept connection
    # --------------------------------------------------------

    await websocket.accept()

    active_websocket_connections.inc()

    try:

        while True:

            result = AsyncResult(
                task_id,
                app=celery_app,
            )

            state = result.state

            await websocket.send_json(
                {
                    "task_id": task_id,
                    "state": state,
                }
            )

            # ------------------------------------------------
            # Success
            # ------------------------------------------------

            if state == "SUCCESS":

                await websocket.send_json(
                    {
                        "task_id": task_id,
                        "state": "SUCCESS",
                        "result": result.result,
                    }
                )

                break

            # ------------------------------------------------
            # Failure
            # ------------------------------------------------

            if state == "FAILURE":

                await websocket.send_json(
                    {
                        "task_id": task_id,
                        "state": "FAILURE",
                        "error": str(result.result),
                    }
                )

                break

            await asyncio.sleep(0.5)

    except WebSocketDisconnect:
        pass

    finally:

        active_websocket_connections.dec()

        try:
            await websocket.close()
        except Exception:
            pass