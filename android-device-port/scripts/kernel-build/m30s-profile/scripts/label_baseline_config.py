#!/usr/bin/env python3
"""Change release metadata only; reject every functional configuration delta."""
from pathlib import Path
import datetime
import hashlib
import json
import re
import sys

BASELINE_SHA256 = 'bb1dbc7b3bf530f4edc547ea936e0d8573da3e09a743a647da4c8de8452401ef'


def settings(text):
    result = {}
    for line in text.splitlines():
        match = re.fullmatch(r'(CONFIG_\w+)=(.*)', line)
        unset = re.fullmatch(r'# (CONFIG_\w+) is not set', line)
        if match:
            assert match[1] not in result, 'Duplicate setting: ' + match[1]
            result[match[1]] = match[2]
        elif unset:
            assert unset[1] not in result, 'Duplicate setting: ' + unset[1]
            result[unset[1]] = 'n'
    return result


def label(mode, baseline, config, date):
    assert re.fullmatch(r'20\d{6}', date), 'Expected YYYYMMDD'
    datetime.datetime.strptime(date, '%Y%m%d')  # reject invalid calendar dates
    original = Path(baseline).read_bytes()
    assert hashlib.sha256(original).hexdigest() == BASELINE_SHA256, 'Unreviewed baseline config'
    expected = settings(original.decode())
    expected['CONFIG_LOCALVERSION'] = '"-perf-' + date + '"'
    expected['CONFIG_LOCALVERSION_AUTO'] = 'n'
    if mode == 'apply':
        text = original.decode().replace('CONFIG_LOCALVERSION=""', 'CONFIG_LOCALVERSION=' + expected['CONFIG_LOCALVERSION'])
        text = text.replace('CONFIG_LOCALVERSION_AUTO=y', '# CONFIG_LOCALVERSION_AUTO is not set')
        assert settings(text) == expected
        Path(config).write_text(text)
    elif mode != 'verify':
        raise ValueError('Use apply or verify')
    actual = settings(Path(config).read_text())
    changes = {key: [expected.get(key), actual.get(key)] for key in expected.keys() | actual.keys()
               if expected.get(key) != actual.get(key)}
    assert not changes, 'Unexpected kernel config changes: ' + json.dumps(changes, sort_keys=True)
    print(json.dumps({'kernel_release': '4.14.113-perf-' + date, 'functional_config_changes': 0,
                      'metadata_changes': ['CONFIG_LOCALVERSION', 'CONFIG_LOCALVERSION_AUTO'],
                      'baseline_sha256': BASELINE_SHA256,
                      'config_sha256': hashlib.sha256(Path(config).read_bytes()).hexdigest()}, indent=2))


if __name__ == '__main__':
    label(*sys.argv[1:])
