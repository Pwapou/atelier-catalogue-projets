# Atelier — catalogue local de projets

Atelier parcourt les dossiers de code que tu choisis et présente les projets logiciels repérés : résumé, langages, architecture documentée, conteneurs et historique Git. Les informations sont lues localement ; le serveur écoute uniquement sur `127.0.0.1`.

## Démarrer

Prérequis : Python 3.9 ou plus récent, Node.js 20.19+ ou 22.12+.

```sh
npm install
npm run build
python3 server.py
```

Ouvre <http://127.0.0.1:8766>. Sur macOS, après la première compilation, tu peux démarrer Atelier avec `Lancer Atelier.command`. Pour changer le port, lance `python3 server.py --port 8767`.

Pendant le développement, démarre aussi `npm run dev` ; Vite transmet les requêtes API au serveur Python.

## Choisir les dossiers à parcourir

Par défaut, Atelier explore `Documents`, `Projects`, `dev`, `Desktop` et `Downloads` dans le compte courant. Il ne parcourt pas automatiquement les autres comptes, volumes, dossiers iCloud ni le reste du Mac.

Pour personnaliser les emplacements, copie `atelier.settings.example.json` en `atelier.settings.json` et modifie `scan_roots` :

```json
{
  "scan_roots": [
    "~/Documents/Code",
    "~/Projects",
    "/Volumes/Development/Work"
  ]
}
```

Les chemins peuvent être absolus ou commencer par `~`. Le fichier personnel `atelier.settings.json` est ignoré par Git. Tu peux aussi définir `ATELIER_SCAN_ROOTS` avec des chemins séparés par `:` sur macOS/Linux ou `;` sur Windows ; cette variable remplace la configuration JSON.

Les racines configurées sont parcourues sans limite de profondeur. Les liens symboliques ne sont pas suivis. Dépendances, caches, données, médias et dossiers générés sont ignorés. Seuls les dossiers ayant du code source non vide sont listés ; README, manifeste ou dépôt vide seuls ne suffisent pas. Le code d’un projet imbriqué indépendant ne fait pas apparaître son parent.

## Informations affichées

- Résumé issu du README, avec technologies déduites des manifestes.
- Historique et changements locaux Git ; Git est consulté en lecture seule, sans fetch, push ni pull.
- État GitHub distant uniquement si tu ajoutes toi-même un relevé local dans `github-status.json`. Aucun service GitHub n’est interrogé automatiquement.
- Fiches détaillées statiques : documentation, versions déclarées, statistiques de code, structure, conteneurs et images mentionnées. Elles ne lancent pas le code du projet et ne valident pas son fonctionnement.

Les résumés personnalisés peuvent être placés dans `descriptions.json`. Ces fichiers sont ignorés par Git et ne sont pas fournis dans le dépôt. Ils ne contiennent donc aucune donnée d’exemple issue des projets d’une personne.

L’inventaire et les fiches détaillées sont servis par l’ordinateur local. Les chemins, noms de projet et résumés apparaissent dans le navigateur local et dans l’export JSON. N’expose pas le serveur sur un réseau public.

## Arborescence

- `inventory.py` : découverte des projets et lecture Git en lecture seule.
- `project_details.py` : extraction statique des informations de projet.
- `deployment_specs.py`, `parse_compose.mjs` : lecture des déclarations Compose et Dockerfile.
- `server.py` : API locale et serveur de l’interface.
- `src/` : interface React.
- `atelier.settings.example.json` : exemple de configuration sans chemin personnel.

## Vérifier et construire

```sh
python3 -m unittest discover -s tests
npm run build
```

Les tests Git utilisent des dépôts temporaires.
