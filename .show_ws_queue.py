p='src/commands/utils/queue.py'
with open(p,'r',encoding='utf-8') as f:
    for i,line in enumerate(f, start=1):
        print(f"{i:04}: {repr(line[:40])} {line.rstrip()}")
