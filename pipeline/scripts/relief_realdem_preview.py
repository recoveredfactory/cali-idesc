#!/usr/bin/env python3
"""Preview: real-DEM green relief with a smooth WEST light (no re-download of the
IDESC product — uses public AWS terrarium elevation tiles).

Fetches terrarium tiles over the relief bbox, decodes to elevation, resamples to
the existing relief grid, computes a gentle west hillshade, applies a green
hypsometric ramp keyed on real metres, modulates lightness by the hillshade
(lighter west / darker-green east), and re-applies the existing coverage alpha.

Args: out_path [azimuth=295] [altitude=42] [zfactor=1.6] [shade=0.7]
"""
import sys, math, io, urllib.request
from concurrent.futures import ThreadPoolExecutor
import numpy as np
from PIL import Image

OUT = sys.argv[1]
AZ = float(sys.argv[2]) if len(sys.argv) > 2 else 295.0   # sun azimuth (W-ish)
ALT = float(sys.argv[3]) if len(sys.argv) > 3 else 42.0    # sun altitude (higher = softer)
ZF = float(sys.argv[4]) if len(sys.argv) > 4 else 1.6      # vertical exaggeration
SHADE = float(sys.argv[5]) if len(sys.argv) > 5 else 0.7   # light/shadow strength
Z = 12
WIDTH = 4000
ALPHA_SRC = "/home/eads/projects/cali-idesc/pipeline/data/dem/dem_oscuro.png"
# bbox corners (lon/lat): TL(-77.2,4) ... BR(-76,2.9)
WEST, EAST, NORTH, SOUTH = -77.2, -76.0, 4.0, 2.9

# green hypsometric ramp by ELEVATION (metres) -> RGB. Valley ~950m.
RAMP = [(850, 240, 235, 218), (1050, 196, 210, 168), (1500, 138, 180, 116),
        (2200, 84, 150, 92), (3000, 46, 112, 68), (4200, 28, 84, 54)]

R = 6378137.0
def mx(lon): return R * math.radians(lon)
def my(lat): return R * math.log(math.tan(math.pi/4 + math.radians(lat)/2))
def lon2tx(lon, z): return (lon + 180.0) / 360.0 * (1 << z)
def lat2ty(lat, z):
    s = math.sin(math.radians(lat))
    return (0.5 - math.log((1+s)/(1-s)) / (4*math.pi)) * (1 << z)

tx0, tx1 = int(math.floor(lon2tx(WEST, Z))), int(math.floor(lon2tx(EAST, Z)))
ty0, ty1 = int(math.floor(lat2ty(NORTH, Z))), int(math.floor(lat2ty(SOUTH, Z)))
nx, ny = tx1 - tx0 + 1, ty1 - ty0 + 1
print(f"tiles z{Z}: x{tx0}..{tx1} y{ty0}..{ty1} = {nx}x{ny} = {nx*ny}")

mosaic = np.zeros((ny*256, nx*256), np.float32)
def fetch(tx, ty):
    url = f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{Z}/{tx}/{ty}.png"
    req = urllib.request.Request(url, headers={"User-Agent": "cali-relief/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        a = np.asarray(Image.open(io.BytesIO(r.read())).convert("RGB")).astype(np.float32)
    elev = a[..., 0]*256 + a[..., 1] + a[..., 2]/256 - 32768
    return tx, ty, elev
with ThreadPoolExecutor(max_workers=16) as ex:
    for tx, ty, elev in ex.map(lambda t: fetch(*t), [(x, y) for x in range(tx0, tx1+1) for y in range(ty0, ty1+1)]):
        r0, c0 = (ty-ty0)*256, (tx-tx0)*256
        mosaic[r0:r0+256, c0:c0+256] = elev

# mosaic mercator extent (web-merc is linear in tiles)
def tx2mx(tx, z): return (tx/(1 << z))*2*math.pi*R - math.pi*R
def ty2my(ty, z): return math.pi*R - (ty/(1 << z))*2*math.pi*R
mosX0, mosX1 = tx2mx(tx0, Z), tx2mx(tx1+1, Z)
mosY0, mosY1 = ty2my(ty0, Z), ty2my(ty1+1, Z)  # north, south

# output grid in mercator (matches the existing relief image extent)
H = round(WIDTH * (my(NORTH)-my(SOUTH)) / (mx(EAST)-mx(WEST)))
ox = np.linspace(mx(WEST), mx(EAST), WIDTH)
oy = np.linspace(my(NORTH), my(SOUTH), H)
fx = (ox - mosX0) / (mosX1 - mosX0) * (mosaic.shape[1]-1)
fy = (mosY0 - oy) / (mosY0 - mosY1) * (mosaic.shape[0]-1)
ix, iy = np.clip(fx, 0, mosaic.shape[1]-1).astype(int), np.clip(fy, 0, mosaic.shape[0]-1).astype(int)
elev = mosaic[np.ix_(iy, ix)]  # nearest is fine at this scale

# pixel size (metres) for slope
px_m = (mx(EAST)-mx(WEST)) / WIDTH * math.cos(math.radians((NORTH+SOUTH)/2))
gy, gx = np.gradient(elev * ZF, px_m)
slope = np.pi/2 - np.arctan(np.hypot(gx, gy))
aspect = np.arctan2(-gy, gx)
azr, altr = math.radians(AZ), math.radians(ALT)
hs = np.sin(altr)*np.sin(slope) + np.cos(altr)*np.cos(slope)*np.cos((azr - math.pi/2) - aspect)
hs = np.clip(hs, 0, 1)

# green tint by elevation
ev = np.array([s[0] for s in RAMP], np.float32)
tint = np.stack([np.interp(elev, ev, np.array([s[i] for s in RAMP], np.float32)) for i in (1, 2, 3)], -1)

# lighter west / darker-green east, smoothly
f = ((1-SHADE/2) + SHADE*hs)[..., None]
out = np.clip(tint * f, 0, 255)

# re-apply existing coverage alpha (irregular Cali shape), resized to this grid
amask = Image.open(ALPHA_SRC).convert("RGBA").resize((WIDTH, H), Image.BILINEAR)
a = np.asarray(amask)[..., 3]
Image.fromarray(np.dstack([out, a]).astype(np.uint8), "RGBA").save(OUT)
print(f"wrote {OUT} {WIDTH}x{H}  elev {elev.min():.0f}..{elev.max():.0f}m  az={AZ} alt={ALT} zf={ZF} shade={SHADE}")
