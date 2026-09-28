"""Collect AI-related official regulatory documents from Regulations.gov's public API."""
from __future__ import annotations

import argparse, concurrent.futures, csv, hashlib, io, json, re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from PyPDF2 import PdfReader

ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'data'/'processed'; RAW=ROOT/'data'/'raw'
API='https://api.regulations.gov/v4'; KEY='DEMO_KEY'
HEAD={'User-Agent':'AIPolicyDatasetBot/0.1 (public-policy research; respectful collection)'}
AI=re.compile(r'\b(artificial intelligence|machine learning|deep learning|generative ai|large language model|algorithmic|automated decision|autonomous system|neural network|computer vision|natural language processing)\b',re.I)
TYPES=('Rule','Proposed Rule','Notice','Guidance')
def clean(s): return re.sub(r'\s+',' ',s or '').strip()
def text(body,is_pdf):
 if is_pdf:return clean('\n'.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(body)).pages))
 s=BeautifulSoup(body,'html.parser');[x.decompose() for x in s(['script','style','noscript','svg'])];return clean(s.get_text(' ',strip=True))
def candidates(limit):
 found={}
 for typ in TYPES:
  page=1
  while True:
   data=requests.get(f'{API}/documents',params={'api_key':KEY,'filter[searchTerm]':'artificial intelligence','filter[documentType]':typ,'page[size]':250,'page[number]':page},headers=HEAD,timeout=40).json()
   for x in data.get('data',[]):found[x['id']]=x['attributes']
   m=data.get('meta',{}); 
   if not m.get('hasNextPage') or (limit and len(found)>=limit):break
   page+=1
 return list(found.items())[:limit or None]
def fetch(i,item):
 did,a=item
 try:
  d=requests.get(f'{API}/documents/{did}',params={'api_key':KEY},headers=HEAD,timeout=30).json()['data']['attributes']
  fs=d.get('fileFormats') or []; f=next((x for x in fs if x.get('format')=='pdf'),None) or next((x for x in fs if x.get('format')=='html'),None)
  if not f or f.get('size',0)>25_000_000:raise ValueError('no safe official content file')
  r=requests.get(f['fileUrl'],headers=HEAD,timeout=30);r.raise_for_status();body=r.content
  tx=text(body,f['format']=='pdf')
  if len(tx)<300 or not AI.search(tx):raise ValueError('no usable AI policy text')
  h=hashlib.sha256(body).hexdigest();pid=f'US-REGS-AI-{i:05d}';ext='.pdf' if f['format']=='pdf' else '.html';raw=RAW/f'{pid}__{h[:16]}{ext}';raw.write_bytes(body)
  return {'policy_id':pid,'title_original':d.get('title',''),'country_or_org':'United States','jurisdiction_level':'national','issuer':d.get('agencyId','US federal agency'),'policy_type':d.get('documentType',''),'legal_status':'unknown','published_date':(d.get('postedDate') or '')[:10],'language':'en','topics':'artificial intelligence','official_url':f'https://www.regulations.gov/document/{did}','official_url_final':r.url,'source_domain':urlparse(r.url).netloc,'content_sha256':h,'raw_file':str(raw.relative_to(ROOT)).replace('\\','/'),'fetched_at_utc':datetime.now(UTC).replace(microsecond=0).isoformat(),'fulltext_char_count':len(tx),'content_extraction_status':'extracted','content_summary_original':tx[:500],'verification_status':'verified_http'},None
 except Exception as e:return None,{'title_original':a.get('title',''),'official_url':f'https://www.regulations.gov/document/{did}','error':clean(str(e))}
def main():
 p=argparse.ArgumentParser();p.add_argument('--limit',type=int,default=0);p.add_argument('--workers',type=int,default=8);a=p.parse_args();OUT.mkdir(parents=True,exist_ok=True);RAW.mkdir(parents=True,exist_ok=True);cs=candidates(a.limit);rows=[];bad=[]
 with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as ex:
  for n,f in enumerate(concurrent.futures.as_completed([ex.submit(fetch,i,x) for i,x in enumerate(cs,1)]),1):
   r,b=f.result(); rows+= [r] if r else [];bad += [b] if b else []
   if n%25==0 or n==len(cs):print(f'[{n}/{len(cs)}] verified={len(rows)} failed={len(bad)}',flush=True)
 rows.sort(key=lambda x:x['policy_id'])
 for name,rs,fb in [('regulations_gov_verified.csv',rows,['policy_id','title_original','official_url']),('regulations_gov_failed.csv',bad,['title_original','official_url','error'])]:
  with (OUT/name).open('w',encoding='utf-8-sig',newline='') as o:w=csv.DictWriter(o,fieldnames=list(rs[0]) if rs else fb);w.writeheader();w.writerows(rs)
 print(json.dumps({'candidates':len(cs),'verified':len(rows),'failed':len(bad)}))
if __name__=='__main__':main()
