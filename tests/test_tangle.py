from game_si.web import tangle
from web_redesign_sample import sample


def test_measure_counts_absolute_components():
    m, s = sample()
    v = tangle.measure(m, s)['values']
    assert v == {'cycle_units': 3, 'links': 4, 'complex_excess': 10,
                 'excess_complexity': 22, 'global_access': 5}


def test_compare_is_100_for_same_result_and_drops_when_untangled():
    base = tangle.measure(*sample())
    assert tangle.compare(base, base)['index'] == 100.0
    after = tangle.measure(*sample(extra_cc=-15, cut=True))
    result = tangle.compare(base, after)
    rows = {r['key']: r for r in result['components']}
    assert rows['cycle_units']['after'] == 0 and rows['links']['after'] == 3
    assert rows['complex_excess']['after'] == 0
    assert result['index'] == 41.36 and result['same_units'] is True


def test_splitting_a_huge_function_lowers_the_complex_part():
    # One CC 120 function split into CC 60 + three CC 25 pieces: more functions past 20, far less past 20.
    def metrics(ccs):
        return {'classes': [], 'methods': [{'cc': cc} for cc in ccs]}
    before, after = tangle.measure(metrics([120, 5])), tangle.measure(metrics([60, 25, 25, 25, 5]))
    assert before['values']['complex_excess'] == 100 and after['values']['complex_excess'] == 55
    assert tangle.compare(before, after)['index'] < 100


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
