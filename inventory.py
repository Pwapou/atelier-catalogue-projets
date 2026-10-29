"""Read-only local project discovery and Git metadata. Standard library only."""
import concurrent.futures
import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

HOME = Path.home()
APP = Path(__file__).resolve().parent
GIT_BINARY = next((p for p in ['/Library/Developer/CommandLineTools/usr/bin/git', shutil.which('git')]
                   if p and Path(p).is_file()), 'git')
SKIP = {'node_modules', 'venv', '.venv', 'env', '__pycache__', 'vendor', 'build', 'dist',
        'target', 'Pods', 'DerivedData', 'site-packages', '.git', '.next', '.cache',
        'data', 'datasets', 'backups', 'backup', 'models', 'artifacts', 'output',
        'outputs', 'coverage', '.output', 'Library', 'Applications', 'Pictures',
        'Music', 'Movies', 'Virtual Machines.localized', 'Bibliothèque calibre',
        'Public'}
MARKERS = {'package.json', 'pyproject.toml', 'go.mod', 'Cargo.toml', 'requirements.txt',
           'pom.xml', 'Package.swift', 'docker-compose.yml', 'compose.yaml', 'compose.yml',
           'CMakeLists.txt', 'pubspec.yaml'}
COMPONENTS = {'frontend', 'backend', 'api', 'src', 'app', 'apps', 'ml', 'workers', 'ios',
              'android', 'design', 'refont', 'docs', 'tests', 'scripts', 'tools', 'examples',
              'fixtures', 'master', 'slave', 'shared', 'labs', 'packages', 'public', 'assets', 'docker', 'infra'}
SOURCE_EXTENSIONS = {'.py', '.pyw', '.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs',
                     '.go', '.rs', '.swift', '.java', '.kt', '.kts', '.cs', '.fs',
                     '.c', '.h', '.cc', '.cpp', '.hpp', '.m', '.mm', '.rb', '.php',
                     '.html', '.htm', '.css', '.scss', '.sass', '.less', '.vue',
                     '.svelte', '.dart', '.r', '.sql', '.sh', '.bash', '.zsh',
                     '.lua', '.pl', '.ex', '.exs', '.erl', '.hs', '.clj', '.elm'}
CONFIG_ONLY = {'package.swift', 'next-env.d.ts', 'postcss.config.js', 'postcss.config.mjs',
               'tailwind.config.js', 'tailwind.config.ts', 'eslint.config.js',
               'eslint.config.mjs', 'vite.config.js', 'vite.config.ts', 'vitest.config.ts',
               'next.config.js', 'next.config.mjs', 'next.config.ts', 'setup.py', 'conftest.py'}
SYSTEM_LOCATIONS = {Path(p) for p in ['/System', '/Library', '/usr', '/private', '/dev',
                    '/bin', '/sbin', '/cores', '/Network', '/opt/homebrew']}

def mac_locations():
    """Return configured project locations; default to common folders in this account."""
    env_roots = os.environ.get('ATELIER_SCAN_ROOTS')
    if env_roots is not None:
        configured = env_roots.split(os.pathsep)
    else:
        settings = APP/'atelier.settings.json'
        try:
            configured = json.loads(read_text(settings, 100000)).get('scan_roots')
            if not isinstance(configured, list) or not all(isinstance(p, str) for p in configured):
                configured = None
        except (ValueError, AttributeError):
            configured = None
    if configured is None:
        configured = ['~/Documents', '~/Projects', '~/dev', '~/Desktop', '~/Downloads']
    roots = []
    for item in configured:
        path = Path(item).expanduser()
        if not path.is_absolute():
            path = HOME/path
        path = path.resolve()
        if path not in roots:
            roots.append(path)
    return roots

def walk_locations(roots, onerror):
    for base in roots:
        for root, dirs, files in os.walk(base, followlinks=False, onerror=onerror):
            p = Path(root)
            dirs[:] = [d for d in dirs if p/d not in SYSTEM_LOCATIONS]
            if p == Path('/usr/local'):
                dirs[:] = [d for d in dirs if d not in {'bin', 'lib', 'include', 'share',
                           'Cellar', 'Caskroom', 'Homebrew', 'Frameworks', 'ykman'}]
            yield base, root, dirs, files

def contains_source(candidate, project_roots, onerror=None):
    """Require real, nonempty source owned by this project, not a nested project."""
    path = candidate['path']
    for root, dirs, files in os.walk(path, followlinks=False, onerror=onerror):
        p = Path(root)
        dirs[:] = [d for d in dirs
                   if (d not in SKIP or (p == path and d == 'dist' and candidate['static']))
                   and not d.startswith('.') and not (p/d).is_symlink()
                   and (p/d) not in project_roots and (p/d).resolve() != APP
                   and not d.endswith(('.git', '.app', '.xcodeproj', '.xcworkspace'))]
        for name in files:
            file = p/name
            lower = name.lower()
            if lower in CONFIG_ONLY or '.config.' in lower or lower.endswith(('.min.js', '.min.css')):
                continue
            if file.suffix.lower() not in SOURCE_EXTENSIONS or file.is_symlink():
                continue
            try:
                if file.stat().st_size and read_text(file, 2048).strip():
                    return True
            except OSError:
                continue
    return False

def read_text(path, limit=14000):
    try:
        with path.open(errors='replace') as f:
            return f.read(limit)
    except (OSError, UnicodeError):
        return ''

def discover(home=HOME, roots=None, max_depth=8):
    candidates = []
    warnings = []
    def error(e):
        warnings.append({'path': str(e.filename), 'message': str(e.strerror)})
    for base, root, dirs, files in walk_locations(roots if roots is not None else [home], error):
        p = Path(root)
        depth = len(p.relative_to(base).parts)
        dirs[:] = sorted(d for d in dirs if d not in SKIP and not d.startswith('.')
                         and not (p/d).is_symlink() and (p/d).resolve() != APP
                         and not d.endswith(('.git', '.app', '.photoslibrary')))
        if max_depth is not None and depth > max_depth:
            dirs[:] = []
            continue
        if depth == 0 or p == home or p.parent == Path('/Users') or p.parent == Path('/Volumes'):
            continue
        fs = set(files)
        has_git = (p/'.git').exists()
        readme = next((f for f in files if f.lower() in {'readme.md', 'readme.txt', 'readme'}), None)
        direct_source = any(Path(f).suffix.lower() in SOURCE_EXTENSIONS and f.lower() not in CONFIG_ONLY
                            and '.config.' not in f.lower() for f in files)
        structure = (('frontend' in dirs and 'backend' in dirs)
                     or any(d.endswith('.xcodeproj') for d in dirs)
                     or bool(readme and 'ios' in dirs))
        static_export = bool(readme and (p/'dist'/'index.html').is_file())
        if p.name in {'Documents', 'Downloads', 'Desktop', 'dev', 'Projects'} and (p.parent == home or p.parent.parent == Path('/Users')):
            continue
        if has_git or fs & MARKERS or direct_source or structure or static_export:
            candidates.append({'path': p, 'git': has_git, 'readme': readme,
                               'structure': structure, 'source': direct_source, 'static': static_export,
                               'manifest': bool(fs & MARKERS), 'web': 'index.html' in fs})
    selected = []
    for c in sorted(candidates, key=lambda c: (len(c['path'].parts), str(c['path']))):
        p = c['path']
        ancestor = next((a for a in reversed(selected) if a['path'] in p.parents), None)
        # Components belong to their enclosing application. Independent nested repos
        # and documented applications remain visible as distinct projects.
        relative = p.relative_to(ancestor['path']).parts if ancestor else ()
        independent = ((c['structure'] or c['web'] or (c['readme'] and (c['static'] or c['source'] or c['manifest'])))
                       and not any(part.lower() in COMPONENTS for part in relative))
        if c['git'] or not ancestor or independent:
            selected.append(c)
    project_roots = {c['path'] for c in selected}
    selected = [c for c in selected if contains_source(c, project_roots, error)]
    return selected, warnings

def git_run(path, *args):
    try:
        r = subprocess.run([GIT_BINARY, '--no-optional-locks', '-c', 'core.fsmonitor=false', '-C', str(path), *args],
                           capture_output=True, timeout=12,
                           env={**os.environ, 'GIT_OPTIONAL_LOCKS': '0', 'GIT_TERMINAL_PROMPT': '0'})
        return r.returncode, r.stdout.decode('utf-8', 'replace'), r.stderr.decode('utf-8', 'replace')
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, '', str(e)

def remote_info(raw):
    raw = raw.strip()
    if re.match(r'[^/]+@[^:]+:', raw):
        raw = 'https://' + raw.split('@', 1)[1].replace(':', '/', 1)
    try:
        u = urlsplit(raw)
        if u.scheme not in {'https', 'http', 'ssh'} or not u.hostname:
            return {'label': 'Distant local' if raw else None, 'url': None, 'key': None}
        path = u.path.removesuffix('.git').rstrip('/')
        return {'label': u.hostname + path, 'key': u.hostname.lower()+path.lower(),
                'url': urlunsplit(('https', u.hostname, path, '', ''))}
    except ValueError:
        return {'label': 'Distant non reconnu', 'url': None, 'key': None}

def git_info(path):
    if not (path/'.git').exists():
        return {'present': False, 'state': 'none', 'commits': [], 'changed': 0}
    code, status, err = git_run(path, 'status', '--porcelain=v1', '-z', '--untracked-files=normal')
    if code:
        return {'present': True, 'state': 'error', 'error': err.strip()[:400], 'commits': [], 'changed': 0}
    records = status.split('\0')
    changes = []
    i = 0
    while i < len(records):
        record = records[i]
        i += 1
        if not record:
            continue
        xy, name = record[:2], record[3:]
        changes.append({'status': xy, 'path': name})
        if 'R' in xy or 'C' in xy:
            i += 1
    _, branch, _ = git_run(path, 'symbolic-ref', '--quiet', '--short', 'HEAD')
    _, log, _ = git_run(path, 'log', '-6', '--format=%H%x1f%h%x1f%cI%x1f%s%x1e')
    commits = []
    for record in log.split('\x1e'):
        bits = record.strip().split('\x1f', 3)
        if len(bits) == 4:
            commits.append(dict(zip(('hash', 'short', 'date', 'subject'), bits)))
    _, remote_names, _ = git_run(path, 'remote')
    names = remote_names.splitlines()
    remote_name = 'origin' if 'origin' in names else names[0] if names else None
    _, raw_remote, _ = git_run(path, 'remote', 'get-url', remote_name) if remote_name else (0, '', '')
    upstream_code, upstream, _ = git_run(path, 'rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{upstream}')
    ahead = behind = None
    if upstream_code == 0:
        tracking_code, counts, _ = git_run(path, 'rev-list', '--left-right', '--count', 'HEAD...@{upstream}')
        if tracking_code == 0:
            try:
                ahead, behind = map(int, counts.split())
            except ValueError:
                pass
    return {'present': True, 'state': 'unborn' if not commits else 'dirty' if changes else 'clean',
            'branch': branch.strip() or 'HEAD détachée', 'commits': commits,
            'changed': len(changes), 'changes': changes[:150],
            'staged': sum(c['status'][0] not in {' ', '?', '!'} for c in changes),
            'untracked': sum(c['status'] == '??' for c in changes),
            'remote': remote_info(raw_remote), 'upstream': upstream.strip() if upstream_code == 0 else None,
            'ahead': ahead, 'behind': behind}

def github_status(project):
    g = project['git']
    if not g['present']:
        return {'state': 'no_git', 'label': 'Sans Git', 'checkedAt': None}
    if g['state'] == 'error':
        return {'state': 'unavailable', 'label': 'Git inaccessible', 'checkedAt': None}
    remote = (g.get('remote') or {}).get('url')
    if not remote or urlsplit(remote).hostname != 'github.com':
        return {'state': 'no_github', 'label': 'Sans distant GitHub', 'checkedAt': None}
    if not g['commits']:
        return {'state': 'no_commit', 'label': 'Sans commit', 'checkedAt': None}
    try:
        snapshot = json.loads(read_text(APP/'github-status.json', 1000000)).get(project['id'])
    except (ValueError, AttributeError):
        snapshot = None
    if not snapshot:
        return {'state': 'unchecked', 'label': 'Non vérifié', 'checkedAt': None}
    if snapshot.get('localHead') != g['commits'][0]['hash'] or snapshot.get('remote') != remote or snapshot.get('localBranch') != g.get('branch'):
        return {'state': 'stale', 'label': 'État local changé', 'checkedAt': snapshot.get('checkedAt')}
    return {**snapshot, 'localChanges': g['changed']}

def technology(path, readme):
    tech = []
    files = set()
    deps = {}
    for part in ['', 'frontend', 'backend', 'workers', 'ml', 'ios']:
        p = path/part
        try:
            files.update(x.name for x in p.iterdir())
        except OSError:
            continue
        try:
            pkg = json.loads(read_text(p/'package.json'))
            deps.update(pkg.get('dependencies', {}))
            deps.update(pkg.get('devDependencies', {}))
        except (ValueError, TypeError):
            pass
    if 'next' in deps: tech.append('Next.js')
    elif 'react' in deps: tech.append('React')
    if '@angular/core' in deps: tech.append('Angular')
    if 'vue' in deps: tech.append('Vue')
    if any(x.endswith(('.xcodeproj', '.swift')) for x in files) or 'Package.swift' in files:
        tech.append('Swift')
    if 'pyproject.toml' in files or 'requirements.txt' in files or any(x.endswith('.py') for x in files):
        tech.append('Python')
    if 'go.mod' in files: tech.append('Go')
    if 'Cargo.toml' in files: tech.append('Rust')
    if 'pom.xml' in files: tech.append('Java')
    if not any(x in tech for x in ['React', 'Next.js', 'Angular', 'Vue']) and 'package.json' in files:
        tech.append('Node.js')
    if 'index.html' in files and not tech: tech.append('HTML / JS')
    if files & {'compose.yaml', 'docker-compose.yml', 'Dockerfile'}: tech.append('Docker')
    return tech

def fallback_summary(readme):
    clean = re.sub(r'```[\s\S]*?```', '', readme)
    clean = re.sub(r'<[^>]+>', '', clean)
    clean = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', clean)
    clean = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', clean)
    for paragraph in re.split(r'\n\s*\n', clean):
        text = re.sub(r'[*`_]', '', paragraph).strip()
        if not text or text.startswith(('#', '|', '>', '-', '---')) or len(text) < 35:
            continue
        if 'generated using' in text or 'Before' in text or 'Prérequis' in text:
            continue
        text = ' '.join(text.split())
        return text[:350] + ('…' if len(text) > 350 else '')
    return 'Projet repéré à partir de ses fichiers. Son objectif reste à documenter dans un README.'

def inspect(candidate, home=HOME):
    path = candidate['path']
    readme = read_text(path/candidate['readme']) if candidate['readme'] else ''
    relative = str(path.relative_to(home)) if path.is_relative_to(home) else str(path)
    display_path = '~/'+relative if path.is_relative_to(home) else str(path)
    try:
        profiles = json.loads(read_text(APP/'descriptions.json', 100000))
    except ValueError:
        profiles = {}
    profile = profiles.get(relative, {})
    title = profile.get('name')
    if not title:
        heading = re.search(r'^#\s+(.+)', readme, re.M)
        title = heading.group(1).strip() if heading else path.name
        title = re.sub(r'[*`#]', '', title)
    git = git_info(path)
    source = relative.split('/')[0]
    if relative.startswith(('.codex/worktrees/', '.claude/worktrees/')):
        source = 'Worktrees'
    elif not path.is_relative_to(home) and Path('/Users') in path.parents:
        source = 'Autres comptes'
    elif Path('/Volumes') in path.parents:
        source = 'Volumes'
    if source not in {'Documents', 'dev', 'Projects', 'Desktop', 'Downloads', 'Worktrees', 'Autres comptes', 'Volumes'}:
        source = 'Autres'
    try:
        modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
    except OSError:
        modified = None
    project = {'id': hashlib.sha256(str(path).encode()).hexdigest()[:16], 'name': title,
            'folder': path.name, 'path': str(path), 'relativePath': display_path,
            'source': source, 'external': source != 'Documents',
            'summary': profile.get('summary') or fallback_summary(readme),
            'summarySource': 'README et structure examinés' if profile else 'Extrait du README' if readme else 'Structure du dossier',
            'family': profile.get('family'), 'tech': technology(path, readme), 'git': git,
            'readme': candidate['readme'], 'modified': modified,
            'activity': git['commits'][0]['date'] if git['commits'] else modified,
            'activitySource': 'commit' if git['commits'] else 'dossier',
            'kind': 'Dépôt Git' if git['present'] else 'Application / sources'}
    project['github'] = github_status(project)
    return project

def scan(home=HOME, whole_mac=True):
    roots = mac_locations() if whole_mac else [home]
    candidates, warnings = discover(home, roots=roots, max_depth=None if whole_mac else 8)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        projects = list(pool.map(lambda c: inspect(c, home), candidates))
    projects.sort(key=lambda p: p.get('activity') or '', reverse=True)
    for p in projects:
        p['related'] = [o['id'] for o in projects if o['id'] != p['id'] and
                        ((p.get('family') and p['family'] == o.get('family')) or
                         ((p['git'].get('remote') or {}).get('key') and
                          (p['git'].get('remote') or {}).get('key') == (o['git'].get('remote') or {}).get('key')))]
    return {'projects': projects, 'warnings': warnings,
            'scannedAt': datetime.now(timezone.utc).isoformat(), 'home': str(home), 'scanRoots': [str(p) for p in roots],
            'scope': 'Exploration en lecture seule des emplacements choisis dans atelier.settings.json ou ATELIER_SCAN_ROOTS. Par défaut, Documents, Projects, dev, Desktop et Downloads du compte courant. Aucun autre compte, volume, dossier iCloud ou emplacement macOS n’est ajouté automatiquement. Seuls les projets contenant du code source non vide sont affichés. Documentation seule, configuration seule et dépôts vides exclus. Les dépendances, caches et données sont ignorés ; les liens symboliques ne sont pas suivis. Les dossiers inaccessibles sont signalés ci-dessous.',
            'trackingNote': 'Le Git local est lu sans fetch. Les résultats GitHub proviennent d’une vérification distante datée, distincte de l’inventaire local. Aucun push ou pull n’est effectué.'}

if __name__ == '__main__':
    print(json.dumps(scan(), ensure_ascii=False, indent=2))
