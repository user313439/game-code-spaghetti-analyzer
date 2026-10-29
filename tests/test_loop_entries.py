import json

from game_si.cli import _fix_loop_entries
from game_si.metrics import compute_metrics


def ast(*methods):
    return {'files': [{'relative_path': 'menu.c', 'classes': [{
        'fully_qualified_name': 'clang.file.menu.c', 'name': 'menu.c', 'start_line': 1, 'end_line': 99,
        'methods': [{'name': name, 'start_line': 1, 'end_line': 2, 'cyclomatic_complexity': 1, 'loc': 2,
                     'is_game_loop_entry': entry, 'invoked_names': calls} for name, entry, calls in methods]}]}]}


def test_a_revision_keeps_the_first_analysis_loop_entries(tmp_path):
    # Real case 2026-10-29: the AI named a new helper updateDataCubeReaderFrame (*Frame = entry by name),
    # which moved another file's loop centrality 0 -> 0.5 and its G-SI 94.23 -> 96.15.
    entries = tmp_path / 'entries.json'
    entries.write_text(json.dumps([['menu.c', 'JE_main']]), encoding='utf8')
    data = ast(('JE_main', True, ['drawMenu']), ('updateReaderFrame', True, ['getCost']), ('drawMenu', False, []), ('getCost', False, []))
    _fix_loop_entries(data, entries)
    flags = {m['name']: m['is_game_loop_entry'] for m in data['files'][0]['classes'][0]['methods']}
    assert flags == {'JE_main': True, 'updateReaderFrame': False, 'drawMenu': False, 'getCost': False}
    centrality = {m.name: m.game_loop_centrality for m in compute_metrics(data).methods}
    assert centrality['getCost'] == 0.0 and centrality['drawMenu'] == 0.5
