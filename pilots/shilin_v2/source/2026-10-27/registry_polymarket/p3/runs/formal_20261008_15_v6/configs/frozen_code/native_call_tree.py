"""Canonical Solana call-tree positions and fail-closed commitment evidence."""
from native_decode import b58decode
from collections import Counter
import re

PROGRAM='6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'
DISCS={'181ec828051c0777','d6904cec5f8b31b4'}

def native_creations(tx):
    msg=tx['transaction']['message'];keys=[a['pubkey'] if isinstance(a,dict) else a for a in msg['accountKeys']]
    inner={g['index']:g['instructions'] for g in tx['meta'].get('innerInstructions',[]) or []};instructions=[]
    def ix(item,path):
        return {'programId':item.get('programId',keys[item['programIdIndex']] if 'programIdIndex' in item else ''),'accounts':[keys[a] if isinstance(a,int) else a for a in item.get('accounts',[])],'data':item.get('data',''),'instructionAddress':path,'transactionIndex':int(tx['transactionIndex'])}
    for outer,item in enumerate(msg['instructions']):
        instructions.append(ix(item,[outer]));stack=[[outer]];counter=Counter()
        for item in inner.get(outer,[]):
            h=item.get('stackHeight')
            if not isinstance(h,int) or h<2:raise ValueError('Native inner stackHeight unavailable')
            while len(stack)>=h:stack.pop()
            if len(stack)!=h-1:raise ValueError('Invalid native call-tree depth')
            parent=tuple(stack[-1]);path=list(parent)+[counter[parent]];counter[parent]+=1
            instructions.append(ix(item,path));stack.append(path)
    pump=[i for i in instructions if i['programId']==PROGRAM];traces=[];stack=[];trace_error=''
    for line in tx['meta'].get('logMessages',[]) or []:
        m=re.fullmatch(r'Program (\S+) invoke \[(\d+)\]',line)
        if m:
            if len(stack)!=int(m[2])-1:trace_error='unbalanced_invocation_depth';break
            node={'program':m[1],'height':int(m[2]),'ok':None,'ancestors':list(stack)};traces.append(node);stack.append(node);continue
        m=re.fullmatch(r'Program (\S+) (success|failed: .*)',line)
        if m:
            if not stack or stack[-1]['program']!=m[1]:trace_error='unbalanced_invocation_outcome';break
            stack.pop()['ok']=m[2]=='success'
    # Truncation of later unrelated log lines cannot revoke a proven top-level
    # success or a completed child whose only unresolved ancestor is top-level.
    pump_traces=[n for n in traces if n['program']==PROGRAM];selected=[]
    for number,i in enumerate(pump):
        if not i['data'] or b58decode(i['data'])[:8].hex() not in DISCS:continue
        node=pump_traces[number] if number<len(pump_traces) else None
        aligned=node is not None and node['height']==len(i['instructionAddress'])
        error=None;reason='';committed=None
        if tx['meta']['err'] is not None:committed=False;reason='failed_atomic_transaction'
        elif len(i['instructionAddress'])==1:committed=True;reason='successful_atomic_transaction_top_level_instruction'
        elif aligned:
            if node['ok'] is False:error='native_invocation_failed'
            if node['ok'] is False or any(a['ok'] is False for a in node['ancestors']):committed=False;reason='failed_invocation_or_rolled_back_inner_ancestor'
            elif node['ok'] is True and all(a['ok'] is True or a['height']==1 for a in node['ancestors']):committed=True;reason='successful_inner_invocation_and_all_inner_ancestors;top_level_success_from_atomic_transaction'
        if committed is None:reason='incomplete_native_invocation_evidence'+(':'+trace_error if trace_error else '')
        selected.append({**i,'isCommitted':committed,'error':error,'commitment_evidence_rule':reason})
    return selected
