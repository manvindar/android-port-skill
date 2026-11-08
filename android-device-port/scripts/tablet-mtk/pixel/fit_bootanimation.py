"""Retarget a boot animation zip to another screen size without scaling the artwork.
The Pixel Tablet animation is made for a 2560x1600 landscape canvas. bootanimation stretches the canvas of desc.txt to the screen, so on this
1200x1920 portrait panel the logo came out squeezed from the sides. Here the canvas becomes the screen size and every trimmed frame keeps its pixel size
and its offset from the canvas centre (trim.txt lines are WxH+X+Y). Usage: fit_bootanimation.py IN.zip OUT.zip [WIDTH HEIGHT]"""
import re, sys, zipfile

def fit(src, dst, w=1200, h=1920):
    zi = zipfile.ZipFile(src)
    desc = zi.read('desc.txt').decode().split('\n')
    ow, oh, fps = desc[0].split()[:3]; ow, oh = int(ow), int(oh)
    dx, dy = w // 2 - ow // 2, h // 2 - oh // 2
    desc[0] = f'{w} {h} {fps}'
    with zipfile.ZipFile(dst, 'w') as zo:                       # bootanimation reads the entries in place: they must be stored, not deflated
        for i in zi.infolist():
            data = zi.read(i)
            if i.filename == 'desc.txt': data = '\n'.join(desc).encode()
            elif i.filename.endswith('/trim.txt'):
                data = re.sub(r'(\d+)x(\d+)\+(-?\d+)\+(-?\d+)', lambda m: f'{m[1]}x{m[2]}+{int(m[3]) + dx}+{int(m[4]) + dy}', data.decode()).encode()
            zo.writestr(zipfile.ZipInfo(i.filename, i.date_time), data, compress_type=zipfile.ZIP_STORED)

if __name__ == '__main__':
    fit(sys.argv[1], sys.argv[2], *map(int, sys.argv[3:5]))
