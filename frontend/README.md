# IP-SHAKTI frontend

Files:
- App.jsx — auth/signup/login, email verification, account/profile page, settings, legal/info routes, 404/403, footer, consent banner.
- research.jsx — research dashboard rebuilt from the supplied app, including quick starters, language/jurisdiction, chat, research result, citations, PDF hook, evaluation hook, TTS, loading and evidence-gap states.
- index.css — small global layer.

Dependencies:
npm i react-router-dom framer-motion lucide-react

Tailwind:
Use the Tailwind setup already present in your project. These files use utility classes directly.

Backend integration points:
1. Signup/login/forgot-password/verification
2. /api/pdf/:documentId in research.jsx
3. Research `send()` mock block in research.jsx
4. EvalDashboard route/button
5. Server-side consent, sessions, authorization, deletion, analytics and security

The partner logos are also present under public/logos. The JSX currently references live image URLs with a fallback text mark.
