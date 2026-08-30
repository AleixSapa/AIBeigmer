from datetime import datetime, timezone
from time import perf_counter
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(title="AIBeigmer API", version="0.2.0", description="AI benchmarking platform")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

CATEGORIES=[
("html","HTML",15),("css","CSS",20),("javascript","JavaScript",30),("python","Python",30),
("sql","SQL",15),("backend","Backend",25),("debugging","Debugging",30),("algorithms","Algoritmes",25),
("apis","APIs",15),("json","JSON",10),("linux","Linux",10),("git","Git",10)]
PROVIDERS=["OpenAI","Google","Anthropic","DeepSeek","OpenRouter","Groq"]
models_store=[]
questions_store=[]
executions=[]

class ModelIn(BaseModel):
    name:str=Field(min_length=1,max_length=100); provider:str; model_id:str; description:str=""; context:int|None=None; active:bool=True
class QuestionIn(BaseModel):
    category:str; title:str; question:str; difficulty:str="medium"; language:str|None=None; requirements:list[str]=[]; evaluation_type:str="manual_review"; weight:float=1; active:bool=True
class ExecutionIn(BaseModel):
    question_id:str; model_id:str

@app.get("/api/health")
def health(): return {"status":"ok","service":"AIBeigmer"}
@app.get("/api/categories")
def categories(): return [{"id":i,"name":n,"question_count":c} for i,n,c in CATEGORIES]
@app.get("/api/providers")
def providers(): return [{"id":p.lower().replace(" ","-"),"name":p} for p in PROVIDERS]
@app.get("/api/models")
def models(): return models_store
@app.post("/api/models",status_code=201)
def create_model(item:ModelIn):
    model={"id":str(len(models_store)+1),**item.model_dump()};models_store.append(model);return model
@app.get("/api/questions")
def questions(category:str|None=None): return [q for q in questions_store if not category or q["category"]==category]
@app.post("/api/questions",status_code=201)
def create_question(item:QuestionIn):
    q={"id":str(len(questions_store)+1),**item.model_dump()};questions_store.append(q);return q
@app.get("/api/benchmarks")
def benchmarks(): return [{"id":"default","name":"AIBeigmer Core Benchmark","categories":len(CATEGORIES)}]
@app.get("/api/results")
def results(): return executions
@app.get("/api/results/{result_id}")
def result(result_id:str):
    for x in executions:
        if x["id"]==result_id:return x
    raise HTTPException(404,"Resultat no trobat")
@app.post("/api/executions",status_code=201)
def create_execution(item:ExecutionIn):
    if not any(q["id"]==item.question_id for q in questions_store): raise HTTPException(404,"Pregunta no trobada")
    if not any(m["id"]==item.model_id for m in models_store): raise HTTPException(404,"Model no trobat")
    x={"id":str(len(executions)+1),**item.model_dump(),"status":"pending","score":None,"created_at":datetime.now(timezone.utc).isoformat()};executions.append(x);return x
@app.get("/api/ranking")
def ranking(): return []
@app.get("/api/stats")
def stats(): return {"average_score":None,"leader":None,"executions":len(executions),"fastest_model":None}
