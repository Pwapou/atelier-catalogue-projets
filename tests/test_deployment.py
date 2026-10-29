import json
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from deployment_specs import deployment_specs

class DeploymentTests(unittest.TestCase):
    def test_declared_services_and_aliases_without_environment_or_commands(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)
            compose=path/'compose.yaml'
            compose.write_text('''x-base: &base
  image: python:3.12-slim
  environment:
    API_KEY: literal-sensitive-value
  env_file: .env
services:
  api:
    <<: *base
    container_name: example-api
    build:
      context: .
      dockerfile: Dockerfile
      target: production
      args:
        SECRET: literal-sensitive-value
    ports:
      - "127.0.0.1:${PORT}:8000"
    volumes:
      - type: bind
        source: ./data
        target: /data
        read_only: true
    depends_on:
      db:
        condition: service_healthy
    healthcheck:
      test: [CMD, echo, literal-sensitive-value]
      interval: 10s
    deploy:
      resources:
        limits:
          memory: 256M
  db:
    image: postgres:17
volumes:
  db-data:
networks:
  private:
    internal: true
''')
            (path/'.env').write_text('SHOULD_NOT_BE_READ=literal-sensitive-value')
            dockerfile=path/'Dockerfile'
            dockerfile.write_text('ARG SECRET=literal-sensitive-value\nFROM node:22-alpine AS builder\nFROM builder AS production\nEXPOSE 8000\nCMD ["echo", "literal-sensitive-value"]\n')
            doc=path/'README.md';doc.write_text('Image de base : `nginx:alpine`\nDocker pull : docker pull postgres:17\ndocker run -d --name local -e KEY=literal-sensitive-value registry.example/team/app:v1\n')
            result=deployment_specs(path,[compose,dockerfile,doc])
            self.assertEqual(len(result['composeFiles'][0]['services']),2)
            service=result['composeFiles'][0]['services'][0]
            self.assertEqual(service['image'],'python:3.12-slim')
            self.assertEqual(service['ports'],['127.0.0.1:${PORT}:8000'])
            self.assertEqual(service['dependsOn'],['db'])
            self.assertEqual(service['resources']['memory'],'256M')
            self.assertTrue(service['healthcheck']['declared'])
            self.assertTrue(result['dockerfiles'][0]['bases'][1]['internalStage'])
            self.assertEqual(result['dockerfiles'][0]['exposedPorts'],['8000'])
            self.assertIn('nginx:alpine',[r['image'] for r in result['documentedImages']])
            self.assertIn('registry.example/team/app:v1',[r['image'] for r in result['documentedImages']])
            self.assertNotIn('literal-sensitive-value',json.dumps(result))

    def test_invalid_compose_is_reported_as_unreadable_not_empty_runtime(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp);compose=path/'docker-compose.yml';compose.write_text('services: [broken')
            result=deployment_specs(path,[compose])
            self.assertEqual(result['composeFileCount'],1)
            self.assertIn('error',result['composeFiles'][0])

if __name__=='__main__': unittest.main()
