from fastapi.testclient import TestClient

from backend.main import app


def test_health_detail_shape():
    client = TestClient(app)
    res = client.get('/health/detail')
    assert res.status_code == 200
    body = res.json()
    assert body.get('status') in ('healthy', 'degraded')
    assert 'ok' in body
    checks = body.get('checks') or {}
    assert 'ollama' in checks
    assert 'data_root' in checks
    assert 'vector_db_path' in checks
    assert 'era_packs' in checks
    assert 'llm_roles' in checks
