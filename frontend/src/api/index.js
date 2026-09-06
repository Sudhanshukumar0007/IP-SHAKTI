/* =========================================================
   API MODULE
   ========================================================= */

export { default as api } from "./client";
export {
  createSession,
  sendChatMessage,
  textToSpeech,
  checkHealth,
  get,
} from "./client";
export { API_BASE_URL, API_ENDPOINTS } from "./config";
