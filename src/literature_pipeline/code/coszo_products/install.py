"""Install verified expanded artifacts, backing up replaced generated files."""
from pathlib import Path
import hashlib, json, shutil

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'package'
TARGET=Path('/Users/quakehunter/Documents/RCN Agent /data/Literature')
BACKUP=ROOT/'before_expansion'
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()

checks=json.loads((SOURCE/'coszo_collection_checksums.json').read_text())
for rel,sha in checks.items():
    assert digest(SOURCE/rel)==sha, rel
copied=0
for src in SOURCE.rglob('*'):
    if not src.is_file(): continue
    rel=src.relative_to(SOURCE); dst=TARGET/rel
    if dst.exists():
        if digest(src)==digest(dst): continue
        backup=BACKUP/rel
        backup.parent.mkdir(parents=True,exist_ok=True)
        if not backup.exists(): shutil.copy2(dst,backup)
    dst.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(src,dst); copied+=1
for rel,sha in checks.items():
    assert digest(TARGET/rel)==sha, rel
print(json.dumps({'copied_or_updated_files':copied,'verified_files':len(checks),'target':str(TARGET),'replaced_file_backup':str(BACKUP)}))
