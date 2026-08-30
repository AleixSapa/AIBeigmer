from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="AIBeigmer API",
    version="0.1.0",
    description="Real AI model benchmarking platform",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

INITIAL_CATEGORIES = [
    {"id": "html", "name": "HTML", "question_count": 15},
    {"id": "css", "name": "CSS", "question_count": 20},
    {"id": "javascript", "name": "JavaScript", "question_count": 30},
    {"id": "python", "name": "Python", "question_count": 30},
    {"id": "sql", "name": "SQL", "question_count": 15},
    {"id": "backend", "name": "Backend", "question_count": 25},
    {"id": "debugging", "name": "Debugging", "question_count": 30},
    {"id": "algorithms", "name": "Algoritmes", "question_count": 25},
    {"id": "apis", "name": "APIs", "question_count": 15},
    {"id": "json", "name": "JSON", "question_count": 10},
    {"id": "linux", "name": "Linux", "question_count": 10},
    {"id": "git", "name": "Git", "question_count": 10},
]


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "AIBeigmer"}


@app.get("/api/categories")
def categories():
    return INITIAL_CATEGORIES


@app.get("/api/models")
def models():
    return []


@app.get("/api/providers")
def providers():
    return []


@app.get("/api/questions")
def questions():
    return []


@app.get("/api/benchmarks")
def benchmarks():
    return []


@app.get("/api/results")
def results():
    return []


@app.get("/api/ranking")
def ranking():
    return []


@app.get("/api/stats")
def stats():
    return {
        "average_score": None,
        "leader": None,
        "executions": 0,
        "fastest_model": None,
    }
