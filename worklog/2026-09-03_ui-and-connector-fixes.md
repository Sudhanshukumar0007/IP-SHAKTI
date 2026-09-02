# UI and Connector Fixes (2026-09-03)

## Accomplishments
- **UI Bug Fix (Answer Rendering)**: Fixed `frontend/pages/1_Chat.py` to correctly parse and render the structured JSON assessment returned by the Groq generator. Previously, the UI was expecting a single "answer" key which caused it to display "No answer provided" despite the backend working properly.
- **Formulation Classification UI**: Ripped out the confusing, hardcoded dummy classification questions from the frontend sidebar. The backend LLM agent naturally handles classification clarification inside the chat anyway.
- **Jurisdiction Settings**: Replaced the old sidebar with a functional "Agent Settings" sidebar that allows the user to explicitly select Jurisdiction Mode (`national`, `international`, or `both`) before executing a query.
- **Live Connector Tweaks**: Broadened the DuckDuckGo live search query in `backend/services/connector.py` (`"{query} patent registry India WIPO"`) and removed the overly strict URL filter that was causing 0 results. It now filters based on URL strings *after* the broader search to ensure we actually pull live evidence.
- **PDF Page Navigation**: Updated the embedded PDF viewer URL in `frontend/pages/1_Chat.py` to include `#page={page_start}` so that clicking "Embed Viewer" jumps exactly to the referenced section rather than relying on PDF.js's finicky text search.
- **Evaluation Dashboard Fix**: Corrected a typo in the SQLite database path inside `frontend/pages/2_Evaluation.py` (added missing `..`) so that the Query Evaluation Dashboard properly reads and displays metrics from the backend log.
- **UI "Thinking" Animation**: Swapped the static `st.spinner` with an expanding/updating `st.status` block in `1_Chat.py` to give visual feedback that the agent pipeline is initializing and working before it streams the final answer.

## Known Issues / Next Steps
- There is an unspecified error that the user encountered which we will investigate and resolve in a future session.
- Consider implementing full SSE streaming from LangGraph to FastAPI to Streamlit for real-time node-by-node updates in the UI.
