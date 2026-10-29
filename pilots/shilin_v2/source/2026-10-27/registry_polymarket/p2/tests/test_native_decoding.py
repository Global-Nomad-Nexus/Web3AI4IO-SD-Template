"""Isolated synthetic decoder tests, never merged with empirical records."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'code'))
from decode import pump_args,b58encode,exact_evm,abi_encode

class NativeDecoding(unittest.TestCase):
    def payload(self,uri):
        b=bytes.fromhex('181ec828051c0777')
        for s in ['sample','T',uri]:b+=len(s.encode()).to_bytes(4,'little')+s.encode()
        return b+bytes(range(32))
    def test_empty_URI_does_not_remove_qualified_creation(self):self.assertEqual(pump_args(b58encode(self.payload('')))['uri'],'')
    def test_non_ascii_initial_attributes_preserved(self):self.assertEqual(pump_args(b58encode(self.payload('ipfs://真实')))['uri'],'ipfs://真实')
    def test_truncated_creator_is_rejected(self):
        with self.assertRaises(ValueError):pump_args(b58encode(self.payload('')[:-1]))
    def test_dynamic_ABI_and_indexed_address_exact_decode(self):
        ev={'inputs':[{'name':'token','type':'address','indexed':True},{'name':'name','type':'string','indexed':False}]}
        a='0x'+'ab'*20;topics=['0x'+'00'*32,'0x'+abi_encode(['address'],[a]).hex()];data='0x'+abi_encode(['string'],['样例']).hex()
        self.assertEqual(exact_evm(ev,topics,data),{'token':a,'name':'样例'})
    def test_noncanonical_extra_ABI_bytes_rejected(self):
        ev={'inputs':[{'name':'amount','type':'uint256','indexed':False}]}
        with self.assertRaises(ValueError):exact_evm(ev,['0x'+'00'*32],'0x'+(abi_encode(['uint256'],[1])+b'\0'*32).hex())

if __name__=='__main__':unittest.main()
