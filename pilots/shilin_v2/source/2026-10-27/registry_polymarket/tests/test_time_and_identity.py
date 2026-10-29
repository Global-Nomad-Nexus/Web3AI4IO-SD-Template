"""Synthetic boundary tests; fixtures never enter processed research data."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'code'))
from common import token_id
from build_views import eligible_price

class Boundaries(unittest.TestCase):
    def price(self,end,allowed=True,value='0.2'):
        return {'effective_information_time_utc':str(end),'eligible_for_asof':allowed,'price':value}
    def test_same_second_bucket_end_excluded(self):
        seq=[self.price(100),self.price(200)]
        self.assertEqual(eligible_price(seq,[100,200],200),seq[0])
    def test_incomplete_future_bucket_excluded(self):
        self.assertIsNone(eligible_price([self.price(300)],[300],250))
    def test_settlement_or_ambiguous_tick_excluded(self):
        self.assertIsNone(eligible_price([self.price(100,False)],[100],101))
    def test_stale_values_remain_missing(self):
        self.assertIsNone(eligible_price([self.price(100)],[100],100+24*3600+1))
    def test_exact_max_age_included(self):
        self.assertIsNotNone(eligible_price([self.price(100)],[100],100+24*3600))
    def test_out_of_range_price_rejected(self):
        self.assertIsNone(eligible_price([self.price(100,True,'1.2')],[100],101))
    def test_cross_chain_evm_identity(self):
        a='0x'+'aB'*20
        self.assertNotEqual(token_id('eip155:56',a),token_id('eip155:8453',a))
        self.assertEqual(token_id('eip155:56',a),token_id('eip155:56',a.lower()))
    def test_solana_case_is_preserved(self):
        a='6a4LJXscVdTwr2pUwApZmuwfCACD6gsfuF9s443cpump'
        self.assertTrue(token_id('solana:mainnet',a).endswith(a))

if __name__=='__main__':unittest.main()
