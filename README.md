# AI Clinical Decision Support Lite
## Day 2 — Retrieval Optimization | Adult Hypertension Clinical RAG

> **Educational prototype only.** This system is not a diagnostic tool, prescription engine, emergency triage service, or replacement for qualified clinical judgment.

This repository is the continuation of **Day 1** of the AI Clinical Decision Support hackathon. Day 1 established a searchable, evidence-traceable hypertension knowledge base. Day 2 keeps that foundation intact and turns retrieval into a **measured engineering problem**: compare chunking strategies, test Top-K values, compare semantic/keyword/hybrid retrieval, inspect failure modes, and select a defensible retrieval baseline.

The official Day 2 objective is not to make the LLM sound better. It is to prove that the retriever consistently surfaces the correct clinical evidence **before** generation is optimized.

---

## 1. Clinical Scope

**Domain:** Adult Hypertension

**Approved project documents:**

1. NICE NG136 — *Hypertension in adults: diagnosis and management*
2. NICE Patient Decision Aid — *How do I control my blood pressure? Lifestyle options and choice of medicines*

The knowledge base is restricted to these approved documents. No arbitrary web pages or user-supplied URLs are added to retrieval.

The project remains educational and evidence-grounded. It must not diagnose, prescribe, recommend personalized doses, or replace a healthcare professional.

---

# 2. Day 1 → Day 2 Handoff

Day 1 already delivered the core indexing pipeline:

```text
NICE PDFs
   ↓
PDF extraction
   ↓
Text cleaning
   ↓
Document-aware section detection
   ↓
Chunking + overlap
   ↓
Embeddings
   ↓
Chroma
   ↓
Query embedding
   ↓
Top-K evidence
```

Day 2 does **not** replace this architecture.

Instead, it introduces an experimental retrieval layer:

```text
Clinical Question
       ↓
Query Cleaning
       ↓
Embedding / Keyword Analysis
       ↓
Candidate Retrieval
       ↓
Top-K
       ↓
Optional Filtering / Hybrid Retrieval
       ↓
Optional Lightweight Reranking
       ↓
Evidence Panel
       ↓
Grounded Generation
```

The Day 1 UI remains the canonical frontend foundation and has been improved rather than replaced.

---

# 3. What Day 2 Adds

### Retrieval experiments

- Chunk configuration A: **500 characters / 75 overlap**
- Chunk configuration B: **850 characters / 150 overlap**
- Top-K: **3 / 5 / 10**
- Semantic/vector retrieval
- Keyword/BM25-style retrieval
- Hybrid retrieval
- Optional lightweight heuristic reranking

### Evaluation

- Expanded from 8 Day-1 questions to **16 labeled clinical questions**
- Precision@3
- Precision@5
- Precision@10
- Mean Reciprocal Rank
- Per-question retrieval results
- Configuration comparison
- Retrieval failure-mode review
- Human relevance-labeling workflow

### UI

The Day-1 interface is upgraded into a ChatGPT-style evidence-first experience:

- Persistent local chat history
- New chat
- Conversation switching
- User/assistant message bubbles
- Copy answer
- Helpful / Not helpful reactions
- Reply / follow-up action
- Evidence displayed before answer generation completes
- Expandable evidence cards
- Score, document, section, page, chunk ID and source URL
- Responsive mobile sidebar

### Security

- Request length validation
- Top-K bounds
- Retrieval strategy validation
- Approved-document retrieval restriction
- Short-lived server-side retrieval context
- In-memory API rate limiting
- Security headers
- Content Security Policy
- No API keys in source code
- No browser-provided evidence accepted as authoritative generation context
- Prompt-injection defense for retrieved text
- Generic production-facing error messages

---

# 4. Repository Structure

```text
AI_Clinical_Decision_Support/
│
├── README.md
├── SETUP.md
├── clinical_scope.md
├── requirements.txt
├── .env.example
├── .gitignore
│
├── data/
│   ├── hypertension_nice_ng136.pdf
│   ├── hypertension_patient_decision_aid.pdf
│   └── clinical_test_questions.json
│
├── docs/
│   ├── DAY1_CODE_DOCUMENTATION.md
│   ├── DAY2_DETAILED_IMPLEMENTATION.md
│   └── DAY2_READINESS_CHECKLIST.md
│
├── outputs/
│   ├── day2_manual_labels.json          # created by the review command
│   └── day2_retrieval_report.json       # created by evaluation
│
├── src/
│   ├── __init__.py
│   ├── config.py
│   ├── ingestion.py
│   ├── vector_store.py
│   ├── evaluation.py
│   ├── llm.py
│   ├── main.py
│   └── web.py
│
├── tests/
│   ├── test_ingestion.py
│   ├── test_evaluation_data.py
│   ├── test_day2_evaluation.py
│   └── test_security_contract.py
│
└── web/
    ├── index.html
    ├── app.js
    └── styles.css
```

`chroma_db/` is generated locally and is intentionally not committed to Git.

---

# 5. Requirements

Recommended environment:

- Python 3.10+
- PowerShell on Windows, or a standard shell on macOS/Linux
- Internet access during dependency/model setup
- Groq API key for answer generation

FastEmbed downloads the embedding model on first use. The first indexing operation can therefore take longer than later searches.

---

# 6. Installation

## Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell does not allow script activation, use the environment's Python directly:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

---

# 7. Environment Configuration

Copy the template:

```powershell
Copy-Item .env.example .env
```

Then set:

```env
GROQ_API_KEY=YOUR_REAL_GROQ_API_KEY
GROQ_MODEL=llama-3.3-70b-versatile
```

Never commit `.env`.

The application does not embed credentials inside Python or JavaScript source code.

---

# 8. Run Tests First

```powershell
python -m pytest -q
```

The current test suite should report:

```text
8 passed
```

The tests cover:

- Day-1 section metadata
- Patient Decision Aid section detection
- Required metadata
- 15–20 question Day-2 evaluation set
- Precision@K arithmetic
- MRR arithmetic
- Approved-document retrieval scope
- API bounds

---

# 9. Build the Day-2 Indexes

Day 2 intentionally keeps two chunk configurations so they can be measured against the same evaluation set.

```powershell
python -m src.main index-day2
```

This creates:

```text
A_500_75
    chunk_size = 500 characters
    overlap    = 75 characters

B_850_150
    chunk_size = 850 characters
    overlap    = 150 characters
```

The second configuration is the Day-1 baseline and is retained specifically so Day 2 can prove whether changing chunk size actually helps.

---

# 10. Manual Relevance Labeling

The official Day-2 workflow asks the team to inspect retrieved chunks and label them relevant or not relevant.

Run:

```powershell
python -m src.main review
```

The command walks through the 16-question evaluation set and reviews the unique Top-5 candidates produced by both chunk configurations and semantic/keyword/hybrid retrieval.

For each result:

```text
y = relevant
n = not relevant
s = skip
```

The labels are saved to:

```text
outputs/day2_manual_labels.json
```

**Do not treat the final Precision@K as authoritative until this human review is complete.** If no human labels exist, the evaluator falls back to deterministic source/section metadata as a reproducibility proxy and marks the report accordingly.

---

# 11. Run Day-2 Evaluation

After building both indexes:

```powershell
python -m src.main evaluate-day2
```

The report is written to:

```text
outputs/day2_retrieval_report.json
```

The report compares:

### Chunking

```text
A_500_75
B_850_150
```

### Retrieval strategies

```text
semantic
keyword
hybrid
```

### Metrics

```text
Precision@3
Precision@5
Precision@10
Mean Reciprocal Rank
```

The primary Day-2 decision metric is **Precision@5**, because the official agenda explicitly emphasizes Precision@3 and Precision@5 while Top-10 is used as a broader recall-oriented comparison.

---

# 12. Search Manually

Semantic search:

```powershell
python -m src.main search "How is hypertension confirmed using ambulatory blood pressure monitoring?" --top-k 5 --strategy semantic --config B_850_150
```

Keyword search:

```powershell
python -m src.main search "ACE inhibitor blood tests" --top-k 5 --strategy keyword --config B_850_150
```

Hybrid search:

```powershell
python -m src.main search "ACE inhibitor blood tests" --top-k 5 --strategy hybrid --config B_850_150
```

Hybrid + lightweight reranking:

```powershell
python -m src.main search "ACE inhibitor blood tests" --top-k 5 --strategy hybrid --config B_850_150 --rerank
```

---

# 13. Generate a Grounded Answer

Generation is still downstream of retrieval.

```powershell
python -m src.main answer "What are common side effects of ACE inhibitors?"
```

The Day-2 CLI uses:

```text
Hybrid retrieval
        ↓
Optional heuristic reranking
        ↓
Retrieved evidence
        ↓
Groq grounded answer
```

Day 2 does not optimize the final generation prompt. Prompt/citation optimization is intentionally left for Day 3.

---

# 14. Start the Web Application

```powershell
python -m uvicorn src.web:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

Health check:

```text
http://127.0.0.1:8000/api/health
```

PowerShell:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

---

# 15. Day-2 Web Interaction Flow

The UI deliberately separates retrieval from generation.

```text
User question
     ↓
POST /api/retrieve
     ↓
Evidence rendered immediately
     ↓
Server-issued retrieval_id
     ↓
POST /api/answer
     ↓
Same cached evidence is supplied to the LLM
     ↓
Grounded answer appears
```

This prevents the UI from hiding the evidence while the LLM is working and makes the retrieval step inspectable during the demo.

---

# 16. Why the Retrieval ID Exists

The browser never submits arbitrary evidence text to the answer endpoint.

Instead:

```text
Browser
   ↓
/api/retrieve
   ↓
Server retrieves trusted chunks
   ↓
Server stores short-lived retrieval context
   ↓
retrieval_id
   ↓
/api/answer
```

The answer endpoint checks that:

- the retrieval context exists
- it has not expired
- the question matches the original retrieval question

This is stronger than trusting the browser to tell the server which evidence should be used.

---

# 17. Chat History

The Day-2 UI provides a ChatGPT-style sidebar.

It supports:

- New chat
- Multiple conversations
- Switching between conversations
- Clear history
- Copy answer
- Helpful reaction
- Not helpful reaction
- Reply / follow-up

For privacy, this demo stores chat history in **browser localStorage**, not in the server database.

The server does not persist personal chat history.

This is appropriate for the hackathon prototype and keeps the security surface smaller.

---

# 18. Security Baseline

Day 2 strengthens the security foundation without introducing unnecessary infrastructure.

### API validation

FastAPI/Pydantic enforces:

- minimum question length
- maximum question length of 1000 characters
- Top-K maximum of 10
- allowed retrieval strategies
- controlled configuration names

### Rate limiting

The API uses a lightweight in-memory per-client rate limiter.

Default:

```text
20 API requests / 60 seconds / client IP
```

This is suitable for a local hackathon demo. A production deployment should use a shared rate limiter at the gateway or reverse-proxy layer.

### Security headers

The application sends:

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: no-referrer`
- restrictive `Content-Security-Policy`
- `Cache-Control: no-store` for API responses

### Retrieval scope

Only the two approved NICE document IDs are eligible for retrieval.

### Prompt injection

Retrieved text is treated as **untrusted evidence**. Instructions embedded inside a PDF chunk cannot override the system prompt.

### Error handling

The API avoids returning raw exception traces to the browser.

---

# 19. Retrieval Strategies

## Semantic

Uses the FastEmbed vector representation and Chroma cosine similarity.

Best for:

- semantically similar clinical concepts
- paraphrased questions

Weakness:

- exact acronyms, drug names, or thresholds can sometimes be under-ranked

## Keyword

Uses a local BM25-style scoring implementation.

Best for:

- exact terms
- drug names
- acronyms
- thresholds

Weakness:

- weaker semantic understanding

## Hybrid

Combines semantic and keyword signals:

```text
Hybrid score
= 0.70 × semantic score
+ 0.30 × keyword score
```

This is intentionally simple and transparent for the hackathon. The weights should be treated as an experimental parameter rather than a universal truth.

## Lightweight reranking

The optional reranker adds lexical overlap and section-match signals to the candidate score.

It is **not** presented as a transformer cross-encoder. It is a transparent heuristic layer that can be evaluated against the base retriever.

A stronger learned reranker can be considered later if the measured retrieval baseline justifies it.

---

# 20. Chunking Experiments

The Day-2 slides explicitly turn chunk size into a measured hyperparameter.

### Experiment A

```text
500 characters
75 overlap
```

### Experiment B

```text
850 characters
150 overlap
```

The system rebuilds the corpus for both configurations and runs the same questions against both.

**Only one experimental variable should change at a time.**

Do not simultaneously change:

- chunk size
- overlap
- K
- embedding model
- retrieval strategy
- reranking

and then claim the result came from one specific change.

---

# 21. Failure Modes

The Day-2 implementation explicitly recognizes:

### Wrong topic

The chunk is medically related but does not answer the actual question.

Potential fixes:

- query formulation
- metadata filtering
- keyword/hybrid retrieval
- reranking

### Missing context

The retrieved chunk contains part of a recommendation but not the criteria around it.

Potential fixes:

- larger chunks
- more overlap
- better section-aware chunking

### Duplicate chunks

Top-K contains near-identical evidence.

Potential fixes:

- lower overlap
- deduplication
- page/section diversity

### Exact term missed

Semantic retrieval under-ranks an acronym, medicine or threshold.

Potential fixes:

- keyword retrieval
- hybrid retrieval

### Correct chunk ranked too low

The evidence exists but appears at rank 7–8.

Potential fixes:

- reranking
- better chunking
- stronger embeddings

### Irrelevant high-score chunk

High similarity does not guarantee clinical relevance.

Potential fixes:

- human relevance labeling
- reranking
- improved retrieval strategy

### Metadata problem

Correct text is retrieved but page/section/chunk metadata is missing.

This must be fixed before Day 3 because broken metadata becomes broken citations.

---

# 22. Day-2 Readiness Gate

Before declaring Day 2 complete, verify all of the following:

- [ ] Correct evidence frequently appears in Top-K
- [ ] Best evidence is reasonably high in the ranking
- [ ] Document, page, section and chunk ID are available
- [ ] Similarity/retrieval scores are visible
- [ ] 15–20 question evaluation set exists
- [ ] Precision@3 is calculated
- [ ] Precision@5 is calculated
- [ ] At least two chunk configurations were compared
- [ ] Retrieval failure cases are documented
- [ ] A final retrieval configuration is chosen based on measured results
- [ ] The team can demonstrate Question → Evidence → Metadata → Score

**The final baseline must be defended with numbers, not intuition.**

---

# 23. Day 3 Boundary

Day 2 ends with a measured retrieval baseline.

Day 3 will take that frozen baseline and focus on:

```text
Retrieved evidence
      ↓
Grounded prompt
      ↓
LLM generation
      ↓
Claim-level citations
      ↓
Evidence strength / refusal behavior
```

Do not keep changing chunk size or K during Day 3 unless the Day-2 readiness gate proves the baseline was not actually ready.

---

# 24. Important Demo Message

The strongest Day-2 demo is not:

> “Look, the chatbot answers.”

It is:

> “We measured retrieval, compared two chunking configurations, compared Top-K and retrieval strategies, identified failure modes, and selected the configuration based on Precision@K.”

That directly addresses the purpose of Day 2 and creates a defensible bridge into Day 3.

---

# 25. License / Source Note

The project uses the supplied NICE documents as the approved educational knowledge base. Source URLs and document version metadata are retained in chunk metadata.

Before external/public redistribution beyond the hackathon, verify the current terms of use and any applicable NICE/NHS reuse requirements.
