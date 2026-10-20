#!/usr/bin/env python3
"""Install a macOS login daemon for an existing isolated paper history."""
import argparse
import os
from pathlib import Path
import plistlib
import subprocess


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path.home()/'.quantit/history/2026-07-01')
    args=parser.parse_args()
    repo=Path(__file__).resolve().parents[1]
    if not (args.root/'service-config.json').is_file() or not (args.root/'report.json').is_file():
        raise SystemExit('Complete and configure the initial history before installing continuation')
    label='com.quantit.history'
    directory=Path.home()/'Library/LaunchAgents'
    directory.mkdir(exist_ok=True,parents=True)
    path=directory/f'{label}.plist'
    path.write_bytes(plistlib.dumps({'Label':label,'ProgramArguments':[str(repo/'.venv311/bin/python'),
        str(repo/'scripts/run_history_service.py'),'--root',str(args.root.resolve())],
        'WorkingDirectory':str(repo),'RunAtLoad':True,'KeepAlive':True,'ThrottleInterval':30,
        'EnvironmentVariables':{'PATH':os.environ.get('PATH','/usr/bin:/bin')},
        'StandardOutPath':str(args.root/'launchd.log'),'StandardErrorPath':str(args.root/'launchd.log')}))
    domain=f'gui/{os.getuid()}'
    subprocess.run(['launchctl','bootout',f'{domain}/{label}'],capture_output=True)
    subprocess.run(['launchctl','bootstrap',domain,str(path)],check=True)
    print(path)


if __name__=='__main__':
    main()
