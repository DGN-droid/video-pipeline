const MAX_FILE_SIZE = 40 * 1024 * 1024;
const ALLOWED_EXTENSIONS = [".mp4", ".mov", ".avi", ".mkv", ".webm"];

const dropZone = document.getElementById("drop-zone");
const fileInput = document.getElementById("file-input");
const chooseButton = document.getElementById("choose-button");
const errorMessage = document.getElementById("error-message");
const statusPanel = document.getElementById("status-panel");
const currentStatus = document.getElementById("current-status");
const loader = document.getElementById("loader");
const progressMessage = document.getElementById("progress-message");
const retryActions = document.getElementById("retry-actions");
const retryButton = document.getElementById("retry-button");
const resultPanel = document.getElementById("result-panel");
const titleInput = document.getElementById("title-input");
const descriptionInput = document.getElementById("description-input");
const videoPlayer = document.getElementById("video-player");
const downloadSrtButton = document.getElementById("download-srt");
const copyTextButton = document.getElementById("copy-text");
const burnButton = document.getElementById("burn-button");
const burnDownloadLink = document.getElementById("burn-download-link");

let currentVideoId = null;
let currentVideoFile = null;
let currentVideoFileUrl = null;
let currentSrtContent = null;
let currentSrtTrackUrl = null;
let pollingTimer = null;

const revokeVideoFileUrl = () => {
  if (currentVideoFileUrl) {
    URL.revokeObjectURL(currentVideoFileUrl);
    currentVideoFileUrl = null;
  }
};

const revokeSrtTrackUrl = () => {
  if (currentSrtTrackUrl) {
    URL.revokeObjectURL(currentSrtTrackUrl);
    currentSrtTrackUrl = null;
  }
};

const showError = (message) => {
  errorMessage.textContent = message;
  errorMessage.classList.remove("hidden");
};

const clearError = () => {
  errorMessage.textContent = "";
  errorMessage.classList.add("hidden");
};

const toggleLoader = (visible) => {
  if (visible) loader.classList.remove("hidden");
  else loader.classList.add("hidden");
};

const setStatus = (statusText) => {
  currentStatus.textContent = statusText;
};

const showStatusPanel = () => {
  statusPanel.classList.remove("hidden");
};

const showResultPanel = () => {
  resultPanel.classList.remove("hidden");
};

const resetUI = () => {
  statusPanel.classList.add("hidden");
  resultPanel.classList.add("hidden");
  retryActions.classList.add("hidden");
  toggleLoader(false);
  clearError();
  revokeSrtTrackUrl();
};

const isValidVideoFile = (file) => {
  const extension = file.name.slice(file.name.lastIndexOf('.')).toLowerCase();
  return ALLOWED_EXTENSIONS.includes(extension);
};

const validateFile = (file) => {
  if (!isValidVideoFile(file)) {
    throw new Error("Format non pris en charge. Utilisez mp4, mov, avi, mkv ou webm.");
  }
  if (file.size > MAX_FILE_SIZE) {
    throw new Error("Le fichier dépasse la limite de 40 Mo.");
  }
};

const requestUploadUrl = async (file) => {
  const response = await fetch("/api/create-upload-url", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename: file.name, content_type: file.type || "application/octet-stream" }),
  });

  if (!response.ok) {
    const { detail, error } = await response.json().catch(() => ({}));
    throw new Error(detail || error || "Impossible de créer l'URL d'upload.");
  }

  return response.json();
};

const uploadFile = async (file) => {
  const uploadInfo = await requestUploadUrl(file);
  const headers = uploadInfo.headers || {};
  headers["Content-Type"] = file.type || "application/octet-stream";

  const uploadResponse = await fetch(uploadInfo.upload_url, {
    method: "PUT",
    body: file,
    headers,
  });

  if (!uploadResponse.ok) {
    throw new Error(`Erreur lors de l'upload direct vers Supabase (${uploadResponse.status}).`);
  }

  return uploadInfo;
};

const processVideo = async (videoId, storagePath) => {
  const response = await fetch("/api/process", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ video_id: videoId, storage_path: storagePath }),
  });

  if (!response.ok) {
    const { detail, error } = await response.json().catch(() => ({}));
    throw new Error(detail || error || "Échec du traitement.");
  }

  return response.json();
};

const fetchStatus = async (videoId) => {
  const response = await fetch(`/api/status?video_id=${encodeURIComponent(videoId)}`);
  if (!response.ok) {
    const { detail, error } = await response.json().catch(() => ({}));
    throw new Error(detail || error || "Échec de la vérification du statut.");
  }
  return response.json();
};

const createSrtBlobUrl = (srtText) => {
  revokeSrtTrackUrl();
  const vttText = srtText
    .replace(/(\d{2}:\d{2}:\d{2}),(\d{3})/g, "$1.$2")
    .replace(/^(\d+)$/gm, "")
    .trim();

  const formatted = `WEBVTT\n\n${vttText}`;
  const blob = new Blob([formatted], { type: "text/vtt" });
  currentSrtTrackUrl = URL.createObjectURL(blob);
  return currentSrtTrackUrl;
};

const downloadSrt = () => {
  if (!currentSrtContent) return;
  const blob = new Blob([currentSrtContent], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `transcription-${currentVideoId}.srt`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
};

const copyText = async () => {
  const text = `Titre : ${titleInput.value}\n\nDescription : ${descriptionInput.value}`;
  await navigator.clipboard.writeText(text);
  copyTextButton.textContent = "Copié !";
  setTimeout(() => {
    copyTextButton.textContent = "Copier titre + description";
  }, 2000);
};

const displayResult = (data) => {
  titleInput.value = data.titre || "";
  descriptionInput.value = data.description || "";
  currentSrtContent = data.srt_content || "";
  currentVideoId = data.video_id;

  if (currentVideoFileUrl) {
    videoPlayer.src = currentVideoFileUrl;
  }

  const trackUrl = createSrtBlobUrl(currentSrtContent);
  videoPlayer.innerHTML = ` <track kind="subtitles" label="Français" srclang="fr" src="${trackUrl}" default>`;
  videoPlayer.load();

  resultPanel.classList.remove("hidden");
};

const pollStatus = async (videoId) => {
  setStatus("Traitement en cours");
  toggleLoader(true);
  showStatusPanel();
  retryActions.classList.add("hidden");
  progressMessage.textContent = "Le traitement est en cours. Cela peut prendre un moment...";

  const poll = async () => {
    try {
      const status = await fetchStatus(videoId);
      if (status.status === "done") {
        clearInterval(pollingTimer);
        setStatus("Terminé");
        toggleLoader(false);
        progressMessage.textContent = "Le traitement est terminé. Voici le résultat :";
        displayResult(status);
      } else if (status.status === "error") {
        clearInterval(pollingTimer);
        setStatus("Erreur");
        toggleLoader(false);
        progressMessage.textContent = "Une erreur est survenue pendant le traitement.";
        retryActions.classList.remove("hidden");
        showError(status.error || "Erreur inconnue.");
      } else {
        setStatus(`En cours (${status.status})`);
      }
    } catch (error) {
      clearInterval(pollingTimer);
      toggleLoader(false);
      setStatus("Erreur");
      retryActions.classList.remove("hidden");
      showError(error.message);
    }
  };

  await poll();
  pollingTimer = setInterval(poll, 3000);
};

const handleFileUpload = async (file) => {
  revokeVideoFileUrl();
  resetUI();
  try {
    validateFile(file);
    clearError();
    showStatusPanel();
    toggleLoader(true);
    setStatus("Upload en cours");
    progressMessage.textContent = "Envoi de la vidéo vers le serveur...";

    currentVideoFile = file;
    currentVideoFileUrl = URL.createObjectURL(file);
    videoPlayer.src = currentVideoFileUrl;
    videoPlayer.load();

    const uploadInfo = await uploadFile(file);
    currentVideoId = uploadInfo.video_id;
    setStatus("Upload terminé");
    progressMessage.textContent = "Début du traitement automatique...";

    await processVideo(uploadInfo.video_id, uploadInfo.storage_path);
    await pollStatus(uploadInfo.video_id);
  } catch (error) {
    toggleLoader(false);
    setStatus("Erreur");
    progressMessage.textContent = "Le traitement n'a pas pu démarrer.";
    showError(error.message || "Une erreur est survenue pendant l'upload ou le traitement.");
    retryActions.classList.remove("hidden");
  }
};

chooseButton.addEventListener("click", (event) => {
  event.stopPropagation();
  fileInput.click();
});
fileInput.addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (file) await handleFileUpload(file);
});

dropZone.addEventListener("click", () => fileInput.click());

dropZone.addEventListener("dragover", (event) => {
  event.preventDefault();
  dropZone.classList.add("drag-over");
});

dropZone.addEventListener("dragleave", (event) => {
  event.preventDefault();
  dropZone.classList.remove("drag-over");
});

dropZone.addEventListener("drop", async (event) => {
  event.preventDefault();
  dropZone.classList.remove("drag-over");
  const file = event.dataTransfer.files[0];
  if (file) await handleFileUpload(file);
});

retryButton.addEventListener("click", async () => {
  clearError();
  if (!currentVideoId) return;
  await pollStatus(currentVideoId);
});

downloadSrtButton.addEventListener("click", downloadSrt);
copyTextButton.addEventListener("click", copyText);
if (burnButton) {
  burnButton.addEventListener("click", async () => {
    if (!currentVideoId) return showError("Aucune vidéo à traiter.");
    burnButton.disabled = true;
    const originalText = burnButton.textContent;
    burnButton.textContent = "Génération en cours... (peut prendre 1-2 minutes)";
    clearError();

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5 * 60 * 1000); // 5 minutes

    try {
      const resp = await fetch("/api/burn-subtitles", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ video_id: currentVideoId }),
        signal: controller.signal,
      });
      clearTimeout(timeout);
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.detail || err.error || "Échec du rendu vidéo.");
      }

      const data = await resp.json();
      if (data.status === "done" && data.download_url) {
        burnDownloadLink.href = data.download_url;
        burnDownloadLink.classList.remove("hidden");
        burnDownloadLink.setAttribute('download', 'video-burned.mp4');
      } else {
        throw new Error(data.error || "Erreur inconnue pendant le rendu.");
      }
    } catch (err) {
      if (err.name === 'AbortError') {
        showError('Le rendu a expiré (timeout). Réessayez plus tard.');
      } else {
        showError(err.message || 'Erreur lors de la génération.');
      }
    } finally {
      burnButton.disabled = false;
      burnButton.textContent = originalText;
    }
  });
}
