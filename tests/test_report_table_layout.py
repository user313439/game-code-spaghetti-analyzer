"""Response-only table layout guards; saved report HTML is never rewritten."""
from pathlib import Path
import shutil
import subprocess

import pytest


STATIC = Path(__file__).resolve().parents[1] / 'game_si/web/static'


def test_report_table_keeps_native_layout_and_scrolls_in_a_wrapper():
    for name in ['report-embed.css', 'report-light.css']:
        css = (STATIC / name).read_text('utf8')
        assert '#hotspot-table{display:table;width:100%;' in css
        assert '.report-table-scroll{' in css and 'overflow-x:auto' in css
        assert '#hotspot-table{display:block;' not in css


def test_direct_report_wraps_table_before_skipping_iframe_resize():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is unavailable for the response script behavior check')
    script = (STATIC / 'report-embed.js').read_text('utf8')
    fixture = r'''
const assert = require('node:assert/strict');
let observed = false;
const host = {classList: {contains() {return false;}}, insertBefore(wrapper, table) { table.parentElement = wrapper; }};
const table = {parentElement: host};
global.document = {
  getElementById(id) { return id === 'hotspot-table' ? table : null; },
  createElement(tag) { return {className: '', classList: {contains() {return false;}}, appendChild(child) {child.parentElement=this;}}; },
};
global.window = {};
global.parent = global.window;
global.ResizeObserver = class { constructor() {observed = true;} };
'''
    assertions = r'''
assert.equal(table.parentElement.className, 'report-table-scroll');
assert.equal(observed, false);
'''
    result = subprocess.run([node, '-e', fixture + script + assertions], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
