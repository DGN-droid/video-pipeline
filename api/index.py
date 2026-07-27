import os
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.request import Request, urlopen

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from lib.cleanup import delete_old_videos
from lib.gemini_client import generate_title_and_description
from lib.groq_client import transcribe_audio
from lib.supabase_client import _get_client, get_video_url, upload_video

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
MAX_FILE_SIZE_BYTES = 40 * 1024 * 1024

app = FastAPI()


class ProcessRequest(BaseModel):
    video_id: str


def _validate_video_file(filename: str, file_bytes: bytes) -> None:
    if not filename:
        raise HTTPException(status_code=400, detail="Le nom du fichier est requis.")

    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Type de fichier non pris en charge. Utilisez un fichier vidéo (.mp4, .mov, .avi, .mkv, .webm).",
        )

    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="Le fichier dépasse la limite autorisée de 40 Mo.")


def _download_video_from_url(url: str) -> str:
    request = Request(url, headers={"User-Agent": "FastAPI"})
    with urlopen(request, timeout=120) as response:
        suffix = Path(url).suffix or ".mp4"
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        temp_file.write(response.read())
        temp_file.close()
        return temp_file.name


def _upsert_video_result(video_id: str, payload: Dict[str, Any]) -> None:
    client = _get_client()
    table = client.table("videos")
    table.upsert({"video_id": video_id, **payload}).execute()


@app.post("/upload")
async def upload_endpoint(file: UploadFile = File(...)) -> Dict[str, str]:
    file_bytes = await file.read()
    _validate_video_file(file.filename, file_bytes)

    video_id = str(uuid.uuid4())
    extension = Path(file.filename).suffix.lower()
    storage_filename = f"{video_id}{extension}"
    upload_video(file_bytes, storage_filename)

    return {"video_id": video_id, "status": "uploaded"}


@app.post("/process")
def process_endpoint(request: ProcessRequest) -> Dict[str, Any]:
    video_id = request.video_id.strip()
    if not video_id:
        raise HTTPException(status_code=400, detail="Le paramètre video_id est requis.")

    filename = f"{video_id}.mp4"
    video_url = get_video_url(filename)
    if not video_url:
        raise HTTPException(status_code=404, detail="Vidéo introuvable dans Supabase.")

    temp_path = _download_video_from_url(video_url)
    try:
        transcription, srt_content = transcribe_audio(temp_path)
        metadata = generate_title_and_description(transcription)
        result_payload = {
            "video_id": video_id,
            "titre": metadata.get("titre", ""),
            "description": metadata.get("description", ""),
            "srt_content": srt_content,
            "transcription": transcription,
            "status": "done",
        }
        _upsert_video_result(video_id, result_payload)
        return result_payload
    except HTTPException:
        raise
    except Exception as exc:
        error_payload = {
            "video_id": video_id,
            "status": "error",
            "error": str(exc),
        }
        try:
            _upsert_video_result(video_id, error_payload)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@app.get("/status")
def status_endpoint(video_id: str = Query(..., min_length=1)) -> Dict[str, Any]:
    client = _get_client()
    table = client.table("videos")
    response = table.select("*").eq("video_id", video_id).execute()
    rows = getattr(response, "data", None) or []
    if not rows:
        raise HTTPException(status_code=404, detail=f"Aucune vidéo trouvée pour le video_id '{video_id}'.")

    row = rows[0]
    payload = {"video_id": row.get("video_id"), "status": row.get("status", "unknown")}
    if row.get("status") == "done":
        payload.update(
            {
                "titre": row.get("titre"),
                "description": row.get("description"),
                "srt_content": row.get("srt_content"),
                "transcription": row.get("transcription"),
            }
        )
    return payload


@app.get("/cleanup")
def cleanup_endpoint() -> Dict[str, Any]:
    return delete_old_videos()
