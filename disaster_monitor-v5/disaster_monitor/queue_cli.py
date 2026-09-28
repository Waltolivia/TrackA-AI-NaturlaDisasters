import argparse,json
from pathlib import Path
from .config import settings
from .services.prompter import JsonPrompter

def main():
    ap=argparse.ArgumentParser(description='Inspect/acknowledge Disaster Monitor machine messages')
    sub=ap.add_subparsers(dest='cmd',required=True)
    sub.add_parser('list')
    for name in ('claim','ack','fail'):
        p=sub.add_parser(name);p.add_argument('file')
    a=ap.parse_args();q=JsonPrompter(settings.outbox_path)
    if a.cmd=='list':
        for state in ('pending','processing','completed','failed'):
            files=sorted((Path(settings.outbox_path)/state).glob('*.json'));print(f'{state}: {len(files)}');[print(' ',x) for x in files]
    else:print(getattr(q,a.cmd)(a.file))
if __name__=='__main__':main()
