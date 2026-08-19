# AI Clinical Decision Support Lite — Day 3

> **Educational prototype only.** This system is not a diagnostic tool, prescription engine, emergency triage service, or replacement for qualified clinical judgment.

Day 3 continues the Day-2 retrieval baseline for **Adult Hypertension** and adds controlled grounded generation, Top-1 evidence policy, structured responses, explicit refusal, authentication, per-user persistent chat history, voice input, polished structured UI, and stronger security.

## Day 3 architecture

```text
User (Text / Voice)
        |
        v
Authentication + User Session
        |
        v
Question Validation
        |
        v
Day-2 Hybrid Retrieval
        |
        v
Top-1 Evidence Gate
        |---- weak/insufficient ---> Insufficient Evidence
        v
Strict Grounded Prompt
        |
        v
Groq LLM → Structured JSON
        |
        v
Citation / Schema Validation
        |
        v
User Answer + Source
        |
        v
User-scoped Persistent History
```

## Implemented requirements

### UI
- Day-2 visual design preserved and improved.
- Register and Login pages.
- Email/password authentication.
- Optional Google OAuth.
- Welcome message with authenticated user name.
- Server-side per-user chat history.
- Same user can logout/login and recover history.
- User A cannot access User B's conversations.
- Structured answer rendering; raw Markdown is not exposed.
- Source cards show document, section and page only.
- Similarity, chunk IDs, ranks and internal retrieval details are hidden.
- Top-1 evidence is used for normal generation.
- Voice input through browser Speech Recognition where supported.
- Message entrance/loading/recording animations.
- `prefers-reduced-motion` support.

### Generation / RAG
- Strict system prompt.
- Retrieved text treated as untrusted evidence.
- No outside medical knowledge.
- No invented citations/pages.
- Structured JSON output.
- `answered`, `insufficient_evidence`, and `safety_refusal`.
- Top-1 confidence/scope gate.
- Citation binding to the retrieved document/section/page.

### Security
- Passwords hashed using `scrypt`.
- HttpOnly/SameSite session cookie.
- Session invalidation on logout.
- Server-side authorization on every history operation.
- OAuth state validation.
- Request length and Top-K bounds.
- Existing Day-2 rate limiting and security headers retained.
- Prompt-injection boundary.
- Voice input never bypasses the normal question pipeline.

## Project structure

```text
AI_Clinical_Decision_Support_Day3/
├── README.md
├── SETUP.md
├── clinical_scope.md
├── requirements.txt
├── .env.example
├── data/
├── docs/
├── outputs/
├── src/
│   ├── config.py
│   ├── ingestion.py
│   ├── vector_store.py
│   ├── evaluation.py
│   ├── llm.py
│   ├── main.py
│   └── web.py
├── tests/
└── web/
    ├── index.html
    ├── app.js
    └── styles.css
```

## Windows PowerShell setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set at minimum:

```env
GROQ_API_KEY=YOUR_GROQ_KEY
GROQ_MODEL=llama-3.3-70b-versatile
TOP1_MIN_SIMILARITY=0.35
```

Optional Google OAuth:

```env
GOOGLE_CLIENT_ID=YOUR_CLIENT_ID
GOOGLE_CLIENT_SECRET=YOUR_CLIENT_SECRET
GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/api/auth/google/callback
COOKIE_SECURE=0
```

## Build the retrieval indexes

```powershell
python -m src.main index-day2
```

## Start the application

```powershell
python -m uvicorn src.web:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

The first screen is Login/Register.

## Tests

```powershell
python -m pytest -q
```

## Important demo checks

1. Register User A and ask a question.
2. Logout.
3. Register/Login User B.
4. Confirm User A history is not visible.
5. Logout and login User A again.
6. Confirm User A history returns.
7. Ask a question by voice.
8. Confirm only the clean source information is shown.
9. Test a question outside the evidence scope and demonstrate refusal.

## Google OAuth

Google login is optional and only works after the OAuth credentials and callback URL are configured in Google Cloud. Without those variables, the button safely reports that Google sign-in is not configured.

## Notes

The SQLite account/history database is created locally at:

```text
data/day3_users.sqlite3
```

Do not commit it to Git. Add it to `.gitignore`.

The vector database remains a local generated artifact. The approved NICE documents remain the project's evidence boundary.

## Day 3 final UX and safety controls

### Authentication
Google sign-in uses the standard OAuth authorization-code flow. Configure the exact callback URI in Google Cloud:
`http://127.0.0.1:8000/api/auth/google/callback`
(or use the exact host/URI configured in `GOOGLE_REDIRECT_URI`). The Google OAuth client must have the redirect URI registered and the account must be allowed by the OAuth consent-screen configuration. If Google returns a provider-side 403/Forbidden, verify those Google Cloud settings; this cannot be fixed purely by frontend code.

### Scope and privacy boundary
The assistant refuses questions requesting database technology, encryption details, credentials, internal architecture, stored sensitive/private data, or other protected implementation information. It also refuses clearly out-of-scope topics and redirects the user to Adult Hypertension evidence questions.

### Clarification
Short or ambiguous questions can return `clarification_needed`. The UI asks the user to clarify before evidence retrieval rather than guessing intent.

### Tables
The generation contract includes an optional structured `table` object. When the evidence supports a comparison or tabular answer, the frontend renders a real HTML table instead of exposing Markdown.

### Sources
Every answered message stores source details bound to that user's conversation. Clicking a source opens the exact evidence excerpt and can open the approved source PDF. Authorization is enforced server-side.

### Feedback and reply
Assistant messages support Helpful / Not helpful feedback, Reply-to-answer, and Copy. Feedback is persisted per user/message.

### Storage
Each user has a configurable server-side storage quota (`USER_STORAGE_LIMIT_BYTES`, default 2 MB). Settings displays usage and warnings at 80% and 100%. When full, the user is directed to Manage storage and can delete their own chat history.

### Appearance
Light, Dark, and System modes are available from Settings and persist in the browser.


### Day 3 usage limits
- Per-user chat storage quota: 2 MB by default (`USER_STORAGE_LIMIT_BYTES=2097152`).
- Daily question quota: 10 questions per user per day (`DAILY_QUESTION_LIMIT=10`). The counter resets automatically on the next calendar day.
- The quota is enforced server-side before retrieval, not only in the browser.
- When the daily quota is exhausted, the UI disables the send action and shows a clear reset-tomorrow message.
