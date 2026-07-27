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

let currentVideoId = null;
let currentVideoFile = null;
let currentVideoFileUrl = null;
let currentSrtContent = null;
let pollingTimer = null;

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

const uploadFile = async (file) => {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch("/api/upload", {
    method: "POST",
    body: formData,
  });

  if (!response.ok) {
    const { error } = await response.json().catch(() => ({}));
    throw new Error(error || "Échec de l'upload.");
  }

  const data = await response.json();
  return data.video_id;
};

const processVideo = async (videoId) => {
  const response = await fetch("/api/process", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ video_id: videoId }),
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
  const vttText = srtText
    .replace(/(\d{2}:\d{2}:\d{2}),(\d{3})/g, "$1.$2")
    .replace(/^(\d+)$/gm, "")
    .trim();

  const formatted = `WEBVTT\n\n${vttText}`;
  const blob = new Blob([formatted], { type: "text/vtt" });
  return URL.createObjectURL(blob);
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
  resetUI();
  try {
    validateFile(file);
    clearError();
    showStatusPanel();
    toggleLoader(true);
    setStatus("Upload en cours");
    progressMessage.textContent = "Envoi de la vidéo vers le serveur...";

    const videoId = await uploadFile(file);
    currentVideoId = videoId;
    setStatus("Upload terminé");
    progressMessage.textContent = "Début du traitement automatique...";

    await processVideo(videoId);
    await pollStatus(videoId);
  } catch (error) {
    toggleLoader(false);
    setStatus("Erreur");
    progressMessage.textContent = "Le traitement n'a pas pu démarrer.";
    showError(error.message);
    retryActions.classList.remove("hidden");
  }
};

chooseButton.addEventListener("click", () => fileInput.click());
fileInput.addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (file) await handleFileUpload(file);
});

dropZone.addEventListener("dragover", (event) => {
  event.preventDefault();
  dropZone.classList.add("drag-over");
});

dropZone.addEventListener("dragleave", () => dropZone.classList.remove("drag-over"));

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
