from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from ..files import generator as files
from ..security.auth import get_current_user
from ..security.audit import record_event

router = APIRouter(prefix="/api/files", tags=["files"])


class DocxRequest(BaseModel):
    title: str
    body_text: str


class ApprovalNoteRequest(BaseModel):
    title: str
    observations: str
    recommendation: str
    references: list[str] = []


class XlsxRequest(BaseModel):
    title: str
    headers: list[str]
    rows: list[list]


class PptxRequest(BaseModel):
    title: str
    slides: list[dict]


@router.post("/generate/docx")
async def gen_docx(req: DocxRequest, user: dict = Depends(get_current_user)):
    path = files.generate_docx(req.title, req.body_text)
    record_event(user["username"], "generate_docx", req.title)
    return {"file_path": str(path), "download_url": f"/api/files/download?path={path}"}


@router.post("/generate/approval-note")
async def gen_approval(req: ApprovalNoteRequest, user: dict = Depends(get_current_user)):
    path = files.generate_approval_note(req.title, req.observations, req.recommendation, req.references)
    record_event(user["username"], "generate_approval_note", req.title)
    return {"file_path": str(path), "download_url": f"/api/files/download?path={path}"}


@router.post("/generate/xlsx")
async def gen_xlsx(req: XlsxRequest, user: dict = Depends(get_current_user)):
    path = files.generate_xlsx(req.title, req.headers, req.rows)
    record_event(user["username"], "generate_xlsx", req.title)
    return {"file_path": str(path), "download_url": f"/api/files/download?path={path}"}


@router.post("/generate/pptx")
async def gen_pptx(req: PptxRequest, user: dict = Depends(get_current_user)):
    path = files.generate_pptx(req.title, req.slides)
    record_event(user["username"], "generate_pptx", req.title)
    return {"file_path": str(path), "download_url": f"/api/files/download?path={path}"}


@router.get("/download")
async def download(path: str, user: dict = Depends(get_current_user)):
    # Resolve symlinks and normalize ".." segments BEFORE the containment
    # check — Path.is_relative_to() compares path parts lexically and does
    # NOT collapse "..", so "/data/generated/../../etc/passwd" would
    # otherwise pass as "under" OUTPUT_DIR while actually resolving outside it.
    file_path = Path(path).resolve()
    output_root = files.OUTPUT_DIR.resolve()
    if not file_path.is_relative_to(output_root):
        raise HTTPException(status_code=403, detail="Path outside generated-files directory")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    record_event(user["username"], "download_file", str(file_path))
    return FileResponse(file_path, filename=file_path.name)
