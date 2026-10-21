"""Joint per-file coverage and isolated pre-review; no live AI calls."""
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from game_si.web import assistant
from game_si.web.app import create_app


def fresh_reply(paths, edits=None):
    changed = {item['path'] for item in edits or []}
    return dict(overview={key:'공동 검토의 코드 근거를 설명합니다.' for key in
        ['title','problem','reason','change','expected_effect']},
        reasons=['코드 근거'], suggestions=['작은 범위 검토'], tests=['원본과 동작 비교'],
        uncertainty='검사 응답입니다.', edits=edits or [], relationships=[],
        file_reviews=[dict(path=path,role='파일의 역할입니다.',finding='확인한 구조입니다.',
            reason='코드에 근거한 검토 이유입니다.',change='변경 범위입니다.',
            expected_effect='검증할 기대 효과입니다.',impact='관련 호출을 확인합니다.',
            decision='refactor' if path in changed else 'keep',targets=['Tick'+path[1:-2]] if path in changed else [],
            evidence=['함수 근거'],checks=['동작 비교']) for path in paths])


def test_large_context_is_bounded_and_retains_all_file_hashes():
    from game_si.web.assistant_context import build_prompt
    sources = {f'u{i}.c': ('/*'+('header '*15000)+'*/\nint Target'+str(i)+'(void) { return 7; }\n').encode() for i in range(5)}
    selected = [dict(fqn=path[:-2],file_path=path,si=100-i,raw={'cc':99}) for i,path in enumerate(sources)]
    methods = [dict(file_path=path,name='Target'+str(i),fqn=path+'.Target',start_line=2,end_line=2,cc=99) for i,path in enumerate(sources)]
    prompt, context = build_prompt('제안 단계', selected, sources, methods)
    data = json.loads(prompt)
    assert len(prompt.encode('utf8')) <= 360000
    assert context['mode'] == 'focused'
    assert context['total_source_bytes'] > 360000
    assert {item['path'] for item in data['sources']} == set(sources)
    assert all('Target' in item['content'] and item['sha256']==assistant.digest(sources[item['path']]) for item in data['sources'])
    assert all(not item['complete'] for item in context['files'])


def test_fresh_file_explanations_require_exact_coverage_and_consistent_edits():
    paths=['a.c','b.c']
    good=fresh_reply(paths)
    assert assistant.validate_scope(good, paths) == good
    for files in [good['file_reviews'][:1],good['file_reviews']+[good['file_reviews'][0]],fresh_reply(['a.c','outside.c'])['file_reviews']]:
        with pytest.raises(ValueError): assistant.validate_scope(dict(good,file_reviews=files),paths)
    with pytest.raises(ValueError):
        assistant.validate_scope(dict(good,edits=[dict(path='a.c',old='x',new='y')]),paths,preview=True)
    legacy=dict(reasons=['근거'],suggestions=['방향'],tests=['확인'],uncertainty='과거 응답')
    assert assistant.validate_advice(legacy)==legacy


def test_fresh_refactor_requires_named_targets_and_schema_requires_the_field():
    data=fresh_reply(['u0.c'],[dict(path='u0.c',old='return 0;',new='return (0);')])
    assert assistant.validate_scope(data,['u0.c'],preview=True)==data
    assert 'targets' in assistant.FILE_REVIEW_SCHEMA['required']
    for targets in [[], [''], 'Tick0', ['x'*301]]:
        data['file_reviews'][0]['targets']=targets
        with pytest.raises(ValueError,match='대상'):
            assistant.validate_scope(data,['u0.c'],preview=True)
    data['file_reviews'][0].pop('targets')
    with pytest.raises(ValueError):
        assistant.validate_scope(data,['u0.c'],preview=True)


def test_focused_context_contains_inventory_and_complete_manageable_functions():
    from game_si.web.assistant_context import build_prompt
    lines=['/*'+'h'*60000+'*/\n']
    methods=[]
    for i in range(8):
        start=len(lines)+1
        lines.extend([f'int Routine{i}(void) {{\n']+[f'    int v{j} = {j}; /*'+('x'*100)+'*/\n' for j in range(80)]+['    return 0;\n','}\n'])
        methods.append(dict(file_path='a.c',fqn=f'a.Routine{i}',name=f'Routine{i}',
                            start_line=start,end_line=len(lines),cc=100-i*10,loc=83))
    sources={'a.c':''.join(lines).encode(),'b.c':b'/*'+b'b'*150000+b'*/'}
    prompt,context=build_prompt('제안 단계',[],sources,methods)
    source=json.loads(prompt)['sources'][0]
    assert context['mode']=='focused'
    assert json.loads(prompt)['prompt_version']=='joint-files-v3'
    assert all(set(row)=={'fqn','name','start_line','end_line','cc','loc'} for row in source['methods'])
    assert source['method_count']==8
    complete=[r for r in source['ranges'] if not r['partial'] and r['start_line']>1]
    assert any(r['start_line']==methods[0]['start_line'] and r['end_line']>=methods[0]['end_line'] for r in complete)
    assert any(f'int Routine{i}(void)' in source['content'] for i in range(4,8))
    assert len(prompt.encode('utf8'))<=360000


def test_preview_context_prioritizes_previous_target_body_and_keeps_targets():
    from game_si.web.assistant_context import build_prompt
    lines=['/*'+('header '*14000)+'*/\n']
    methods=[]
    for i in range(8):
        start=len(lines)+1
        lines.extend([f'int Routine{i}(void) {{\n']+[f'    int target{i}_{j} = {j};\n' for j in range(250)]+[f'    return target{i}_249;\n','}\n'])
        methods.append(dict(file_path='a.c',fqn=f'a.Routine{i}',name=f'Routine{i}',start_line=start,end_line=len(lines),cc=100-i,loc=253))
    advice=fresh_reply(['a.c'])
    advice['file_reviews'][0].update(decision='refactor',targets=['Routine7'])
    prompt,context=build_prompt('변경안 단계',[],{'a.c':''.join(lines).encode(),'b.c':b'/*'+b'b'*150000+b'*/'},methods,advice)
    data=json.loads(prompt);source=data['sources'][0]
    assert context['mode']=='focused'
    assert data['previous_advice']['file_reviews'][0]['targets']==['Routine7']
    assert 'return target7_249;' in source['content']
    assert any(r['start_line']==methods[7]['start_line'] and r['end_line']>=methods[7]['end_line'] and not r['partial'] for r in source['ranges'])


def test_large_complex_function_leaves_room_for_complete_manageable_function():
    from game_si.web.assistant_context import build_prompt
    lines=['/*'+'h'*60000+'*/\n']
    methods=[]
    for name,size,cc in [('Large',30000,99),('Manageable',7000,4)]:
        start=len(lines)+1
        lines.extend([f'int {name}(void) {{\n','/*'+'x'*size+'*/\n','return 0;\n','}\n'])
        methods.append(dict(file_path='a.c',name=name,fqn='a.'+name,start_line=start,end_line=len(lines),cc=cc,loc=4))
    prompt,_=build_prompt('제안 단계',[],{'a.c':''.join(lines).encode(),'b.c':b'/*'+b'b'*150000+b'*/'},methods)
    source=json.loads(prompt)['sources'][0]
    assert 'int Large(void)' in source['content']
    assert any(r['start_line']==methods[1]['start_line'] and r['end_line']==methods[1]['end_line'] and not r['partial'] for r in source['ranges'])


def test_method_inventory_is_bounded_and_discloses_total():
    from game_si.web.assistant_context import build_prompt
    methods=[dict(file_path='a.c',fqn='a.'+str(i),name='Routine'+str(i),start_line=1,end_line=1,cc=i,loc=1) for i in range(500)]
    prompt,_=build_prompt('제안 단계',[],{'a.c':b'int Value;'},methods)
    source=json.loads(prompt)['sources'][0]
    assert source['method_count']==500
    assert 1<=len(source['methods'])<=80
    assert len(json.dumps(source['methods'],ensure_ascii=False).encode('utf8'))<=12500


def wait_assistant(client,url):
    for _ in range(150):
        state=client.get(url).json()
        if state['state']!='running':return state
        time.sleep(.02)
    pytest.fail('Assistant worker did not finish')


def test_cached_five_file_review_can_preview_only_selected_two(review_workbench,monkeypatch):
    client,url,headers,job=review_workbench
    calls=[]
    def provider(service,mode,prompt,*args):
        data=json.loads(prompt);calls.append(data)
        paths=[item['path'] for item in data['sources']]
        if data['stage']=='제안 단계':
            response=fresh_reply(paths)
            response['overview']={key:'FIVE FILE ONLY OVERVIEW' for key in response['overview']}
            response['relationships']=['FIVE FILE ONLY RELATIONSHIP']
            for row in response['file_reviews']:
                row.update(reason=row['path']+' 선택 근거입니다.',decision='refactor',targets=['Tick'+row['path'][1:-2]])
            return response
        return fresh_reply(paths,[dict(path='u1.c',old='return 1;',new='return (1);')])
    monkeypatch.setattr(assistant,'call_provider',provider)
    connection=dict(service='codex',mode='cli',model='fixture-model')
    original=(job/'assistant.json').read_bytes()
    assert client.post(url,headers=headers,json=dict(connection,action='review')).status_code==202
    assert wait_review(client,url)['state']=='complete'
    assert (job/'assistant.json').read_bytes()==original
    response=client.post(url,headers=headers,json=dict(connection,action='preview',candidates=['u1','u3']))
    assert response.status_code==202,response.text
    state=wait_assistant(client,url)
    assert state['state']=='complete',state
    assert len(calls)==2  # no additional advice call
    prior=calls[1]['previous_advice']
    assert {r['path'] for r in prior['file_reviews']}=={'u1.c','u3.c'}
    assert all(r['targets'] for r in prior['file_reviews'])
    assert 'FIVE FILE ONLY' not in json.dumps(prior)
    assert set(state['source_hashes'])=={'u1.c','u3.c'}
    assert all(state['source_hashes'][p]==assistant.digest((job/'input'/p).read_bytes()) for p in state['source_hashes'])
    assert (state['service'],state['mode'],state['model'])==('codex','cli','fixture-model')
    assert {r['path'] for r in state['advice']['file_reviews']}=={'u1.c','u3.c'}
    assert {r['path'] for r in state['change_advice']['file_reviews']}=={'u1.c','u3.c'}


@pytest.mark.parametrize('invalid',['hash','service','mode','model','selection','schema'])
def test_invalid_cached_review_never_silently_starts_provider(review_workbench,monkeypatch,invalid):
    client,url,headers,job=review_workbench
    calls=[]
    def provider(service,mode,prompt,*args):
        data=json.loads(prompt);calls.append(data)
        return fresh_reply([item['path'] for item in data['sources']])
    monkeypatch.setattr(assistant,'call_provider',provider)
    connection=dict(service='codex',mode='cli',model='fixture-model')
    assert client.post(url,headers=headers,json=dict(connection,action='review')).status_code==202
    assert wait_review(client,url)['state']=='complete'
    preview=dict(connection,action='preview',candidates=['u1','u3'])
    if invalid=='hash':(job/'input/u4.c').write_text('int Changed(void) { return 9; }')
    elif invalid=='service':preview['service']='claude'
    elif invalid=='mode':preview.update(mode='api',api_key='fixture-key')
    elif invalid=='model':preview['model']='different-model'
    elif invalid=='selection':preview['candidates']=['u1','u5']
    elif invalid=='schema':
        state=client.app.state.assistant.reviews.records[next(iter(client.app.state.assistant.reviews.records))]['active']
        state['advice']['file_reviews'][0].pop('targets')
    original=(job/'assistant.json').read_bytes()
    response=client.post(url,headers=headers,json=preview)
    assert response.status_code==400,response.text
    assert len(calls)==1
    assert (job/'assistant.json').read_bytes()==original


def test_existing_legacy_advice_can_seed_preview_without_rewriting_it(review_workbench,monkeypatch):
    client,url,headers,job=review_workbench
    legacy=fresh_reply(['u1.c'])
    legacy['file_reviews'][0].pop('targets')
    saved=dict(state='complete',action='advice',candidate='u1',candidates=['u1'],file_path='u1.c',
        source_hashes={'u1.c':assistant.digest((job/'input/u1.c').read_bytes())},
        service='codex',mode='cli',model='',advice=legacy)
    (job/'assistant.json').write_text(json.dumps(saved),encoding='utf8')
    received=[]
    def provider(service,mode,prompt,*args):
        received.append(json.loads(prompt))
        return fresh_reply(['u1.c'],[dict(path='u1.c',old='return 1;',new='return (1);')])
    monkeypatch.setattr(assistant,'call_provider',provider)
    assert client.post(url,headers=headers,json=dict(action='preview',service='codex',mode='cli',candidates=['u1'])).status_code==202
    state=wait_assistant(client,url)
    assert state['state']=='complete',state
    assert state['advice']==legacy
    assert received[0]['previous_advice']['file_reviews'][0]['path']=='u1.c'


def test_existing_advice_requires_matching_connection_for_preview(review_workbench,monkeypatch):
    client,url,headers,_=review_workbench
    calls=[]
    def provider(service,mode,prompt,*args):
        calls.append(json.loads(prompt))
        return fresh_reply(['u1.c'])
    monkeypatch.setattr(assistant,'call_provider',provider)
    request=dict(service='codex',mode='cli',candidates=['u1'])
    assert client.post(url,headers=headers,json=dict(request,action='advice')).status_code==202
    assert wait_assistant(client,url)['state']=='complete'
    assert client.post(url,headers=headers,json=dict(request,action='preview',service='claude')).status_code==400
    assert len(calls)==1


@pytest.mark.parametrize('decision',['keep','needs_context'])
def test_empty_preview_saves_latest_reasons_without_approval_and_retry_uses_them(review_workbench,monkeypatch,decision):
    client,url,headers,job=review_workbench
    calls=[]
    def provider(service,mode,prompt,*args):
        data=json.loads(prompt);calls.append(data)
        response=fresh_reply(['u1.c'])
        response['file_reviews'][0]['reason']='LATEST_NO_CHANGE_REASON' if len(calls)>1 else 'INITIAL_ADVICE_REASON'
        if len(calls)==2:
            response['file_reviews'][0]['decision']=decision
        elif len(calls)==3:
            assert data['previous_advice']['file_reviews'][0]['reason']=='LATEST_NO_CHANGE_REASON'
            response=fresh_reply(['u1.c'],[dict(path='u1.c',old='return 1;',new='return (1);')])
        return response
    monkeypatch.setattr(assistant,'call_provider',provider)
    request=dict(service='codex',mode='cli',candidates=['u1'])
    assert client.post(url,headers=headers,json=dict(request,action='advice')).status_code==202
    assert wait_assistant(client,url)['state']=='complete'
    assert client.post(url,headers=headers,json=dict(request,action='preview')).status_code==202
    state=wait_assistant(client,url)
    assert state['state']=='complete',state
    assert state['no_changes'] is True
    assert state['change_advice']['file_reviews'][0]['reason']=='LATEST_NO_CHANGE_REASON'
    assert state['change_advice']['file_reviews'][0]['decision']==decision
    assert not state.get('preview_id') and not state.get('preview')
    assert json.loads((job/'assistant.json').read_text('utf8'))['change_advice']==state['change_advice']
    assert client.post(url+'/apply',headers=headers,json={'preview_id':'anything'}).status_code==400
    assert client.post(url,headers=headers,json=dict(request,action='preview')).status_code==202
    state=wait_assistant(client,url)
    assert state['state']=='complete',state
    assert not state.get('no_changes')
    assert state['preview_id'] and state['preview']['files']


@pytest.mark.parametrize('action',['advice','review','preview'])
def test_fresh_targets_must_resolve_to_real_file_methods(review_workbench,monkeypatch,action):
    client,url,headers,_=review_workbench
    def provider(service,mode,prompt,*args):
        request=json.loads(prompt)
        paths=[source['path'] for source in request['sources']]
        response=fresh_reply(paths)
        if action=='preview' and request['stage']=='제안 단계':return response
        response['file_reviews'][0].update(decision='refactor',targets=['GhostFunction'])
        if action=='preview':response['edits']=[dict(path=paths[0],old='return 1;',new='return (1);')]
        return response
    monkeypatch.setattr(assistant,'call_provider',provider)
    request=dict(service='codex',mode='cli',candidates=['u1'])
    if action=='preview':
        assert client.post(url,headers=headers,json=dict(request,action='advice')).status_code==202
        assert wait_assistant(client,url)['state']=='complete'
    assert client.post(url,headers=headers,json=dict(request,action=action)).status_code==202
    state=wait_review(client,url) if action=='review' else wait_assistant(client,url)
    assert state['state']=='failed',state
    assert '대상' in state['error']
    assert not state.get('preview_id')
    assert not state.get('advice') or all('GhostFunction' not in row['targets'] for row in state['advice']['file_reviews'])


@pytest.mark.parametrize('kind',['undeclared','declared','fqn','helper','unlogged_helper','nonstatic_helper','helper_only'])
def test_preview_checks_actual_changed_functions_instead_of_old_anchor(review_workbench,monkeypatch,kind):
    client,url,headers,job=review_workbench
    original='int Tick1(void) {\n    return 1;\n}\nint Other1(void) {\n    return 2;\n}\n'
    (job/'input/u1.c').write_text(original,encoding='utf8')
    methods=[dict(file_path='u1.c',name=name,fqn='u1.'+name,start_line=start,end_line=start+2,cc=1,loc=3)
             for name,start in [('Tick1',1),('Other1',4)]]
    (job/'result/metrics.json').write_text(json.dumps({'methods':methods}),encoding='utf8')
    def provider(service,mode,prompt,*args):
        if json.loads(prompt)['stage']=='제안 단계':return fresh_reply(['u1.c'])
        after=original.replace('return 2;','return (2);')
        targets=['Other1'] if kind=='declared' else ['u1.Other1'] if kind=='fqn' else ['Tick1']
        if 'helper' in kind:
            helper=('' if kind=='nonstatic_helper' else 'static ')+'int Helper(void) {\n    return 1;\n}\n'
            after=helper+(original if kind=='helper_only' else original.replace('return 1;','return Helper();'))
        response=fresh_reply(['u1.c'],[dict(path='u1.c',old=original,new=after)])
        response['file_reviews'][0]['targets']=targets
        if kind!='unlogged_helper':response['file_reviews'][0]['evidence']=['Helper 호출을 Tick1에서 사용합니다.']
        return response
    monkeypatch.setattr(assistant,'call_provider',provider)
    request=dict(service='codex',mode='cli',candidates=['u1'])
    assert client.post(url,headers=headers,json=dict(request,action='advice')).status_code==202
    assert wait_assistant(client,url)['state']=='complete'
    assert client.post(url,headers=headers,json=dict(request,action='preview')).status_code==202
    state=wait_assistant(client,url)
    if kind in {'declared','fqn','helper'}:
        assert state['state']=='complete',state
        assert state['preview_id']
        if kind=='helper':assert state['preview']['files'][0]['added_helpers']==['Helper']
    else:
        assert state['state']=='failed',state
        assert not state.get('preview_id') and not state.get('preview')


@pytest.mark.parametrize('variant',['valid','nonstatic','unlogged','uncalled'])
def test_actual_preview_detects_helpers_independently_of_diff_alignment(variant):
    from game_si.web.assistant_context import validate_preview_targets
    case=Path(__file__).resolve().parents[1]/'docs/_demo_phase_v3'
    if not (case/'actual_preview.json').is_file():pytest.skip('실제 preview 검증 자료가 없는 환경입니다.')
    saved=json.loads((case/'actual_preview.json').read_text('utf8'))
    methods=json.loads((case/'01_original/analysis/metrics.json').read_text('utf8'))['methods']
    preview=saved['preview'];advice=saved['change_advice']
    item=next(row for row in preview['files'] if row['path']=='tyrian2.c')
    review=next(row for row in advice['file_reviews'] if row['path']=='tyrian2.c')
    helper='find_free_enemy_slot'
    if variant=='nonstatic':
        assert 'static int '+helper in item['after']
        item['after']=item['after'].replace('static int '+helper,'int '+helper,1)
    elif variant=='unlogged':
        review['change']=review['change'].replace(helper,'익명 보조 함수')
        review['evidence']=[text.replace(helper,'익명 보조 함수') for text in review['evidence']]
    elif variant=='uncalled':
        call=helper+'(enemyOffset)'
        assert call in item['after']
        item['after']=item['after'].replace(call,'0 /* '+call+' */')
    if variant=='valid':
        validate_preview_targets(advice,methods,preview)
        assert item['added_helpers']==[helper]
    else:
        with pytest.raises(ValueError,match='보조 함수'):
            validate_preview_targets(advice,methods,preview)


def test_preview_cannot_edit_source_omitted_from_focused_prompt():
    from game_si.web.assistant_context import build_prompt, validate_edit_context
    text='\n'.join(['int Preamble;']*100+['int UnseenUnique = 17;']+['int Tail;']*100)
    # A large file makes the body outside the preamble and tail unavailable.
    text=text.replace('int Preamble;', '/*'+'x'*1500+'*/ int Preamble;')
    prompt,context=build_prompt('변경안 단계',[dict(fqn='a',file_path='a.c',si=100,raw={})],
        {'a.c':text.encode(),'b.c':text.encode()},[])
    assert context['mode']=='focused'
    assert 'int UnseenUnique = 17;' not in json.loads(prompt)['sources'][0]['content']
    with pytest.raises(ValueError,match='제공한 코드'):
        validate_edit_context(prompt,[dict(path='a.c',old='int UnseenUnique = 17;',new='int UnseenUnique = 18;')])
    validate_edit_context(prompt,[dict(path='a.c',old='int Tail;',new='int Tail2;')])
    windows_prompt=json.dumps({'sources':[{'path':'a.c','content':'int x;\r\nint y;\r\n'}]})
    validate_edit_context(windows_prompt,[dict(path='a.c',old='int x;\nint y;',new='int z;')])


def test_running_pre_review_prevents_record_deletion(review_workbench,monkeypatch):
    import threading
    client,url,headers,job=review_workbench
    entered,release=threading.Event(),threading.Event()
    def provider(service,mode,prompt,*args):
        entered.set()
        assert release.wait(5)
        return fresh_reply([item['path'] for item in json.loads(prompt)['sources']])
    monkeypatch.setattr(assistant,'call_provider',provider)
    try:
        assert client.post(url,headers=headers,json=dict(action='review',service='codex',mode='cli')).status_code==202
        assert entered.wait(3)
        assert client.post(url.removesuffix('/assistant')+'/delete',headers=headers).status_code==409
    finally:
        release.set()
    assert wait_review(client,url)['state']=='complete'


@pytest.fixture
def review_workbench(tmp_path):
    app=create_app(tmp_path)
    manager=app.state.manager
    ident=manager.create('사전 검토 검사', 'folder')['id']
    job=manager.directory(ident)
    rows=[]
    for i in range(6):
        (job/'input'/f'u{i}.c').write_text(f'int Tick{i}(void) {{ return {i}; }}\n',encoding='utf8')
        rows.append(dict(fqn=f'u{i}',file_path=f'u{i}.c',si=100-i,raw={'cc':1}))
    result=job/'result';result.mkdir()
    (result/'scoring.json').write_text(json.dumps({'class_scores':rows}),encoding='utf8')
    methods=[dict(file_path=f'u{i}.c',name=f'Tick{i}',fqn=f'u{i}.Tick{i}',start_line=1,end_line=1,cc=1,loc=1) for i in range(6)]
    (result/'metrics.json').write_text(json.dumps({'methods':methods}),encoding='utf8')
    manager.update(ident,state='complete',options={'lang':'c','subdir':'.'})
    pending=dict(state='complete',action='preview',preview_id='a'*32,preview={'files':[]},candidate='u0')
    (job/'assistant.json').write_text(json.dumps(pending),encoding='utf8')
    with TestClient(app,base_url='http://127.0.0.1:8765') as client:
        yield client,f'/api/jobs/{ident}/assistant',{'X-Game-SI-Token':client.get('/api/session').json()['token']},job


def wait_review(client,url):
    for _ in range(120):
        state=client.get(url+'/review').json()
        if state['state']!='running':return state
        time.sleep(.02)
    pytest.fail('Review worker did not finish')


def test_pre_review_cache_never_changes_pending_approval_and_invalidates_source(review_workbench,monkeypatch):
    client,url,headers,job=review_workbench
    original=(job/'assistant.json').read_bytes()
    calls=[]
    def provider(service,mode,prompt,*args):
        data=json.loads(prompt);calls.append(data)
        return fresh_reply([item['path'] for item in data['sources']])
    monkeypatch.setattr(assistant,'call_provider',provider)
    body=dict(action='review',service='codex',mode='cli')
    assert client.get(url+'/review').json()['state']=='idle'
    assert client.post(url,headers=headers,json=body).status_code==202
    state=wait_review(client,url)
    assert state['state']=='complete',state
    assert len(state['advice']['file_reviews'])==5
    assert {s['path'] for s in calls[0]['sources']}=={f'u{i}.c' for i in range(5)}
    assert (job/'assistant.json').read_bytes()==original
    assert client.post(url,headers=headers,json=body).status_code==202
    assert wait_review(client,url)['cached'] is True
    assert len(calls)==1
    scoring=job/'result/scoring.json'
    scores=json.loads(scoring.read_text('utf8'))
    scores['class_scores'][0]['raw']['cc']=2
    scoring.write_text(json.dumps(scores),encoding='utf8')
    assert client.get(url+'/review').json()['state']=='idle'
    assert client.post(url,headers=headers,json=body).status_code==202
    assert wait_review(client,url)['state']=='complete'
    assert len(calls)==2
    (job/'input/u0.c').write_text('int Changed(void) { return 8; }',encoding='utf8')
    assert client.get(url+'/review').json()['state']=='idle'
    assert client.post(url,headers=headers,json=body).status_code==202
    assert wait_review(client,url)['state']=='complete'
    assert len(calls)==3
    assert client.post(url,headers=headers,json=dict(body,model='other')).status_code==202
    assert wait_review(client,url)['state']=='complete'
    assert len(calls)==4
    assert (job/'assistant.json').read_bytes()==original
