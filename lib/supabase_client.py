import json
import logging
import os
from typing import Optional

from dotenv import load_dotenv
from supabase import Client, create_client

try:
    from storage3.exceptions import StorageApiError
except ImportError:
    StorageApiError = Exception

try:
    import httpx
except ImportError:
    httpx = None

load_dotenv()


def _get_client() -> Client:
    """Initialise et retourne un client Supabase depuis les variables d'environnement."""
    try:
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")

        if not supabase_url or not supabase_key:
            raise ValueError("SUPABASE_URL et SUPABASE_KEY doivent être définies dans l'environnement.")

        return create_client(supabase_url, supabase_key)
    except Exception as exc:
        raise RuntimeError(f"Échec de la connexion à Supabase : {exc}") from exc


def upload_video(file_bytes: bytes, filename: str) -> str:
    """Upload un fichier vidéo dans le bucket Supabase Storage 'videos'."""
    try:
        client = _get_client()
        bucket = client.storage.from_("videos")
        bucket.upload(path=filename, file=file_bytes)
        return bucket.get_public_url(filename)
    except Exception as exc:
        raise RuntimeError(f"Échec de l'upload vidéo '{filename}' : {exc}") from exc


def delete_video(filename: str) -> bool:
    """Supprime un fichier vidéo du bucket Supabase Storage 'videos'."""
    try:
        client = _get_client()
        bucket = client.storage.from_("videos")
        bucket.remove([filename])
        return True
    except Exception as exc:
        raise RuntimeError(f"Échec de la suppression du fichier '{filename}' : {exc}") from exc


def get_video_url(filename: str, expires_in: int = 3600) -> Optional[str]:
    """Retourne une URL signée temporaire pour accéder à un fichier vidéo."""
    try:
        client = _get_client()
        bucket = client.storage.from_("videos")
        response = bucket.create_signed_url(path=filename, expires_in=expires_in)

        if isinstance(response, dict):
            return response.get("signedURL") or response.get("signed_url") or response.get("url")

        return response
    except Exception as exc:
        raise RuntimeError(f"Échec de la génération de l'URL signée pour '{filename}' : {exc}") from exc


def _extract_response_body(exc: Exception) -> str:
    response_body = ""

    if hasattr(exc, "response") and exc.response is not None:
        try:
            response_body = exc.response.text
        except Exception:
            response_body = str(exc.response)

        if response_body:
            try:
                parsed = json.loads(response_body)
                response_body = json.dumps(parsed, indent=2, ensure_ascii=False)
            except Exception:
                pass

    return response_body or "<corps de réponse introuvable>"


def create_signed_upload_url(storage_path: str) -> dict:
    """Crée une URL signée pour un upload direct depuis le navigateur vers Supabase Storage."""
    client = _get_client()
    bucket = client.storage.from_("videos")

    try:
        response = bucket.create_signed_upload_url(path=storage_path)

        if isinstance(response, dict):
            return {
                "signed_url": response.get("signed_url") or response.get("signedUrl"),
                "headers": {},
                "path": response.get("path", storage_path),
            }

        return {"signed_url": response, "headers": {}, "path": storage_path}
    except StorageApiError as exc:
        status_code = getattr(exc, "status_code", "inconnu")
        response_body = _extract_response_body(exc)
        error_message = (
            f"StorageApiError (HTTP {status_code}) lors de la génération de l'URL d'upload signée pour '{storage_path}'."
            f" Réponse : {response_body}"
        )
        logging.error(error_message)
        raise RuntimeError(error_message) from exc
    except Exception as exc:
        if httpx is not None and isinstance(exc, httpx.HTTPStatusError):
            status_code = exc.response.status_code if exc.response is not None else "inconnu"
            response_body = _extract_response_body(exc)
            error_message = (
                f"HTTPStatusError (HTTP {status_code}) lors de la génération de l'URL d'upload signée pour '{storage_path}'."
                f" Réponse : {response_body}"
            )
            logging.error(error_message)
            raise RuntimeError(error_message) from exc

        raise RuntimeError(f"Échec de la génération de l'URL d'upload signée pour '{storage_path}' : {exc}") from exc
