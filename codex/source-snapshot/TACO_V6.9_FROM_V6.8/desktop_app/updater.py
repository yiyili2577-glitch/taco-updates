"""TACO V6.9 獨立更新器：安全解壓、安裝目錄交換、健康檢查與回復。"""
import argparse
import hashlib
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
import uuid
import zipfile
from datetime import datetime
from pathlib import Path,PurePosixPath

MAX_ENTRIES=20000
MAX_EXTRACTED_BYTES=4*1024*1024*1024


def _inside(child,parent):
    child=Path(child).resolve(); parent=Path(parent).resolve()
    return child==parent or parent in child.parents


def verify_sha256(path,expected):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    if h.hexdigest().lower()!=str(expected).lower(): raise RuntimeError('更新套件 SHA-256 二次驗證失敗。')


def safe_extract(package,destination):
    destination=Path(destination).resolve(); destination.mkdir(parents=True,exist_ok=True); seen=set(); total=0
    with zipfile.ZipFile(package,'r') as zf:
        members=zf.infolist()
        if len(members)>MAX_ENTRIES: raise RuntimeError('更新包檔案數量超過限制。')
        for member in members:
            name=member.filename.replace('\\','/'); pure=PurePosixPath(name)
            if pure.is_absolute() or '..' in pure.parts or re.match(r'^[A-Za-z]:',name): raise RuntimeError('更新包包含不安全路徑。')
            key=name.casefold().rstrip('/')
            if key in seen: raise RuntimeError('更新包包含重複路徑。')
            seen.add(key); mode=member.external_attr>>16
            if stat.S_ISLNK(mode): raise RuntimeError('更新包不可包含符號連結。')
            total+=member.file_size
            if total>MAX_EXTRACTED_BYTES: raise RuntimeError('更新包解壓大小超過限制。')
            target=(destination/Path(*pure.parts)).resolve()
            if not _inside(target,destination): raise RuntimeError('更新包路徑逸出。')
        zf.extractall(destination)


def backup_install_dir(install_dir,backup_dir):
    stamp=datetime.now().strftime('%Y%m%d_%H%M%S'); target=Path(backup_dir)/f'APP_UPDATE_PRE_{stamp}.zip'; target.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as zf:
        for root,dirs,files in os.walk(install_dir):
            dirs[:]=[d for d in dirs if d.lower() not in {'data','backups','auditlogs','logs'}]
            for name in files:
                src=Path(root)/name; zf.write(src,arcname=str(src.relative_to(install_dir)))
    return target


def apply_update(package,install_dir,backup_dir,restart_exe='',expected_sha256=''):
    package=Path(package).resolve(); install_dir=Path(install_dir).resolve(); backup_dir=Path(backup_dir).resolve()
    if not package.is_file() or not install_dir.is_dir(): raise RuntimeError('更新套件或安裝目錄不存在。')
    if _inside(install_dir,backup_dir) or _inside(backup_dir,install_dir): raise RuntimeError('安裝目錄與 ProgramData／備份目錄不可互相包含。')
    if expected_sha256: verify_sha256(package,expected_sha256)
    stage=Path(tempfile.mkdtemp(prefix='taco-update-stage-')); candidate=install_dir.parent/f'.{install_dir.name}.candidate-{uuid.uuid4().hex}'; retired=install_dir.parent/f'.{install_dir.name}.retired-{uuid.uuid4().hex}'
    try:
        safe_extract(package,stage); payload=stage/'app'
        if not payload.is_dir(): raise RuntimeError('更新包缺少 app/ 目錄。')
        marker=payload/'BUILD_VERSION.txt'
        if not marker.is_file() or not re.fullmatch(r'\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?',marker.read_text(encoding='utf-8').strip()): raise RuntimeError('更新包缺少有效 BUILD_VERSION.txt。')
        if not (payload/'TACO.exe').is_file() or not (payload/'TACOUpdater.exe').is_file(): raise RuntimeError('更新包缺少 TACO.exe 或 TACOUpdater.exe。')
        backup=backup_install_dir(install_dir,backup_dir); shutil.copytree(payload,candidate)
        os.replace(install_dir,retired); os.replace(candidate,install_dir)
        if not (install_dir/'TACO.exe').is_file(): raise RuntimeError('更新後健康檢查失敗。')
    except Exception:
        if retired.exists():
            failed=install_dir.parent/f'.{install_dir.name}.failed-{uuid.uuid4().hex}'
            if install_dir.exists(): os.replace(install_dir,failed)
            os.replace(retired,install_dir); shutil.rmtree(failed,ignore_errors=True)
        shutil.rmtree(candidate,ignore_errors=True); raise
    else: shutil.rmtree(retired,ignore_errors=True)
    finally: shutil.rmtree(stage,ignore_errors=True)
    if restart_exe and Path(restart_exe).exists(): subprocess.Popen([restart_exe],cwd=str(install_dir))
    return str(backup)


def main():
    p=argparse.ArgumentParser(); p.add_argument('--package',required=True); p.add_argument('--install-dir',required=True); p.add_argument('--backup-dir',required=True); p.add_argument('--restart',default=''); p.add_argument('--wait-pid',type=int,default=0); p.add_argument('--sha256',default=''); a=p.parse_args()
    if a.wait_pid:
        for _ in range(120):
            try: os.kill(a.wait_pid,0); time.sleep(.5)
            except OSError: break
    apply_update(a.package,a.install_dir,a.backup_dir,a.restart,a.sha256)


if __name__=='__main__': main()
