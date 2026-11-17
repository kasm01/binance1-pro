"""Stage19: isolated Redis protocol, NOT a real/live risk authorization.

BEGIN closes any prior grant, incrementing epoch before broker reads.
PUBLISH binds local digest to epoch; Lua cannot authenticate broker responses.
RESERVE issues monotonic fencing serial atomically and is never an order permit.
"""
from __future__ import annotations
import hashlib
import hmac
import json
from typing import Any, Mapping

SCRIPT=r'''
local action=ARGV[1]
local epoch=tonumber(ARGV[2])
local digest=ARGV[3]
local request=ARGV[4]
local strategy=ARGV[5]
local symbol=ARGV[6]
local side=ARGV[7]
local token=ARGV[8]
local position=ARGV[9]
local now=tonumber(ARGV[10]) or 0
local ttl=tonumber(ARGV[11]) or 0
local attested=ARGV[12]
local function ans(state,reason,extra)
 local x={state=state,reason=reason,live_order_authorized=false}
 if extra then for k,v in pairs(extra) do x[k]=v end end
 return cjson.encode(x)
end
local current=tonumber(redis.call('GET',KEYS[2])) or 0
if action=='BEGIN' then
  local nextEpoch=redis.call('INCR',KEYS[2])
  redis.call('SET',KEYS[1],'CLOSED')
  redis.call('DEL',KEYS[3])
  return ans('READY','capture_started',{epoch=nextEpoch})
end
if not epoch or epoch~=current or epoch<=0 then
 return ans('REJECT','epoch_stale_or_unissued',{current_epoch=current})
end
if action=='PUBLISH' then
  if #digest~=64 or attested~='LOCAL_RESEARCH_VERIFIED' then
   return ans('REJECT','research_evidence_invalid')
  end
  if redis.call('HLEN',KEYS[5])>0 or redis.call('HLEN',KEYS[6])>0 then
   return ans('REJECT','unresolved_exposure')
  end
  -- The evidence producer is NOT authenticated by Redis. Proof only in tests.
  redis.call('SET',KEYS[3],digest)
  redis.call('SET',KEYS[1],'RESEARCH_OPEN')
  return ans('READY','research_snapshot_bound',{epoch=epoch})
end
if redis.call('GET',KEYS[1])~='RESEARCH_OPEN'
 or redis.call('GET',KEYS[3])~=digest or #digest~=64 then
 return ans('REJECT','gate_closed_or_evidence_changed')
end
if (strategy~='LONG1' and strategy~='SHORT1') or
  (strategy=='LONG1' and (symbol~='NEARUSDT' or side~='long')) or
  (strategy=='SHORT1' and (symbol~='INJUSDT' or side~='short')) then
 return ans('REJECT','strategy_identity_invalid')
end
if now<=0 or ttl<=0 or ttl>60000 or request=='' or token=='' then
 return ans('REJECT','invalid_request')
end
local cached=redis.call('HGET',KEYS[7],request)
if action=='RESERVE' then
 if cached then
  local prior=cjson.decode(cached)
  if prior.epoch==epoch and prior.digest==digest
     and prior.strategy==strategy and prior.symbol==symbol
     and prior.side==side and prior.token==token then
    -- Idempotency must not resurrect an expired reservation. Even if its
    -- state is still present, only a fresh broker reconciliation may clear it.
    if now>tonumber(prior.reply.expires_at) then
     return ans('REJECT','expired_idempotent_replay')
    end
    return ans('READY','idempotent_reservation',prior.reply)
  end
  return ans('REJECT','request_id_conflict')
 end
 if redis.call('HEXISTS',KEYS[5],strategy)==1
 or redis.call('HEXISTS',KEYS[6],strategy)==1 then
  return ans('REJECT','strategy_slot_occupied')
 end
 if redis.call('HLEN',KEYS[5])+redis.call('HLEN',KEYS[6])>=2 then
  return ans('REJECT','portfolio_slots_full')
 end
 local fence=redis.call('INCR',KEYS[4])
 local item={epoch=epoch,digest=digest,request=request,
  strategy=strategy,symbol=symbol,side=side,token=token,fence=fence,
  expires_at=now+ttl}
 redis.call('HSET',KEYS[5],strategy,cjson.encode(item))
 local reply={epoch=epoch,fence=fence,expires_at=now+ttl}
 redis.call('HSET',KEYS[7],request,cjson.encode({epoch=epoch,
   digest=digest,strategy=strategy,symbol=symbol,side=side,token=token,reply=reply}))
 return ans('READY','research_reserved',reply)
end
local raw=redis.call('HGET',KEYS[5],strategy)
if not raw then return ans('REJECT','pending_reservation_missing') end
local item=cjson.decode(raw)
if item.epoch~=epoch or item.digest~=digest or item.request~=request
  or item.token~=token or item.strategy~=strategy then
 return ans('REJECT','fencing_owner_mismatch')
end
if action=='COMMIT' then
 if position=='' or now>item.expires_at then
  return ans('REJECT','position_missing_or_expired')
 end
 -- A local position string is NOT exchange fill proof. Remains research-only.
 item.position_id=position
 redis.call('HSET',KEYS[6],strategy,cjson.encode(item))
 redis.call('HDEL',KEYS[5],strategy)
 return ans('READY','research_committed',{fence=item.fence,epoch=epoch})
end
if action=='RELEASE' then
 if position~='ISOLATED_TEST_EXCHANGE_FLAT' then
  return ans('REJECT','independent_flat_proof_missing')
 end
 redis.call('HDEL',KEYS[5],strategy)
 return ans('READY','research_uncommitted_released',{fence=item.fence})
end
return ans('REJECT','unknown_action')
'''

class IsolatedEpochFenceRisk:
    def __init__(self, redis_client, prefix='research:stage19:fenced'):
        self.r=redis_client
        self.keys=[prefix+':gate',prefix+':epoch',prefix+':digest',
                   prefix+':fence',prefix+':pending',
                   prefix+':committed',prefix+':requests']
    def action(self,action,*,epoch=0,digest='',request='',strategy='',
               symbol='',side='',token='',position='',now=1000000,
               ttl=30000,attested=''):
        return json.loads(self.r.eval(SCRIPT,len(self.keys),*self.keys,
            action,epoch,digest,request,strategy,symbol,side,token,position,
            now,ttl,attested))

def local_evidence_digest(snapshot:Mapping[str,Any], *, secret:bytes)->str:
    """HMAC is useful only if a separate trusted verifier controls secret.
    Not a replacement for authenticated broker/portfolio proof.
    """
    if not isinstance(snapshot,Mapping) or not secret:
        raise ValueError('snapshot_or_test_secret_missing')
    payload=json.dumps(snapshot,sort_keys=True,ensure_ascii=False,
                       separators=(',',':'),allow_nan=False)
    return hmac.new(secret,payload.encode(),hashlib.sha256).hexdigest()
