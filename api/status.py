import json
from typing import Any, Dict

from lib.supabase_client import _get_client


def _json_response(status_code: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Construit une réponse JSON compatible avec Vercel."""
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload),
    }


def _get_video_id_from_request(request: Dict[str, Any]) -> str:
    """Extrait le video_id depuis les query params ou le body JSON."""
    if not isinstance(request, dict):
        raise ValueError("Requête invalide.")

    query_params = request.get("query") or {}
    if isinstance(query_params, dict):
        video_id = query_params.get("video_id")
        if video_id:
            return str(video_id)

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

    raise ValueError("Le paramètre video_id est requis.")


def handler(request: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """Handler serverless Vercel pour interroger le statut d'une vidéo."""
    try:
        video_id = _get_video_id_from_request(request)
        client = _get_client()
        table = client.table("videos")
        response = table.select("*").eq("video_id", video_id).execute()

        rows = getattr(response, "data", None) or []
        if not rows:
            return _json_response(404, {"error": f"Aucune vidéo trouvée pour le video_id '{video_id}'."})

        row = rows[0]
        payload = {
            "video_id": row.get("video_id"),
            "status": row.get("status", "unknown"),
        }

        if row.get("status") == "done":
            payload.update(
                {
                    "titre": row.get("titre"),
                    "description": row.get("description"),
                    "srt_content": row.get("srt_content"),
                    "transcription": row.get("transcription"),
                }
            )

        return _json_response(200, payload)
    except ValueError as exc:
        return _json_response(400, {"error": str(exc)})
    except Exception as exc:
        return _json_response(500, {"error": f"Échec de la récupération du statut : {exc}"})
