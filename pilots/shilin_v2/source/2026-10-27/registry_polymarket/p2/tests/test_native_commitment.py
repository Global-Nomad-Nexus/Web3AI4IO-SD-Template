"""Synthetic commitment boundaries, isolated from all actual-data tables."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'code'))
from native_call_tree import native_creations,PROGRAM
from decode import b58encode

DATA=b58encode(bytes.fromhex('d6904cec5f8b31b4'))
def i(program=PROGRAM,height=1):return {'programId':program,'accounts':[],'data':DATA if program==PROGRAM else '', 'stackHeight':height}
def tx(outer,inner,logs,err=None):return {'transactionIndex':3,'transaction':{'message':{'accountKeys':['payer'],'instructions':outer}},'meta':{'err':err,'innerInstructions':[{'index':0,'instructions':inner}] if inner else [],'logMessages':logs}}
class CommitmentBoundaries(unittest.TestCase):
    def test_top_level_success_survives_unrelated_log_truncation(self):
        r=native_creations(tx([i(),i('Other')],[],['Log truncated']))
        self.assertTrue(r[0]['isCommitted'])
    def test_successful_child_is_rolled_back_with_failed_inner_ancestor(self):
        logs=['Program Wrap invoke [1]','Program Inner invoke [2]',f'Program {PROGRAM} invoke [3]',f'Program {PROGRAM} success','Program Inner failed: custom program error','Program Wrap success']
        r=native_creations(tx([i('Wrap')],[i('Inner',2),i(PROGRAM,3)],logs))
        self.assertFalse(r[0]['isCommitted']);self.assertEqual(r[0]['instructionAddress'],[0,0,0])
    def test_failed_create_caught_by_outer_is_not_committed(self):
        logs=['Program Wrap invoke [1]',f'Program {PROGRAM} invoke [2]',f'Program {PROGRAM} failed: rejected','Program Wrap success']
        r=native_creations(tx([i('Wrap')],[i(PROGRAM,2)],logs))
        self.assertFalse(r[0]['isCommitted'])
    def test_missing_inner_ancestor_outcome_stays_unknown(self):
        logs=['Program Wrap invoke [1]','Program Inner invoke [2]',f'Program {PROGRAM} invoke [3]',f'Program {PROGRAM} success','Log truncated']
        r=native_creations(tx([i('Wrap')],[i('Inner',2),i(PROGRAM,3)],logs))
        self.assertIsNone(r[0]['isCommitted'])
    def test_atomic_failure_excludes_even_successful_outer_instruction(self):
        r=native_creations(tx([i()],[],[f'Program {PROGRAM} invoke [1]',f'Program {PROGRAM} success'],{'InstructionError':[1,'failed_later']}))
        self.assertFalse(r[0]['isCommitted'])
if __name__=='__main__':unittest.main()
