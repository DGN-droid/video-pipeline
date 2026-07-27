import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from dotenv import load_dotenv

from lib.supabase_client import _get_client


load_dotenv()


def delete_old_videos() -> Dict[str, Any]:
    """Supprime les vidéos anciennes (> 7 jours) du storage et nettoie la table 'videos'."""
    try:
        client = _get_client()
        table = client.table("videos")
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=7)

        response = table.select("video_id, created_at").lt("created_at", cutoff_date.isoformat()).execute()
        rows = getattr(response, "data", None) or []

        deleted_files = []
        for row in rows:
            video_id = row.get("video_id")
            if not video_id:
                continue

            filename = f"{video_id}.mp4"
            try:
                bucket = client.storage.from_("videos")
                bucket.remove([filename])
                deleted_files.append(filename)
            except Exception:
                # Le fichier peut déjà être absent ou déjà supprimé.
                pass

        if rows:
            table.delete().lt("created_at", cutoff_date.isoformat()).execute()

        return {
            "deleted_rows": len(rows),
            "deleted_files": deleted_files,
            "status": "ok",
        }
    except Exception as exc:
        raise RuntimeError(f"Échec du nettoyage des vidéos anciennes : {exc}") from exc
