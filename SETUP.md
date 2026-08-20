# Day 4 Setup Guide

## Windows / PowerShell

```powershell
cd "C:\Path\To\AI_Clinical_Decision_Support_Day4"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Add the Groq API key to `.env`.

## Google OAuth

Configure the OAuth application in Google Cloud and use this local redirect URI:

```text
http://127.0.0.1:8000/api/auth/google/callback
```

Set:

```env
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://127.0.0.1:8000/api/auth/google/callback
COOKIE_SECURE=0
```

## Build the indexes

```powershell
python -m src.main index-day2
```

## Test

```powershell
python -m pytest -q
```

## Day-4 evaluation

```powershell
python -m src.main evaluate-day4
```

## Run the web app

```powershell
python -m uvicorn src.web:app --reload
```

Open `http://127.0.0.1:8000`.

## Storage policy

The maximum stored chat history for each user is **2 MB**.
There is **no daily question quota**.

When storage reaches the maximum, the user is asked to manage/delete their own chat history before saving more.
