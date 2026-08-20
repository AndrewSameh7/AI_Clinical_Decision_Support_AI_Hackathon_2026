# AI Clinical Decision Support Lite — Day 4

> **Educational prototype only.** This system is not a diagnostic tool, prescription engine, emergency triage service, or replacement for qualified clinical judgment.

Day 4 continues the Day-3 Adult Hypertension RAG system and adds a measurable safety and internal-evaluation layer.

## Clinical scope

- **Domain:** Adult Hypertension
- **Approved sources:** NICE NG136 + NICE patient decision aid
- **Retrieval:** Day-2 hybrid retrieval, B_850_150 configuration, optional reranking
- **Generation:** Groq with a strict evidence-grounding contract
- **User-facing evidence:** top-1 retrieved evidence remains the generation context

## What Day 4 adds

### 1. Pre-generation risk classification

The system classifies queries before retrieval/generation:

- In-scope clinical evidence question → retrieve
- Ambiguous question → clarify
- Patient-specific request → safety refusal
- Diagnosis request → safety refusal
- Medication/dosage request → safety refusal
- Emergency-like request → redirect to professional/emergency care
- Out-of-scope request → scope refusal
- Prompt-injection/adversarial request → reject and remain grounded

### 2. Retrieval confidence gate

Generation is not forced when the best evidence falls below `TOP1_MIN_SIMILARITY`.
The system returns an explicit insufficient-evidence response instead of guessing.

### 3. Post-generation evidence validation

Day 4 adds a lightweight claim-support checker. Generated claims are compared with the supplied evidence. Unsupported claims are removed when supported claims remain; if no meaningful claim is supported, the answer falls back to insufficient evidence.

The implementation is intentionally conservative and explainable. Manual review remains necessary for semantic citation correctness.

### 4. Partial-answer policy

A multi-part question does **not** automatically fail because one part is unsupported.

If the evidence supports only part of a question:

1. Answer the supported part.
2. Do not invent the missing part.
3. Tell the user which information could not be established from the approved evidence.

### 5. User storage

Each user has a **hard maximum of 2 MB** of local chat-history storage.

There is **no daily question limit**.

Users can inspect storage usage in Settings and clear their own history when needed.

### 6. Dark-mode source readability

Source-detail modal text, evidence excerpts, links, notes, tables and partial-answer notices have explicit dark-mode colors so they remain readable.

## Day-4 evaluation set

`data/day4_evaluation_questions.json` contains **35 new test cases** covering:

- direct evidence questions
- patient decision-aid questions
- multi-part / partial-answer cases
- ambiguous questions
- patient-specific safety refusals
- dosage refusals
- out-of-scope questions
- privacy-boundary questions
- prompt-injection attempts

The set stores expected behavior plus expected document/section/page information where applicable.

## Day-4 metrics

Run:

```powershell
python -m src.main evaluate-day4
```

The command produces:

`outputs/day4_evaluation_report.json`

The report includes:

- retrieval Precision@5 proxy
- retrieval hit rate
- input-risk classification accuracy
- optional citation validity / coverage / faithfulness / unsupported-claim metrics when `outputs/day4_answer_review.json` is supplied

## Setup

### 1. Create a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 3. Configure environment variables

```powershell
Copy-Item .env.example .env
```

Add the real Groq key to `.env`.

For Google login, configure:

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REDIRECT_URI`

The local callback is:

`http://127.0.0.1:8000/api/auth/google/callback`

### 4. Build the Day-2 retrieval indexes

```powershell
python -m src.main index-day2
```

### 5. Run tests

```powershell
python -m pytest -q
```

### 6. Run the Day-4 evaluation

```powershell
python -m src.main evaluate-day4
```

### 7. Start the web application

```powershell
python -m uvicorn src.web:app --reload
```

Open:

`http://127.0.0.1:8000`

## Architecture

```text
User Query
   ↓
Input Risk Classification
   ↓
Clarify / Refuse / Continue
   ↓
Day-2 Hybrid Retrieval
   ↓
Top-1 Evidence Threshold
   ↓
Grounded Generation
   ↓
Claim Support Validation
   ↓
Citation / Safety Validation
   ↓
Final UX Response
   ↓
Authenticated User History
```

## Repository structure

```text
AI_Clinical_Decision_Support_Day3/
├── README.md
├── SETUP.md
├── clinical_scope.md
├── requirements.txt
├── .env.example
├── data/
│   ├── hypertension_nice_ng136.pdf
│   ├── hypertension_patient_decision_aid.pdf
│   ├── clinical_test_questions.json
│   └── day4_evaluation_questions.json
├── docs/
│   └── DAY3_CODE_DOCUMENTATION.md
├── outputs/
├── src/
│   ├── config.py
│   ├── ingestion.py
│   ├── vector_store.py
│   ├── evaluation.py
│   ├── day4_safety.py
│   ├── llm.py
│   ├── main.py
│   └── web.py
├── tests/
└── web/
    ├── index.html
    ├── app.js
    └── styles.css
```

## Security principles

- Secrets are environment variables.
- Retrieval is restricted to approved document IDs.
- Browser-supplied evidence is never treated as authoritative generation context.
- Retrieved text is treated as untrusted data and prompt-injection instructions inside it are ignored.
- Authentication isolates user histories server-side.
- Security headers and request validation remain enabled.
- Sensitive infrastructure information is not exposed through normal chat responses.

## Important Day-4 note

The claim-support checker is a safety net, not a substitute for clinical review. Citation validity and semantic citation correctness should still be manually reviewed in the internal evaluation set before the final demo.
