"""Descriptive evidence from local files. Never imports or runs project code."""
import os
import re
import json
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit, quote
from inventory import SKIP, SOURCE_EXTENSIONS, CONFIG_ONLY, read_text, git_run, APP
from deployment_specs import deployment_specs

LANGUAGES = {'.py':'Python','.pyw':'Python','.js':'JavaScript','.jsx':'JavaScript',
 '.mjs':'JavaScript','.cjs':'JavaScript','.ts':'TypeScript','.tsx':'TypeScript',
 '.swift':'Swift','.go':'Go','.rs':'Rust','.java':'Java','.kt':'Kotlin','.cs':'C#',
 '.c':'C / C++','.h':'C / C++','.cpp':'C / C++','.hpp':'C / C++',
 '.html':'HTML','.htm':'HTML','.css':'CSS','.scss':'CSS','.sass':'CSS',
 '.vue':'Vue','.svelte':'Svelte','.rb':'Ruby','.php':'PHP','.dart':'Dart',
 '.sh':'Shell','.bash':'Shell','.zsh':'Shell','.sql':'SQL','.r':'R'}
IMPORTANT_DEPS = {'react','react-dom','next','vite','vue','svelte','@angular/core',
 'typescript','fastify','express','prisma','@prisma/client','pg','better-sqlite3',
 'fastapi','pydantic','sqlalchemy','streamlit','scikit-learn','numpy','pandas',
 'hdbscan','spacy','torch','supabase','@supabase/supabase-js','openai','vitest','pytest'}
DB_DEPS = {'pg':'PostgreSQL','psycopg':'PostgreSQL','psycopg2':'PostgreSQL',
 'psycopg2-binary':'PostgreSQL','better-sqlite3':'SQLite','sqlite3':'SQLite',
 'pymongo':'MongoDB','mongoose':'MongoDB','redis':'Redis','mysql2':'MySQL'}

def clean(text):
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'[*`]', '', text)
    return ' '.join(text.split())[:600]

def documented_sections(readme, source='README', usage_guide=False):
    sections=[]
    current=None
    fenced=False
    for line in readme.splitlines():
        if line.strip().startswith('```'):
            fenced=not fenced
            continue
        if fenced: continue
        heading=re.match(r'^(#{1,6})\s+(.+)',line)
        if heading:
            current={'heading':clean(heading[2]),'level':len(heading[1]),'lines':[]}
            sections.append(current)
        elif current:
            current['lines'].append(line)
    features=[]
    audience=None
    for s in sections:
        title=s['heading'].casefold()
        functional = re.search(r'fonctionnalit|ce que fait|ce que tu peux|ce qui fonctionne|features|périmètre mvp|ce que valide|utiliser l.application|^étape\s+\d',title)
        guide_section = usage_guide and re.search(r'explorer|se connecter|régler|contacter|écrans',title)
        if functional or guide_section:
            start=len(features)
            for line in s['lines']:
                match=re.match(r'^\s{0,3}(?:[-*+]|\d+[.)])\s+(.+)',line)
                if match and len(clean(match[1]))>8:
                    features.append({'text':clean(match[1]),'source':source+' · '+s['heading']})
            if len(features)==start and (guide_section or title.startswith('étape')):
                paragraph=next((clean(line) for line in s['lines'] if line.strip() and not line.lstrip().startswith(('#','|','>'))),'')
                features.append({'text':s['heading']+(' — '+paragraph if paragraph else ''),'source':source+' · '+s['heading']})
        if re.search(r'public vis|pour qui|audience|utilisateurs cibles',title):
            audience=clean(' '.join(s['lines'])) or None
    return features[:14],audience

def documented_limits(text,source):
    result=[]
    for paragraph in re.split(r'\n\s*\n',text):
        if (paragraph.lstrip().startswith('>') and re.search(r'état|limite|prototype',paragraph,re.I)):
            result.append({'text':clean(paragraph.lstrip('> ')),'source':source})
    for match in re.finditer(r'(?ms)^#{2,4}\s+([^\n]*(?:[Ll]imite|[Cc]e qui reste)[^\n]*)\n(.*?)(?=^#{1,4}\s|\Z)',text):
        paragraph=next((clean(p) for p in re.split(r'\n\s*\n',match[2]) if p.strip() and not p.lstrip().startswith('```')),'')
        if paragraph:result.append({'text':paragraph,'source':source+' · '+clean(match[1])})
    return result[:4]

def safe_version(value):
    text=str(value)
    return text[:80] if re.fullmatch(r'[\w\s.^~<>=!*+|,/-]+',text) and not text.startswith(('file:','git','http','/')) else 'Référence déclarée (URL masquée)'

def describe(path, project, all_projects):
    path=Path(path)
    others={Path(p['path']) for p in all_projects if p['id']!=project['id']}
    readme=read_text(path/project['readme'],100000) if project.get('readme') else ''
    features,audience=documented_sections(readme)
    limits=documented_limits(readme,project.get('readme') or 'README')
    if not features:
        guide=path/'docs/guide-utilisation.md'
        if guide.is_file() and not guide.is_symlink():
            text=read_text(guide,100000)
            features,_=documented_sections(text,'docs/guide-utilisation.md',usage_guide=True)
            limits.extend(documented_limits(text,'docs/guide-utilisation.md'))
    languages={}
    source_count=total_bytes=read_bytes=0
    physical=nonblank=tests=docs=0
    truncated=False
    warnings=[]
    screenshot_paths=[]
    manifests=[]
    source_examples=[]
    databases={}
    technical_files=[]
    def error(e): warnings.append(str(Path(e.filename).relative_to(path)) if e.filename else 'Dossier inaccessible')
    for root,dirs,files in os.walk(path,followlinks=False,onerror=error):
        current=Path(root)
        dirs[:]=sorted(d for d in dirs if (d not in SKIP or (current==path and d=='dist' and (path/'dist/index.html').is_file()))
                      and not d.startswith('.') and not (current/d).is_symlink()
                      and current/d not in others and current/d!=APP
                      and not d.endswith(('.git','.app','.xcodeproj','.xcworkspace')))
        for name in sorted(files):
            file=current/name
            if file.is_symlink() or name.startswith('.'): continue
            relative=str(file.relative_to(path))
            lower=name.lower()
            if (file.suffix.lower() in {'.md','.rst'} or 'compose' in lower or 'dockerfile' in lower):
                technical_files.append(file)
            if lower.endswith(('.md','.rst')): docs+=1
            if (name in {'package.json','pyproject.toml','requirements.txt','go.mod','Cargo.toml','Package.swift','pom.xml'}
                or lower.startswith('requirements') and lower.endswith('.txt')):
                manifests.append(file)
            ext=file.suffix.lower()
            if name=='schema.prisma':
                for match in re.finditer(r'provider\s*=\s*"(postgresql|sqlite|mysql|mongodb|sqlserver)"',read_text(file,30000)):
                    databases.setdefault(match[1],relative+' · provider')
            if ext in {'.png','.jpg','.jpeg','.webp'} and re.search(r'screenshot|capture|screen[-_]|maquette|preview|mockup',relative,re.I) and len(screenshot_paths)<6:
                try:
                    if file.stat().st_size<=15_000_000:screenshot_paths.append(relative)
                except OSError:pass
            if ext not in SOURCE_EXTENSIONS or lower in CONFIG_ONLY or '.config.' in lower or lower.endswith(('.min.js','.min.css')):
                continue
            try: size=file.stat().st_size
            except OSError: warnings.append(relative); continue
            if not size: continue
            source_count+=1
            total_bytes+=size
            lang=LANGUAGES.get(ext,ext.lstrip('.').upper())
            group=languages.setdefault(lang,{'language':lang,'files':0,'bytes':0,'lines':0,'nonblank':0})
            group['files']+=1;group['bytes']+=size
            is_test=bool(re.search(r'(^|/)(tests?|__tests__)(/|$)|Tests/|(^|/)(test_|.*[._](test|spec)\.)',relative))
            if is_test: tests+=1
            if len(source_examples)<8 and not is_test: source_examples.append(relative)
            if size>2_000_000 or read_bytes+size>20_000_000 or source_count>5000:
                truncated=True;continue
            text=read_text(file,2_000_001)
            if not text and size:
                warnings.append(relative);truncated=True
            read_bytes+=size
            lines=text.splitlines()
            count=len(lines); nb=sum(bool(line.strip()) for line in lines)
            physical+=count;nonblank+=nb;group['lines']+=count;group['nonblank']+=nb
            if re.search(r'^\s*(import sqlite3|from sqlite3\b)',text,re.M): databases.setdefault('SQLite',relative+' · import sqlite3')
            if file.suffix=='.prisma':
                for match in re.finditer(r'provider\s*=\s*"(postgresql|sqlite|mysql|mongodb|sqlserver)"',text):
                    databases.setdefault(match[1],relative+' · provider')
    dependencies=[]
    runtimes=[]
    for file in manifests:
        relative=str(file.relative_to(path));text=read_text(file,200000)
        if file.name=='package.json':
            try: pkg=json.loads(text)
            except (ValueError,TypeError):continue
            if not isinstance(pkg,dict):continue
            for section in ['dependencies','devDependencies']:
                declared=pkg.get(section) or {}
                if not isinstance(declared,dict):continue
                for name,value in declared.items():
                    dependencies.append({'name':name,'version':safe_version(value),'source':relative,'development':section=='devDependencies'})
                    if name in DB_DEPS:databases.setdefault(DB_DEPS[name],relative+' · '+name)
            for name,value in (pkg.get('engines') or {}).items():
                runtimes.append({'name':name,'version':safe_version(value),'source':relative+' · engines'})
        elif file.name=='go.mod':
            version=re.search(r'^go\s+([\d.]+)',text,re.M)
            if version:runtimes.append({'name':'Go','version':version[1],'source':relative})
        elif file.name=='Package.swift':
            version=re.search(r'swift-tools-version:\s*([\d.]+)',text)
            if version:runtimes.append({'name':'Swift tools','version':version[1],'source':relative})
        elif file.name=='pyproject.toml':
            version=re.search(r'requires-python\s*=\s*["\x27]([^"\x27]+)',text)
            if version:runtimes.append({'name':'Python','version':safe_version(version[1]),'source':relative})
            block=re.search(r'(?ms)^dependencies\s*=\s*\[(.*?)\]',text)
            if block:
                for spec in re.findall(r'["\x27]([^"\x27]+)["\x27]',block[1]):
                    add_python_dependency(spec,relative,dependencies,databases)
        elif file.name.startswith('requirements'):
            for spec in text.splitlines(): add_python_dependency(spec,relative,dependencies,databases)
    dependencies.sort(key=lambda d:(d['name'].lower() not in IMPORTANT_DEPS,d['development'],d['name'].lower(),d['source']))
    components=[]
    for folder,label in [('frontend','Interface web'),('backend','Backend / API'),('src','Sources applicatives'),
                         ('app','Application'),('ios','Client iOS'),('Sources','Sources Swift'),
                         ('workers','Traitements différés'),('ml','Modèles / machine learning'),
                         ('master','Composant master'),('slave','Composant slave'),
                         ('prisma','Schéma de données'),('supabase','Configuration Supabase')]:
        if (path/folder).is_dir() and path/folder not in others:
            components.append({'name':label,'source':folder+'/','evidence':'Dossier présent'})
    services=[]
    for name,pattern in [('Azure',r'\bAzure\b'),('Azure Foundry',r'\bFoundry\b'),('OpenAI',r'\bOpenAI\b'),
                         ('Ollama',r'\bOllama\b'),('Supabase',r'\bSupabase\b'),('Nginx',r'\bNginx\b'),
                         ('Docker Compose',r'docker compose|Docker Compose')]:
        if re.search(pattern,readme,re.I):services.append({'name':name,'source':project.get('readme'),'evidence':'Mentionné dans le README'})
    history={'count':None,'firstCommit':None,'shallow':False}
    if project['git'].get('commits'):
        code,value,_=git_run(path,'rev-list','--count','HEAD')
        if code==0 and value.strip().isdigit():history['count']=int(value.strip())
        code,value,_=git_run(path,'rev-parse','--is-shallow-repository')
        history['shallow']=code==0 and value.strip()=='true'
        code,value,_=git_run(path,'log','--reverse','--format=%cI','HEAD')
        if code==0 and value.strip():history['firstCommit']=value.splitlines()[0]
    label='Projet structuré' if source_count>=20 else 'Projet léger' if source_count<=5 else 'Ensemble de sources'
    evidence=[f'{source_count} fichiers de source repérés',f'{tests} fichiers de test repérés',f'{docs} documents Markdown / reStructuredText']
    return {'analyzedAt':datetime.now(timezone.utc).isoformat(), 'purpose':project['summary'],
            'purposeSource':project['summarySource'],'audience':audience,'features':features,'documentedLimits':limits[:4],
            'components':components,'dependencies':dependencies[:80], 'dependencyCount':len(dependencies),
            'deployment':deployment_specs(path,technical_files),
            'runtimes':runtimes,'databases':[{'name':name,'source':source} for name,source in databases.items()],
            'services':services,'history':history,'structure':{'label':label,'evidence':evidence},
            'code':{'files':source_count,'bytes':total_bytes,'lines':physical,'nonblank':nonblank,
                    'languages':sorted(languages.values(),key=lambda v:v['bytes'],reverse=True),
                    'tests':tests,'docs':docs,'examples':source_examples,'truncated':truncated},
            'screenshots':[{'path':p,'url':f'/api/projects/{project["id"]}/media?path={quote(p,safe="")}'} for p in screenshot_paths],
            'links':documented_links(readme,project.get('readme')),'warnings':warnings,
            'limits':'Analyse statique des fichiers locaux, sans exécuter l’application ni les tests. Les versions sont celles déclarées dans les manifestes. Les lignes physiques incluent commentaires et lignes vides. Dépendances, caches, sous-projets indépendants et builds générés exclus ; un export statique dist seul reste compté. Les fonctionnalités documentées ne prouvent pas leur bon fonctionnement.'}

def add_python_dependency(spec,source,dependencies,databases):
    if re.match(r'^\s*(?:https?://|git\+|file:|\.{1,2}/)',spec):return
    match=re.match(r'^\s*([A-Za-z][\w.-]*)(?:\[[^]]+\])?\s*([<>=!~][\w.,<>=!~*+-]*)?',spec)
    if not match or spec.strip().startswith(('#','-')):return
    name=match[1]
    dependencies.append({'name':name,'version':match[2] or 'Non précisée','source':source,'development':bool(re.search(r'dev|test',source,re.I))})
    if name in DB_DEPS:databases.setdefault(DB_DEPS[name],source+' · '+name)

def documented_links(readme,source):
    links=[];seen=set()
    for line in readme.splitlines():
        for raw in re.findall(r'https?://[^\s<>\)\]`"\x27]+',line):
            try:
                u=urlsplit(raw.rstrip('.,;'))
                if not u.hostname or u.username or u.password:continue
                local=u.hostname in {'localhost','127.0.0.1','0.0.0.0'}
                deployment=bool(re.search(r'URL|héberg|version en ligne|publi|domain|site|deployed',line,re.I))
                if not local and (not deployment or u.hostname.startswith(('github.','learn.','docs.','developer.'))):continue
                if local and u.path not in {'','/'}:continue
                url=urlunsplit((u.scheme,u.netloc,u.path,'',''))
                if url in seen:continue
                seen.add(url)
                links.append({'url':url,'kind':'Adresse locale documentée' if local else 'Adresse mentionnée','source':source})
            except ValueError:continue
    return links[:8]
