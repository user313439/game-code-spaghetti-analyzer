"""A fresh demonstration case must not replace the preserved case registration."""
import json
from fastapi.testclient import TestClient
from game_si.web import app as module


def test_new_case_routes_without_replacing_previous_registration(tmp_path,monkeypatch):
    cases=tmp_path/'project'
    monkeypatch.setattr(module,'REPO_ROOT',cases)
    app=module.create_app(tmp_path/'jobs')
    manager=app.state.manager
    ident=manager.create('새 유지보수 검증','folder')['id']
    manager.update(ident,state='complete',options={'lang':'c','subdir':'.'})
    root=cases/'docs/_demo_phase_v3'
    root.mkdir(parents=True)
    (root/'demo_job.json').write_text(json.dumps({'id':ident}),encoding='utf8')
    with TestClient(app,base_url='http://127.0.0.1:8765') as client:
        state=client.get(f'/api/jobs/{ident}/demo').json()
        assert state['available'] is True
        assert state['game_title']=='OpenTyrian'
        assert app.state.casual_demo.root!=root
