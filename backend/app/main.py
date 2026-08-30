import os
from datetime import datetime, timezone
from time import perf_counter
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app=FastAPI(title='AIBeigmer API',version='0.3.0',description='AI benchmarking platform')
app.add_middleware(CORSMiddleware,allow_origins=['*'],allow_methods=['*'],allow_headers=['*'])
CATEGORIES=[('html','HTML',15),('css','CSS',20),('javascript','JavaScript',30),('python','Python',30),('sql','SQL',15),('backend','Backend',25),('debugging','Debugging',30),('algorithms','Algoritmes',25),('apis','APIs',15),('json','JSON',10),('linux','Linux',10),('git','Git',10)]
PROVIDERS=['OpenAI','Google','Anthropic','DeepSeek','OpenRouter','Groq'];models_store=[];questions_store=[];executions=[]
class ModelIn(BaseModel):
 name:str=Field(min_length=1,max_length=100);provider:str;model_id:str;description:str='';context:int|None=None;active:bool=True
class QuestionIn(BaseModel):
 category:str;title:str;question:str;difficulty:str='medium';language:str|None=None;requirements:list[str]=[];evaluation_type:str='manual_review';weight:float=1;active:bool=True
class ExecutionIn(BaseModel): question_id:str;model_id:str
@app.get('/api/health')
def health(): return {'status':'ok','service':'AIBeigmer'}
@app.get('/api/categories')
def categories(): return [{'id':i,'name':n,'question_count':c} for i,n,c in CATEGORIES]
@app.get('/api/providers')
def providers(): return [{'id':p.lower().replace(' ','-'),'name':p} for p in PROVIDERS]
@app.get('/api/models')
def models(): return models_store
@app.post('/api/models',status_code=201)
def create_model(item:ModelIn):
 if item.provider not in PROVIDERS: raise HTTPException(400,'Proveïdor no suportat')
 if any(m['model_id']==item.model_id and m['provider']==item.provider for m in models_store): raise HTTPException(409,'Aquest model ja existeix')
 model={'id':str(len(models_store)+1),**item.model_dump()};models_store.append(model);return model
@app.get('/api/questions')
def questions(category:str|None=None): return [q for q in questions_store if q.get('active',True) and (not category or q['category']==category)]
@app.post('/api/questions',status_code=201)
def create_question(item:QuestionIn):
 q={'id':str(len(questions_store)+1),**item.model_dump()};questions_store.append(q);return q
@app.get('/api/benchmarks')
def benchmarks(): return [{'id':'default','name':'AIBeigmer Core Benchmark','categories':len(CATEGORIES)}]
@app.get('/api/results')
def results(): return executions
@app.get('/api/results/{result_id}')
def result(result_id:str):
 for x in executions:
  if x['id']==result_id:return x
 raise HTTPException(404,'Resultat no trobat')
@app.post('/api/executions',status_code=201)
def create_execution(item:ExecutionIn):
 if not any(q['id']==item.question_id for q in questions_store): raise HTTPException(404,'Pregunta no trobada')
 if not any(m['id']==item.model_id and m.get('active',True) for m in models_store): raise HTTPException(404,'Model no trobat o inactiu')
 x={'id':str(len(executions)+1),**item.model_dump(),'status':'pending','score':None,'created_at':datetime.now(timezone.utc).isoformat()};executions.append(x);return x
async def generate(model,prompt):
 p=model['provider'];mid=model['model_id']
 keys={'OpenAI':os.getenv('OPENAI_API_KEY'),'DeepSeek':os.getenv('DEEPSEEK_API_KEY'),'OpenRouter':os.getenv('OPENROUTER_API_KEY'),'Groq':os.getenv('GROQ_API_KEY')}
 if p in keys:
  key=keys[p]
  if not key: raise RuntimeError(f'Falta {p.upper()}_API_KEY al backend')
  urls={'OpenAI':'https://api.openai.com/v1/chat/completions','DeepSeek':'https://api.deepseek.com/chat/completions','OpenRouter':'https://openrouter.ai/api/v1/chat/completions','Groq':'https://api.groq.com/openai/v1/chat/completions'}
  async with httpx.AsyncClient(timeout=120) as c:
   r=await c.post(urls[p],headers={'Authorization':f'Bearer {key}','Content-Type':'application/json'},json={'model':mid,'messages':[{'role':'user','content':prompt}]});r.raise_for_status();j=r.json()
  return j['choices'][0]['message']['content'],j.get('usage',{}).get('total_tokens')
 if p=='Anthropic':
  key=os.getenv('ANTHROPIC_API_KEY')
  if not key: raise RuntimeError('Falta ANTHROPIC_API_KEY al backend')
  async with httpx.AsyncClient(timeout=120) as c:
   r=await c.post('https://api.anthropic.com/v1/messages',headers={'x-api-key':key,'anthropic-version':'2023-06-01','content-type':'application/json'},json={'model':mid,'max_tokens':4096,'messages':[{'role':'user','content':prompt}]});r.raise_for_status();j=r.json()
  return ''.join(x.get('text','') for x in j.get('content',[])),j.get('usage',{}).get('input_tokens',0)+j.get('usage',{}).get('output_tokens',0)
 if p=='Google':
  key=os.getenv('GOOGLE_API_KEY')
  if not key: raise RuntimeError('Falta GOOGLE_API_KEY al backend')
  async with httpx.AsyncClient(timeout=120) as c:
   r=await c.post(f'https://generativelanguage.googleapis.com/v1beta/models/{mid}:generateContent?key={key}',json={'contents':[{'parts':[{'text':prompt}]}]});r.raise_for_status();j=r.json()
  return j['candidates'][0]['content']['parts'][0]['text'],j.get('usageMetadata',{}).get('totalTokenCount')
 raise RuntimeError(f'Proveïdor no implementat: {p}')
@app.post('/api/executions/{execution_id}/run')
async def run_execution(execution_id:str):
 x=next((e for e in executions if e['id']==execution_id),None)
 if not x: raise HTTPException(404,'Execució no trobada')
 q=next(q for q in questions_store if q['id']==x['question_id']);m=next(m for m in models_store if m['id']==x['model_id'])
 prompt=f"Ets un participant d'un benchmark de programació. Resol la prova de manera precisa. Categoria: {q['category']}. Dificultat: {q['difficulty']}. Requisits: {', '.join(q.get('requirements',[])) or 'Cap requisit addicional'}.\n\nPROVA:\n{q['question']}"
 x['status']='running';start=perf_counter()
 try:
  response,tokens=await generate(m,prompt);x.update({'status':'completed','response':response,'time_seconds':round(perf_counter()-start,3),'tokens':tokens,'tests_passed':None,'tests_total':None,'score':None,'error':None})
 except Exception as e:x.update({'status':'error','time_seconds':round(perf_counter()-start,3),'error':str(e)})
 return x
@app.get('/api/ranking')
def ranking():
 done=[e for e in executions if e.get('score') is not None];out=[]
 for m in models_store:
  s=[e['score'] for e in done if e['model_id']==m['id']]
  if s: out.append({'model':m['name'],'score':round(sum(s)/len(s),1)})
 return sorted(out,key=lambda x:x['score'],reverse=True)
@app.get('/api/stats')
def stats():
 done=[e for e in executions if e.get('score') is not None]
 return {'average_score':round(sum(e['score'] for e in done)/len(done),1) if done else None,'leader':None,'executions':len(executions),'fastest_model':None}
