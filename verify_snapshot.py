from pathlib import Path
import runpy,sys
root=Path(__file__).resolve().parent
maintenance=root/'02_设定层'/'题库维护'
sys.path.insert(0,str(maintenance))
runpy.run_path(str(maintenance/'verify.py'),run_name='__main__')
