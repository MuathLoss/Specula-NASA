"""Run focused numerical regression tests using only the runtime dependencies."""
import importlib.util
from pathlib import Path
import traceback

if __name__=='__main__':
    passed=failed=0
    for path in sorted(Path(__file__).parent.glob('test_*.py')):
        spec=importlib.util.spec_from_file_location(path.stem,path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        for name in sorted(vars(module)):
            if not name.startswith('test_'): continue
            try:
                getattr(module,name)();passed+=1
            except Exception:
                failed+=1;print(path.name,name);traceback.print_exc()
    print(f'{passed} passed; {failed} failed')
    raise SystemExit(bool(failed))
