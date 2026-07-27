# API Vercel Python - Upload, Process et Status

Ce document décrit les trois endpoints Python disponibles dans le projet pour gérer l’upload, le traitement et le statut des vidéos.

## Base URL

Si le projet est déployé sur Vercel, les endpoints sont accessibles via :

- https://<votre-domaine>.vercel.app/api/upload
- https://<votre-domaine>.vercel.app/api/process
- https://<votre-domaine>.vercel.app/api/status

---

## 1) Upload - POST /api/upload

### Description
Permet d’envoyer une vidéo au backend pour démarrer l’upload vers Supabase Storage.

### Méthode HTTP
- POST

### Paramètres attendus
Le corps doit être envoyé en multipart/form-data avec un champ nommé `file`.

#### Champs requis
- `file`: fichier vidéo à uploader

#### Restrictions
- Formats autorisés : `.mp4`, `.mov`, `.avi`, `.mkv`, `.webm`
- Taille maximale : 40 Mo

### Exemple de requête
Form-data :
- file = [fichier vidéo]

### Réponse réussie
Code HTTP : `200`

```json
{
  "video_id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "uploaded"
}
```

### Erreurs possibles
- `400 Bad Request`
  - fichier manquant
  - type de fichier non pris en charge
  - fichier trop volumineux
  - corps de requête invalide
- `405 Method Not Allowed`
  - méthode différente de `POST`
- `429 Too Many Requests`
  - trop d’uploads depuis la même IP dans l’heure
- `500 Internal Server Error`
  - erreur d’upload ou problème serveur

---

## 2) Process - POST /api/process

### Description
Démarre le traitement d’une vidéo déjà uploadée : transcription, génération de sous-titres SRT, génération du titre et de la description.

### Méthode HTTP
- POST

### Paramètres attendus
Le backend accepte soit un body JSON, soit un paramètre `video_id` dans la query string.

#### Champs requis
- `video_id`: identifiant unique de la vidéo

### Exemple de requête
```json
{
  "video_id": "123e4567-e89b-12d3-a456-426614174000"
}
```

### Réponse réussie
Code HTTP : `200`

```json
{
  "video_id": "123e4567-e89b-12d3-a456-426614174000",
  "titre": "Titre généré",
  "description": "Description générée à partir de la transcription.",
  "srt_content": "1\n00:00:00,000 --> 00:00:05,000\nBonjour",
  "transcription": "Bonjour, ceci est une transcription.",
  "status": "done"
}
```

### Erreurs possibles
- `400 Bad Request`
  - `video_id` manquant ou invalide
- `500 Internal Server Error`
  - erreur de transcription
  - erreur Gemini
  - problème de téléchargement ou de stockage

---

## 3) Status - GET /api/status

### Description
Permet de vérifier l’état d’une vidéo après upload ou traitement.

### Méthode HTTP
- GET

### Paramètres attendus
Le `video_id` doit être fourni en query string.

#### Paramètre requis
- `video_id`: identifiant unique de la vidéo

### Exemple de requête
```text
GET /api/status?video_id=123e4567-e89b-12d3-a456-426614174000
```

### Réponse réussie
Code HTTP : `200`

#### Si la vidéo est en cours de traitement ou uploadée
```json
{
  "video_id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "uploaded"
}
```

#### Si le traitement est terminé
```json
{
  "video_id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "done",
  "titre": "Titre généré",
  "description": "Description générée",
  "srt_content": "1\n00:00:00,000 --> 00:00:05,000\nBonjour",
  "transcription": "Bonjour, ceci est une transcription."
}
```

### Erreurs possibles
- `400 Bad Request`
  - `video_id` manquant
- `404 Not Found`
  - aucun enregistrement trouvé pour ce `video_id`
- `500 Internal Server Error`
  - erreur lors de la lecture dans la base

---

## Notes importantes pour le frontend

- Après un upload réussi, le frontend doit récupérer le `video_id` renvoyé et l’utiliser pour appeler l’endpoint de traitement.
- Le statut peut être vérifié régulièrement via `/api/status` jusqu’à ce que `status` devienne `done`.
- Si un traitement échoue, le statut sera `error` et un message d’erreur sera renvoyé dans la réponse ou stocké dans la base.
