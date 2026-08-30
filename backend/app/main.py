import os
import json
import re
from datetime import datetime, timezone
from time import perf_counter

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import text
from .database import engine

app = FastAPI(title="AIBeigmer API", version="1.1.1", description="Real AI benchmarking platform")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

CATEGORIES = [("html", "HTML", 15), ("css", "CSS", 20), ("javascript", "JavaScript", 30), ("python", "Python", 30), ("sql", "SQL", 15), ("backend", "Backend", 25), ("debugging", "Debugging", 30), ("algorithms", "Algoritmes", 25), ("apis", "APIs", 15), ("json", "JSON", 10), ("linux", "Linux", 10), ("git", "Git", 10)]
PROVIDERS = ["OpenAI", "Google", "Anthropic", "DeepSeek", "OpenRouter", "Groq", "FreeLLMAPI"]
PROVIDER_KEYS = {p: p.upper().replace(" ", "_") + "_API_KEY" for p in PROVIDERS}
EVALUATION_TYPES = ["unit_tests", "html_validation", "css_validation", "json_validation", "text_match", "static_analysis", "llm_judge", "manual_review"]


def now():
    return datetime.now(timezone.utc).isoformat()


def init_db():
    ddl = [
        "CREATE TABLE IF NOT EXISTS models (id TEXT PRIMARY KEY, name TEXT NOT NULL, provider TEXT NOT NULL, model_id TEXT NOT NULL, description TEXT DEFAULT '', context INTEGER, active BOOLEAN NOT NULL DEFAULT TRUE, created_at TEXT NOT NULL, UNIQUE(provider, model_id))",
        "CREATE TABLE IF NOT EXISTS categories (id TEXT PRIMARY KEY, name TEXT NOT NULL, question_limit INTEGER NOT NULL, active BOOLEAN NOT NULL DEFAULT TRUE)",
        "CREATE TABLE IF NOT EXISTS benchmarks (id TEXT PRIMARY KEY, name TEXT NOT NULL, active BOOLEAN NOT NULL DEFAULT TRUE, created_at TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS questions (id TEXT PRIMARY KEY, category TEXT NOT NULL, title TEXT NOT NULL, question TEXT NOT NULL, difficulty TEXT NOT NULL, language TEXT, requirements TEXT NOT NULL DEFAULT '[]', evaluation_type TEXT NOT NULL DEFAULT 'manual_review', weight DOUBLE PRECISION NOT NULL DEFAULT 1, active BOOLEAN NOT NULL DEFAULT TRUE, created_at TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS test_cases (id TEXT PRIMARY KEY, question_id TEXT NOT NULL REFERENCES questions(id) ON DELETE CASCADE, input TEXT, expected TEXT, weight DOUBLE PRECISION NOT NULL DEFAULT 1, created_at TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS executions (id TEXT PRIMARY KEY, question_id TEXT NOT NULL REFERENCES questions(id), model_id TEXT NOT NULL REFERENCES models(id), status TEXT NOT NULL, response TEXT, error TEXT, time_seconds DOUBLE PRECISION, tokens INTEGER, created_at TEXT NOT NULL, finished_at TEXT)",
        "CREATE TABLE IF NOT EXISTS results (id TEXT PRIMARY KEY, execution_id TEXT NOT NULL UNIQUE REFERENCES executions(id) ON DELETE CASCADE, score DOUBLE PRECISION, tests_passed INTEGER, tests_total INTEGER, evaluation_type TEXT NOT NULL, evaluator_details TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS scores (id TEXT PRIMARY KEY, result_id TEXT NOT NULL REFERENCES results(id) ON DELETE CASCADE, component TEXT NOT NULL, points DOUBLE PRECISION NOT NULL, max_points DOUBLE PRECISION NOT NULL, created_at TEXT NOT NULL)",
    ]
    with engine.begin() as db:
        for sql in ddl:
            db.execute(text(sql))
        for cid, name, limit_ in CATEGORIES:
            db.execute(text("INSERT INTO categories(id,name,question_limit) VALUES(:id,:name,:limit) ON CONFLICT(id) DO UPDATE SET name=EXCLUDED.name,question_limit=EXCLUDED.question_limit"), {"id": cid, "name": name, "limit": limit_})
        db.execute(text("INSERT INTO benchmarks(id,name,created_at) VALUES('default','AIBeigmer Core Benchmark',:created) ON CONFLICT(id) DO NOTHING"), {"created": now()})


# Do not execute database DDL while Python is importing the module. A transient DB
# outage must not kill Uvicorn and turn every request into a Cloudflare 502.
db_startup_error = None
@app.on_event("startup")
async def startup_database():
    global db_startup_error
    try:
        init_db()
        db_startup_error = None
    except Exception as exc:
        db_startup_error = str(exc)


class ProviderDiscoverIn(BaseModel):
    provider: str
    api_key: str = Field(min_length=1, repr=False)
    base_url: str = ""


class QuestionIn(BaseModel):
    id: str | None = None
    category: str
    title: str
    question: str
    difficulty: str = "medium"
    language: str | None = None
    requirements: list[str] = []
    evaluation_type: str = "manual_review"
    weight: float = 1
    active: bool = True


class TestCaseIn(BaseModel):
    input: str = ""
    expected: str
    weight: float = 1


class ExecutionIn(BaseModel):
    question_id: str
    model_id: str


class BenchmarkRunIn(BaseModel):
    model_id: str


def rows(sql, params=None):
    try:
        with engine.connect() as db:
            return [dict(r) for r in db.execute(text(sql), params or {}).mappings().all()]
    except Exception as exc:
        raise HTTPException(503, f"Base de dades no disponible: {exc}")


def one(sql, params=None):
    try:
        with engine.connect() as db:
            r = db.execute(text(sql), params or {}).mappings().first()
            return dict(r) if r else None
    except Exception as exc:
        raise HTTPException(503, f"Base de dades no disponible: {exc}")


@app.get("/api/health")
def health():
    try:
        with engine.connect() as db:
            db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok", "version": app.version}
    except Exception as exc:
        return {"status": "degraded", "database": "error", "error": str(exc), "version": app.version}


@app.get("/api/providers")
def providers():
    return [{"id": p.lower().replace(" ", "-"), "name": p} for p in PROVIDERS]


@app.get("/api/evaluation-types")
def evaluation_types():
    return EVALUATION_TYPES


@app.get("/api/categories")
def categories():
    return rows("SELECT id,name,question_limit AS question_count,active FROM categories ORDER BY id")


@app.get("/api/models")
def models():
    return rows("SELECT id,name,provider,model_id,description,context,active FROM models ORDER BY provider,name")


@app.get("/api/questions")
def questions(category: str | None = None):
    data = rows("SELECT * FROM questions WHERE active=TRUE AND (:category IS NULL OR category=:category) ORDER BY category,id", {"category": category})
    for q in data:
        q["requirements"] = json.loads(q.get("requirements") or "[]")
    return data


@app.get("/api/benchmarks")
def benchmarks():
    return rows("SELECT b.id,b.name,b.active,COUNT(q.id) AS questions,COUNT(q.id) FILTER (WHERE q.active=TRUE) AS active_questions FROM benchmarks b LEFT JOIN questions q ON TRUE GROUP BY b.id,b.name,b.active ORDER BY b.id")


@app.post("/api/questions", status_code=201)
def create_question(item: QuestionIn):
    if item.category not in {x[0] for x in CATEGORIES}:
        raise HTTPException(400, "Categoria no vàlida")
    if item.evaluation_type not in EVALUATION_TYPES:
        raise HTTPException(400, "Tipus d'avaluació no vàlid")
    qid = item.id or f"q-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
    with engine.begin() as db:
        db.execute(text("INSERT INTO questions(id,category,title,question,difficulty,language,requirements,evaluation_type,weight,active,created_at) VALUES(:id,:category,:title,:question,:difficulty,:language,:requirements,:evaluation_type,:weight,:active,:created_at)"), {**item.model_dump(), "id": qid, "requirements": json.dumps(item.requirements), "created_at": now()})
    return one("SELECT * FROM questions WHERE id=:id", {"id": qid})


@app.post("/api/questions/{question_id}/tests", status_code=201)
def add_test(question_id: str, item: TestCaseIn):
    if not one("SELECT id FROM questions WHERE id=:id", {"id": question_id}):
        raise HTTPException(404, "Pregunta no trobada")
    tid = f"t-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
    with engine.begin() as db:
        db.execute(text("INSERT INTO test_cases(id,question_id,input,expected,weight,created_at) VALUES(:id,:q,:input,:expected,:weight,:created_at)"), {"id": tid, "q": question_id, **item.model_dump(), "created_at": now()})
    return one("SELECT * FROM test_cases WHERE id=:id", {"id": tid})


URLS = {"OpenAI": "https://api.openai.com/v1/models", "DeepSeek": "https://api.deepseek.com/models", "Groq": "https://api.groq.com/openai/v1/models", "OpenRouter": "https://openrouter.ai/api/v1/models", "Anthropic": "https://api.anthropic.com/v1/models", "Google": "https://generativelanguage.googleapis.com/v1beta/models"}

def normal(s):
    return re.sub(r"[^a-z0-9]", "", str(s).lower())

async def free_catalog():
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get("https://freellmapi.co/models")
            r.raise_for_status()
            return [re.sub(r"\s+", " ", x).strip() for x in re.findall(r"<a[^>]*>([^<>]{2,100})</a>", r.text, re.I)]
    except Exception:
        return []

async def discover(item: ProviderDiscoverIn):
    if item.provider not in URLS:
        raise HTTPException(400, "Proveïdor no compatible per autodetecció")
    headers = {"Authorization": f"Bearer {item.api_key}"}; params = {}
    if item.provider == "Anthropic": headers = {"x-api-key": item.api_key, "anthropic-version": "2023-06-01"}
    if item.provider == "Google": headers, params = {}, {"key": item.api_key}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(URLS[item.provider], headers=headers, params=params)
            response.raise_for_status(); payload = response.json()
    except Exception as exc:
        raise HTTPException(502, f"No s'han pogut detectar els models: {exc}")
    data = payload.get("data", []) if isinstance(payload, dict) else payload.get("models", [])
    os.environ[PROVIDER_KEYS[item.provider]] = item.api_key
    catalog = await free_catalog(); added = []
    for raw in data if isinstance(data, list) else []:
        mid = str(raw.get("id") or raw.get("name") or "").removeprefix("models/").strip()
        name = str(raw.get("display_name") or raw.get("name") or mid)
        if not mid: continue
        if catalog and not any(normal(mid) in normal(c) or normal(c) in normal(mid) for c in catalog if len(normal(c)) >= 4): continue
        context = raw.get("context_length") or raw.get("context_window") or raw.get("input_token_limit")
        model = {"id": f"{item.provider.lower()}-{mid}", "name": name, "provider": item.provider, "model_id": mid, "description": "Detectat des del catàleg de models gratuïts", "context": context if isinstance(context, int) else None, "active": True, "created_at": now()}
        with engine.begin() as db:
            db.execute(text("INSERT INTO models(id,name,provider,model_id,description,context,active,created_at) VALUES(:id,:name,:provider,:model_id,:description,:context,:active,:created_at) ON CONFLICT(provider,model_id) DO UPDATE SET name=EXCLUDED.name,description=EXCLUDED.description,context=EXCLUDED.context,active=TRUE"), model)
        added.append(one("SELECT id,name,provider,model_id,description,context,active FROM models WHERE provider=:p AND model_id=:m", {"p": item.provider, "m": mid}))
    return {"provider": item.provider, "detected": len(data) if isinstance(data, list) else 0, "added": len(added), "models": added}

@app.post("/api/providers/discover")
async def discover_provider(item: ProviderDiscoverIn): return await discover(item)

@app.post("/api/models")
async def legacy_discover(item: ProviderDiscoverIn): return await discover(item)

@app.delete("/api/models/{model_id}")
def delete_model(model_id: str):
    with engine.begin() as db: result = db.execute(text("DELETE FROM models WHERE id=:id"), {"id": model_id})
    if not result.rowcount: raise HTTPException(404, "Model no trobat")
    return {"ok": True}

async def generate(model, prompt):
    provider = model["provider"]; key = os.getenv(PROVIDER_KEYS[provider])
    if not key: raise RuntimeError(f"Falta {PROVIDER_KEYS[provider]} al backend")
    async with httpx.AsyncClient(timeout=120) as client:
        if provider in {"OpenAI", "DeepSeek", "OpenRouter", "Groq"}:
            urls = {"OpenAI": "https://api.openai.com/v1/chat/completions", "DeepSeek": "https://api.deepseek.com/chat/completions", "OpenRouter": "https://openrouter.ai/api/v1/chat/completions", "Groq": "https://api.groq.com/openai/v1/chat/completions"}
            r = await client.post(urls[provider], headers={"Authorization": f"Bearer {key}"}, json={"model": model["model_id"], "messages": [{"role": "user", "content": prompt}], "temperature": 0}); r.raise_for_status(); data = r.json(); return data["choices"][0]["message"]["content"], data.get("usage", {}).get("total_tokens")
        if provider == "Anthropic":
            r = await client.post("https://api.anthropic.com/v1/messages", headers={"x-api-key": key, "anthropic-version": "2023-06-01"}, json={"model": model["model_id"], "max_tokens": 4096, "temperature": 0, "messages": [{"role": "user", "content": prompt}]}); r.raise_for_status(); data = r.json(); return "".join(x.get("text", "") for x in data.get("content", [])), data.get("usage", {}).get("input_tokens", 0) + data.get("usage", {}).get("output_tokens", 0)
        r = await client.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model['model_id']}:generateContent?key={key}", json={"contents": [{"parts": [{"text": prompt}]}]}); r.raise_for_status(); data = r.json(); return data["candidates"][0]["content"]["parts"][0]["text"], data.get("usageMetadata", {}).get("totalTokenCount")

def evaluate(q, answer):
    if q["evaluation_type"] == "json_validation":
        try: json.loads(answer); return {"score": 100.0, "passed": 1, "total": 1, "details": {"valid_json": True}}
        except json.JSONDecodeError as exc: return {"score": 0.0, "passed": 0, "total": 1, "details": {"valid_json": False, "error": str(exc)}}
    return {"score": None, "passed": None, "total": None, "details": {"status": "not_automatically_evaluable"}}

def persist_result(execution_id, evaluation):
    result_id = f"r-{execution_id}"
    with engine.begin() as db:
        db.execute(text("INSERT INTO results(id,execution_id,score,tests_passed,tests_total,evaluation_type,evaluator_details,created_at) SELECT :rid,e.id,:score,:passed,:total,q.evaluation_type,:details,:created FROM executions e JOIN questions q ON q.id=e.question_id WHERE e.id=:eid"), {"rid": result_id, "eid": execution_id, "score": evaluation["score"], "passed": evaluation["passed"], "total": evaluation["total"], "details": json.dumps(evaluation["details"]), "created": now()})
        if evaluation["score"] is not None: db.execute(text("INSERT INTO scores(id,result_id,component,points,max_points,created_at) VALUES(:id,:rid,'evaluation',:points,100,:created)"), {"id": f"s-{execution_id}", "rid": result_id, "points": evaluation["score"], "created": now()})

@app.post("/api/executions", status_code=201)
def create_execution(item: ExecutionIn):
    if not one("SELECT id FROM questions WHERE id=:id AND active=TRUE", {"id": item.question_id}): raise HTTPException(404, "Pregunta no trobada")
    if not one("SELECT id FROM models WHERE id=:id AND active=TRUE", {"id": item.model_id}): raise HTTPException(404, "Model no trobat o inactiu")
    eid = f"e-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
    with engine.begin() as db: db.execute(text("INSERT INTO executions(id,question_id,model_id,status,created_at) VALUES(:id,:q,:m,'pending',:created)"), {"id": eid, "q": item.question_id, "m": item.model_id, "created": now()})
    return one("SELECT * FROM executions WHERE id=:id", {"id": eid})

@app.post("/api/executions/{execution_id}/run")
async def run_execution(execution_id: str):
    execution = one("SELECT * FROM executions WHERE id=:id", {"id": execution_id})
    if not execution: raise HTTPException(404, "Execució no trobada")
    q = one("SELECT * FROM questions WHERE id=:id", {"id": execution["question_id"]}); model = one("SELECT * FROM models WHERE id=:id", {"id": execution["model_id"]}); start = perf_counter()
    with engine.begin() as db: db.execute(text("UPDATE executions SET status='running',error=NULL WHERE id=:id"), {"id": execution_id})
    try:
        answer, tokens = await generate(model, q["question"]); evaluation = evaluate(q, answer); elapsed = round(perf_counter() - start, 3)
        with engine.begin() as db: db.execute(text("UPDATE executions SET status='completed',response=:response,time_seconds=:time,tokens=:tokens,finished_at=:finished WHERE id=:id"), {"id": execution_id, "response": answer, "time": elapsed, "tokens": tokens, "finished": now()})
        persist_result(execution_id, evaluation)
    except Exception as exc:
        elapsed = round(perf_counter() - start, 3)
        with engine.begin() as db: db.execute(text("UPDATE executions SET status='error',error=:error,time_seconds=:time,finished_at=:finished WHERE id=:id"), {"id": execution_id, "error": str(exc), "time": elapsed, "finished": now()})
    return one("SELECT e.*,r.score,r.tests_passed,r.tests_total,r.evaluation_type,r.evaluator_details FROM executions e LEFT JOIN results r ON r.execution_id=e.id WHERE e.id=:id", {"id": execution_id})

@app.get("/api/executions")
def execution_list(question_id: str | None = None, model_id: str | None = None): return rows("SELECT e.*,r.score,r.tests_passed,r.tests_total,r.evaluation_type,r.evaluator_details FROM executions e LEFT JOIN results r ON r.execution_id=e.id WHERE (:q IS NULL OR e.question_id=:q) AND (:m IS NULL OR e.model_id=:m) ORDER BY e.created_at DESC", {"q": question_id, "m": model_id})

@app.get("/api/results")
def results(): return rows("SELECT r.*,e.question_id,e.model_id,e.response,e.time_seconds,e.tokens,e.error,e.created_at AS execution_created_at FROM results r JOIN executions e ON e.id=r.execution_id ORDER BY r.created_at DESC")

@app.get("/api/results/{result_id}")
def result(result_id: str):
    item = one("SELECT r.*,e.question_id,e.model_id,e.response,e.time_seconds,e.tokens,e.error FROM results r JOIN executions e ON e.id=r.execution_id WHERE r.id=:id", {"id": result_id})
    if not item: raise HTTPException(404, "Resultat no trobat")
    item["scores"] = rows("SELECT component,points,max_points FROM scores WHERE result_id=:id ORDER BY component", {"id": result_id}); return item

@app.get("/api/ranking")
def ranking(): return rows("SELECT m.id AS model_id,m.name,m.provider,AVG(r.score) FILTER (WHERE r.score IS NOT NULL) AS global_score,AVG(e.time_seconds) AS average_time,COUNT(r.id) AS evaluated_results FROM models m LEFT JOIN executions e ON e.model_id=m.id LEFT JOIN results r ON r.execution_id=e.id GROUP BY m.id,m.name,m.provider ORDER BY global_score DESC NULLS LAST")

@app.get("/api/stats")
def stats(): return {"executions": one("SELECT COUNT(*) AS n FROM executions")["n"], "scored_executions": one("SELECT COUNT(*) AS n FROM results WHERE score IS NOT NULL")["n"], "average_score": one("SELECT AVG(score) AS value FROM results WHERE score IS NOT NULL")["value"]}

@app.post("/api/benchmarks/default/run")
async def run_full_benchmark(item: BenchmarkRunIn):
    if not one("SELECT id FROM models WHERE id=:id AND active=TRUE", {"id": item.model_id}): raise HTTPException(404, "Model no trobat o inactiu")
    qs = rows("SELECT id FROM questions WHERE active=TRUE ORDER BY category,id"); results = []
    for q in qs:
        execution = create_execution(ExecutionIn(question_id=q["id"], model_id=item.model_id)); results.append(await run_execution(execution["id"]))
    scored = [r["score"] for r in results if r.get("score") is not None]
    return {"status": "completed", "model_id": item.model_id, "total": len(results), "scored": len(scored), "average_score": round(sum(scored) / len(scored), 2) if scored else None}
