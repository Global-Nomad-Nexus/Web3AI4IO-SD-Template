"""Finite P2 source/schema discovery before freezing the cohort."""
from p2io import *
import shutil
def run():
    c=Client(budget=35);found={}
    for slug in ['solana-mainnet','base-mainnet','binance-mainnet']:
        for t in [1791417600,1791504000]:
            d,m=c.json(f'https://portal.sqd.dev/datasets/{slug}/timestamps/{t}/block',label='candidate_boundary')
            found[slug+':'+str(t)]={'data':d,'request_ref':m['raw_ref'],'ok':m['ok']}
            print(slug,t,m['http_status'],d,flush=True)
    for version in ['v0','v1','v2','v3','v3.1','v4']:
        url=f'https://raw.githubusercontent.com/clanker-devco/clanker-sdk/4f4d2bbf41c7f10543559dc043c85f443a6d452e/src/abi/{version}/Clanker.ts'
        b,m=c.request(url,label='official_Clanker_ABI_'+version)
        if m['ok']:(ROOT/'configs'/('clanker_'+version+'.ts')).write_bytes(b)
    for rev in ['8cda1fa30ea658b20909d8aedf002047119388d2','2293f9a66c654e9fe82dc5e8f4618538f24bb35f']:
        b,m=c.request(f'https://raw.githubusercontent.com/pump-fun/pump-public-docs/{rev}/idl/pump.json',label='official_Pump_IDL_window_versions')
        if m['ok']:(ROOT/'configs'/('pump_'+rev+'.json')).write_bytes(b)
    b,m=c.request('https://raw.githubusercontent.com/four-meme-community/four-meme-ai/c81f0eebbabec16998b2457f7e881e1b70b86420/skills/four-meme-integration/references/event-listening.md',label='official_FourMeme_definitions')
    if m['ok']:(ROOT/'configs/four_meme_event_definitions.md').write_bytes(b)
    shutil.copyfile(PILOT/'sources/four-meme-ai/token-manager2-events.json',ROOT/'configs/four_meme_v2_events.json')
    write_json(ROOT/'reports/discovery.json',found)
if __name__=='__main__':run()
