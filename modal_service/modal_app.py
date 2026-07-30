import os
import tempfile
import subprocess
import requests
import json
import modal
from pathlib import Path

from supabase import create_client


# Modal app configuration
image = modal.Image.debian_slim().apt_install("ffmpeg").pip_install("requests", "supabase", "fastapi[standard]")
app = modal.App(name="video-pipeline-burn-subtitles", image=image)

# This file is intended to be deployed on Modal.com as a separate service.
# It exposes a web endpoint `burn_subtitles` which receives a signed video URL
# and .srt content, burns the subtitles into the video with ffmpeg and uploads
# the processed file to the Supabase bucket `videos-processed`.

def burn_subtitles_handler(payload: dict) -> dict:
    required = ["video_id", "video_url", "storage_path", "srt_content", "supabase_url", "supabase_key"]
    for key in required:
        if key not in payload:
            return {"status": "error", "error": f"Paramètre manquant: {key}"}

    video_id = payload["video_id"]
    video_url = payload["video_url"]
    storage_path = payload["storage_path"]
    srt_content = payload["srt_content"]
    supabase_url = payload["supabase_url"]
    supabase_key = payload["supabase_key"]

    suffix = Path(storage_path).suffix or ".mp4"
    debug_info = f"[DEBUG] storage_path reçu: '{storage_path}' | suffix calculé: '{suffix}'"

    try:
        # Download source video
        resp = requests.get(video_url, stream=True, timeout=120)
        resp.raise_for_status()
    except Exception as exc:
        return {"status": "error", "error": f"{debug_info} | Échec du téléchargement de la vidéo: {exc}"}

    try:
        in_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        for chunk in resp.iter_content(chunk_size=8192):
            if chunk:
                in_tmp.write(chunk)
        in_tmp.flush()
        in_tmp.close()

        srt_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".srt")
        srt_tmp.write(srt_content.encode("utf-8"))
        srt_tmp.flush()
        srt_tmp.close()

        out_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        out_tmp.close()

        # Run ffmpeg to burn subtitles
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            in_tmp.name,
            "-vf",
            f"subtitles={srt_tmp.name}",
            "-c:a",
            "copy",
            out_tmp.name,
        ]

        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            err = proc.stderr or proc.stdout
            return {"status": "error", "error": f"{debug_info} | ffmpeg failed: {err}"}

        # Upload to Supabase processed bucket
        try:
            client = create_client(supabase_url, supabase_key)
            bucket = client.storage.from_("videos-processed")
            filename = f"{video_id}.mp4"
            with open(out_tmp.name, "rb") as fh:
                bucket.upload(path=filename, file=fh.read())

            signed = bucket.create_signed_url(path=filename, expires_in=24 * 3600)
            if isinstance(signed, dict):
                download_url = signed.get("signed_url") or signed.get("signedUrl") or signed.get("url")
            else:
                download_url = signed

            return {"status": "done", "download_url": download_url}
        except Exception as exc:
            return {"status": "error", "error": f"Échec de l'upload vers Supabase: {exc}"}

    finally:
        # Clean up temp files
        for p in [locals().get("in_tmp"), locals().get("srt_tmp"), locals().get("out_tmp")]:
            try:
                if p and Path(p.name).exists():
                    Path(p.name).unlink()
            except Exception:
                pass


# Minimal wrapper for Modal web endpoint compatibility.
@app.function(timeout=600)
@modal.fastapi_endpoint(method="POST")
def burn_subtitles(payload: dict) -> dict:
    """Modal FastAPI endpoint wrapper around the burn_subtitles_handler.

    Receives the JSON payload and returns the handler result. The Modal
    FastAPI integration handles JSON serialization and status codes.
    """
    result = burn_subtitles_handler(payload)
    return result
