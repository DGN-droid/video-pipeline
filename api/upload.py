import cgi
import io
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from lib.supabase_client import _get_client, upload_video


ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
MAX_FILE_SIZE_BYTES = 40 * 1024 * 1024
MAX_UPLOADS_PER_HOUR = 10


def _get_client_ip(headers: Optional[Dict[str, str]]) -> str:
    """Extrait l'adresse IP du client depuis les en-têtes de requête."""
    if not headers:
        return "unknown"

    forwarded = headers.get("x-forwarded-for") or headers.get("X-Forwarded-For") or ""
    if forwarded:
        return forwarded.split(",")[0].strip()

    real_ip = headers.get("x-real-ip") or headers.get("X-Real-IP") or ""
    if real_ip:
        return real_ip.strip()

    return headers.get("remote-addr", "unknown")


def _check_rate_limit(ip_address: str) -> None:
    """Applique un rate limiting simple basé sur l'IP avec une table Supabase."""
    try:
        client = _get_client()
        window_start = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        table = client.table("rate_limits")
        response = table.select("request_count").eq("ip_address", ip_address).eq("window_start", window_start.isoformat()).execute()

        rows = getattr(response, "data", None) or []
        if rows:
            current_count = int(rows[0].get("request_count", 0))
            if current_count >= MAX_UPLOADS_PER_HOUR:
                raise RuntimeError("Trop de requêtes depuis cette adresse IP. Réessayez plus tard.")
            table.update({"request_count": current_count + 1}).eq("ip_address", ip_address).eq("window_start", window_start.isoformat()).execute()
        else:
            table.insert({"ip_address": ip_address, "window_start": window_start.isoformat(), "request_count": 1}).execute()
    except Exception:
        # Le rate limiting est best-effort : si la table est absente ou inaccessible, on continue.
        pass


def _parse_multipart(request: Dict[str, Any]) -> tuple[Optional[str], Optional[bytes]]:
    """Parse un corps multipart/form-data et retourne le nom de fichier et le contenu binaire."""
    body = request.get("body")
    headers = request.get("headers") or {}

    if body is None:
        return None, None

    if isinstance(body, str):
        body_bytes = body.encode("utf-8")
    elif isinstance(body, bytes):
        body_bytes = body
    else:
        body_bytes = bytes(body)

    content_type = headers.get("content-type") or headers.get("Content-Type") or ""
    if not content_type.startswith("multipart/form-data"):
        raise ValueError("Le contenu doit être envoyé en multipart/form-data.")

    form = cgi.FieldStorage(
        fp=io.BytesIO(body_bytes),
        headers={"content-type": content_type},
        environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": content_type},
    )

    if "file" not in form or not getattr(form["file"], "filename", None):
        raise ValueError("Aucun fichier vidéo n'a été envoyé.")

    file_item = form["file"]
    file_bytes = file_item.file.read()
    filename = file_item.filename
    return filename, file_bytes


def _validate_video_file(filename: str, file_bytes: bytes) -> None:
    """Valide la taille et l'extension du fichier vidéo."""
    if not filename:
        raise ValueError("Le nom de fichier est obligatoire.")

    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("Type de fichier non pris en charge. Utilisez un fichier vidéo (.mp4, .mov, .avi, .mkv, .webm).")

    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise ValueError("Le fichier dépasse la limite autorisée de 40 Mo.")


def _json_response(status_code: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Construit une réponse JSON compatible avec Vercel."""
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload),
    }


def handler(request: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """Handler serverless Vercel pour l'upload d'une vidéo."""
    try:
        if not isinstance(request, dict):
            raise TypeError("La requête doit être un dictionnaire compatible avec le runtime Vercel.")

        method = (request.get("method") or "").upper()
        if method and method != "POST":
            return _json_response(405, {"error": "Méthode non autorisée. Utilisez POST."})

        ip_address = _get_client_ip(request.get("headers") or {})
        _check_rate_limit(ip_address)

        filename, file_bytes = _parse_multipart(request)
        if filename is None or file_bytes is None:
            raise ValueError("Le corps de la requête est vide.")

        _validate_video_file(filename, file_bytes)

        video_id = str(uuid.uuid4())
        ext = os.path.splitext(filename)[1].lower()
        storage_filename = f"{video_id}{ext}"

        upload_video(file_bytes, storage_filename)

        return _json_response(200, {"video_id": video_id, "status": "uploaded"})
    except RuntimeError as exc:
        if "Trop de requêtes" in str(exc):
            return _json_response(429, {"error": str(exc)})
        return _json_response(500, {"error": str(exc)})
    except ValueError as exc:
        return _json_response(400, {"error": str(exc)})
    except Exception as exc:
        return _json_response(500, {"error": f"Échec de l'upload : {exc}"})
