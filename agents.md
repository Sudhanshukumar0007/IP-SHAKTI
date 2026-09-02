# IP-SHAKTI Agent Guidelines

Welcome, AI Agent! You are working on the IP-SHAKTI (IP Sahayak) platform.
When working on this repository, please adhere strictly to the following workflow rules:

## 1. Review Planning Documents First
Before implementing any feature, adding a new technology, or modifying the architecture, you MUST review the documents in the `planning/` directory.
- `planning/ip-sakti-tech-stack.md`: Outlines the specific tools and frameworks (e.g. FastAPI, LangGraph, ChromaDB) permitted in this project. Do not deviate from these unless explicitly instructed by the user.
- Review architecture diagrams (`planning/IP_SHAKTI_FULL_ARCHITECTURE.png`) for context on the data layer and ingestion pipelines.
- Ensure the `Corpus` structure aligns with `corpus_structure.md`.

## 2. Worklog Requirement
After completing any significant implementation task, deployment, or structural change, you MUST create a log entry in the `worklog/` directory.
- Filename format: `YYYY-MM-DD_short_description.md`
- Include:
  - What was accomplished
  - Any architectural decisions made
  - Any issues encountered or workarounds implemented

## 3. Tech Stack Consistency
We are running a dockerized environment for both frontend (Nginx/HTML/CSS/JS) and backend (FastAPI/LangGraph). When installing new Python packages, update `backend/requirements.txt` and ensure `docker-compose.yml` configurations remain intact.
