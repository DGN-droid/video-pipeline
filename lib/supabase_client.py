import os
from typing import Optional

from dotenv import load_dotenv
from supabase import Client, create_client


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
