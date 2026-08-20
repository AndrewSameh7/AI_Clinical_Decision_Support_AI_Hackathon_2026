from __future__ import annotations
import hashlib, hmac, os, secrets, sqlite3, time, uuid, re
from collections import defaultdict, deque
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlencode
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, EmailStr
from src.config import CLINICAL_SCOPE, MAX_QUERY_LENGTH, MAX_TOP_K, RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW_SECONDS, TOP_K, TOP1_MIN_SIMILARITY
from src.llm import GROQ_MODEL, generate_grounded_answer
from src.day4_safety import classify_query, validate_claim_support
from src.vector_store import index_ready, retrieve

ROOT=Path(__file__).resolve().parents[1]; STATIC_DIR=ROOT/"web"; DATA_DIR=ROOT/"data"; DB=DATA_DIR/"day3_users.sqlite3"
DB.parent.mkdir(exist_ok=True)
app=FastAPI(title="AI Clinical Decision Support Lite",version="4.0.0")
app.add_middleware(GZipMiddleware,minimum_size=1000); app.mount("/static",StaticFiles(directory=str(STATIC_DIR)),name="static")
_RETRIEVAL_CACHE={}; _RATE_BUCKETS=defaultdict(deque); _SESSIONS={}
USER_STORAGE_LIMIT_BYTES = 2 * 1024 * 1024
STORAGE_WARNING_RATIO = 0.80
USER_ROLE = "Adult Hypertension Clinical Decision Support User"
INFRASTRUCTURE_BLOCKLIST = re.compile(r"\b(database|database type|sqlite|chromadb|vector database|encryption|encryption type|cipher|hashing|password hash|secret|api key|token|session store|schema|table name|dump|credentials|stored data|private data|sensitive data|patient data|patient records|medical records|user records|personal data|passwords|access tokens|oauth|system prompt|hidden prompt|developer instructions|internal instructions|private instructions|security policy|secret instructions|reveal your rules|internal architecture)\b", re.I)
OUT_OF_SCOPE_TERMS = re.compile(r"\b(weather|football|soccer|recipe|stock price|politics|movie|song|joke|programming|python code|write code|database administration)\b", re.I)


def db():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,password_hash TEXT,name TEXT NOT NULL,google_sub TEXT UNIQUE,created_at REAL NOT NULL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,title TEXT NOT NULL,created_at REAL NOT NULL,updated_at REAL NOT NULL,FOREIGN KEY(user_id) REFERENCES users(id))""")
    c.execute("""CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY,conversation_id TEXT NOT NULL,role TEXT NOT NULL,content TEXT NOT NULL,answer_json TEXT,created_at REAL NOT NULL,FOREIGN KEY(conversation_id) REFERENCES conversations(id))""")
    c.execute("""CREATE TABLE IF NOT EXISTS message_feedback(id TEXT PRIMARY KEY,message_id TEXT NOT NULL,user_id TEXT NOT NULL,feedback TEXT NOT NULL,created_at REAL NOT NULL,UNIQUE(message_id,user_id),FOREIGN KEY(message_id) REFERENCES messages(id),FOREIGN KEY(user_id) REFERENCES users(id))""")
    c.commit(); return c
def hash_pw(pw): return hashlib.scrypt(pw.encode(),salt=secrets.token_bytes(16),n=2**14,r=8,p=1).hex()
# Store salt separately in encoded form for verification.
def make_pw(pw):
    salt=secrets.token_bytes(16); dk=hashlib.scrypt(pw.encode(),salt=salt,n=2**14,r=8,p=1); return f"scrypt${salt.hex()}${dk.hex()}"
def check_pw(pw,stored):
    try:
        _,sh,dh=stored.split("$"); dk=hashlib.scrypt(pw.encode(),salt=bytes.fromhex(sh),n=2**14,r=8,p=1); return hmac.compare_digest(dk.hex(),dh)
    except Exception: return False
def session_user(request):
    sid=request.cookies.get("day3_session"); uid=_SESSIONS.get(sid)
    if not uid: raise HTTPException(401,"Authentication required.")
    c=db(); row=c.execute("SELECT id,email,name FROM users WHERE id=?",(uid,)).fetchone(); c.close()
    if not row: raise HTTPException(401,"Authentication required.")
    return dict(row)
def issue_session(uid,response):
    sid=secrets.token_urlsafe(32); _SESSIONS[sid]=uid
    response.set_cookie("day3_session",sid,httponly=True,samesite="lax",secure=os.getenv("COOKIE_SECURE","0")=="1",max_age=60*60*8)
def public_user(u): return {"id":u["id"],"email":u["email"],"name":u["name"],"role":USER_ROLE}

class Register(BaseModel): name:str=Field(min_length=2,max_length=80); email:EmailStr; password:str=Field(min_length=8,max_length=128)
class Login(BaseModel): email:EmailStr; password:str=Field(min_length=8,max_length=128)
class RetrieveRequest(BaseModel):
    question:str=Field(min_length=3,max_length=MAX_QUERY_LENGTH); top_k:int=Field(default=1,ge=1,le=MAX_TOP_K)
    strategy:str=Field(default="hybrid",pattern="^(semantic|keyword|hybrid)$"); config:str=Field(default="B_850_150",pattern="^[A-Za-z0-9_-]{3,40}$"); rerank:bool=False
class AnswerRequest(BaseModel): retrieval_id:str=Field(min_length=20,max_length=80); question:str=Field(min_length=3,max_length=MAX_QUERY_LENGTH); conversation_id:Optional[str]=None
class ChatMessage(BaseModel): role:str; content:str
class FeedbackRequest(BaseModel): feedback:str=Field(pattern="^(up|down)$")
class ReplyRequest(BaseModel): content:str=Field(min_length=1,max_length=MAX_QUERY_LENGTH)

def _refusal_for_scope(q, user=None):
    if INFRASTRUCTURE_BLOCKLIST.search(q):
        name = (user or {}).get("name") or "the signed-in user"
        return {"status":"safety_refusal","recommendation":f"For privacy and security, I can identify only your account name and role: {name} — {USER_ROLE}. I can’t provide database details, encryption details, credentials, stored sensitive data, internal architecture, secrets, or private system information. I can answer Adult Hypertension clinical evidence questions instead.","supporting_evidence":[],"confidence":"Insufficient Evidence","missing_information":[],"safety_note":"System and security details are protected. Please ask an Adult Hypertension clinical evidence question instead."}
    if OUT_OF_SCOPE_TERMS.search(q):
        return {"status":"safety_refusal","recommendation":"I’m specialized in Adult Hypertension clinical evidence only. I can’t answer questions outside that scope. Please ask an Adult Hypertension question based on the approved clinical documents.","supporting_evidence":[],"confidence":"Insufficient Evidence","missing_information":[],"safety_note":"Educational information only; not a diagnosis or medical advice."}
    return None

def _needs_clarification(q):
    words=q.strip().split()
    if len(words) < 4 or re.search(r"\\b(it|this|that|they|them|something|stuff)\\b", q.lower()) and len(words) < 10:
        return True
    return False

def _clarification(q):
    return {"status":"clarification_needed","recommendation":"I want to make sure I understand your question. Could you clarify what you mean? For example, are you asking about diagnosis, lifestyle management, medicines, or blood-pressure targets?","supporting_evidence":[],"confidence":"Insufficient Evidence","missing_information":["A clearer clinical question"],"safety_note":"Please clarify the intended Adult Hypertension question before I search the evidence."}

def _storage_usage(c,user_id):
    rows=c.execute("""SELECT length(content) AS n, length(COALESCE(answer_json,'')) AS a FROM messages
                     WHERE conversation_id IN (SELECT id FROM conversations WHERE user_id=?)""",(user_id,)).fetchall()
    titles=c.execute("SELECT length(title) AS n FROM conversations WHERE user_id=?",(user_id,)).fetchall()
    used=sum((r["n"] or 0)+(r["a"] or 0) for r in rows)+sum((r["n"] or 0) for r in titles)
    return int(used)

def _storage_payload(c,user_id):
    used=_storage_usage(c,user_id); limit=USER_STORAGE_LIMIT_BYTES
    ratio=used/limit if limit else 1
    return {"used_bytes":used,"limit_bytes":limit,"used_percent":round(ratio*100,1),"warning":ratio>=STORAGE_WARNING_RATIO,"full":ratio>=1.0}

@app.middleware("http")
async def sec(request:Request,call_next):
    ip=request.client.host if request.client else "unknown"; now=time.time(); b=_RATE_BUCKETS[ip]
    while b and now-b[0]>RATE_LIMIT_WINDOW_SECONDS:b.popleft()
    if request.url.path.startswith("/api/"):
        if len(b)>=RATE_LIMIT_REQUESTS:return _json_error(429,"Too many requests. Please wait.")
        b.append(now)
    response=await call_next(request)
    for k,v in {"X-Content-Type-Options":"nosniff","X-Frame-Options":"DENY","Referrer-Policy":"no-referrer","Cache-Control":"no-store" if request.url.path.startswith("/api/") else "public, max-age=300","Content-Security-Policy":"default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self' https://accounts.google.com https://oauth2.googleapis.com https://www.googleapis.com; img-src 'self' data: https://*.googleusercontent.com; frame-ancestors 'none'; base-uri 'self'; form-action 'self' https://accounts.google.com"}.items():response.headers[k]=v
    return response
def _json_error(code,msg):
    from fastapi.responses import JSONResponse
    return JSONResponse(code,{"detail":msg})

@app.get("/",include_in_schema=False)
def home(): return FileResponse(STATIC_DIR/"index.html")

@app.post("/api/auth/register")
def register(x:Register):
    c=db()
    if c.execute("SELECT id FROM users WHERE email=?",(str(x.email).lower(),)).fetchone(): c.close(); raise HTTPException(409,"An account with this email already exists.")
    uid=uuid.uuid4().hex; c.execute("INSERT INTO users VALUES(?,?,?,?,?,?)",(uid,str(x.email).lower(),make_pw(x.password),x.name,None,time.time())); c.commit(); c.close()
    from fastapi.responses import JSONResponse
    r=JSONResponse({"user":{"id":uid,"email":str(x.email).lower(),"name":x.name}}); issue_session(uid,r); return r
@app.post("/api/auth/login")
def login(x:Login):
    c=db(); row=c.execute("SELECT * FROM users WHERE email=?",(str(x.email).lower(),)).fetchone(); c.close()
    if not row or not row["password_hash"] or not check_pw(x.password,row["password_hash"]): raise HTTPException(401,"Invalid email or password.")
    from fastapi.responses import JSONResponse
    r=JSONResponse({"user":{"id":row["id"],"email":row["email"],"name":row["name"]}}); issue_session(row["id"],r); return r
@app.post("/api/auth/logout")
def logout(request:Request):
    sid=request.cookies.get("day3_session"); _SESSIONS.pop(sid,None)
    from fastapi.responses import JSONResponse
    r=JSONResponse({"ok":True}); r.delete_cookie("day3_session"); return r
@app.get("/api/auth/me")
def me(request:Request):
    u=session_user(request); c=db(); storage=_storage_payload(c,u["id"]); c.close()
    return {"user":{**u,"role":USER_ROLE},"storage":storage}

@app.get("/api/auth/google")
def google_start():
    cid=os.getenv("GOOGLE_CLIENT_ID"); redirect=os.getenv("GOOGLE_REDIRECT_URI","http://127.0.0.1:8000/api/auth/google/callback")
    if not cid: raise HTTPException(503,"Google sign-in is not configured.")
    state=secrets.token_urlsafe(24); _SESSIONS["oauth:"+state]="oauth"
    q=urlencode({"client_id":cid,"redirect_uri":redirect,"response_type":"code","scope":"openid email profile","state":state,"access_type":"offline","prompt":"select_account"})
    return RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth?"+q)
@app.get("/api/auth/google/callback")
async def google_callback(request:Request,code:Optional[str]=None,state:Optional[str]=None,error:Optional[str]=None):
    if error:
        return RedirectResponse("/?auth_error=Google+sign-in+was+cancelled+or+rejected")
    if not code or not state:
        return RedirectResponse("/?auth_error=Google+sign-in+did+not+return+a+valid+authorization+code")
    if _SESSIONS.pop("oauth:"+state,None)!="oauth": raise HTTPException(400,"Invalid OAuth state.")
    cid=os.getenv("GOOGLE_CLIENT_ID"); secret=os.getenv("GOOGLE_CLIENT_SECRET"); redirect=os.getenv("GOOGLE_REDIRECT_URI","http://127.0.0.1:8000/api/auth/google/callback")
    if not cid or not secret: raise HTTPException(503,"Google sign-in is not configured.")
    async with httpx.AsyncClient(timeout=10) as client:
        tok=(await client.post("https://oauth2.googleapis.com/token",data={"code":code,"client_id":cid,"client_secret":secret,"redirect_uri":redirect,"grant_type":"authorization_code"})).json()
        if "access_token" not in tok: raise HTTPException(401,"Google authentication failed.")
        info=(await client.get("https://www.googleapis.com/oauth2/v3/userinfo",headers={"Authorization":"Bearer "+tok["access_token"]})).json()
    email=str(info.get("email","")).lower(); sub=info.get("sub"); name=info.get("name") or email.split("@")[0]
    if not email or not sub: raise HTTPException(401,"Google account information unavailable.")
    c=db(); row=c.execute("SELECT * FROM users WHERE google_sub=? OR email=?",(sub,email)).fetchone()
    if row:
        c.execute("UPDATE users SET google_sub=?,name=? WHERE id=?",(sub,name,row["id"])); uid=row["id"]
    else:
        uid=uuid.uuid4().hex; c.execute("INSERT INTO users VALUES(?,?,?,?,?,?)",(uid,email,None,name,sub,time.time()))
    c.commit(); c.close()
    r=RedirectResponse("/"); issue_session(uid,r); return r

@app.get("/api/history")
def history(request:Request):
    u=session_user(request); c=db(); rows=c.execute("SELECT id,title,updated_at FROM conversations WHERE user_id=? ORDER BY updated_at DESC",(u["id"],)).fetchall(); c.close()
    return {"conversations":[dict(r) for r in rows]}
@app.post("/api/history")
def new_history(request:Request):
    u=session_user(request); cid=uuid.uuid4().hex; now=time.time(); c=db(); c.execute("INSERT INTO conversations VALUES(?,?,?,?,?)",(cid,u["id"],"New clinical question",now,now)); c.commit(); c.close(); return {"id":cid,"title":"New clinical question"}
@app.get("/api/history/{cid}")
def get_history(cid:str,request:Request):
    u=session_user(request); c=db(); conv=c.execute("SELECT * FROM conversations WHERE id=? AND user_id=?",(cid,u["id"])).fetchone()
    if not conv:c.close(); raise HTTPException(404,"Conversation not found.")
    msgs=c.execute("SELECT id,role,content,answer_json,created_at FROM messages WHERE conversation_id=? ORDER BY created_at",(cid,)).fetchall(); c.close()
    return {"conversation":dict(conv),"messages":[dict(m) for m in msgs]}
@app.delete("/api/history")
def clear_history(request:Request):
    u=session_user(request); c=db(); ids=[r["id"] for r in c.execute("SELECT id FROM conversations WHERE user_id=?",(u["id"],)).fetchall()]
    for cid in ids:c.execute("DELETE FROM messages WHERE conversation_id=?",(cid,))
    c.execute("DELETE FROM conversations WHERE user_id=?",(u["id"],)); c.commit(); c.close(); return {"ok":True}

@app.get("/api/settings/storage")
def storage_settings(request:Request):
    u=session_user(request); c=db(); data=_storage_payload(c,u["id"]); c.close(); return data

@app.delete("/api/settings/storage")
def manage_storage(request:Request):
    return clear_history(request)

@app.post("/api/messages/{message_id}/feedback")
def feedback(message_id:str,x:FeedbackRequest,request:Request):
    u=session_user(request); c=db()
    ok=c.execute("""SELECT m.id FROM messages m JOIN conversations cv ON cv.id=m.conversation_id
                    WHERE m.id=? AND cv.user_id=? AND m.role='assistant'""",(message_id,u["id"])).fetchone()
    if not ok: c.close(); raise HTTPException(404,"Message not found.")
    c.execute("""INSERT INTO message_feedback VALUES(?,?,?,?,?) ON CONFLICT(message_id,user_id)
                 DO UPDATE SET feedback=excluded.feedback,created_at=excluded.created_at""",
              (uuid.uuid4().hex,message_id,u["id"],x.feedback,time.time()))
    c.commit(); c.close(); return {"ok":True,"feedback":x.feedback}

@app.get("/api/source-document/{document_id}")
def source_document(document_id:str,request:Request):
    session_user(request)
    allowed={"hypertension_nice_ng136":"hypertension_nice_ng136.pdf","hypertension_patient_decision_aid":"hypertension_patient_decision_aid.pdf"}
    name=allowed.get(document_id)
    if not name: raise HTTPException(404,"Approved source not found.")
    return FileResponse(DATA_DIR/name,media_type="application/pdf",filename=name)

@app.get("/api/source/{conversation_id}/{message_id}")
def source_details(conversation_id:str,message_id:str,request:Request):
    u=session_user(request); c=db()
    row=c.execute("""SELECT m.answer_json FROM messages m JOIN conversations cv ON cv.id=m.conversation_id
                     WHERE m.id=? AND m.conversation_id=? AND cv.user_id=? AND m.role='assistant'""",
                  (message_id,conversation_id,u["id"])).fetchone()
    c.close()
    if not row: raise HTTPException(404,"Source not found.")
    data=__import__("json").loads(row["answer_json"] or "{}")
    return {"sources":data.get("source_details",[]),"citations":data.get("supporting_evidence",[])}

@app.get("/api/health")
def health(): return {"status":"ok" if index_ready("B_850_150") else "degraded","scope":CLINICAL_SCOPE,"model":GROQ_MODEL,"index_ready":index_ready("B_850_150")}

@app.post("/api/retrieve")
def retrieve_evidence(x:RetrieveRequest,request:Request):
    u=session_user(request); q=" ".join(x.question.split())
    c=db(); c.close()
    risk = classify_query(q)
    blocked=_refusal_for_scope(q,u)
    if risk["action"] == "refuse" and not blocked:
        blocked = {"status":"safety_refusal","recommendation":"This request is outside the safe clinical evidence-support boundary. I can help with Adult Hypertension questions grounded in the approved NICE evidence.","supporting_evidence":[],"confidence":"Insufficient Evidence","missing_information":[],"safety_note":"Educational information only; not a diagnosis or medical advice."}
    if risk["action"] == "redirect" and not blocked:
        blocked = {"status":"safety_refusal","recommendation":"This sounds urgent or patient-specific. I cannot provide emergency or individualized treatment decisions. Please seek appropriate professional medical care.","supporting_evidence":[],"confidence":"Insufficient Evidence","missing_information":[],"safety_note":"Educational information only; not a diagnosis or medical advice."}
    if blocked:
        rid=uuid.uuid4().hex; _RETRIEVAL_CACHE[rid]={"created":time.time(),"question":q,"rows":[],"pre_result":blocked}
        return {"retrieval_id":rid,"question":q,"scope":CLINICAL_SCOPE,"strategy":x.strategy,"config":x.config,"top_k":1,"evidence":[],"pre_result":blocked,"risk":risk}
    if _needs_clarification(q):
        rid=uuid.uuid4().hex; pre=_clarification(q); _RETRIEVAL_CACHE[rid]={"created":time.time(),"question":q,"rows":[],"pre_result":pre}
        return {"retrieval_id":rid,"question":q,"scope":CLINICAL_SCOPE,"strategy":x.strategy,"config":x.config,"top_k":1,"evidence":[],"pre_result":pre,"risk":risk}
    try: rows=retrieve(q,top_k=1,strategy=x.strategy,config_name=x.config,rerank=x.rerank)
    except Exception: raise HTTPException(400,"Retrieval failed. Check the local index.")
    rid=uuid.uuid4().hex; _RETRIEVAL_CACHE[rid]={"created":time.time(),"question":q,"rows":rows}
    return {"retrieval_id":rid,"question":q,"scope":CLINICAL_SCOPE,"strategy":x.strategy,"config":x.config,"top_k":1,"evidence":[_public_evidence(rows[0])] if rows else [],"risk":risk}

@app.post("/api/answer")
def answer(x:AnswerRequest,request:Request):
    u=session_user(request); cached=_RETRIEVAL_CACHE.get(x.retrieval_id)
    if not cached or time.time()-cached["created"]>300: raise HTTPException(410,"Retrieval context expired. Please search again.")
    q=" ".join(x.question.split())
    if q!=cached["question"]: raise HTTPException(400,"Question does not match the retrieval context.")
    if cached.get("pre_result"):
        result=cached["pre_result"]
    else:
        rows=cached["rows"][:1]
        if not rows or float(rows[0].get("similarity",0.0)) < TOP1_MIN_SIMILARITY:
            result={"status":"insufficient_evidence","recommendation":"I could not find enough supporting evidence in the approved clinical documents to answer this confidently.","supporting_evidence":[],"confidence":"Insufficient Evidence","missing_information":["Stronger relevant evidence"],"safety_note":"Educational information only; not a diagnosis or medical advice."}
        else:
            try: result=generate_grounded_answer(q,rows)
            except RuntimeError as exc: raise HTTPException(503,str(exc))
            except Exception: raise HTTPException(502,"The answer service could not complete the request.")
            if result.get("status") == "answered" and rows:
                table_text = " ".join([str(x) for row in (result.get("table", {}) or {}).get("rows", []) if isinstance(row, list) for x in row])
                support = validate_claim_support((result.get("recommendation", "") + " " + table_text).strip(), rows[0].get("text", ""))
                result["claim_validation"] = support
                if support["unsupported"] and support["supported"]:
                    result["recommendation"] = " ".join(x["claim"] for x in support["supported"])
                    result.setdefault("missing_information", []).append("Some parts of the question were not directly supported by the retrieved evidence and were not answered.")
                elif support["unsupported"] and not support["supported"]:
                    result = {"status":"insufficient_evidence","recommendation":"I found evidence related to the request, but it did not support a safe answer to the requested claims. Please narrow the question to the Adult Hypertension topic covered by the approved sources.","supporting_evidence":[],"confidence":"Insufficient Evidence","missing_information":[x["claim"] for x in support["unsupported"]],"safety_note":"Educational information only; not a diagnosis or medical advice.","claim_validation":support}
        if result.get("status")=="answered" and rows:
            m=rows[0]["metadata"]
            result["source_details"]=[{"document_name":m.get("document_name"),"section":m.get("section"),"page_number":m.get("page_number"),"source_url":m.get("source_url") or "/api/source-document/"+str(m.get("document_id")),"excerpt":rows[0].get("text","")}]
    cid=x.conversation_id; c=db()
    current_storage=_storage_usage(c,u["id"])
    if current_storage >= USER_STORAGE_LIMIT_BYTES:
        c.close(); raise HTTPException(507,"Your chat storage is full. Open Settings → Manage storage and delete older conversations before saving a new one.")
    if cid:
        ok=c.execute("SELECT id FROM conversations WHERE id=? AND user_id=?",(cid,u["id"])).fetchone()
        if not ok:c.close(); raise HTTPException(404,"Conversation not found.")
    else:
        cid=uuid.uuid4().hex; now=time.time(); c.execute("INSERT INTO conversations VALUES(?,?,?,?,?)",(cid,u["id"],q[:70],now,now))
    uid=uuid.uuid4().hex; aid=uuid.uuid4().hex
    c.execute("INSERT INTO messages VALUES(?,?,?,?,?,?)",(uid,cid,"user",q,None,time.time()))
    c.execute("INSERT INTO messages VALUES(?,?,?,?,?,?)",(aid,cid,"assistant",result.get("recommendation",""),__import__("json").dumps(result),time.time()))
    c.execute("UPDATE conversations SET updated_at=? WHERE id=?",(time.time(),cid)); c.commit(); c.close()
    return {"retrieval_id":x.retrieval_id,"conversation_id":cid,"assistant_message_id":aid,"question":q,"result":result,"scope":CLINICAL_SCOPE,"model":GROQ_MODEL}

def _public_evidence(row):
    m=row["metadata"]; return {"document_id":m.get("document_id"),"document_name":m.get("document_name"),"section":m.get("section"),"page_number":m.get("page_number"),"source":m.get("source"),"source_url":m.get("source_url"),"version":m.get("version")}
