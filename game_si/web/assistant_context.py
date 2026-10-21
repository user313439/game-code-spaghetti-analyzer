"""Bounded, disclosed source context; original hashes always cover full files."""
from __future__ import annotations

import difflib
import json
from pathlib import Path
import re
from . import change_rules as rules
from .assistant import digest

PROMPT_VERSION = 'joint-files-v3'
MAX_PROMPT_BYTES = 360_000


def validate_edit_context(prompt, edits):
    payload=json.loads(prompt)
    provided={item['path']:item['content'].replace('\r\n','\n') for item in payload['sources']+payload.get('companions_available',[])}
    for edit in edits:
        old=edit.get('old')
        if not isinstance(old,str) or not old or old.replace('\r\n','\n') not in provided.get(edit.get('path'),''):
            raise ValueError('AI에 제공한 코드 범위 밖의 변경안입니다. 해당 구간을 포함해 다시 검토해 주세요.')


def validate_target_methods(advice, methods):
    resolved={}
    for row in advice['file_reviews']:
        if row.get('change_type','functions')=='declarations':
            continue
        candidates=[m for m in methods if m.get('file_path','').replace('\\','/')==row['path']]
        groups=[]
        for name in row['targets']:
            matches=[index for index,m in enumerate(candidates) if name in {m.get('name'),m.get('fqn')}]
            if not matches:
                raise ValueError(f"수정 대상 {row['path']}의 {name} 함수를 실제 함수 목록에서 확인할 수 없습니다.")
            groups.append(set(matches))
        resolved[row['path']]=(candidates,groups)
    return resolved


def _source_tree(path, text):
    if Path(path).suffix.lower() not in {'.c','.h','.cpp','.cc','.cxx','.hpp'}:return None
    from tree_sitter import Language, Parser
    import tree_sitter_c
    import tree_sitter_cpp
    grammar=tree_sitter_c if Path(path).suffix.lower() in {'.c','.h'} else tree_sitter_cpp
    return Parser(Language(grammar.language())).parse(text.encode('utf8')).root_node


def _inserted_helpers(path, text):
    root=_source_tree(path,text)
    if root is None:return []
    if root.has_error:return []
    names=[]
    for node in root.named_children:
        if node.type=='comment':continue
        if node.type!='function_definition' or not any(child.type=='storage_class_specifier' and child.text==b'static' for child in node.children):return []
        declarator=node.child_by_field_name('declarator')
        while declarator is not None and declarator.type!='identifier':
            declarator=declarator.child_by_field_name('declarator')
        if declarator is None:return []
        names.append(declarator.text.decode('utf8'))
    return names


def _ast_functions(path,text):
    root=_source_tree(path,text)
    if root is None:return {}
    from ..cpp_analyzer import _function_name
    functions={};pending=[root];source=text.encode('utf8')
    while pending:
        node=pending.pop()
        pending.extend(reversed(node.named_children))
        if node.type!='function_definition':continue
        declarator=node.child_by_field_name('declarator')
        if declarator is None:continue
        identity=' '.join(declarator.text.decode('utf8').split())
        calls=set();body=node.child_by_field_name('body');children=[body] if body is not None else []
        while children:
            child=children.pop();children.extend(child.named_children)
            if child.type=='call_expression':
                function=child.child_by_field_name('function')
                if function is not None and function.type in {'identifier','qualified_identifier'}:
                    calls.add(function.text.decode('utf8').rsplit('::',1)[-1])
        functions[identity]=dict(name=_function_name(node,source),calls=calls,
            source=node.text,valid=not node.has_error,
            static=any(child.type=='storage_class_specifier' and child.text==b'static' for child in node.children))
    return functions


def _new_ast_helpers(item, candidates, declared, explanation):
    before=_ast_functions(item['path'],item['before'])
    after=_ast_functions(item['path'],item['after'])
    targets={candidates[index].get('name') for index in declared}
    called=set().union(*(row['calls'] for identity,row in after.items()
        if row['name'] in targets and identity in before and row['source']!=before[identity]['source']))
    old_names={row['name'] for row in before.values()}
    helpers=[]
    for identity,row in after.items():
        if identity in before:continue
        name=row['name']
        if (not name or not row['valid'] or not row['static'] or name in old_names
                or not re.search(r'(?<![A-Za-z0-9_])'+re.escape(name)+r'(?![A-Za-z0-9_])',explanation) or name not in called):
            raise ValueError('새 보조 함수는 정적 함수이며 설명에 이름이 있고 변경된 대상 함수에서 실제 호출되어야 합니다.')
        helpers.append(name)
    return helpers


def _declarations_only(path, text):
    root=_source_tree(path,text)
    if root is None or root.has_error:return False
    pending=[root]
    while pending:
        node=pending.pop()
        if node.type=='function_definition':return False
        pending.extend(node.named_children)
    return True


def _function_sources(path, text):
    """Every function definition in document order. A list, not a name map: definitions with the
    same signature under #if/#else must each be compared."""
    root=_source_tree(path,text)
    if root is None:return []
    found=[];pending=[root]
    while pending:
        node=pending.pop()
        if node.type=='function_definition':
            found.append(node.text);continue
        pending.extend(reversed(node.named_children))
    return found


def _lines(text):
    """Lines split on '\\n' only (with ends), the way the analyzer numbers them."""
    return re.findall(r'[^\n]*\n|[^\n]+$',text)


def validate_preview_targets(advice, methods, preview, companions=frozenset()):
    resolved=validate_target_methods(advice,methods)
    reviews={row['path']:row for row in advice['file_reviews']}
    companion_paths={c['path'] for c in advice.get('companions',[])}
    edited=[item for item in preview['files'] if not item.get('created')]
    moves=[]
    for item in preview['files']:
        if item.get('created'):
            item['role']='created'
            if not _declarations_only(item['path'],item['after']):
                raise ValueError(f"새 헤더 {item['path']}에는 선언만 넣을 수 있습니다.")
            # The include must be a real directive (not inside a comment) that is new in this change.
            if not any(rules.resolves_to(target,item['path'])
                       for other in edited for target in rules.includes(other['after'])-rules.includes(other['before'])):
                raise ValueError(f"새 헤더 {Path(item['path']).name}를 #include로 사용하는 변경이 없습니다.")
            moves.append((item['path'],'',item['after'],True))
            continue
        if item['path'] in companion_paths:
            item['role']='companion'
            if not rules.companion_ok(item['before'],item['after']):
                raise ValueError(f"함께 수정되는 파일은 #include/using 줄만 파일당 6줄 이하로 바꿀 수 있습니다: {item['path']}")
            continue
        item['role']='target'
        review=reviews.get(item['path'])
        if review is None:
            raise ValueError(f"설명이 없는 파일의 변경안은 승인할 수 없습니다: {item['path']}")
        if review.get('change_type','functions')=='declarations':
            if Path(item['path']).suffix.lower() not in rules.C_FAMILY:
                raise ValueError('C# 파일은 아직 함수 단위 변경만 지원합니다.')
            if _function_sources(item['path'],item['before'])!=_function_sources(item['path'],item['after']):
                raise ValueError(f"선언 정리(declarations)는 함수 본문을 바꿀 수 없습니다: {item['path']}")
            moves.append((item['path'],item['before'],item['after'],False))
            continue
        candidates,groups=resolved[item['path']]
        target_indexes=set().union(*groups) if groups else set()
        before=_lines(item['before'])
        after=_lines(item['after'])
        spans=[(int(m.get('start_line') or 0),int(m.get('end_line') or 0)) for m in candidates]
        touched=set();outside=[];changed_text=[]
        for tag,i1,i2,j1,j2 in difflib.SequenceMatcher(None,before,after,autojunk=False).get_opcodes():
            if tag=='equal':continue
            if tag=='insert':
                current={index for index,(start,end) in enumerate(spans) if start-1<i1<end}
                if not current:outside.append(''.join(after[j1:j2]));continue
            else:
                current={index for index,(start,end) in enumerate(spans) if start<=i2 and end>i1}
                if any(not any(start<=line<=end for start,end in spans) for line in range(i1+1,i2+1)):
                    raise ValueError('선언한 대상 함수 밖의 기존 코드 변경은 승인할 수 없습니다.')
            if current-target_indexes:
                raise ValueError('실제 변경 함수와 파일별 수정 대상이 일치하지 않습니다.')
            touched.update(current)
            changed_text.append(''.join(after[j1:j2]))
        if not touched or any(not group.intersection(touched) for group in groups):
            raise ValueError('선언한 대상 함수의 실제 변경을 확인할 수 없습니다.')
        explanation=review['change']+'\n'+'\n'.join(review['evidence'])
        helpers=_new_ast_helpers(item,candidates,target_indexes,explanation)
        for text in outside:
            names=_inserted_helpers(item['path'],text)
            if (not names or any(name in {m.get('name') for m in candidates}
                    or name not in explanation or not re.search(r'\b'+re.escape(name)+r'\s*\(',''.join(changed_text)) for name in names)):
                raise ValueError('대상 함수 밖의 추가 코드는 설명과 호출이 확인된 새 정적 보조 함수만 허용합니다.')
            helpers.extend(names)
        if helpers:item['added_helpers']=list(dict.fromkeys(helpers))
    if moves:
        error=rules.declaration_moves(moves)
        if error:
            raise ValueError(error)


def _prior(advice):
    if not advice:
        return None
    return dict(overview=advice.get('overview', {}),
                file_reviews=[{key: value[:1500] if isinstance(value,str) else
                               [item[:1500] for item in value[:12] if isinstance(item,str)]
                               for key,value in row.items() if isinstance(value,(str,list))}
                              for row in advice.get('file_reviews',[])[:5]],
                suggestions=[item[:1000] for item in advice.get('suggestions',[])[:5]])


def _file_methods(path, methods, targets):
    rows=[{key:m.get(key) for key in ['fqn','name','start_line','end_line','cc','loc']}
          for m in methods if m.get('file_path','').replace('\\','/')==path]
    ranked=sorted(rows,key=lambda m:-(m.get('cc') or 0))
    targeted=[m for m in ranked if targets.intersection({m.get('name'),m.get('fqn')})]
    manageable=sorted(rows,key=lambda m:((m.get('loc') or
        max(1,(m.get('end_line') or 1)-(m.get('start_line') or 1)+1)),m.get('cc') or 0))
    ordered=[]
    for row in targeted+ranked[:2]+manageable+ranked:
        if row not in ordered:ordered.append(row)
    inventory=[];size=0
    for row in ordered:
        count=len(json.dumps(row,ensure_ascii=False).encode('utf8'))
        if size+count>12_000 or len(inventory)>=80:continue
        inventory.append(row);size+=count
    return inventory,len(rows),ordered, len(targeted)


def _focused_content(path, text, ordered, target_count, budget):
    lines=text.splitlines(keepends=True) or ['']
    chunks=[];ranges=[];used=0

    def add(start,end,limit):
        nonlocal used
        if any(not r['partial'] and r['start_line']<=start and r['end_line']>=end for r in ranges):return
        available=min(limit,budget-used-150)
        if available<=0:return
        snippet,where=_excerpt(lines,start,end,available)
        chunk=f"/* 제공 범위: {path}:{where['start_line']}-{where['end_line']} */\n"+snippet
        chunks.append(chunk);ranges.append(where)
        used+=len(chunk.encode('utf8'))+1

    for index,m in enumerate(ordered):
        start=int(m.get('start_line') or 1)
        end=int(m.get('end_line') or start)
        size=len(''.join(lines[max(0,start-1):end]).encode('utf8'))
        available=budget-used-4_000
        if available<=0:break
        if size<=available and (index<target_count or size<=budget//2):
            add(start,end,size)
        elif index<target_count:
            add(start,end,min(available,budget//2))
        elif index<target_count+2:
            add(start,end,min(available,budget//6))
    add(1,min(40,len(lines)),max(1,(budget-used)//2))
    add(max(1,len(lines)-24),len(lines),budget-used)
    return '\n'.join(chunks),ranges


def _excerpt(lines, start, end, budget):
    start=max(1,min(start,len(lines)))
    end=max(start,min(end,len(lines)))
    original=''.join(lines[start-1:end])
    text=original.encode('utf8')[:budget].decode('utf8',errors='ignore')
    actual_end=start+max(0,len(text.splitlines())-1)
    return text,dict(start_line=start,end_line=actual_end,partial=len(text)<len(original))


def build_prompt(stage, selected, sources, methods, advice=None, companions=None):
    decoded={path:raw.decode('utf-8-sig') for path,raw in sources.items()}
    total=sum(map(len,sources.values()))
    targets={row['path']:set(row.get('targets',[])) for row in (advice or {}).get('file_reviews',[])}
    inventories={path:_file_methods(path,methods,targets.get(path,set())) for path in decoded}
    base=dict(stage=stage,candidates=selected,previous_advice=_prior(advice),
        prompt_version=PROMPT_VERSION,
        review_paths=sorted(decoded),   # every file in sources, including paired headers sent with a selection
        scope='선택한 파일을 함께 검토합니다. 모든 파일의 역할·근거·수정 또는 유지 이유를 빠짐없이 설명합니다. 발췌되지 않은 부분의 동작을 단정하지 않습니다.',
        companions_available=[{key:item[key] for key in ['path','content','ranges']} for item in (companions or {}).values()])

    def serialize(items, mode):
        context=dict(mode=mode,total_source_bytes=total,
            sent_source_bytes=sum(len(item['content'].encode('utf8')) for item in items),
            prompt_version=PROMPT_VERSION,
            files=[{key:item[key] for key in ['path','complete','ranges']} for item in items])
        prompt=json.dumps(dict(base,sources=items,context=context),ensure_ascii=False)
        return prompt,context

    full=[dict(path=path,sha256=digest(sources[path]),content=text,complete=True,
               methods=inventories[path][0],method_count=inventories[path][1],
               ranges=[dict(start_line=1,end_line=max(1,len(text.splitlines())),partial=False)]) for path,text in decoded.items()]
    prompt,context=serialize(full,'full')
    if total<=240_000 and len(prompt.encode('utf8'))<=MAX_PROMPT_BYTES:
        return prompt,context
    budget=36_000
    while budget>=2_250:
        items=[]
        for path,text in decoded.items():
            if len(text.encode('utf8'))<=budget:
                items.append(next(item for item in full if item['path']==path))
                continue
            inventory,count,ordered,target_count=inventories[path]
            content,ranges=_focused_content(path,text,ordered,target_count,budget)
            items.append(dict(path=path,sha256=digest(sources[path]),content=content,complete=False,ranges=ranges,
                              methods=inventory,method_count=count))
        prompt,context=serialize(items,'focused')
        if len(prompt.encode('utf8'))<=MAX_PROMPT_BYTES:
            return prompt,context
        budget//=2
    raise ValueError('검토할 코드 문맥이 너무 큽니다. 선택 범위를 줄여 주세요.')
