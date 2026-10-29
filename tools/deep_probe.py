"""Run the app's 'deep' AI change on analysed jobs outside the web server and record why replies are turned down.

Copies each job (job.json, result/, input/) into a scratch jobs folder, starts the same AssistantJobs flow the
page starts (direct plan, top candidates by G-SI, one per file), and keeps every AI program's raw answer and
token count next to the app's own records. Nothing in the original jobs folder is changed.

    py -3.10 tools/deep_probe.py --jobs <jobs folder> --job <id> [--job <id> ...] --out <scratch folder>
        [--service codex] [--model gpt-6.1-sol] [--files 5] [--passes 1] [--effort low]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from game_si.web import assistant, assistant_jobs  # noqa: E402
from game_si.web.assistant_jobs import AssistantJobs  # noqa: E402
from game_si.web.jobs import JobManager  # noqa: E402

CAPTURE_LOCK = threading.Lock()


def copy_job(source: Path, target: Path):
    if target.exists():
        return
    target.mkdir(parents=True)
    for name in ['job.json', 'compile_commands.json']:
        if (source / name).is_file():
            shutil.copy2(source / name, target / name)
    for name in ['result', 'input']:
        shutil.copytree(source / name, target / name)


def capture(folder: Path, effort=''):
    """Wrap run_cli: keep the command (without the prompt), the reply file, stdout/stderr and the time taken.
    `effort` adds a Codex reasoning effort (the app sends none, so each model's default applies)."""
    original = assistant.run_cli
    counter = [0]

    def run_cli(command, prompt, root, timeout=None, env=None):
        if effort and 'exec' in command and command[-1] == '-':
            command = command[:-1] + ['-c', f'model_reasoning_effort="{effort}"', '-']
        started = time.time()
        error = None
        try:
            result = original(command, prompt, root, timeout, env)
            return result
        except BaseException as exc:
            error, result = repr(exc), None
            raise
        finally:
            reply_path = None
            if '-o' in command:
                reply_path = Path(command[command.index('-o') + 1])
            reply = reply_path.read_text('utf8', errors='replace') if reply_path and reply_path.is_file() else None
            stderr = (result.stderr if result else '') or ''
            tokens = re.findall(r'tokens used\s*\n?\s*([\d,]+)', stderr)
            with CAPTURE_LOCK:
                counter[0] += 1
                number = counter[0]
            row = {'number': number, 'thread': threading.current_thread().name, 'seconds': round(time.time() - started, 1),
                   'prompt_bytes': len(prompt.encode('utf8')), 'returncode': result.returncode if result else None,
                   'error': error, 'tokens_used': tokens[-1] if tokens else None,
                   'command': [c for c in command if len(c) < 300],
                   'stdout_tail': (result.stdout if result else '')[-4000:], 'stderr_tail': stderr[-6000:], 'reply': reply}
            (folder / f'call-{number:03d}.json').write_text(json.dumps(row, ensure_ascii=False, indent=1), encoding='utf8')
    assistant.run_cli = run_cli


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--jobs', required=True, type=Path)
    parser.add_argument('--job', action='append', required=True)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--service', default='codex')
    parser.add_argument('--model', default='gpt-6.1-sol')
    parser.add_argument('--files', type=int, default=5)
    parser.add_argument('--passes', type=int, default=1)
    parser.add_argument('--effort', default='')
    parser.add_argument('--pick', action='append', default=[], help='file name to take (repeatable); default: top G-SI')
    args = parser.parse_args()

    assistant_jobs.DEEP_PASSES = args.passes
    root = args.out / 'jobs'
    root.mkdir(parents=True, exist_ok=True)
    for ident in args.job:
        copy_job(args.jobs / ident, root / ident)
    calls = args.out / 'calls'
    calls.mkdir(exist_ok=True)
    capture(calls, args.effort)
    manager = JobManager(root)
    jobs = AssistantJobs(manager)
    summary = []
    for ident in args.job:
        candidates, seen = [], set()
        for row in jobs.candidates(ident):
            name = Path(row['file_path']).name
            if row['file_path'] in seen or (args.pick and name not in args.pick):
                continue
            seen.add(row['file_path'])
            candidates.append(row['fqn'])
            if len(candidates) == args.files:
                break
        body = {'action': 'preview', 'strategy': 'deep', 'direct': True, 'candidates': candidates,
                'service': args.service, 'mode': 'cli', 'model': args.model}
        started = time.time()
        print(f'[{ident[:8]}] {manager.get(ident)["name"]}: {len(candidates)} files, {args.service} {args.model}', flush=True)
        jobs.start(ident, body)
        while jobs.get(ident).get('state') == 'running':
            time.sleep(5)
        state = jobs.get(ident)
        for w in state.get('workers', []):
            row = {'job': manager.get(ident)['name'], 'file': w['label'], 'state': w['state'], 'seconds': w.get('seconds'),
                   'targets': w.get('targets'), 'retried': w.get('retried'), 'retry_reason': w.get('retry_reason'),
                   'error': w.get('error'), 'note': w.get('note'), 'steps_done': w.get('steps_done'),
                   'passes': [{k: p.get(k) for k in ['step', 'state', 'reason', 'cc', 'helpers']} for p in w.get('passes') or []]}
            summary.append(row)
            print(f"  {w['label']}: {w['state']} | {(w.get('error') or w.get('note') or '')[:160]}", flush=True)
        print(f'  ({round(time.time() - started)}s, job state {state.get("state")}: {(state.get("error") or "")[:200]})', flush=True)
        (args.out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf8')


if __name__ == '__main__':
    main()
