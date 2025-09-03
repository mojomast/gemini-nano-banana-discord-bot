import py_compile, pathlib, sys, traceback
errors=0
for p in pathlib.Path('src').rglob('*.py'):
    try:
        py_compile.compile(str(p), doraise=True)
    except Exception:
        print('Compile error in', p)
        traceback.print_exc()
        errors+=1
if errors:
    sys.exit(2)
print('All source files compiled successfully')
