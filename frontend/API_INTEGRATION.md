# AyurLex Frontend API Integration Guide

## Overview

This document describes the API endpoints that the frontend expects from the backend. The frontend has been updated to call these endpoints and falls back to demo data if the API is unavailable.

## Configuration

The API base URL is configured in `src/api/config.js`:

```javascript
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
```

You can override this by setting the `VITE_API_BASE_URL` environment variable.

## API Endpoints

### 1. Health Check

**Endpoint:** `GET /api/health`

**Response:**
```json
{
  "status": "ok",
  "version": "1.0.0"
}
```

---

### 2. Generate Research

**Endpoint:** `POST /api/research`

**Request Body:**
```json
{
  "classification": "CLASSICAL / GENERIC MEDICINE",
  "jurisdiction": "India",
  "language": "English",
  "answers": {
    "classification_1": "No",
    "classification_2": "No",
    "classification_3": "Yes",
    "followup_1": "Ashwagandha, Brahmi, Shatavari",
    "followup_2": "Tablet",
    "followup_3": "Wellness, stress relief",
    "followup_4": "India only",
    "followup_5": "Yes"
  }
}
```

**Response:**
```json
{
  "summary": "Based on the information provided...",
  "findings": [
    "The formulation should be compared...",
    "The ingredients, dosage form..."
  ],
  "references": [
    {
      "title": "Drugs and Cosmetics Act, 1940",
      "section": "Section 3(a) — Ayurvedic, Siddha or Unani drug",
      "description": "Statutory definitions relevant to...",
      "url": "https://cdsco.gov.in/opencms/opencms/en/Acts-and-rules/"
    }
  ]
}
```

**Frontend Fallback:** If the API call fails, the frontend uses a hardcoded demo response.

---

### 3. Follow-Up Chat (Streaming)

**Endpoint:** `POST /api/chat`

**Request Body:**
```json
{
  "question": "What licences are needed?",
  "classification": "CLASSICAL / GENERIC MEDICINE",
  "jurisdiction": "India",
  "language": "English",
  "context": [
    { "role": "user", "content": "What licences are needed?" }
  ]
}
```

**Response:** Streaming text (chunked transfer encoding)

The response should be a stream of text chunks. The frontend will concatenate them to form the complete response.

**Frontend Fallback:** If the API call fails, the frontend uses a keyword-matched demo response.

---

### 4. Text-to-Speech (Bhashini)

**Endpoint:** `POST /api/tts`

**Request Body:**
```json
{
  "text": "Namaste. Before I begin the legal research...",
  "language": "hi-IN"
}
```

**Response:** Audio blob (binary data)

The response should be an audio file (e.g., WAV, MP3) that the frontend can play directly.

**Frontend Fallback:** If the API call fails, the frontend uses the browser's built-in `speechSynthesis` API.

---

## Error Handling

The frontend handles API errors gracefully:

1. **Network errors:** Falls back to demo data
2. **4xx/5xx responses:** Falls back to demo data
3. **Streaming errors:** Uses whatever text was received before the error

All errors are logged to the console with `console.warn()`.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_BASE_URL` | `http://localhost:8000` | Base URL for the API server |

---

## Frontend Files

| File | Description |
|------|-------------|
| `src/api/config.js` | API configuration (base URL, endpoints) |
| `src/api/client.js` | API client with all methods |
| `src/api/index.js` | Module exports |
| `src/App.jsx` | Updated to use API client |
| `src/components/FormulationFlow.jsx` | Updated to use API client |

---

## Testing the Integration

1. Start the backend server on `http://localhost:8000`
2. Start the frontend dev server: `npm run dev`
3. The frontend will automatically try to connect to the backend
4. Check the browser console for API call logs

If the backend is not running, the frontend will use demo data and display a warning in the console.
