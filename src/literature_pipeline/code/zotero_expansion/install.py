"""Install the verified unified package while backing up replaced files."""
import hashlib,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'package'
TARGET=Path('/Users/quakehunter/Documents/RCN Agent /data/Literature')
BACKUP=ROOT/'before_zotero_expansion'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
checks=json.loads((SOURCE/'literature_collection_checksums.json').read_text())
for rel,h in checks.items():assert sha(SOURCE/rel)==h,rel
copied=0
for src in SOURCE.rglob('*'):
    if not src.is_file():continue
    rel=src.relative_to(SOURCE);dst=TARGET/rel
    if dst.exists() and sha(dst)==sha(src):continue
    if dst.exists():
        old=BACKUP/rel;old.parent.mkdir(parents=True,exist_ok=True)
        if not old.exists():shutil.copy2(dst,old)
    dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst);copied+=1
for rel,h in checks.items():assert sha(TARGET/rel)==h,rel
print(json.dumps({'copied_or_updated_files':copied,'verified_files':len(checks),'target':str(TARGET),'backup':str(BACKUP)}))
