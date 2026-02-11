from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import app


def test_content_catalog_exposes_items() -> None:
    client = TestClient(app)
    res = client.get('/v2/content/catalog')
    assert res.status_code == 200
    body = res.json()
    assert isinstance(body.get('items'), list)
    assert len(body['items']) >= 1
    first = body['items'][0]
    assert 'setting_id' in first
    assert 'period_id' in first
    assert 'legacy_era_id' in first


def test_content_default_returns_known_period() -> None:
    client = TestClient(app)
    res = client.get('/v2/content/default')
    assert res.status_code == 200
    body = res.json()
    assert body['setting_id']
    assert body['period_id']
    assert body['legacy_era_id']


def test_setup_auto_invalid_canonical_period_returns_400() -> None:
    client = TestClient(app)
    res = client.post('/v2/setup/auto', json={'setting_id': 'star_wars_legends', 'period_id': 'totally_not_real', 'player_concept': 'test'})
    assert res.status_code == 400
    payload = res.json()
    assert payload['error_code'].startswith('SETUP_HTTP_400')
    assert 'Unknown period' in payload['message']
