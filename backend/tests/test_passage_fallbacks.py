from fastapi.testclient import TestClient
from unittest.mock import patch
import os
import tempfile

from backend.app.db.migrate import apply_schema


def test_start_passage_missing_pack_returns_fallback_payload():
    tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    tmp.close()
    try:
        apply_schema(tmp.name)
        with patch('backend.app.api.v2_campaigns.DEFAULT_DB_PATH', tmp.name):
            from backend.main import app
            client = TestClient(app)
            r = client.post('/v2/campaigns', json={"title": "x", "player_name": "p", "starting_location": "loc-cantina"})
            cid = r.json()['campaign_id']
            res = client.post(f'/v2/campaigns/{cid}/start_passage', json={"pack_id": "does_not_exist", "mode": "PASSAGE"})
            assert res.status_code == 200
            body = res.json()
            assert body.get('error')
            assert len(body.get('choices') or []) >= 2
    finally:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
