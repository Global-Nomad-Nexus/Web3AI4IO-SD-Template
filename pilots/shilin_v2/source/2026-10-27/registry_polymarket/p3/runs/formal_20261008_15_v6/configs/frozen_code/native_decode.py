"""Decode frozen native events. Never filter on URI availability or token success."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'p2/vendor'))
from eth_abi import decode as abi_decode,encode as abi_encode
from collections import Counter

ALPHABET='123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
def b58decode(s):
    n=0
    for ch in s:n=n*58+ALPHABET.index(ch)
    return b'\0'*(len(s)-len(s.lstrip('1')))+(n.to_bytes((n.bit_length()+7)//8,'big') if n else b'')
def b58encode(b):
    n=int.from_bytes(b,'big');out=''
    while n:n,k=divmod(n,58);out=ALPHABET[k]+out
    return '1'*(len(b)-len(b.lstrip(b'\0')))+out
def pump_args(data):
    b=b58decode(data);disc=b[:8].hex()
    if disc not in ['181ec828051c0777','d6904cec5f8b31b4']:raise ValueError('Not a qualified Pump create discriminator')
    offset=8;values={}
    for name in ['name','symbol','uri']:
        if offset+4>len(b):raise ValueError('Truncated string length')
        length=int.from_bytes(b[offset:offset+4],'little');offset+=4
        if offset+length>len(b):raise ValueError('Truncated Borsh string')
        values[name]=b[offset:offset+length].decode();offset+=length
    if offset+32>len(b):raise ValueError('Truncated creator')
    values['creator']=b58encode(b[offset:offset+32]);offset+=32
    values['native_instruction']='create' if disc=='181ec828051c0777' else 'create_v2'
    values['uninterpreted_optional_tail_hex']=b[offset:].hex()
    return values
def exact_evm(event,topics,data):
    regular=[x for x in event['inputs'] if not x.get('indexed')];indexed=[x for x in event['inputs'] if x.get('indexed')]
    if len(topics)!=1+len(indexed):raise ValueError('Wrong indexed topic count')
    types=[x['type'] for x in regular];raw=bytes.fromhex(data[2:]);vals=abi_decode(types,raw,strict=True)
    if abi_encode(types,vals)!=raw:raise ValueError('Noncanonical ABI payload')
    out={x['name']:v for x,v in zip(regular,vals)}
    for x,t in zip(indexed,topics[1:]):out[x['name']]=abi_decode([x['type']],bytes.fromhex(t[2:]),strict=True)[0]
    def precise(v):
        if isinstance(v,bytes):return '0x'+v.hex()
        if isinstance(v,(list,tuple)):return [precise(x) for x in v]
        if isinstance(v,int) and not isinstance(v,bool):return str(v)
        return v
    return {k:precise(v) for k,v in out.items()}
