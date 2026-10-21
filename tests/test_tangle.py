from game_si.web import tangle
from web_redesign_sample import sample


def test_measure_counts_absolute_components():
    m, s = sample()
    v = tangle.measure(m, s)['values']
    assert v == {'cycle_units': 3, 'links': 4, 'complex_functions': 1,
                 'excess_complexity': 22, 'global_access': 5}


def test_compare_is_100_for_same_result_and_drops_when_untangled():
    base = tangle.measure(*sample())
    assert tangle.compare(base, base)['index'] == 100.0
    after = tangle.measure(*sample(extra_cc=-15, cut=True))
    result = tangle.compare(base, after)
    rows = {r['key']: r for r in result['components']}
    assert rows['cycle_units']['after'] == 0 and rows['links']['after'] == 3
    assert rows['complex_functions']['after'] == 0
    assert result['index'] == 41.36 and result['same_units'] is True


def test_zero_baseline_components_are_excluded():
    m, s = sample()
    for c in m['classes']:
        c['global_state'] = 0
    base = tangle.measure(m, s)
    result = tangle.compare(base, base)
    assert 'global_access' not in {r['key'] for r in result['components'] if r['included']}
    assert result['index'] == 100.0


def test_unit_set_change_is_reported():
    base = tangle.measure(*sample())
    m, s = sample()
    m['classes'].append({'fqn': 'e', 'name': 'e', 'file_path': 'e.c', 'out_neighbors': [],
                         'in_neighbors': [], 'global_state': 0})
    assert tangle.compare(base, tangle.measure(m, s))['same_units'] is False
