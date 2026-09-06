/* =========================================================
   API CLIENT
   ========================================================= */

import { API_BASE_URL, API_ENDPOINTS } from "./config";

/* =========================================================
   HELPER: FETCH WITH ERROR HANDLING
   ========================================================= */

async function apiFetch(endpoint, options = {}) {
  const url = `${API_BASE_URL}${endpoint}`;

  try {
    const response = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...options.headers,
      },
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(
        errorData.message || errorData.detail || `API error: ${response.status} ${response.statusText}`
      );
    }

    return response;
  } catch (error) {
    console.error(`API call failed: ${endpoint}`, error);
    throw error;
  }
}

/* =========================================================
   SESSION GENERATION
   ========================================================= */

/**
 * Creates a new session on the backend.
 * @param {string} jurisdictionMode - "national", "international", or "both"
 * @param {string} language - The selected output language (e.g., "English", "Hindi")
 * @returns {Promise<string>} The session ID
 */
export async function createSession(jurisdictionMode = "national", language = "English") {
  const response = await apiFetch(API_ENDPOINTS.session, {
    method: "POST",
    body: JSON.stringify({
      jurisdiction_mode: jurisdictionMode,
      language: language
    }),
  });
  const data = await response.json();
  return data.session_id;
}

/* =========================================================
   CHAT REQUEST
   ========================================================= */

/**
 * Sends a message to the backend chat endpoint.
 *
 * @param {string} sessionId - The session ID
 * @param {string} message - The user's query or clarification answer
 * @param {string} jurisdictionMode - "national", "international", or "both"
 * @returns {Promise<Object>} The chat response
 */
export async function sendChatMessage(sessionId, message, jurisdictionMode, language) {
  const response = await apiFetch(API_ENDPOINTS.chat, {
    method: "POST",
    body: JSON.stringify({
      session_id: sessionId,
      message,
      jurisdiction_mode: jurisdictionMode,
      language: language
    }),
  });
  
  return response.json();
}

/* =========================================================
   TEXT-TO-SPEECH (BHASHINI)
   ========================================================= */

/**
 * Convert text to speech using Bhashini API.
 *
 * @param {Object} data - The TTS request data
 * @param {string} data.text - The text to convert
 * @param {string} data.language - The language code (e.g., "hi-IN", "en-IN")
 * @returns {Promise<Blob>} Audio blob
 */
export async function textToSpeech(data) {
  const response = await apiFetch(API_ENDPOINTS.tts, {
    method: "POST",
    body: JSON.stringify(data),
  });

  return response.blob();
}

/* =========================================================
   HEALTH CHECK
   ========================================================= */

/**
 * Check if the API server is running.
 *
 * @returns {Promise<Object>} Health status
 */
export async function checkHealth() {
  const response = await apiFetch(API_ENDPOINTS.health);
  return response.json();
}

/* =========================================================
   GENERIC GET
   ========================================================= */

/**
 * Generic GET request
 * @param {string} endpoint - The endpoint to fetch
 * @returns {Promise<Object>} JSON response
 */
export async function get(endpoint) {
  const response = await apiFetch(endpoint, {
    method: "GET"
  });
  return response.json();
}

/* =========================================================
   EXPORTS
   ========================================================= */

export default {
  createSession,
  sendChatMessage,
  textToSpeech,
  checkHealth,
  get,
};
