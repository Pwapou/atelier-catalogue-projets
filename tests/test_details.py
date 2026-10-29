import tempfile
import unittest
import json
from unittest.mock import patch
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from project_details import describe, documented_links, documented_sections, documented_limits
from inventory import github_status

class DetailTests(unittest.TestCase):
    def test_usage_steps_and_limits_have_document_sources(self):
        readme='''# Demo
## Utiliser l'application
1. Importer les documents.
```sh
echo "not a feature"
```
2. Explorer les résultats.
## Limite actuelle
La carte ne contient pas encore de lieux.
'''
        features,_=documented_sections(readme)
        self.assertEqual([f['text'] for f in features],['Importer les documents.','Explorer les résultats.'])
        self.assertIn('README',features[0]['source'])
        self.assertEqual(documented_limits(readme,'README.md')[0]['text'],'La carte ne contient pas encore de lieux.')
    def test_static_evidence_versions_and_nested_code_exclusion(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)
            (path/'src').mkdir()
            (path/'src/app.py').write_text('import sqlite3\n\nprint("hello")\n')
            (path/'tests').mkdir()
            (path/'tests/test_app.py').write_text('assert 1 == 1\n')
            (path/'node_modules/dep').mkdir(parents=True)
            (path/'node_modules/dep/library.js').write_text('console.log(1)')
            (path/'separate').mkdir()
            (path/'separate/app.go').write_text('package main')
            (path/'requirements.txt').write_text('fastapi==0.115.0\n# comment\n-e git+https://token@example.com/x\nhttps://secret@example.com/model.whl\n')
            (path/'README.md').write_text('# Demo\n\n## Fonctionnalités\n- Import de documents.\n- Exploration des résultats.\n\n## Public visé\nLes analystes.\n')
            p={'id':'demo','path':str(path),'readme':'README.md','summary':'Projet de démonstration.',
               'summarySource':'README','git':{'commits':[]}}
            detail=describe(path,p,[p,{'id':'nested','path':str(path/'separate')}])
            self.assertEqual(detail['code']['files'],2)
            self.assertEqual(detail['code']['lines'],4)
            self.assertEqual(detail['code']['tests'],1)
            self.assertEqual(len(detail['features']),2)
            self.assertEqual(detail['audience'],'Les analystes.')
            self.assertEqual(detail['dependencies'][0]['version'],'==0.115.0')
            self.assertEqual(len(detail['dependencies']),1)
            self.assertEqual(detail['databases'][0]['name'],'SQLite')
            self.assertNotIn('token',str(detail))

    def test_documented_links_drop_credentials_query_and_fragments(self):
        text='Site : https://user:secret@example.com/\nURL : https://demo.example.com/?token=secret#secret\nhttp://localhost:3000\nhttps://learn.microsoft.com/guide'
        links=documented_links(text,'README.md')
        self.assertEqual([l['url'] for l in links],['https://demo.example.com/','http://localhost:3000'])
        self.assertNotIn('secret',str(links))

    def test_no_remote_is_not_proof_of_github_absence(self):
        self.assertEqual(github_status({'git':{'present':False}})['state'],'no_git')
        self.assertEqual(github_status({'git':{'present':True,'state':'clean','remote':None}})['state'],'no_github')

    def test_remote_result_is_invalidated_after_local_commit_change(self):
        project={'id':'example','git':{'present':True,'state':'dirty','changed':3,'branch':'main',
                 'commits':[{'hash':'abc'}],'remote':{'url':'https://github.com/owner/repo'}}}
        result={'example':{'localHead':'abc','localBranch':'main','remote':'https://github.com/owner/repo',
                          'state':'synced','checkedAt':'2026-10-25T00:00:00Z'}}
        with patch('inventory.read_text',return_value=json.dumps(result)):
            verified=github_status(project)
            self.assertEqual(verified['state'],'synced')
            self.assertEqual(verified['localChanges'],3)
            project['git']['commits'][0]['hash']='changed'
            self.assertEqual(github_status(project)['state'],'stale')

if __name__=='__main__':unittest.main()
