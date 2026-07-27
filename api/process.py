import json
import os
import tempfile
from typing import Any, Dict

import requests

from lib.cleanup import cleanup_video
from lib.gemini_client import generate_title_and_description
from lib.groq_client import transcribe_audio
from lib.supabase_client import _get_client, get_video_url


def _json_response(status_code: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Construit une réponse JSON compatible avec Vercel."""
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload),
    }


def _upsert_video_result(video_id: str, payload: Dict[str, Any]) -> None:
    """Insère ou met à jour le résultat de traitement dans la table Supabase 'videos'."""
    client = _get_client()
    table = client.table("videos")
    table.upsert({"video_id": video_id, **payload}).execute()


def _get_video_id_from_request(request: Dict[str, Any]) -> str:
    """Extrait le video_id depuis le body JSON ou les query params."""
    if not isinstance(request, dict):
        raise ValueError("Requête invalide.")

    body = request.get("body") or ""
    if isinstance(body, str) and body:
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict):
                video_id = parsed.get("video_id")
                if video_id:
                    return str(video_id)
        except json.JSONDecodeError:
            pass

    query_params = request.get("query") or {}
    if isinstance(query_params, dict):
        video_id = query_params.get("video_id")
        if video_id:
            return str(video_id)

    raise ValueError("Le paramètre video_id est requis.")


def _download_video_to_tempfile(video_url: str) -> str:
    """Télécharge une vidéo à partir d'une URL vers un fichier temporaire."""
    response = requests.get(video_url, timeout=120)
    response.raise_for_status()

    suffix = ".mp4"
    temp_file = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        temp_file.write(response.content)
        temp_file.flush()
        temp_file.close()
        return temp_file.name
    except Exception:
        temp_file.close()
        os.remove(temp_file.name)
        raise


def handler(request: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """Handler serverless Vercel pour traiter une vidéo et stocker les métadonnées."""
    try:
        video_id = _get_video_id_from_request(request)
        video_url = get_video_url(f"{video_id}.mp4")

        temp_file_path = _download_video_to_tempfile(video_url)
        try:
            transcription_text, srt_content = transcribe_audio(temp_file_path)
            metadata = generate_title_and_description(transcription_text)
            result_payload = {
                "video_id": video_id,
                "titre": metadata.get("titre", ""),
                "description": metadata.get("description", ""),
                "srt_content": srt_content,
                "transcription": transcription_text,
                "status": "done",
            }
            _upsert_video_result(video_id, result_payload)
            cleanup_video(f"{video_id}.mp4")
            return _json_response(200, result_payload)
        finally:
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
    except Exception as exc:
        error_payload = {
            "video_id": None,
            "status": "error",
            "error": str(exc),
        }
        try:
            video_id = _get_video_id_from_request(request)
            error_payload["video_id"] = video_id
            _upsert_video_result(video_id, error_payload)
        except Exception:
            pass
        return _json_response(500, error_payload)
