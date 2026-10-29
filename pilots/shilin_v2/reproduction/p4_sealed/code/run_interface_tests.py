"""Run isolated tests and retain machine-readable case results and synthetic CLI outputs."""
import argparse,csv,hashlib,json,subprocess,sys,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class Result(unittest.TextTestResult):
 def __init__(self,*a,**k):super().__init__(*a,**k);self.cases=[]
 def addSuccess(self,test):super().addSuccess(test);self.cases.append({'case':test.id(),'status':'passed'})
 def addFailure(self,test,err):super().addFailure(test,err);self.cases.append({'case':test.id(),'status':'failed','error':self._exc_info_to_string(err,test)})
 def addError(self,test,err):super().addError(test,err);self.cases.append({'case':test.id(),'status':'error','error':self._exc_info_to_string(err,test)})

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output
 if 'test_outputs' not in out.resolve().parts:raise ValueError('synthetic evidence must be under test_outputs')
 out.mkdir(parents=True,exist_ok=True);start=time.monotonic()
 with (out/'unittest.log').open('w') as f:
  result=unittest.TextTestRunner(stream=f,verbosity=2,resultclass=Result).run(unittest.defaultTestLoader.discover(str(ROOT/'tests')))
 fixture=json.loads((ROOT/'tests/fixtures/lifecycle_cases.json').read_text())
 for name in ['registry','events','coverage','crosswalk']:
  with (out/(name+'.csv')).open('w',newline='',encoding='utf-8') as f:
   w=csv.DictWriter(f,fieldnames=list(fixture[name][0]));w.writeheader();w.writerows(fixture[name])
 command=[sys.executable,'-B',str(ROOT/'code/lifecycle_adapter.py'),'--registry',str(out/'registry.csv'),'--events',str(out/'events.csv'),'--coverage',str(out/'coverage.csv'),'--crosswalk',str(out/'crosswalk.csv'),'--config',str(ROOT/'configs/adapter_config.json'),'--mode','synthetic_test','--cutoff',fixture['cutoff'],'--output',str(out/'positive_cli')]
 cli=subprocess.run(command,capture_output=True,text=True)
 (out/'cli.log').write_text(cli.stdout+cli.stderr)
 receipt={'dataset_kind':'synthetic_test','status':'passed' if result.wasSuccessful() and cli.returncode==0 else 'failed','tests_run':result.testsRun,'failure_count':len(result.failures)+len(result.errors),'cases':result.cases,'cli_exit_code':cli.returncode,'elapsed_seconds':round(time.monotonic()-start,3),'interface_version':'shilin_lifecycle_adapter_v1','real_lifecycle_integration_status':'awaiting_integration'}
 (out/'interface_test_results.json').write_text(json.dumps(receipt,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
 print('INTERFACE',receipt['status'],result.testsRun,'tests',flush=True)
 if receipt['status']!='passed':raise SystemExit(1)
if __name__=='__main__':main()
