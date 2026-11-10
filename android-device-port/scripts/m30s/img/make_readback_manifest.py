#!/usr/bin/env python3
"""Hash a raw system image once into contiguous 256 MiB readback windows."""
from pathlib import Path
import hashlib
import json
import os
import sys

SYSTEM_BYTES = 5033164800
WINDOW_BYTES = 256 * 1024 * 1024


def hash_file(path, window_bytes=WINDOW_BYTES):
    assert window_bytes > 0
    whole = hashlib.sha256(); windows = []; offset = 0
    with Path(path).open('rb') as stream:
        before = os.fstat(stream.fileno())
        while offset < before.st_size:
            length = min(window_bytes, before.st_size - offset)
            remaining = length; digest = hashlib.sha256()
            while remaining:
                block = stream.read(min(2 * 1024 * 1024, remaining))
                assert block, 'Unexpected end of raw image'
                digest.update(block); whole.update(block); remaining -= len(block)
            windows.append({'index': len(windows), 'offset_bytes': offset,
                            'length_bytes': length, 'sha256': digest.hexdigest()})
            offset += length
        assert not stream.read(1), 'Raw image grew during hashing'
        after = os.fstat(stream.fileno())
        assert (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns), 'Raw image changed during hashing'
    return {'size_bytes': offset, 'sha256': whole.hexdigest(), 'window_bytes': window_bytes, 'windows': windows}


def write_manifest(image, output):
    assert Path(image).stat().st_size == SYSTEM_BYTES, 'Unexpected raw M30s system size'
    result = hash_file(image)
    assert len(result['windows']) == 19 and result['windows'][-1]['length_bytes'] == 192 * 1024 * 1024
    result.update({'schema': 'm30s-raw-readback-v1', 'partition': 'system', 'raw_image': Path(image).name,
                   'source_commit': os.environ['GITHUB_SHA'], 'release_tag': os.environ['RELEASE_TAG'],
                   'actions_run': os.environ['GITHUB_SERVER_URL'] + '/' + os.environ['GITHUB_REPOSITORY'] + '/actions/runs/' + os.environ['GITHUB_RUN_ID']})
    Path(output).write_text(json.dumps(result, indent=2) + '\n')
    print('Raw SHA256', result['sha256'], '; 19 contiguous system readback windows recorded.')


if __name__ == '__main__':
    write_manifest(*sys.argv[1:])
