import os
import shutil
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
# the processed file to the Supabase bucket `videos-processed ...

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

    work_dir = tempfile.mkdtemp()
    in_path = os.path.join(work_dir, f"input{suffix}")
    srt_path = os.path.join(work_dir, "subs.srt")
    out_path = os.path.join(work_dir, f"output{suffix}")

    try:
        with open(in_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(srt_content)

        # Run ffmpeg to burn subtitles
        import stat
        srt_exists = os.path.exists(srt_path)
        srt_size = os.path.getsize(srt_path) if srt_exists else -1
        srt_perms = oct(os.stat(srt_path).st_mode) if srt_exists else "N/A"
        dir_listing = os.listdir(work_dir)

        diagnostic = (
            f"work_dir={work_dir} | dir_listing={dir_listing} | "
            f"srt_exists={srt_exists} | srt_size={srt_size} | srt_perms={srt_perms}"
        )

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            os.path.basename(in_path),
            "-vf",
            "subtitles=subs.srt",
            "-c:a",
            "copy",
            os.path.basename(out_path),
        ]

        env = os.environ.copy()
        env["HOME"] = "/tmp"

        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=work_dir, env=env)
        if proc.returncode != 0:
            err = proc.stderr or proc.stdout
            return {"status": "error", "error": f"{diagnostic} | ffmpeg failed: {err}"}

        # Upload to Supabase processed bucket
        try:
            client = create_client(supabase_url, supabase_key)
            bucket = client.storage.from_("videos-processed")
            filename = f"{video_id}.mp4"
            with open(out_path, "rb") as fh:
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
        shutil.rmtree(work_dir, ignore_errors=True)


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
