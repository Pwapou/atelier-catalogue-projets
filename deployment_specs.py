"""Extract declared container specifications, never invoking Docker or project code."""
import json
import re
import shutil
import shlex
import subprocess
from pathlib import Path
from inventory import APP, read_text

def dockerfile_specs(path,source):
    text=read_text(path,300000)
    logical=re.sub(r'\\\s*\n',' ',text)
    bases=[];ports=[];stages=set();variables={}
    for line in logical.splitlines():
        line=line.strip()
        if line.startswith('#'):continue
        arg=re.match(r'ARG\s+([A-Za-z_][\w]*)(?:=(.*))?$',line,re.I)
        if arg:
            variables[arg[1]]=arg[2] or None
        match=re.match(r'FROM\s+(?:--platform=\S+\s+)?(\S+)(?:\s+AS\s+(\S+))?',line,re.I)
        if match:
            image,stage=match[1],match[2]
            bases.append({'image':image,'stage':stage,'source':source,'internalStage':image.lower() in stages})
            if stage:stages.add(stage.lower())
        match=re.match(r'EXPOSE\s+(.+)',line,re.I)
        if match:ports.extend(match[1].split())
    return {'source':source,'bases':bases,'exposedPorts':ports,
            'healthcheckDeclared':bool(re.search(r'^HEALTHCHECK\b',text,re.I|re.M)),
            'commandDeclared':bool(re.search(r'^(?:CMD|ENTRYPOINT)\b',text,re.I|re.M)),
            'arguments':[{'name':name,'hasDefault':value is not None} for name,value in variables.items()]}

def documented_images(file,source):
    result=[]
    known=r'(?:python|node|nginx|postgres|redis|mongo|mysql|mariadb|alpine|ubuntu|debian|traefik|caddy|busybox):[\w.+-]+'
    patterns=[r'\bimage:\s*[\x27"]?([\w${}./:@+-]+)',
              r'\bFROM\s+(?:--platform=\S+\s+)?([\w${}./:@+-]+)',
              r'\bdocker\s+pull\s+([\w${}./:@+-]+)',
              r'\bdocker\s+build\s+(?:[^\n]*?\s)?(?:-t|--tag)\s+([\w${}./:@+-]+)',
              r'\b(?:ghcr\.io|docker\.io|mcr\.microsoft\.com|[\w.-]+\.azurecr\.io)/[\w./-]+(?::[\w.+-]+)?(?:@sha256:[a-f0-9]+)?',
              known]
    for number,line in enumerate(read_text(file,150000).splitlines(),1):
        for pattern in patterns:
            for match in re.finditer(pattern,line,re.I):
                image=match[1] if match.lastindex else match[0]
                if len(image)>220 or image in {'AS','as','scratch'} or image.startswith(('http:','https:')):continue
                if '/' not in image and ':' not in image and '$' not in image:continue
                result.append({'image':image,'source':source,'line':number})
        image=docker_run_image(line)
        if image:result.append({'image':image,'source':source,'line':number})
    return result

def docker_run_image(line):
    match=re.search(r'\bdocker\s+run\s+(.+)',line)
    if not match:return None
    try:tokens=shlex.split(match[1].strip().strip('`'))
    except ValueError:return None
    arguments={'-p','--publish','-e','--env','--env-file','-v','--volume','--name','--network',
               '--user','-u','--workdir','-w','--entrypoint','--cpus','--memory','-m','--label','-l',
               '--hostname','--restart','--mount','--add-host','--pull','--platform'}
    switches={'-d','--detach','-i','--interactive','-t','--tty','-it','-ti','--rm','--init',
              '--read-only','--privileged'}
    i=0
    while i<len(tokens):
        value=tokens[i]
        if value in arguments:i+=2;continue
        if value in switches or value.startswith('--') and '=' in value:i+=1;continue
        if value.startswith('-'):return None
        return value if re.fullmatch(r'[\w][\w./-]*(?::[\w.+-]+)?(?:@sha256:[a-fA-F0-9]+)?',value) else None
    return None

def deployment_specs(path,files):
    path=Path(path)
    compose=[];dockerfiles=[];docs=[]
    for file in files:
        name=file.name.lower();relative=str(file.relative_to(path))
        if re.match(r'^(?:docker-)?compose(?:[.-][\w.-]+)?\.ya?ml$',name):compose.append((file,relative))
        if name=='dockerfile' or name.endswith('.dockerfile') or name.startswith('dockerfile.'):
            dockerfiles.append(dockerfile_specs(file,relative))
        if file.suffix.lower() in {'.md','.rst'}:docs.append((file,relative))
    warnings=[];configs=[]
    node=shutil.which('node')
    if compose and node:
        payload={'files':[{'source':s,'content':read_text(f,1_000_000)} for f,s in compose[:30]]}
        try:
            result=subprocess.run([node,str(APP/'parse_compose.mjs')],input=json.dumps(payload),capture_output=True,text=True,timeout=12)
            if result.returncode==0:configs=json.loads(result.stdout)
            else:warnings.append('Lecture Compose indisponible ; vérifier la dépendance locale yaml.')
        except (OSError,ValueError,subprocess.TimeoutExpired):warnings.append('Lecture Compose indisponible ou limite de temps atteinte.')
    elif compose:warnings.append('Node.js non disponible pour analyser les fichiers Compose.')
    if len(compose)>30:warnings.append('Les 30 premiers fichiers Compose sont analysés.')
    docs.sort(key=lambda pair:(pair[1].lower()!='readme.md',not bool(re.search(r'docker|deploy|architec|conteneur',pair[1],re.I)),pair[1]))
    images=[];seen=set()
    for file,source in docs[:40]:
        for image in documented_images(file,source):
            key=(image['image'],image['source'])
            if key not in seen:images.append(image);seen.add(key)
    return {'composeFiles':configs,'dockerfiles':dockerfiles,'documentedImages':images[:80],
            'composeFileCount':len(compose),'dockerfileCount':len(dockerfiles),'warnings':warnings,
            'limits':'Configuration déclarée uniquement : aucun conteneur exécuté ou inspecté, aucune image téléchargée. Chaque fichier Compose est présenté séparément, sans fusion des variantes ni substitution des variables. Les fichiers .env et env_file ne sont pas lus. Les valeurs d’environnement, arguments de build et commandes ne sont pas exposés. Les mentions documentaires peuvent être anciennes. Jusqu’à 30 Compose et 40 documents sont examinés.'}
