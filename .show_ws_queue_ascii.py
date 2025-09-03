p='src/commands/utils/queue.py'
with open(p,'r',encoding='utf-8') as f:
    for i,line in enumerate(f, start=1):
        s=line.rstrip('\n')
        safe=s.encode('unicode_escape').decode('ascii')
        print(f"{i:04}: {safe[:80]}")
