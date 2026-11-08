#!/usr/bin/env python3
"""3-way merge of upstream linux-stable (BASE -> TARGET) into Samsung's tree (OURS, based on BASE).
usage: merge_stable.py BASE_DIR TARGET_DIR OURS_DIR REPORT
Edits OURS_DIR in place. Conflicted files keep git conflict markers and are listed in REPORT."""
import filecmp, os, shutil, subprocess, sys

base, target, ours, report = sys.argv[1:5]
clean, conflicts, added, deleted, skipped = [], [], [], [], []

def files(root):
    for d, _, fs in os.walk(root):
        for f in fs:
            yield os.path.relpath(os.path.join(d, f), root)

def same(a, b):
    return filecmp.cmp(a, b, shallow=False)

for rel in sorted(set(files(base)) | set(files(target))):
    b, t, o = (os.path.join(r, rel) for r in (base, target, ours))
    hb, ht, ho = os.path.lexists(b), os.path.lexists(t), os.path.lexists(o)
    if hb and ht and same(b, t):
        continue                                   # upstream did not touch it
    if os.path.islink(t) or os.path.islink(o):
        skipped.append(rel); continue
    if not ht:                                     # upstream deleted it
        if ho and hb and same(b, o):
            os.remove(o); deleted.append(rel)
        elif ho:
            conflicts.append((rel, "deleted upstream, modified by Samsung"))
        continue
    if not hb:                                     # upstream added it
        if not ho:
            os.makedirs(os.path.dirname(o), exist_ok=True); shutil.copy2(t, o); added.append(rel)
        elif not same(t, o):
            conflicts.append((rel, "added upstream, exists differently in Samsung tree"))
        continue
    if not ho:                                     # Samsung removed it, upstream changed it: keep removed
        skipped.append(rel); continue
    if same(b, o):                                 # Samsung did not touch it
        shutil.copy2(t, o); clean.append(rel); continue
    r = subprocess.run(["git", "merge-file", "-L", "samsung", "-L", "base", "-L", "stable", o, b, t],
                       capture_output=True)
    if r.returncode == 0:
        clean.append(rel)
    elif r.returncode > 0 and r.returncode < 127:
        conflicts.append((rel, "%d hunk(s)" % r.returncode))
    else:
        conflicts.append((rel, "merge-file failed (binary?): " + r.stderr.decode()[:80]))

with open(report, "w") as f:
    f.write("merged clean (incl. untouched-by-Samsung): %d\nadded: %d\ndeleted: %d\nskipped: %d\nCONFLICTS: %d\n\n"
            % (len(clean), len(added), len(deleted), len(skipped), len(conflicts)))
    for rel, why in conflicts:
        f.write("%s\t%s\n" % (rel, why))
    f.write("\n# skipped\n" + "\n".join(skipped) + "\n")
print(open(report).read().split("\n\n")[0])
