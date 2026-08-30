import os,json,re
from datetime import datetime,timezone
from time import perf_counter
import httpx
from fastapi import FastAPI,HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel,Field
from sqlalchemy import text
from .database import engine

app=FastAPI(title='AIBeigmer API',version='0.9.0',description='AI benchmarking platform')
app.add_middleware(CORSMiddleware,allow_origins=['*'],allow_methods=['*'],allow_headers=['*'])
CATEGORIES=[('html','HTML',15),('css','CSS',20),('javascript','JavaScript',30),('python','Python',30),('sql','SQL',15),('backend','Backend',25),('debugging','Debugging',30),('algorithms','Algoritmes',25),('apis','APIs',15),('json','JSON',10),('linux','Linux',10),('git','Git',10)]
PROVIDERS=['OpenAI','Google','Anthropic','DeepSeek','OpenRouter','Groq','FreeLLMAPI']
PROVIDER_KEYS={p:p.upper().replace(' ','_')+'_API_KEY' for p in PROVIDERS}
EVALUATION_TYPES=['unit_tests','html_validation','css_validation','json_validation','text_match','static_analysis','llm_judge','manual_review']
FREE_CATALOG_URL='https://freellmapi.co/models'

with engine.begin() as db:
 db.execute(text('''CREATE TABLE IF NOT EXISTS models(id TEXT PRIMARY KEY,name TEXT NOT NULL,provider TEXT NOT NULL,model_id TEXT NOT NULL,description TEXT DEFAULT '',context INTEGER,active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL,UNIQUE(provider,model_id))'''))
 db.execute(text('''CREATE TABLE IF NOT EXISTS questions(id TEXT PRIMARY KEY,category TEXT NOT NULL,title TEXT NOT NULL,question TEXT NOT NULL,difficulty TEXT NOT NULL,language TEXT,requirements TEXT NOT NULL DEFAULT '[]',evaluation_type TEXT NOT NULL DEFAULT 'manual_review',weight REAL NOT NULL DEFAULT 1,active INTEGER NOT NULL DEFAULT 1,created_at TEXT NOT NULL)'''))

def load_models():
 with engine.connect() as db:return [dict(r) for r in db.execute(text('SELECT id,name,provider,model_id,description,context,active FROM models ORDER BY provider,name')).mappings().all()]
def save_model(m):
 with engine.begin() as db:db.execute(text('''INSERT INTO models(id,name,provider,model_id,description,context,active,created_at) VALUES(:id,:name,:provider,:model_id,:description,:context,:active,:created_at) ON CONFLICT(provider,model_id) DO UPDATE SET name=excluded.name,description=excluded.description,context=excluded.context,active=excluded.active'''),m)
 return next(x for x in load_models() if x['provider']==m['provider'] and x['model_id']==m['model_id'])
def load_questions():
 with engine.connect() as db:rows=db.execute(text('SELECT * FROM questions ORDER BY rowid')).mappings().all()
 return [{**dict(r),'requirements':json.loads(r['requirements'] or '[]'),'active':bool(r['active'])} for r in rows]

def seed_questions():
 # The initial benchmark is created automatically and every seeded question is active.
 with engine.connect() as db:count=db.execute(text('SELECT COUNT(*) FROM questions')).scalar_one()
 if count>=sum(x[2] for x in CATEGORIES):
  with engine.begin() as db:db.execute(text('UPDATE questions SET active=1'))
  return
 now=datetime.now(timezone.utc).isoformat();rows=[]
 prompts={'html':'Crea una solució HTML5 semàntica i accessible per al problema indicat.','css':'Crea una solució CSS moderna, responsive i accessible per al problema indicat.','javascript':'Resol el problema amb JavaScript modern, validant entrades i casos límit.','python':'Resol el problema amb Python de forma clara, robusta i eficient.','sql':'Escriu la consulta SQL correcta i considera casos límit i integritat de dades.','backend':'Dissenya la solució backend amb validació, errors i una API clara.','debugging':'Analitza el problema, explica la causa i proporciona una correcció robusta.','algorithms':'Implementa l’algoritme i indica la seva complexitat temporal i espacial.','apis':'Dissenya la petició i resposta de l’API, incloent errors i validació.','json':'Construeix el JSON sol·licitat respectant estrictament l’estructura indicada.','linux':'Proporciona les ordres Bash necessàries i explica breument el resultat.','git':'Proporciona les ordres Git necessàries per resoldre la situació.'}
 langs={'html':'HTML','css':'CSS','javascript':'JavaScript','python':'Python','sql':'SQL','backend':'Python','debugging':'Python','algorithms':'Python','apis':'HTTP','json':'JSON','linux':'Bash','git':'Git'}
 for cid,name,total in CATEGORIES:
  for i in range(1,total+1):
   difficulty='easy' if i<=total/3 else 'medium' if i<=2*total/3 else 'hard'
   rows.append({'id':f'{cid}-{i}','category':cid,'title':f'{name} — Prova {i}','question':f"{prompts[cid]}\nProva {i}: crea una implementació generalitzable i cobreix els casos límit.",'difficulty':difficulty,'language':langs[cid],'requirements':'[]','evaluation_type':'manual_review','weight':1,'active':1,'created_at':now})
 with engine.begin() as db:
  for q in rows:db.execute(text('''INSERT OR IGNORE INTO questions(id,category,title,question,difficulty,language,requirements,evaluation_type,weight,active,created_at) VALUES(:id,:category,:title,:question,:difficulty,:language,:requirements,:evaluation_type,:weight,:active,:created_at)'''),q)
  db.execute(text('UPDATE questions SET active=1'))
seed_questions()

class ProviderDiscoverIn(BaseModel):provider:str;api_key:str=Field(min_length=1,repr=False);base_url:str=''
class FreeLLMDiscoverIn(BaseModel):api_key:str=Field(min_length=1,repr=False);base_url:str='http://localhost:3001/v1'
class QuestionIn(BaseModel):category:str;title:str;question:str;difficulty:str='medium';language:str|None=None;requirements:list[str]=[];evaluation_type:str='manual_review';weight:float=1;active:bool=True
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
def models():return load_models()
@app.get('/api/questions')
def questions(category:str|None=None):return [q for q in load_questions() if q['active'] and (not category or q['category']==category)]
@app.get('/api/benchmarks')
def benchmarks():return [{'id':'default','name':'AIBeigmer Core Benchmark','categories':len(CATEGORIES),'questions':len(load_questions()),'active_questions':sum(q['active'] for q in load_questions())}]

async def free_catalog_names():
 try:
  async with httpx.AsyncClient(timeout=20) as c:r=await c.get(FREE_CATALOG_URL);r.raise_for_status();html=r.text
 except Exception as e:raise HTTPException(502,f'No s’ha pogut consultar FreeLLMAPI: {e}')
 return [re.sub(r'\s+',' ',x).strip() for x in re.findall(r'<a[^>]*>([^<>]{2,100})</a>',html,re.I) if x.strip()]
def norm(s):return re.sub(r'[^a-z0-9]','',str(s).lower())
def free_match(mid,name,catalog):
 vals=[norm(mid),norm(name)]
 for c in catalog:
  n=norm(c)
  if len(n)>=4 and any(n in v or v in n for v in vals):return c
 return None
@app.post('/api/providers/discover')
async def discover_provider(item:ProviderDiscoverIn):
 urls={'OpenAI':'https://api.openai.com/v1/models','DeepSeek':'https://api.deepseek.com/models','Groq':'https://api.groq.com/openai/v1/models','OpenRouter':'https://openrouter.ai/api/v1/models','Anthropic':'https://api.anthropic.com/v1/models','Google':'https://generativelanguage.googleapis.com/v1beta/models'}
 if item.provider not in urls:raise HTTPException(400,'Proveïdor no vàlid')
 catalog=await free_catalog_names();headers={'Authorization':f'Bearer {item.api_key}'};params={}
 if item.provider=='Anthropic':headers={'x-api-key':item.api_key,'anthropic-version':'2023-06-01'}
 if item.provider=='Google':headers={};params={'key':item.api_key}
 try:
  async with httpx.AsyncClient(timeout=30) as c:r=await c.get(urls[item.provider],headers=headers,params=params);r.raise_for_status();payload=r.json()
 except Exception as e:raise HTTPException(502,f'No s’han pogut detectar els models: {e}')
 data=payload.get('data',[]) if isinstance(payload,dict) else payload.get('models',[]);added=[];seen=set();os.environ[PROVIDER_KEYS[item.provider]]=item.api_key
 for raw in data if isinstance(data,list) else []:
  mid=str(raw.get('id') or raw.get('name') or '').removeprefix('models/').strip();name=str(raw.get('display_name') or raw.get('name') or mid)
  if not mid or mid in seen:continue
  seen.add(mid)
  if not free_match(mid,name,catalog):continue
  context=raw.get('context_length') or raw.get('context_window') or raw.get('input_token_limit');context=context if isinstance(context,int) else None
  added.append(save_model({'id':f'{item.provider.lower()}-{mid}','name':name,'provider':item.provider,'model_id':mid,'description':'Model gratuït detectat segons FreeLLMAPI','context':context,'active':True,'created_at':datetime.now(timezone.utc).isoformat()}))
 return {'provider':item.provider,'detected':len(data) if isinstance(data,list) else 0,'added':len(added),'models':added}
@app.post('/api/providers/freellmapi/discover')
async def discover_freellmapi(item:FreeLLMDiscoverIn):
 base=item.base_url.rstrip('/');base=base if base.endswith('/v1') else base+'/v1'
 try:
  async with httpx.AsyncClient(timeout=30) as c:r=await c.get(base+'/models',headers={'Authorization':f'Bearer {item.api_key}'});r.raise_for_status();payload=r.json()
 except Exception as e:raise HTTPException(502,f'No s’han pogut detectar els models: {e}')
 data=payload.get('data',[]) if isinstance(payload,dict) else [];os.environ['FREELLMAPI_API_KEY']=item.api_key;os.environ['FREELLMAPI_BASE_URL']=base;added=[]
 for raw in data if isinstance(data,list) else []:
  mid=str(raw.get('id','')).strip()
  if mid:added.append(save_model({'id':f'freellmapi-{mid}','name':raw.get('name') or mid,'provider':'FreeLLMAPI','model_id':mid,'description':'Model gratuït detectat automàticament','context':raw.get('context_length') or raw.get('context_window'),'active':True,'created_at':datetime.now(timezone.utc).isoformat()}))
 return {'provider':'FreeLLMAPI','total_detected':len(data) if isinstance(data,list) else 0,'added':len(added),'models':added}
@app.delete('/api/models/{model_id}')
def delete_model(model_id:str):
 with engine.begin() as db:r=db.execute(text('DELETE FROM models WHERE id=:id'),{'id':model_id})
 if not r.rowcount:raise HTTPException(404,'Model no trobat')
 return {'ok':True}

executions=[]
@app.post('/api/executions',status_code=201)
def create_execution(item:ExecutionIn):
 if not any(q['id']==item.question_id and q['active'] for q in load_questions()):raise HTTPException(404,'Pregunta no trobada')
 if not any(m['id']==item.model_id and m['active'] for m in load_models()):raise HTTPException(404,'Model no trobat o inactiu')
 x={'id':str(len(executions)+1),**item.model_dump(),'status':'pending','score':None,'created_at':datetime.now(timezone.utc).isoformat()};executions.append(x);return x
async def generate(model,prompt):
 p=model['provider'];key=os.getenv(PROVIDER_KEYS[p]);mid=model['model_id']
 if not key:raise RuntimeError(f'Falta {PROVIDER_KEYS[p]} al backend')
 async with httpx.AsyncClient(timeout=120) as c:
  if p in {'OpenAI','DeepSeek','OpenRouter','Groq','FreeLLMAPI'}:
   urls={'OpenAI':'https://api.openai.com/v1/chat/completions','DeepSeek':'https://api.deepseek.com/chat/completions','OpenRouter':'https://openrouter.ai/api/v1/chat/completions','Groq':'https://api.groq.com/openai/v1/chat/completions','FreeLLMAPI':os.getenv('FREELLMAPI_BASE_URL','http://localhost:3001/v1').rstrip('/')+'/chat/completions'};r=await c.post(urls[p],headers={'Authorization':f'Bearer {key}','Content-Type':'application/json'},json={'model':mid,'messages':[{'role':'user','content':prompt}],'temperature':0});r.raise_for_status();j=r.json();return j['choices'][0]['message']['content'],j.get('usage',{}).get('total_tokens')
  if p=='Anthropic':
   r=await c.post('https://api.anthropic.com/v1/messages',headers={'x-api-key':key,'anthropic-version':'2023-06-01'},json={'model':mid,'max_tokens':4096,'temperature':0,'messages':[{'role':'user','content':prompt}]});r.raise_for_status();j=r.json();return ''.join(x.get('text','') for x in j.get('content',[])),j.get('usage',{}).get('output_tokens')
  r=await c.post(f'https://generativelanguage.googleapis.com/v1beta/models/{mid}:generateContent?key={key}',json={'contents':[{'parts':[{'text':prompt}]}]});r.raise_for_status();j=r.json();return j['candidates'][0]['content']['parts'][0]['text'],j.get('usageMetadata',{}).get('totalTokenCount')
def evaluate(q,answer):
 if q['evaluation_type']=='json_validation':
  try:json.loads(answer);return 100,1,1
  except:return 0,0,1
 return None,None,None
@app.post('/api/executions/{execution_id}/run')
async def run_execution(execution_id:str):
 x=next((e for e in executions if e['id']==execution_id),None)
 if not x:raise HTTPException(404,'Execució no trobada')
 q=next(q for q in load_questions() if q['id']==x['question_id']);m=next(m for m in load_models() if m['id']==x['model_id']);x['status']='running';start=perf_counter()
 try:
  ans,tok=await generate(m,q['question']);score,passed,total=evaluate(q,ans);x.update({'status':'completed','response':ans,'time_seconds':round(perf_counter()-start,3),'tokens':tok,'tests_passed':passed,'tests_total':total,'score':score,'error':None})
 except Exception as e:x.update({'status':'error','time_seconds':round(perf_counter()-start,3),'error':str(e)})
 return x
@app.post('/api/benchmarks/default/run')
async def run_full_benchmark(item:BenchmarkRunIn):
 if not any(m['id']==item.model_id and m['active'] for m in load_models()):raise HTTPException(404,'Model no trobat o inactiu')
 qs=load_questions();results=[]
 for q in qs:
  e=create_execution(ExecutionIn(question_id=q['id'],model_id=item.model_id));results.append(await run_execution(e['id']))
 scores=[x['score'] for x in results if x.get('score') is not None];times=[x['time_seconds'] for x in results if x.get('time_seconds') is not None]
 return {'status':'completed','model_id':item.model_id,'total':len(qs),'completed':len(results),'scored':len(scores),'average_score':round(sum(scores)/len(scores),1) if scores else None,'average_time':round(sum(times)/len(times),3) if times else None,'results':results}
@app.get('/api/results')
def results():return executions
@app.get('/api/results/{result_id}')
def result(result_id:str):
 x=next((e for e in executions if e['id']==result_id),None)
 if not x:raise HTTPException(404,'Resultat no trobat')
 return x
@app.get('/api/ranking')
def ranking():
 out=[]
 for m in load_models():
  s=[e['score'] for e in executions if e.get('model_id')==m['id'] and e.get('score') is not None]
  if s:out.append({'model':m['name'],'score':round(sum(s)/len(s),1)})
 return sorted(out,key=lambda x:x['score'],reverse=True)
@app.get('/api/stats')
def stats():
 done=[e for e in executions if e.get('score') is not None];r=ranking();return {'average_score':round(sum(x['score'] for x in done)/len(done),1) if done else None,'leader':r[0]['model'] if r else None,'executions':len(executions),'fastest_model':None}
