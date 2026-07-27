import json
import os
import re
from typing import Dict

import google.generativeai as genai
from dotenv import load_dotenv


load_dotenv()


def _get_client() -> genai.GenerativeModel:
    """Initialise et retourne un client Gemini à partir de la variable d'environnement GEMINI_API_KEY."""
    try:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY doit être défini dans l'environnement.")
        genai.configure(api_key=api_key)
        return genai.GenerativeModel("gemini-1.5-flash")
    except Exception as exc:
        raise RuntimeError(f"Échec de la connexion à l'API Gemini : {exc}") from exc


def _clean_json_response(text: str) -> str:
    """Nettoie une réponse Gemini pour extraire un JSON valide."""
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[len("```json"):]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()


def generate_title_and_description(transcription_text: str) -> Dict[str, str]:
    """Génère un titre court et une description à partir d'une transcription."""
    try:
        if not transcription_text or not transcription_text.strip():
            raise ValueError("La transcription ne doit pas être vide.")

        client = _get_client()
        prompt = """
        Tu es un assistant expert en création de contenu vidéo.
        À partir de la transcription fournie, génère un titre court et accrocheur (maximum 70 caractères)
        et une description de 2 à 3 phrases résumant le contenu de la vidéo.

        Réponds STRICTEMENT en JSON au format suivant :
        {"titre": "...", "description": "..."}

        Règles :
        - Ne renvoie aucun texte autour du JSON.
        - N'ajoute pas de balises markdown.
        - Utilise des guillemets doubles et un JSON valide.
        - Si la transcription est floue, fais une synthèse prudente.
        """

        response = client.generate_content([prompt, transcription_text])
        raw_text = getattr(response, "text", "") or ""
        cleaned = _clean_json_response(raw_text)

        parsed = json.loads(cleaned)
        if not isinstance(parsed, dict):
            raise ValueError("La réponse Gemini n'est pas un objet JSON valide.")

        titre = parsed.get("titre")
        description = parsed.get("description")
        if not isinstance(titre, str) or not isinstance(description, str):
            raise ValueError("Le JSON retourné ne contient pas de champ 'titre' et 'description' valides.")

        return {"titre": titre.strip(), "description": description.strip()}
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Échec du parsing JSON de la réponse Gemini : {exc}") from exc
    except ValueError as exc:
        raise RuntimeError(f"Erreur de contenu : {exc}") from exc
    except Exception as exc:
        raise RuntimeError(f"Échec de la génération du titre et de la description : {exc}") from exc
