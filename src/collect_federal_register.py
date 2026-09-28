"""Collect AI-related U.S. Federal Register documents with full official text."""
from __future__ import annotations
import argparse,csv,hashlib,json,re,time
from datetime import UTC,datetime
from pathlib import Path
from urllib.parse import urlparse
import io,requests
from bs4 import BeautifulSoup
from PyPDF2 import PdfReader
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'data'/'processed'; RAW=ROOT/'data'/'raw'
HEAD={'User-Agent':'AIPolicyDatasetBot/0.1 (public-policy research; respectful collection)'}
AI_RE=re.compile(r'\b(artificial intelligence|machine learning|deep learning|generative ai|large language model|neural network|computer vision|natural language processing|algorithm(?:s|ic)?|automated decision|automated system|autonomous(?: system| vehicle)?|machine vision|expert system|decision support|robotic(?:s)?|predictive analytics|predictive model|data mining|data science|automation|facial recognition|biometric(?:s| identification)?)\b',re.I)
def clean(v):return re.sub(r'\s+',' ',v or '').strip()
def gettext(b):
 s=BeautifulSoup(b,'html.parser');[x.decompose() for x in s(['script','style','noscript','svg'])];return clean(s.get_text(' ',strip=True))
def main():
 p=argparse.ArgumentParser();p.add_argument('--limit',type=int,default=50);p.add_argument('--page',type=int,default=1);p.add_argument('--term',default='artificial intelligence');p.add_argument('--label',default='');p.add_argument('--append',action='store_true');a=p.parse_args();s=requests.Session();s.headers.update(HEAD)
 d=s.get('https://www.federalregister.gov/api/v1/documents.json',params={'conditions[term]':a.term,'per_page':100,'page':a.page},timeout=30).json(); cand=d['results'][:a.limit]; rows=[];bad=[];RAW.mkdir(parents=True,exist_ok=True)
 for i,x in enumerate(cand,1):
  u=x['html_url']; pdf=x.get('pdf_url')
  try:
   r=s.get(pdf or u,timeout=3,stream=True);r.raise_for_status()
   if int(r.headers.get('content-length','0') or 0)>3_000_000:raise requests.RequestException('Source file exceeds 3 MB extraction safety limit')
   body=r.content
   if len(body)>3_000_000:raise requests.RequestException('Source file exceeds 3 MB extraction safety limit')
   tx=clean('\n'.join(page.extract_text() or '' for page in PdfReader(io.BytesIO(body)).pages[:100])) if pdf else gettext(body)
   if len(tx)<300:raise requests.RequestException('No usable policy text')
   if not AI_RE.search(tx):raise requests.RequestException('Document text is not AI-related')
   h=hashlib.sha256(body).hexdigest();label=(a.label or 'ai').upper();pid=f'US-FR-{label}-{a.page:03d}-{i:04d}';raw=RAW/f"{pid}__{h[:16]}{'.pdf' if pdf else '.html'}";raw.write_bytes(body)
   rows.append({'policy_id':pid,'title_original':x['title'],'country_or_org':'United States','jurisdiction_level':'national','issuer':'; '.join(z.get('name','') for z in x.get('agencies',[])),'policy_type':x.get('type',''),'legal_status':'unknown','published_date':x.get('publication_date',''),'language':'en','topics':'','official_url':u,'official_url_final':r.url,'source_domain':urlparse(r.url).netloc,'content_sha256':h,'raw_file':str(raw.relative_to(ROOT)).replace('\\','/'),'fetched_at_utc':datetime.now(UTC).replace(microsecond=0).isoformat(),'fulltext_char_count':len(tx),'content_extraction_status':'extracted','content_summary_original':tx[:500],'verification_status':'verified_http'})
   print(f'[{i}/{len(cand)}] OK {pid}')
  except requests.RequestException as e:bad.append({'title_original':x.get('title',''),'official_url':u,'error':clean(str(e))})
  time.sleep(.12)
 suffix=f'_{a.label}' if a.label else ''
 for n,rs in [(f'federal_register_verified{suffix}.csv',rows),(f'federal_register_failed{suffix}.csv',bad)]:
  path=OUT/n
  if a.append and path.exists():
   with path.open(encoding='utf-8-sig',newline='') as f:
    existing=list(csv.DictReader(f))
   seen={x.get('official_url','') for x in existing}
   rs=existing+[x for x in rs if x.get('official_url','') not in seen]
  fs=list(rs[0]) if rs else ['title_original','official_url','error'];
  with path.open('w',encoding='utf-8-sig',newline='') as f:w=csv.DictWriter(f,fieldnames=fs);w.writeheader();w.writerows(rs)
 print(json.dumps({'candidates':len(cand),'verified':len(rows),'failed':len(bad)}));
if __name__=='__main__':main()
