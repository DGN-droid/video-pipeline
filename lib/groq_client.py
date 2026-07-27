import io
import os
from pathlib import Path
from typing import BinaryIO, Optional, Union

from dotenv import load_dotenv
from groq import Groq


load_dotenv()


def _get_client() -> Groq:
    """Initialise et retourne un client Groq à partir de la variable d'environnement GROQ_API_KEY."""
    try:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("GROQ_API_KEY doit être défini dans l'environnement.")
        return Groq(api_key=api_key)
    except Exception as exc:
        raise RuntimeError(f"Échec de la connexion à l'API Groq : {exc}") from exc


def _format_srt_timestamp(seconds: float) -> str:
    """Convertit un temps en secondes au format SRT HH:MM:SS,mmm."""
    total_ms = int(round(seconds * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds_part, milliseconds = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds_part:02d},{milliseconds:03d}"


def _build_srt_from_segments(segments: Optional[list]) -> str:
    """Construit un contenu SRT à partir des segments retournés par l'API."""
    if not segments:
        return ""

    lines: list[str] = []
    for index, segment in enumerate(segments, start=1):
        start = getattr(segment, "start", None)
        end = getattr(segment, "end", None)
        text = getattr(segment, "text", None) or ""

        if start is None or end is None:
            continue

        lines.append(str(index))
        lines.append(f"{_format_srt_timestamp(float(start))} --> {_format_srt_timestamp(float(end))}")
        lines.append(text.strip())
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def transcribe_audio(file_path_or_bytes: Union[str, bytes, bytearray, BinaryIO]) -> tuple[str, str]:
    """Transcrit un fichier audio/vidéo avec Whisper et retourne le texte + le contenu SRT."""
    try:
        client = _get_client()

        if isinstance(file_path_or_bytes, (bytes, bytearray)):
            filename = "audio.wav"
            file_obj = io.BytesIO(bytes(file_path_or_bytes))
        elif isinstance(file_path_or_bytes, (str, os.PathLike)):
            path = Path(file_path_or_bytes)
            if not path.exists():
                raise FileNotFoundError(f"Le fichier '{path}' est introuvable.")
            filename = path.name
            file_obj = path.open("rb")
        elif hasattr(file_path_or_bytes, "read"):
            filename = "audio.wav"
            file_obj = file_path_or_bytes
        else:
            raise TypeError("Le paramètre doit être un chemin de fichier, des bytes ou un objet de type fichier.")

        try:
            try:
                file_obj.seek(0)
                response = client.audio.transcriptions.create(
                    file=(filename, file_obj),
                    model="whisper-large-v3",
                    response_format="srt",
                )
                if isinstance(response, str):
                    return response.strip(), response.strip()
            except Exception as first_error:
                file_obj.seek(0)
                response = client.audio.transcriptions.create(
                    file=(filename, file_obj),
                    model="whisper-large-v3",
                    response_format="verbose_json",
                )

                full_text = getattr(response, "text", None) or ""
                segments = getattr(response, "segments", None) or []
                srt_content = _build_srt_from_segments(segments)
                return full_text.strip(), srt_content

        finally:
            if hasattr(file_obj, "close") and file_obj is not None:
                file_obj.close()

    except FileNotFoundError as exc:
        raise RuntimeError(f"Fichier introuvable : {exc}") from exc
    except TypeError as exc:
        raise RuntimeError(f"Type de fichier invalide : {exc}") from exc
    except Exception as exc:
        error_message = str(exc).lower()
        if "quota" in error_message or "rate limit" in error_message or "limit" in error_message:
            raise RuntimeError("Échec de la transcription : quota ou limite dépassé sur l'API Groq.") from exc
        if "too large" in error_message or "size" in error_message:
            raise RuntimeError("Échec de la transcription : le fichier est trop volumineux.") from exc
        if "network" in error_message or "timeout" in error_message or "connection" in error_message:
            raise RuntimeError("Échec de la transcription : erreur réseau ou délai d'attente dépassé.") from exc
        raise RuntimeError(f"Échec de la transcription audio : {exc}") from exc
