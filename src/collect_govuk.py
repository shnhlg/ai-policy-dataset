"""Collect AI-policy records from the public GOV.UK search API."""
from __future__ import annotations
import argparse, csv, hashlib, json, re, time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
from html_content import document_text

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data'/'processed'; RAW=ROOT/'data'/'raw'
API='https://www.gov.uk/api/search.json'
HEAD={'User-Agent':'AIPolicyDatasetBot/0.1 (public-policy research; respectful collection)'}
ALLOWED={'policy_paper','consultation','guidance','detailed_guide','statutory_guidance','strategy'}
AI_RE=re.compile(r'\bartificial intelligence\b|\bgenerative ai\b|\bmachine learning\b|\balgorithmic\b|\bAI\b',re.I)

def clean(s:str)->str:return re.sub(r'\s+',' ',s or '').strip()
def text(body:bytes)->str:
 return document_text(body)
def main()->int:
 p=argparse.ArgumentParser();p.add_argument('--limit',type=int,default=100);p.add_argument('--start',type=int,default=0);p.add_argument('--query',default='artificial intelligence');p.add_argument('--label',default='');p.add_argument('--append',action='store_true');p.add_argument('--pause',type=float,default=.4);a=p.parse_args()
 sess=requests.Session();sess.headers.update(HEAD); results=[];start=a.start
 while len(results)<a.limit:
  data=sess.get(API,params={'q':a.query,'count':100,'start':start},timeout=30).json()
  batch=data.get('results',[])
  if not batch:break
  for r in batch:
   blob=' '.join([r.get('title',''),r.get('description','')])
   if r.get('format') in ALLOWED and AI_RE.search(blob):results.append(r)
   if len(results)>=a.limit:break
  start+=len(batch)
  if start>=data.get('total',0):break
 rows=[]; failed=[]; RAW.mkdir(parents=True,exist_ok=True)
 for i,r in enumerate(results,1):
  url=urljoin('https://www.gov.uk',r['link'])
  try:
   resp=sess.get(url,timeout=30);resp.raise_for_status(); body=resp.content; full=text(body)
   if len(full)<300:raise requests.RequestException('No usable policy text')
   digest=hashlib.sha256(body).hexdigest(); label=(a.label or 'ai').upper(); pid=f'UK-MASS-{label}-{a.start+i:06d}'; raw=RAW/f'{pid}__{digest[:16]}.html';raw.write_bytes(body)
   soup=BeautifulSoup(body,'html.parser');date=(soup.select_one('time') or {}).get('datetime','') or r.get('public_timestamp','')
   rows.append({'policy_id':pid,'title_original':r.get('title',''),'country_or_org':'United Kingdom','jurisdiction_level':'national','issuer':'; '.join(o.get('title','') for o in r.get('organisations',[])),'policy_type':r.get('format',''),'legal_status':'unknown','published_date':date[:10],'language':'en','topics':'','official_url':url,'official_url_final':resp.url,'source_domain':urlparse(resp.url).netloc,'content_sha256':digest,'raw_file':str(raw.relative_to(ROOT)).replace('\\','/'),'fetched_at_utc':datetime.now(UTC).replace(microsecond=0).isoformat(),'fulltext_char_count':len(full),'content_extraction_status':'extracted','content_summary_original':full[:500],'verification_status':'verified_http'})
   print(f'[{i}/{len(results)}] OK {pid}')
  except requests.RequestException as e: failed.append({'title_original':r.get('title',''),'official_url':url,'error':clean(str(e))});print(f'[{i}/{len(results)}] FAIL {url}')
  time.sleep(a.pause)
 suffix=f'_{a.label}' if a.label else ''
 for name,records in [(f'govuk_verified{suffix}.csv',rows),(f'govuk_failed{suffix}.csv',failed)]:
  path=OUT/name
  if a.append and path.exists():
   with path.open(encoding='utf-8-sig',newline='') as f:
    existing=list(csv.DictReader(f))
   seen={x.get('official_url','') for x in existing}
   records=existing+[x for x in records if x.get('official_url','') not in seen]
  fields=list(records[0]) if records else ['title_original','official_url','error']
  with path.open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(records)
 print(json.dumps({'candidates':len(results),'verified':len(rows),'failed':len(failed)},ensure_ascii=False));return 0
if __name__=='__main__':raise SystemExit(main())
