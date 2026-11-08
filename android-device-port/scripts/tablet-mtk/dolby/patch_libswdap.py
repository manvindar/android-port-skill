"""Patch the stock Lenovo /vendor/lib/soundfx/libswdap.so (Dolby DAP effect) so the audio HAL does not double free.
Usage: patch_libswdap.py IN.so OUT.so. Only the original of the TB-X606V_USR_S300665 firmware is accepted (SHA-256 below); the patch is 4 bytes: a Thumb-2 `nop.w`
replaces the call at file offset 0xcc80c. The library itself is not in this repository."""
import hashlib, sys
ORIG = '033bce6c8479686fe47b474bc2a711356544e591f9c44fff3ae01e7ae7b12d88'
PATCHED = 'e36e7e6b3006a98e4823f259ba146366ffd540e971a9ed55b09713497cf13942'
OFF, OLD, NEW = 0xcc80c, bytes.fromhex('cff008ef'), bytes.fromhex('aff30080')

def patch(data):
    h = hashlib.sha256(data).hexdigest()
    if h == PATCHED: return data
    if h != ORIG: raise SystemExit(f'unknown libswdap.so (sha256 {h}): only the TB-X606V firmware V9.56 library is supported')
    assert data[OFF:OFF + 4] == OLD
    out = data[:OFF] + NEW + data[OFF + 4:]
    assert hashlib.sha256(out).hexdigest() == PATCHED
    return out

if __name__ == '__main__':
    open(sys.argv[2], 'wb').write(patch(open(sys.argv[1], 'rb').read()))
