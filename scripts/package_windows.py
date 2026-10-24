"""Create a source installer ZIP containing only public project files and model."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    version=re.search(r"APP_VERSION='([^']+)'",(ROOT/'Source/main.py').read_text()).group(1)
    output=args.output or ROOT/'artifacts'/f'AirControl-Windows-{version}.zip'
    output.parent.mkdir(parents=True,exist_ok=True)
    paths=['Source','BrowserGestures','windows','checks','docs','requirements-windows.lock','requirements-windows.in','LICENSE','NOTICE.md','PRIVACY.md','README.md','README.ru.md','CHANGELOG.md','UPSTREAM.json']
    files=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z','--',*paths],cwd=ROOT).decode().split('\0')
    files=sorted({p for p in files if p and (ROOT/p).is_file()})
    model='Models/gestures/hand_landmarker.task'
    expected='fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1'
    if hashlib.sha256((ROOT/model).read_bytes()).hexdigest()!=expected:raise SystemExit('Hand model checksum mismatch; run setup first.')
    files.append(model)
    prefix=f'AirControl-Windows-{version}'
    hashes={}
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for relative in files:
            data=(ROOT/relative).read_bytes()
            archive.writestr(prefix+'/'+relative,data)
            hashes[relative]=hashlib.sha256(data).hexdigest()
        archive.writestr(prefix+'/SHA256SUMS.json',json.dumps(hashes,indent=2)+'\n')
    print(output)

if __name__=='__main__':main()
