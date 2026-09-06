/* =========================================================
   API CONFIGURATION
   ========================================================= */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const API_ENDPOINTS = {
  session: "/session",
  chat: "/chat",
  tts: "/api/tts", // frontend fallback to window.speechSynthesis
  health: "/health",
};

export { API_BASE_URL, API_ENDPOINTS };
