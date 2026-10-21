"""Small analysis result shared by the redesigned web data tests."""


def sample(extra_cc=0, cut=False):
    # a→b→c→a 순환(3), d는 a를 부름. b는 전역 상태 5.
    out = {'a': ['b'], 'b': ['c'], 'c': [] if cut else ['a'], 'd': ['a']}
    classes = [{'fqn': n, 'name': n, 'file_path': f'{n}.c', 'out_neighbors': out[n],
                'in_neighbors': [k for k, v in out.items() if n in v],
                'global_state': 5 if n == 'b' else 0} for n in 'abcd']
    methods = [{'fqn': 'a.big', 'class_fqn': 'a', 'name': 'big', 'cc': 30 + extra_cc, 'loc': 90, 'start_line': 3},
               {'fqn': 'a.small', 'class_fqn': 'a', 'name': 'small', 'cc': 4, 'loc': 8, 'start_line': 99},
               {'fqn': 'b.mid', 'class_fqn': 'b', 'name': 'mid', 'cc': 12, 'loc': 30, 'start_line': 1}]

    def raw(cc, cp, cy, gs):
        return {'cc': cc, 'coupling': cp, 'dependency_cycle': cy, 'global_state': gs, 'game_loop_centrality': 0.0}

    scores = [dict(fqn='a', name='a', file_path='a.c', loc=120, si=100.0, grade='E', raw=raw(30, 3, 2, 0)),
              dict(fqn='b', name='b', file_path='b.c', loc=40, si=75.0, grade='D', raw=raw(12, 2, 2, 5)),
              dict(fqn='c', name='c', file_path='c.c', loc=20, si=50.0, grade='C', raw=raw(1, 2, 2, 0)),
              dict(fqn='d', name='d', file_path='d.c', loc=10, si=25.0, grade='B', raw=raw(1, 1, 0, 0))]
    metrics = {'classes': classes, 'methods': methods, 'cycles': []}
    scoring = {'class_scores': scores, 'total_classes': 4, 'total_methods': 3,
               'grade_distribution': {'A': 0, 'B': 1, 'C': 1, 'D': 1, 'E': 1},
               'analysis_status': {'state': 'complete', 'language': 'c', 'syntax_files': 0}}
    return metrics, scoring
