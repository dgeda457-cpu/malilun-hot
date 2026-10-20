"""Print source files as a Git tree payload, without private caches or raw HTML."""
import argparse,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def files():
    keep=[]
    for p in ROOT.rglob('*'):
        if not p.is_file():continue
        rel=p.relative_to(ROOT)
        if any(a in rel.parts for a in ['.cache','.git','dist','__pycache__','.tmp','node_modules']):continue
        if rel.parts[0]=='evidence' and p.suffix=='.html':continue
        if p.name.startswith('.env') or p.name in ('inspect_sources.py','inspect_details.py'):continue
        keep.append(p)
    return sorted(keep)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--index',type=int);parser.add_argument('--group',type=int);args=parser.parse_args();keep=files()
    if args.group is not None:
        groups=[];group=[];size=0
        for p in keep:
            if group and size+p.stat().st_size>125000:groups.append(group);group=[];size=0
            group.append(p);size+=p.stat().st_size
        if group:groups.append(group)
        if args.group<0:print(len(groups))
        else:print(json.dumps([{'path':p.relative_to(ROOT).as_posix(),'mode':'100644','type':'blob','content':p.read_text(encoding='utf8')} for p in groups[args.group]],ensure_ascii=False))
    elif args.index is None:print(json.dumps([{'path':p.relative_to(ROOT).as_posix(),'size':p.stat().st_size} for p in keep],ensure_ascii=False))
    else:
        p=keep[args.index];print(json.dumps({'path':p.relative_to(ROOT).as_posix(),'mode':'100644','type':'blob','content':p.read_text(encoding='utf8')},ensure_ascii=False))
