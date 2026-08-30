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

app=FastAPI(title='AIBeigmer API',version='0.8.0',description='AI benchmarking platform')
app.add_middleware(CORSMiddleware,allow_origins=['*'],allow_methods=['*'],allow_headers=['*'])
CATEGORIES=[('html','HTML',15),('css','CSS',20),('javascript','JavaScript',30),('python','Python',30),('sql','SQL',15),('backend','Backend',25),('debugging','Debugging',30),('algorithms','Algoritmes',25),('apis','APIs',15),('json','JSON',10),('linux','Linux',10),('git','Git',10)]
PROVIDERS=['OpenAI','Google','Anthropic','DeepSeek','OpenRouter','Groq','FreeLLMAPI']
PROVIDER_KEYS={'OpenAI':'OPENAI_API_KEY','DeepSeek':'DEEPSEEK_API_KEY','OpenRouter':'OPENROUTER_API_KEY','Groq':'GROQ_API_KEY','Anthropic':'ANTHROPIC_API_KEY','Google':'GOOGLE_API_KEY','FreeLLMAPI':'FREELLMAPI_API_KEY'}
EVALUATION_TYPES=['unit_tests','html_validation','css_validation','json_validation','text_match','static_analysis','llm_judge','manual_review']
FREE_CATALOG_URL='https://freellmapi.co/models'

# Persistent local SQLite database. API keys are never stored here.
with engine.begin() as db:
 db.execute(text('''CREATE TABLE IF NOT EXISTS models(id TEXT PRIMARY KEY,name TEXT NOT NULL,provider TEXT NOT NULL,model_id TEXT NOT NULL,description TEXT DEFAULT '',context INTEGER,active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,UNIQUE(provider,model_id))'''))
models_store=[];questions_store=[];executions=[]

def load_models():
 with engine.connect() as db:return [dict(r) for r in db.execute(text('SELECT id,name,provider,model_id,description,context,active FROM models ORDER BY rowid')).mappings().all()]
models_store=load_models()

def save_model(model):
 with engine.begin() as db:
  db.execute(text('''INSERT INTO models(id,name,provider,model_id,description,context,active,created_at) VALUES(:id,:name,:provider,:model_id,:description,:context,:active,:created_at) ON CONFLICT(provider,model_id) DO UPDATE SET name=excluded.name,description=excluded.description,context=excluded.context,active=excluded.active'''),model)
 return next((m for m in load_models() if m['provider']==model['provider'] and m['model_id']==model['model_id']),model)

def delete_saved_model(model_id):
 with engine.begin() as db:db.execute(text('DELETE FROM models WHERE id=:id'),{'id':model_id})

class ModelIn(BaseModel):
 name:str=Field(min_length=1,max_length=100);provider:str;model_id:str;api_key:str=Field(min_length=1,repr=False);description:str='';context:int|None=None;active:bool=True
class FreeLLMDiscoverIn(BaseModel):
 api_key:str=Field(min_length=1,repr=False);base_url:str='http://localhost:3001/v1'
class ProviderDiscoverIn(BaseModel):
 provider:str;api_key:str=Field(min_length=1,repr=False);base_url:str=''
class QuestionIn(BaseModel):
 category:str;title:str;question:str;difficulty:str='medium';language:str|None=None;requirements:list[str]=[];evaluation_type:str='manual_review';weight:float=1;active:bool=True
class ExecutionIn(BaseModel):question_id:str;model_id:str
class BenchmarkRunIn(BaseModel):model_id:str

@app.get('/api/health')
def health():return {'status':'ok','service':'AIBeigmer'}
@app.get('/api/categories')
def categories():return [{'id':i,'name':n,'question_count':c} for i,n,c in CATEGORIES]
@app.get('/api/providers')
def providers():return [{'id':p.lower().replace(' ','-'),'name':p} for p in PROVIDERS]
@app.get('/api/evaluation-types')
def evaluation_types():return EVALUATION_TYPES
@app.get('/api/models')
def models():
 global models_store;models_store=load_models();return models_store
@app.post('/api/models',status_code=201)
def create_model(item:ModelIn):
 if item.provider not in PROVIDERS:raise HTTPException(400,'Proveïdor no suportat')
 if any(m['model_id']==item.model_id and m['provider']==item.provider for m in load_models()):raise HTTPException(409,'Aquest model ja existeix')
 os.environ[PROVIDER_KEYS[item.provider]]=item.api_key
 data=item.model_dump(exclude={'api_key'});model={'id':f"{item.provider.lower()}-{item.model_id}",**data,'created_at':datetime.now(timezone.utc).isoformat()};saved=save_model(model);models_store=load_models();return saved

async def free_catalog_names():
 try:
  async with httpx.AsyncClient(timeout=20) as c:r=await c.get(FREE_CATALOG_URL);r.raise_for_status();html=r.text
 except Exception as e:raise HTTPException(502,f'No s’ha pogut consultar el catàleg de FreeLLMAPI: {e}')
 names=[]
 for x in re.findall(r'<a[^>]*>([^<>]{2,100})</a>',html,re.I):
  x=re.sub(r'\s+',' ',x).strip()
  if x and x.lower() not in {'models','pricing','github','go live'}:names.append(x)
 if not names:raise HTTPException(502,'El catàleg de FreeLLMAPI no ha retornat models')
 return names

def norm(s):return re.sub(r'[^a-z0-9]+','',str(s).lower())
def free_match(raw_id,raw_name,catalog):
 rid=norm(raw_id);rname=norm(raw_name);hay=[rid,rname]
 for family in catalog:
  f=norm(family)
  if len(f)<4:continue
  if any(f in h or h in f for h in hay):return family
 # Family-aware matching for IDs such as gpt-5-mini vs "GPT 5 Mini".
 tokens=[t for t in re.findall(r'[a-z]+|\d+(?:\.\d+)?',str(raw_id).lower()) if len(t)>1]
 for family in catalog:
  ft=[t for t in re.findall(r'[a-z]+|\d+(?:\.\d+)?',family.lower()) if len(t)>1]
  if ft and all(any(t in x for x in tokens) for t in ft):return family
 return None

def provider_models(provider,base_url):
 if provider=='OpenAI':return 'https://api.openai.com/v1/models','openai'
 if provider=='DeepSeek':return 'https://api.deepseek.com/models','deepseek'
 if provider=='Groq':return 'https://api.groq.com/openai/v1/models','groq'
 if provider=='OpenRouter':return 'https://openrouter.ai/api/v1/models','openrouter'
 if provider=='Anthropic':return 'https://api.anthropic.com/v1/models','anthropic'
 if provider=='Google':return 'https://generativelanguage.googleapis.com/v1beta/models','google'
 return base_url.rstrip('/')+'/models','generic'

@app.post('/api/providers/discover')
async def discover_provider(item:ProviderDiscoverIn):
 if item.provider not in PROVIDERS or item.provider=='FreeLLMAPI':raise HTTPException(400,'Aquest proveïdor utilitza el descobriment de FreeLLMAPI')
 catalog=await free_catalog_names();url,kind=provider_models(item.provider,item.base_url)
 headers={'Authorization':f'Bearer {item.api_key}'}
 params={}
 if kind=='anthropic':headers={'x-api-key':item.api_key,'anthropic-version':'2023-06-01'}
 if kind=='google':headers={};params={'key':item.api_key}
 try:
  async with httpx.AsyncClient(timeout=30) as c:
   r=await c.get(url,headers=headers,params=params);r.raise_for_status();payload=r.json()
 except Exception as e:raise HTTPException(502,f'No s’han pogut detectar els models de {item.provider}: {e}')
 data=payload.get('data',[]) if isinstance(payload,dict) else payload.get('models',[]) if isinstance(payload,dict) else []
 if not isinstance(data,list):raise HTTPException(502,'La resposta del proveïdor no té un catàleg vàlid')
 os.environ[PROVIDER_KEYS[item.provider]]=item.api_key
 added=[];seen=set()
 for raw in data:
  mid=str(raw.get('id') or raw.get('name','')).strip();mid=mid.removeprefix('models/')
  if not mid or mid in seen:continue
  seen.add(mid)
  display=str(raw.get('name') or raw.get('display_name') or mid).replace('models/','')
  family=free_match(mid,display,catalog)
  if not family:continue
  context=raw.get('context_length') or raw.get('context_window') or raw.get('input_token_limit') or raw.get('max_model_len')
  if not isinstance(context,int):context=None
  model={'id':f"{item.provider.lower()}-{mid}",'name':display,'provider':item.provider,'model_id':mid,'description':f'Gratuït segons el catàleg de FreeLLMAPI · {family}','context':context,'active':True,'created_at':datetime.now(timezone.utc).isoformat()}
  added.append(save_model(model))
 global models_store;models_store=load_models()
 return {'provider':item.provider,'catalog_source':FREE_CATALOG_URL,'provider_models':len(data),'added':len(added),'models':added}

@app.post('/api/providers/freellmapi/discover')
async def discover_freellmapi(item:FreeLLMDiscoverIn):
 base=item.base_url.rstrip('/');base=base if base.endswith('/v1') else base+'/v1'
 try:
  async with httpx.AsyncClient(timeout=30) as c:r=await c.get(base+'/models',headers={'Authorization':f'Bearer {item.api_key}'});r.raise_for_status();payload=r.json()
 except Exception as e:raise HTTPException(502,f'No s’han pogut detectar els models de FreeLLMAPI: {e}')
 data=payload.get('data',[]) if isinstance(payload,dict) else []
 if not isinstance(data,list):raise HTTPException(502,'La resposta de FreeLLMAPI no té un catàleg vàlid')
 os.environ['FREELLMAPI_API_KEY']=item.api_key;os.environ['FREELLMAPI_BASE_URL']=base;added=[]
 for raw in data:
  mid=str(raw.get('id','')).strip()
  if not mid:continue
  model={'id':f'freellmapi-{mid}','name':raw.get('name') or mid,'provider':'FreeLLMAPI','model_id':mid,'description':'Model gratuït detectat automàticament per FreeLLMAPI','context':raw.get('context_length') or raw.get('context_window') or raw.get('max_model_len'),'active':True,'created_at':datetime.now(timezone.utc).isoformat()};added.append(save_model(model))
 global models_store;models_store=load_models();return {'provider':'FreeLLMAPI','base_url':base,'total_detected':len(data),'added':len(added),'models':added}

@app.patch('/api/models/{model_id}')
def update_model(model_id:str,item:ModelIn):
 if item.provider not in PROVIDERS:raise HTTPException(400,'Proveïdor no suportat')
 if not any(m['id']==model_id for m in load_models()):raise HTTPException(404,'Model no trobat')
 os.environ[PROVIDER_KEYS[item.provider]]=item.api_key;data=item.model_dump(exclude={'api_key'});data['id']=model_id;data['created_at']=datetime.now(timezone.utc).isoformat();save_model(data);return next(m for m in load_models() if m['id']==model_id)
@app.delete('/api/models/{model_id}')
def delete_model(model_id:str):
 if not any(m['id']==model_id for m in load_models()):raise HTTPException(404,'Model no trobat')
 delete_saved_model(model_id);return {'ok':True}
@app.get('/api/questions')
def questions(category:str|None=None):return [q for q in questions_store if q.get('active',True) and (not category or q['category']==category)]
@app.post('/api/questions',status_code=201)
def create_question(item:QuestionIn):
 if item.evaluation_type not in EVALUATION_TYPES:raise HTTPException(400,'Tipus d’avaluació no suportat')
 q={'id':str(len(questions_store)+1),**item.model_dump()};questions_store.append(q);return q
@app.get('/api/benchmarks')
def benchmarks():return [{'id':'default','name':'AIBeigmer Core Benchmark','categories':len(CATEGORIES)}]
@app.get('/api/results')
def results():return executions
@app.get('/api/results/{result_id}')
def result(result_id:str):
 x=next((e for e in executions if e['id']==result_id),None)
 if not x:raise HTTPException(404,'Resultat no trobat')
 return x
@app.post('/api/executions',status_code=201)
def create_execution(item:ExecutionIn):
 if not any(q['id']==item.question_id and q.get('active',True) for q in questions_store):raise HTTPException(404,'Pregunta no trobada')
 if not any(m['id']==item.model_id and m.get('active',True) for m in load_models()):raise HTTPException(404,'Model no trobat o inactiu')
 x={'id':str(len(executions)+1),**item.model_dump(),'status':'pending','score':None,'created_at':datetime.now(timezone.utc).isoformat()};executions.append(x);return x
async def generate(model,prompt):
 p=model['provider'];mid=model['model_id'];key=os.getenv(PROVIDER_KEYS[p])
 if not key:raise RuntimeError(f'Falta {PROVIDER_KEYS[p]} al backend')
 async with httpx.AsyncClient(timeout=120) as c:
  if p in {'OpenAI','DeepSeek','OpenRouter','Groq','FreeLLMAPI'}:
   urls={'OpenAI':'https://api.openai.com/v1/chat/completions','DeepSeek':'https://api.deepseek.com/chat/completions','OpenRouter':'https://openrouter.ai/api/v1/chat/completions','Groq':'https://api.groq.com/openai/v1/chat/completions','FreeLLMAPI':os.getenv('FREELLMAPI_BASE_URL','http://localhost:3001/v1').rstrip('/')+'/chat/completions'};r=await c.post(urls[p],headers={'Authorization':f'Bearer {key}','Content-Type':'application/json'},json={'model':mid,'messages':[{'role':'system','content':'Resolve la prova del benchmark amb precisió. Retorna només la resposta demanada.'},{'role':'user','content':prompt}],'temperature':0});r.raise_for_status();j=r.json();return j['choices'][0]['message']['content'],j.get('usage',{}).get('total_tokens')
  if p=='Anthropic':
   r=await c.post('https://api.anthropic.com/v1/messages',headers={'x-api-key':key,'anthropic-version':'2023-06-01','content-type':'application/json'},json={'model':mid,'max_tokens':4096,'temperature':0,'messages':[{'role':'user','content':prompt}]});r.raise_for_status();j=r.json();return ''.join(x.get('text','') for x in j.get('content',[])),j.get('usage',{}).get('input_tokens',0)+j.get('usage',{}).get('output_tokens',0)
  r=await c.post(f'https://generativelanguage.googleapis.com/v1beta/models/{mid}:generateContent?key={key}',json={'contents':[{'parts':[{'text':prompt}]}],'generationConfig':{'temperature':0}});r.raise_for_status();j=r.json();return j['candidates'][0]['content']['parts'][0]['text'],j.get('usageMetadata',{}).get('totalTokenCount')
def evaluate(q,answer):
 kind=q.get('evaluation_type','manual_review');req=q.get('requirements') or []
 if kind=='json_validation':
  try:json.loads(answer);return 100,1,1
  except:return 0,0,1
 if kind=='text_match':
  if not req:return None,None,None
  hits=sum(1 for r in req if r.lower() in answer.lower());return round(hits/len(req)*100),hits,len(req)
 if kind in {'html_validation','css_validation','static_analysis'}:
  if not req:return None,None,None
  hits=sum(1 for r in req if r.lower() in answer.lower());return round(hits/len(req)*100),hits,len(req)
 return None,None,None
@app.post('/api/executions/{execution_id}/run')
async def run_execution(execution_id:str):
 x=next((e for e in executions if e['id']==execution_id),None)
 if not x:raise HTTPException(404,'Execució no trobada')
 q=next((q for q in questions_store if q['id']==x['question_id']),None);m=next((m for m in load_models() if m['id']==x['model_id']),None)
 if not q or not m:raise HTTPException(404,'Pregunta o model no trobat')
 prompt=f"Categoria: {q['category']}\nDificultat: {q['difficulty']}\nLlenguatge: {q.get('language') or 'general'}\nRequisits: {', '.join(q.get('requirements') or []) or 'cap'}\nTipus d'avaluació: {q.get('evaluation_type','manual_review')}\n\nPROVA:\n{q['question']}";x['status']='running';start=perf_counter()
 try:
  response,tokens=await generate(m,prompt);score,passed,total=evaluate(q,response);x.update({'status':'completed','response':response,'time_seconds':round(perf_counter()-start,3),'tokens':tokens,'tests_passed':passed,'tests_total':total,'score':score,'evaluation_type':q.get('evaluation_type'),'error':None})
 except Exception as e:x.update({'status':'error','time_seconds':round(perf_counter()-start,3),'error':str(e)})
 return x
@app.post('/api/benchmarks/default/run')
async def run_full_benchmark(item:BenchmarkRunIn):
 m=next((m for m in load_models() if m['id']==item.model_id and m.get('active',True)),None)
 if not m:raise HTTPException(404,'Model no trobat o inactiu')
 qs=[q for q in questions_store if q.get('active',True)]
 if not qs:raise HTTPException(400,'No hi ha preguntes actives al benchmark')
 results=[]
 for q in qs:created=create_execution(ExecutionIn(question_id=q['id'],model_id=m['id']));results.append(await run_execution(created['id']))
 scores=[r['score'] for r in results if r.get('score') is not None];times=[r['time_seconds'] for r in results if r.get('time_seconds') is not None]
 return {'status':'completed','model_id':m['id'],'model':m['name'],'total':len(qs),'completed':len(results),'scored':len(scores),'average_score':round(sum(scores)/len(scores),1) if scores else None,'average_time':round(sum(times)/len(times),3) if times else None,'results':results}
@app.get('/api/ranking')
def ranking():
 out=[]
 for m in load_models():
  s=[e['score'] for e in executions if e.get('model_id')==m['id'] and e.get('score') is not None]
  if s:out.append({'model':m['name'],'score':round(sum(s)/len(s),1)})
 return sorted(out,key=lambda x:x['score'],reverse=True)
@app.get('/api/stats')
def stats():
 done=[e for e in executions if e.get('score') is not None];ranked=ranking();return {'average_score':round(sum(e['score'] for e in done)/len(done),1) if done else None,'leader':ranked[0]['model'] if ranked else None,'executions':len(executions),'fastest_model':None}
