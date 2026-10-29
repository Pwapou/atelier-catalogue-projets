import json
import subprocess
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from inventory import discover, git_info, remote_info, inspect, GIT_BINARY

def git(path, *args):
    return subprocess.run([GIT_BINARY, '-C', str(path), *args], check=True, capture_output=True)

class InventoryTests(unittest.TestCase):
    def test_multiple_scan_roots_and_projects_outside_home(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            home=root/'user'
            home.mkdir()
            external=root/'external-volume'
            app=external/'project'
            app.mkdir(parents=True)
            (app/'main.js').write_text('console.log("external")')
            roots, warnings=discover(home, roots=[home, external], max_depth=None)
            self.assertEqual([c['path'] for c in roots], [app])
            project=inspect(roots[0], home)
            self.assertEqual(project['relativePath'], str(app))
            self.assertTrue(project['external'])
            self.assertEqual(warnings, [])

    def test_detection_groups_components_keeps_independent_and_nested_repos(self):
        with tempfile.TemporaryDirectory() as temp:
            home = Path(temp)
            app = home/'Documents'/'product'
            (app/'frontend').mkdir(parents=True)
            (app/'backend').mkdir()
            (app/'frontend'/'package.json').write_text('{}')
            (app/'frontend'/'main.ts').write_text('console.log("product")')
            (app/'backend'/'requirements.txt').write_text('')
            (app/'README.md').write_text('# Product')
            (app/'docker'/'frontend').mkdir(parents=True)
            (app/'docker'/'backend').mkdir()
            (app/'frontend'/'node_modules'/'fake').mkdir(parents=True)
            (app/'frontend'/'node_modules'/'fake'/'package.json').write_text('{}')
            nested = app/'other-product'
            nested.mkdir()
            git(nested, 'init')
            (nested/'main.go').write_text('package main\nfunc main() {}')
            roots, warnings = discover(home)
            self.assertEqual({p['path'] for p in roots}, {app, nested})
            self.assertEqual(warnings, [])

    def test_ios_application_groups_scripts_and_client(self):
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp)
            app=home/'Documents'/'ios-app'
            (app/'ios'/'Demo.xcodeproj').mkdir(parents=True)
            (app/'scripts').mkdir()
            (app/'scripts'/'export.py').write_text('print(1)')
            (app/'README.md').write_text('# Demo')
            roots, _=discover(home)
            self.assertEqual([p['path'] for p in roots],[app])

    def test_excludes_docs_empty_repos_configuration_and_parent_containers(self):
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp)
            for name in ['docs', 'empty-repo', 'config', 'empty-source', 'dependencies-only', 'container']:
                (home/name).mkdir()
            (home/'docs'/'README.md').write_text('# Documentation')
            git(home/'empty-repo', 'init')
            (home/'config'/'package.json').write_text('{}')
            (home/'config'/'vite.config.js').write_text('export default {}')
            (home/'empty-source'/'main.py').write_text('   \n')
            deps=home/'dependencies-only'
            (deps/'package.json').write_text('{}')
            (deps/'node_modules'/'lib').mkdir(parents=True)
            (deps/'node_modules'/'lib'/'index.js').write_text('console.log(1)')
            parent=home/'container'
            git(parent, 'init')
            child=parent/'child'
            child.mkdir()
            git(child, 'init')
            (child/'app.py').write_text('print("real source")')
            exported=home/'static-site'
            (exported/'dist').mkdir(parents=True)
            (exported/'README.md').write_text('# Site')
            (exported/'dist'/'index.html').write_text('<h1>Hello</h1>')
            roots, _=discover(home)
            self.assertEqual({c['path'] for c in roots}, {child, exported})

    def test_git_states_rename_and_tracking_are_read_only(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)
            self.assertEqual(git_info(path)['state'], 'none')
            git(path,'init')
            git(path,'config','user.name','Fixture')
            git(path,'config','user.email','fixture@example.invalid')
            (path/'first.txt').write_text('hello\n')
            self.assertEqual(git_info(path)['state'], 'unborn')
            git(path,'add','first.txt')
            git(path,'commit','-m','Premier commit')
            initial=git_info(path)
            self.assertEqual(initial['state'], 'clean')
            self.assertEqual(initial['commits'][0]['subject'], 'Premier commit')
            git(path,'mv','first.txt','renamed.txt')
            (path/'new.txt').write_text('new')
            before=git(path,'status','--porcelain=v1','-z').stdout
            dirty=git_info(path)
            after=git(path,'status','--porcelain=v1','-z').stdout
            self.assertEqual(before,after)
            self.assertEqual(dirty['state'],'dirty')
            self.assertEqual(dirty['changed'],2)
            self.assertEqual(dirty['staged'],1)
            self.assertEqual(dirty['untracked'],1)
            self.assertEqual({c['path'] for c in dirty['changes']},{'renamed.txt','new.txt'})
            git(path,'checkout','--detach')
            self.assertEqual(git_info(path)['branch'],'HEAD détachée')

    def test_remote_credential_redaction(self):
        info=remote_info('https://user:secret@github.com/owner/repo.git?token=secret')
        self.assertEqual(info['url'],'https://github.com/owner/repo')
        self.assertNotIn('secret',json.dumps(info))
        self.assertEqual(remote_info('git@github.com:owner/repo.git')['url'],info['url'])
        self.assertIsNone(remote_info('file:///tmp/repo')['url'])

if __name__=='__main__': unittest.main()
