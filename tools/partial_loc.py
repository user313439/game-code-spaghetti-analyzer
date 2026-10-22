"""How well the G-SI ranking points at files with past bug-fix touches, beyond file size.

Uses exactly the file set and rank correlation of game_si/validate.py (reports/<case>/validation.json,
file_rows; Spearman with average ranks, two-sided p from the Fisher z normal approximation).
LOC here is validate.py's loc_total: the summed body lines of the functions in the file.

1. Top 20% of files by G-SI, LOC and CC: share of all bug-fix touches they hold. Files tied at the
   cut-off are counted fractionally (the expected share when ties are broken at random), so the
   share of a random 20% of files is exactly 20%.
2. Spearman partial correlation with bug-fix touches, controlling for size:
   r_xy.z = (r_xy - r_xz r_yz) / sqrt((1 - r_xz^2)(1 - r_yz^2)), p from z = atanh(r) sqrt((n-4)/1.06).
   Size is LOC, and as a robustness check the physical line count of each file in the fixed
   benchmark checkout (benchmarks/, same commits as the fixed experiment).
3. Bootstrap 95% intervals (2,000 resamples of files, seed 20261022) for the partial correlations
   and for rho(G-SI) - rho(CC).

Writes reports/partial_loc.json. Run from the repository root:  py -3.10 tools/partial_loc.py
"""
import json, math, random, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from game_si.validate import spearman, _phi  # noqa: E402

# case -> (benchmark checkout, analysed subfolder, fixed commit)
CASES = {'openra-game': ('OpenRA', 'OpenRA.Game', '8f2138c71106aaffd8a288b56d1c9ef6013700ba'),
         'openra-mods-common': ('OpenRA', 'OpenRA.Mods.Common', '8f2138c71106aaffd8a288b56d1c9ef6013700ba'),
         'chocolate-doom': ('chocolate-doom', 'src', 'c62b634f394e64dd51dec7e6f890496f43a56ade'),
         'openrct2': ('OpenRCT2', 'src/openrct2', '7a2cddeed1304f284829ffb0c91f31557819c51e')}
SEED, RESAMPLES, SHARE = 20261022, 2000, 0.2


def partial(rxy, rxz, ryz):
    return (rxy - rxz * ryz) / math.sqrt((1 - rxz ** 2) * (1 - ryz ** 2))


def partial_p(r, n):
    z = math.atanh(r) * math.sqrt((n - 4) / 1.06)
    return math.erfc(abs(z) / math.sqrt(2))


def top_share(score, bug, share=SHARE):
    """Expected share of all bug-fix touches in the top `share` of files, ties at the cut-off split evenly."""
    k = len(score) * share
    groups = {}
    for s, b in zip(score, bug):
        groups.setdefault(s, []).append(b)
    taken, found = 0.0, 0.0
    for s in sorted(groups, reverse=True):
        g = groups[s]
        room = k - taken
        if room <= 0:
            break
        part = min(1.0, room / len(g))
        found += part * sum(g)
        taken += part * len(g)
    return found / sum(bug)


def stats(gsi, size, cc, bug):
    r = {k: spearman(x, bug)[0] for k, x in [('gsi', gsi), ('size', size), ('cc', cc)]}
    return r, partial(r['gsi'], spearman(gsi, size)[0], r['size']), partial(r['cc'], spearman(cc, size)[0], r['size'])


def interval(values):
    v = sorted(x for x in values if not math.isnan(x))
    return [round(v[int(0.025 * len(v))], 3), round(v[int(0.975 * len(v)) - 1], 3)]


def physical_lines(case, rows):
    repo, subdir, sha = CASES[case]
    checkout = ROOT / 'benchmarks' / repo
    head = subprocess.check_output(['git', '-C', str(checkout), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = subprocess.check_output(['git', '-C', str(checkout), 'status', '--porcelain'], text=True).strip()
    if head != sha or dirty:
        raise RuntimeError(f'{repo} is not the clean fixed commit {sha}')
    return [float(len((checkout / subdir / r['file_path']).read_bytes().splitlines())) for r in rows]


def main():
    rng = random.Random(SEED)
    out = {'source': 'reports/<case>/validation.json file_rows (same files as file_correlations); physical lines from benchmarks/ at the fixed commits',
           'loc': 'validate.py loc_total = summed body lines of the functions in the file',
           'method': {'top_share': f'top {SHARE:.0%} of files by each score, ties at the cut-off counted fractionally; random = {SHARE:.0%}',
                      'partial': 'Spearman first-order partial correlation controlling for size; p from Fisher z, sqrt((n-4)/1.06)',
                      'bootstrap': f'{RESAMPLES} resamples of files, seed {SEED}, percentile 95% interval'},
           'cases': {}}
    for case in CASES:
        v = json.loads((ROOT / 'reports' / case / 'validation.json').read_text('utf-8-sig'))
        rows = v['file_rows']
        gsi, loc, cc, bug = ([float(r[k]) for r in rows] for k in ['si_max', 'loc_total', 'cc_max', 'bugfix_count'])
        lines = physical_lines(case, rows)
        n = len(rows)
        r, p_g, p_c = stats(gsi, loc, cc, bug)
        rl, pl_g, pl_c = stats(gsi, lines, cc, bug)
        # the same correlations as table 11 (validation.json)
        table = {c['name']: c for c in v['file_correlations']}
        assert table['file_si_vs_bugfix']['n'] == n
        for key, name in [('gsi', 'file_si_vs_bugfix'), ('size', 'file_loc_vs_bugfix'), ('cc', 'file_cc_vs_bugfix')]:
            assert round(r[key], 4) == table[name]['spearman_rho'], (case, key)
        boot = {k: [] for k in ['gsi', 'cc', 'diff', 'gsi_lines', 'cc_lines']}
        for _ in range(RESAMPLES):
            idx = [rng.randrange(n) for _ in range(n)]
            pick = lambda xs: [xs[i] for i in idx]
            try:
                br, bg, bc = stats(pick(gsi), pick(loc), pick(cc), pick(bug))
                _, lg, lc = stats(pick(gsi), pick(lines), pick(cc), pick(bug))
            except (ValueError, ZeroDivisionError):
                continue
            for k, x in [('gsi', bg), ('cc', bc), ('diff', br['gsi'] - br['cc']), ('gsi_lines', lg), ('cc_lines', lc)]:
                boot[k].append(x)
        shares = {k: top_share(x, bug) for k, x in [('gsi', gsi), ('loc', loc), ('cc', cc), ('lines', lines)]}
        rho = {'gsi': r['gsi'], 'loc': r['size'], 'cc': r['cc'], 'lines': rl['size']}
        out['cases'][case] = {
            'files': n, 'bugfix_touches': int(sum(bug)), 'files_without_function_loc': sum(1 for x in loc if x == 0),
            'rho': {k: round(x, 4) for k, x in rho.items()},
            # validate.py prints 0 once 1 - Phi(z) underflows; erfc gives the same p without that rounding
            'p_value_rho': {k: math.erfc(abs(math.atanh(x) * math.sqrt((n - 3) / 1.06)) / math.sqrt(2)) for k, x in rho.items()},
            'partial_given_loc': {'gsi': round(p_g, 3), 'cc': round(p_c, 3)},
            'partial_p': {'gsi': partial_p(p_g, n), 'cc': partial_p(p_c, n)},
            'partial_ci95': {'gsi': interval(boot['gsi']), 'cc': interval(boot['cc'])},
            'partial_given_lines': {'gsi': round(pl_g, 3), 'cc': round(pl_c, 3)},
            'partial_lines_ci95': {'gsi': interval(boot['gsi_lines']), 'cc': interval(boot['cc_lines'])},
            'rho_gsi_minus_cc': round(r['gsi'] - r['cc'], 4), 'rho_gsi_minus_cc_ci95': interval(boot['diff']),
            'bootstrap_valid_resamples': len(boot['gsi']),
            'top20_share': {k: round(x, 3) for k, x in shares.items()},
            'top20_vs_random': {k: round(x / SHARE, 2) for k, x in shares.items()},
        }
    dest = ROOT / 'reports' / 'partial_loc.json'
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
    print('wrote', dest.relative_to(ROOT))


if __name__ == '__main__':
    main()
