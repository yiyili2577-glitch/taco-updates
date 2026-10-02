"""把 PyInstaller dist/TACO 轉成 Updater 可用的 ZIP（根目錄 app/）。"""
import argparse, os, zipfile
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument('--app-dir',required=True); p.add_argument('--version',required=True); p.add_argument('--out-dir',default='public'); a=p.parse_args()
    app=Path(a.app_dir).resolve(); out=Path(a.out_dir).resolve(); out.mkdir(parents=True,exist_ok=True); target=out/f'TACO_Update_{a.version}_win-x64.zip'
    marker=app/'BUILD_VERSION.txt'
    if not (app/'TACO.exe').is_file() or not (app/'TACOUpdater.exe').is_file() or not marker.is_file(): raise SystemExit('app-dir 缺少 TACO.exe、TACOUpdater.exe 或 BUILD_VERSION.txt')
    if marker.read_text(encoding='utf-8').strip()!=a.version: raise SystemExit('BUILD_VERSION 與 --version 不一致')
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
      for root,_,files in os.walk(app):
        for name in files:
          src=Path(root)/name; z.write(src,arcname='app/'+str(src.relative_to(app)))
    print(target)
if __name__=='__main__': main()
