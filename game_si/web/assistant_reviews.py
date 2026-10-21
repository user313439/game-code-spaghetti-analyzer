"""Explicit, cached top-five reviews, separate from pending edit approvals."""
from copy import deepcopy
import json
import threading
import time
from . import assistant
from .assistant_context import build_prompt, PROMPT_VERSION, validate_target_methods
from .jobs import BusyError


class AssistantReviews:
    def __init__(self, owner):
        self.owner=owner
        self.lock=owner.lock
        self.records={}
        self.threads=[]

    def _record(self, ident):
        if ident not in self.records:
            path=self.owner.folder(ident)/'assistant_reviews.json'
            data=json.loads(path.read_text('utf8')) if path.is_file() else dict(active={'state':'idle'},entries={})
            if data['active'].get('state')=='running':
                data['active'].update(state='interrupted',error='사전 검토가 중단되었습니다.')
            self.records[ident]=data
        return self.records[ident]

    def _save(self,ident):
        path=self.owner.folder(ident)/'assistant_reviews.json'
        temporary=path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.records[ident],ensure_ascii=False,indent=2),encoding='utf8')
        temporary.replace(path)

    def _snapshot(self,ident):
        selected=[];seen=set()
        for row in self.owner.candidates(ident):
            if row['file_path'] not in seen:
                selected.append(row);seen.add(row['file_path'])
            if len(selected)==5:break
        if not selected:
            raise ValueError('검토할 소스 후보가 없습니다.')
        sources={row['file_path']:assistant.source_file(self.owner.source(ident),row['file_path']).read_bytes() for row in selected}
        return selected,sources,{path:assistant.digest(raw) for path,raw in sources.items()}

    def busy(self,ident):
        return self._record(ident)['active'].get('state')=='running'

    def _key(self,selected,hashes,service,mode,model):
        return assistant.digest(json.dumps(dict(hashes=hashes,candidates=selected,service=service,
            mode=mode,model=model,version=PROMPT_VERSION),ensure_ascii=False,sort_keys=True).encode('utf8'))

    def get(self,ident):
        self.owner.folder(ident)
        with self.lock:
            state=deepcopy(self._record(ident)['active'])
            if state.get('state')=='complete':
                try:
                    selected,_,hashes=self._snapshot(ident)
                    key=self._key(selected,hashes,state.get('service'),state.get('mode'),state.get('model',''))
                    if key!=state.get('review_key'):
                        return {'state':'idle','stale':True}
                except ValueError:
                    return {'state':'idle','stale':True}
            return state

    def selected_advice(self,ident,selected,hashes,service,mode,model):
        review=self.get(ident)
        names={row['fqn'] for row in selected}
        if (review.get('state')!='complete' or review.get('prompt_version')!=PROMPT_VERSION
                or (review.get('service'),review.get('mode'),review.get('model',''))!=(service,mode,model)
                or not names.issubset(set(review.get('candidates',[])))
                or any(review.get('source_hashes',{}).get(path)!=value for path,value in hashes.items())):
            return None
        advice=deepcopy(review.get('advice'))
        try:
            assistant.validate_scope(advice,list(review['source_hashes']))
            methods=json.loads((self.owner.folder(ident)/'result/metrics.json').read_text('utf8')).get('methods',[])
            validate_target_methods(advice,methods)
        except (ValueError,KeyError,TypeError):
            return None
        paths=set(hashes)
        advice['file_reviews']=[row for row in advice['file_reviews'] if row['path'] in paths]
        if len(paths)!=len(review['source_hashes']):
            rows=advice['file_reviews']
            def summary(key):
                return '\n'.join(f"{row['path']}: {row[key]}" for row in rows)[:1500]
            advice['overview']=dict(title=f'선택한 {len(rows)}개 파일의 검토입니다.',
                problem=summary('finding'),reason=summary('reason'),change=summary('change'),
                expected_effect=summary('expected_effect'))
            advice['relationships']=[]
            advice['reasons']=[f"{row['path']}: {row['reason']}"[:5000] for row in rows]
            advice['suggestions']=[f"{row['path']}: {row['change']}"[:5000] for row in rows]
            advice['tests']=list(dict.fromkeys(check for row in rows for check in row['checks']))[:8]
        advice['edits']=[]
        return assistant.validate_scope(advice,list(hashes))

    def start(self,ident,body):
        service,mode=body.get('service'),body.get('mode')
        if service not in assistant.SERVICES or mode not in {'cli','api'}:
            raise ValueError('AI 연결 방식을 선택해 주세요.')
        if mode=='api' and (not body.get('api_key') or not body.get('model')):
            raise ValueError('본인 API 키와 모델 이름이 필요합니다.')
        with self.lock:
            record=self._record(ident)
            if self.busy(ident) or self.owner.get(ident).get('state')=='running':
                raise BusyError('진행 중인 AI 작업을 기다려 주세요.')
            selected,sources,hashes=self._snapshot(ident)
            key=self._key(selected,hashes,service,mode,body.get('model',''))
            if key in record['entries']:
                record['active']=dict(deepcopy(record['entries'][key]),cached=True)
                self._save(ident)
                return self.get(ident)
            methods=json.loads((self.owner.folder(ident)/'result/metrics.json').read_text('utf8')).get('methods',[])
            prompt,context=build_prompt('제안 단계',selected,sources,methods)
            record['active']=dict(state='running',action='review',candidates=[row['fqn'] for row in selected],
                source_hashes=hashes,service=service,mode=mode,model=body.get('model',''),started_at=time.time(),
                cached=False,review_key=key,prompt_version=PROMPT_VERSION,context=context,
                progress=dict(stage='ai',label='상위 후보를 함께 검토합니다.',step=1,total=4,indeterminate=True))
            self._save(ident)
            worker=threading.Thread(target=self._run,args=(ident,dict(body),prompt,key),daemon=True)
            self.threads.append(worker);worker.start()
            return self.get(ident)

    def _run(self,ident,body,prompt,key):
        try:
            data=assistant.call_provider(body['service'],body['mode'],prompt,body.get('model',''),body.get('api_key',''))
            with self.lock:
                record=self.records[ident];state=record['active']
                selected,_,hashes=self._snapshot(ident)
                if self._key(selected,hashes,state['service'],state['mode'],state['model'])!=key:
                    raise ValueError('사전 검토 중 원본 코드나 지표가 변경되었습니다. 다시 검토해 주세요.')
                assistant.validate_scope(data,list(hashes))
                methods=json.loads((self.owner.folder(ident)/'result/metrics.json').read_text('utf8')).get('methods',[])
                validate_target_methods(data,methods)
                state.update(state='complete',advice=data,finished_at=time.time(),
                    progress=dict(stage='complete',label='사전 검토를 마쳤습니다.',step=4,total=4,indeterminate=False))
                record['entries'][key]=deepcopy(state)
                while len(record['entries'])>8:record['entries'].pop(next(iter(record['entries'])))
                self._save(ident)
        except Exception as exc:
            with self.lock:
                self.records[ident]['active'].update(state='failed',finished_at=time.time(),
                    error=str(exc) if isinstance(exc,ValueError) else '사전 검토를 완료하지 못했습니다. AI 연결을 확인해 주세요.')
                self._save(ident)
        finally:
            body.pop('api_key',None)

    def close(self):
        for worker in self.threads:worker.join(timeout=1)
