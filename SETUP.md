# Setup — Day 2

## 1. Create and activate the virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, use:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 2. Install dependencies

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 3. Configure Groq

```powershell
Copy-Item .env.example .env
```

Set:

```env
GROQ_API_KEY=YOUR_REAL_GROQ_API_KEY
GROQ_MODEL=llama-3.3-70b-versatile
```

Do not paste the key into source files or commit `.env`.

## 4. Run tests

```powershell
python -m pytest -q
```

Expected:

```text
8 passed
```

## 5. Build Day-2 indexes

```powershell
python -m src.main index-day2
```

This builds:

- `A_500_75`
- `B_850_150`

## 6. Label retrieval results

```powershell
python -m src.main review
```

Answer `y`, `n`, or `s` for each retrieved chunk.

## 7. Evaluate

```powershell
python -m src.main evaluate-day2
```

Output:

```text
outputs/day2_retrieval_report.json
```

## 8. Start the web app

```powershell
python -m uvicorn src.web:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

## 9. Manual retrieval examples

```powershell
python -m src.main search "ACE inhibitor blood tests" --top-k 5 --strategy semantic --config B_850_150
python -m src.main search "ACE inhibitor blood tests" --top-k 5 --strategy keyword --config B_850_150
python -m src.main search "ACE inhibitor blood tests" --top-k 5 --strategy hybrid --config B_850_150 --rerank
```

## 10. If you change ingestion/chunking code

Rebuild the Day-2 indexes:

```powershell
Remove-Item -Recurse -Force .\chroma_db -ErrorAction SilentlyContinue
python -m src.main index-day2
```

Then rerun:

```powershell
python -m src.main review
python -m src.main evaluate-day2
```

## 11. Day-2 completion artifact

The key file is:

```text
outputs/day2_retrieval_report.json
```

It should be kept with the experiment notes because Day 3 depends on the selected measured retrieval baseline.
