"""Stage29 RESEARCH-only monotonic observation journal for Stage26 AOF escrow.

Only an actual authoritative broker reconciler may someday clear escrow.
No actor here can resubmit, commit, release, or authorize a LIVE order.
No imports into production entry paths.
"""
from __future__ import annotations
import hashlib,json
from typing import Any

SEVERITY={
 'PROTECTED_EVIDENCE_ONLY':1,
 'FLAT_EVIDENCE_ONLY':1,
 'RECOVERED_FILL_PENDING_JOURNAL':4,
 'HOLD_RECONCILIATION':3,
 'UNKNOWN_FREEZE':5,
 'FREEZE_UNPROTECTED':6,
}
LUA=r'''
-- KEYS: stage26_gate, stage26_pending, stage26_quarantine,
--       stage26_epoch, observation_epoch, event_index, latest_by_intent,
--       event_stream, hazard_stream
-- ARGV: action, intent, strategy, owner, client_order_id,
--       reserve_epoch, reserve_fence, observation_epoch, event_id,
--       evidence_state, severity, evidence_digest, started_ms, finished_ms
local action=ARGV[1]
local iid=ARGV[2]
local strategy=ARGV[3]
local owner=ARGV[4]
local cid=ARGV[5]
local re=tonumber(ARGV[6])
local rf=tonumber(ARGV[7])
local oe=tonumber(ARGV[8])
local eid=ARGV[9]
local label=ARGV[10]
local sev=tonumber(ARGV[11])
local digest=ARGV[12]
local started=tonumber(ARGV[13])
local finished=tonumber(ARGV[14])
local function ans(st,why,extra)
 local x={state=st,reason=why,can_resubmit=false,
  can_commit=false,can_release=false,live_order_authorized=false}
 if extra then for k,v in pairs(extra) do x[k]=v end end
 return cjson.encode(x)
end
-- BEGIN seals risk before a broker read; obtains globally monotonically
-- increasing observation sequence for this Redis generation.
if action=='BEGIN' then
 redis.call('SET',KEYS[1],'CLOSED')
 local next=redis.call('INCR',KEYS[5])
 return ans('READY','observation_started',{observation_epoch=next})
end
if action~='RECORD' then return ans('REJECT','unsupported_action') end
local current=tonumber(redis.call('GET',KEYS[5])) or 0
if not oe or oe<=0 or oe>current or not re or re<=0 or
 not rf or rf<=0 or iid=='' or owner=='' or cid=='' or eid=='' or
 strategy=='' or not sev or sev<1 or sev>6 or #digest~=64 or
 not started or not finished or started<=0 or finished<started or
 finished-started>15000 then
 return ans('REJECT','invalid_observation')
end
local approved={
 PROTECTED_EVIDENCE_ONLY=1,FLAT_EVIDENCE_ONLY=1,
 RECOVERED_FILL_PENDING_JOURNAL=4,HOLD_RECONCILIATION=3,
 UNKNOWN_FREEZE=5,FREEZE_UNPROTECTED=6}
if approved[label]~=sev then return ans('REJECT','severity_mismatch') end
-- A later observation does not authorize an earlier reservation by itself.
local store=redis.call('HGET',KEYS[2],strategy)
local quarantine=false
if not store then
 store=redis.call('HGET',KEYS[3],strategy)
 quarantine=true
end
if not store then return ans('REJECT','risk_reservation_missing') end
local ok,row=pcall(cjson.decode,store)
if not ok or type(row)~='table' then return ans('REJECT','reservation_record_corrupt') end
if row.request~=iid or row.strategy~=strategy or
 row.owner~=owner or row.clientid~=cid or
 row.epoch~=re or row.fence~=rf then
 return ans('REJECT','fenced_reservation_identity_mismatch')
end
local payload=iid..'|'..strategy..'|'..owner..'|'..cid..'|'..
 tostring(re)..'|'..tostring(rf)..'|'..tostring(oe)..'|'..
 label..'|'..digest
local previous=redis.call('HGET',KEYS[6],eid)
if previous then
 if previous==payload then
  return ans('READY','idempotent_evidence_event')
 end
 return ans('REJECT','evidence_event_id_conflict')
end
local oldraw=redis.call('HGET',KEYS[7],iid)
local prior=nil
if oldraw then
 local decoded,v=pcall(cjson.decode,oldraw)
 if not decoded or type(v)~='table' then return ans('REJECT','audit_record_invalid') end
 prior=v
end
local oldmax=prior and tonumber(prior.max_severity) or 0
local max_severity=math.max(oldmax,sev)
local last_epoch=prior and tonumber(prior.latest_observation_epoch) or 0
local latest_epoch=last_epoch
local latest_label=prior and prior.latest_label or 'UNKNOWN_FREEZE'
if oe>last_epoch then latest_epoch=oe;latest_label=label end
-- Every event that is observed while a submission may be in flight
-- quarantines its risk, even positive evidence. Only an independent
-- authenticated reconciliation could change that in FUTURE work.
redis.call('SET',KEYS[1],'CLOSED')
if not quarantine then
 redis.call('HSET',KEYS[3],strategy,store)
 redis.call('HDEL',KEYS[2],strategy)
end
redis.call('HSET',KEYS[6],eid,payload)
redis.call('HSET',KEYS[7],iid,cjson.encode({
 request=iid,owner=owner,clientid=cid,epoch=re,fence=rf,
 latest_observation_epoch=latest_epoch,latest_label=latest_label,
 max_severity=max_severity,events=(prior and tonumber(prior.events) or 0)+1}))
redis.call('XADD',KEYS[8],'*','event_id',eid,'intent_id',iid,
 'observation_epoch',tostring(oe),'label',label,'severity',tostring(sev),
 'stale',(oe<latest_epoch) and '1' or '0')
if sev>=3 then
 redis.call('XADD',KEYS[9],'*','event_id',eid,'intent_id',iid,
  'observation_epoch',tostring(oe),'hazard',label,'severity',tostring(sev))
end
return ans('READY','durable_quarantine_recorded',{max_severity=max_severity,
  latest_observation_epoch=latest_epoch,quarantined=true})
'''

class IsolatedRecoveryJournal:
    def __init__(self,redis_client,stage26_keys,prefix="research:stage29:journal"):
        if len(stage26_keys)!=9:
            raise ValueError("stage26_risk_keys_invalid")
        self.redis=redis_client
        self.keys=[stage26_keys[0],stage26_keys[3],stage26_keys[7],
           stage26_keys[1],prefix+':observation_epoch',
           prefix+':events_by_id',prefix+':latest',
           prefix+':stream',prefix+':hazard_outbox']
    def begin(self):
        return json.loads(self.redis.eval(LUA,len(self.keys),*self.keys,
            'BEGIN','','','','',0,0,0,'','',0,'',0,0))
    def record(self,*,intent_id:str,strategy:str,owner:str,client_order_id:str,
               reservation_epoch:int,reservation_fence:int,
               observation_epoch:int,event_id:str,evidence:dict,
               started_ms:int,finished_ms:int):
        state=str(evidence.get('state') or 'UNKNOWN_FREEZE')
        if state not in SEVERITY:state='UNKNOWN_FREEZE'
        payload=json.dumps({'state':state,'reason':evidence.get('reason','unknown')},
              sort_keys=True,separators=(',',':'))
        digest=hashlib.sha256(payload.encode()).hexdigest()
        return json.loads(self.redis.eval(LUA,len(self.keys),*self.keys,
          'RECORD',intent_id,strategy,owner,client_order_id,
          reservation_epoch,reservation_fence,observation_epoch,event_id,
          state,SEVERITY[state],digest,started_ms,finished_ms))
