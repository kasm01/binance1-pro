"""Stage26: jointly size by real CentralRiskMaster, reserve atomically in LOCAL TEST Redis.

NOT production broker authorization. Authenticated exchange snapshots, final
live stop verification and atomic Binance order submission NOT implemented.
All responses explicitly order_authorized=false. Do not import into live gate.
"""
from __future__ import annotations
import json,math
from orchestration.risk.central_risk_master import (
 EntryRiskRequest,PortfolioRiskState,PositionExposure,
)
from orchestration.risk.central_risk_enforce_dry_profile import build_enforce_dry_master

LUA=r'''
-- Keys: gate, epoch, snapshot_digest, reservation_hash, request_ids,
--       fence_counter, audit_stream, committed_hash, budget_cap
-- ARGV: action, epoch, digest, request, strategy, symbol, side,
--       owner, client_order_id, requested_notional, approved_notional,
--       ts_ms, ttl_ms, acknowledged_fence
local action=ARGV[1]
local epoch=tonumber(ARGV[2])
local digest=ARGV[3]
local rid=ARGV[4]
local strategy=ARGV[5]
local symbol=ARGV[6]
local side=ARGV[7]
local owner=ARGV[8]
local clientid=ARGV[9]
local requested=tonumber(ARGV[10])
local approved=tonumber(ARGV[11])
local now=tonumber(ARGV[12])
local ttl=tonumber(ARGV[13])
local ack=tonumber(ARGV[14])
local function answer(status,reason,more)
 local x={state=status,reason=reason,order_authorized=false,
          source='STAGE26_ISOLATED_RESEARCH'}
 if more then for k,v in pairs(more) do x[k]=v end end
 return cjson.encode(x)
end
if action=='BEGIN' then
 local e=redis.call('INCR',KEYS[2])
 redis.call('SET',KEYS[1],'CLOSED')
 redis.call('DEL',KEYS[3])
 redis.call('DEL',KEYS[9])
 return answer('READY','epoch_started',{epoch=e})
end
local current=tonumber(redis.call('GET',KEYS[2])) or 0
if not epoch or epoch~=current or epoch<=0 then
 return answer('REJECT','epoch_stale')
end
if action=='BIND_TEST' then
 -- Test-only input: NO independent broker/equity attestation.
 if #digest~=64 or not requested or requested<=0 or
    requested~=requested or requested==math.huge or
    redis.call('HLEN',KEYS[4])~=0 or
    redis.call('HLEN',KEYS[8])~=0 then
  return answer('REJECT','unresolved_or_invalid_snapshot')
 end
 redis.call('SET',KEYS[3],digest)
 redis.call('SET',KEYS[9],tostring(requested))
 redis.call('SET',KEYS[1],'TEST_OPEN')
 return answer('READY','test_epoch_bound')
end
if redis.call('GET',KEYS[1])~='TEST_OPEN' or
   redis.call('GET',KEYS[3])~=digest then
 return answer('REJECT','gate_closed')
end
if not now or now<=0 or not ttl or ttl<=0 or ttl>60000 then
 return answer('REJECT','bad_time')
end
if strategy~='LONG1' and strategy~='SHORT1' then
 return answer('REJECT','bad_strategy')
end
if strategy=='LONG1' and (symbol~='NEARUSDT' or side~='long') then
 return answer('REJECT','bad_strategy_symbol')
end
if strategy=='SHORT1' and (symbol~='INJUSDT' or side~='short') then
 return answer('REJECT','bad_strategy_symbol')
end
if rid=='' or owner=='' or clientid=='' then
 return answer('REJECT','bad_identity')
end
if action=='RESERVE' then
 if not approved or not requested or approved~=approved or requested~=requested or
    approved<=0 or requested<=0 or approved>requested then
  return answer('REJECT','invalid_central_notional')
 end
 local prev=redis.call('HGET',KEYS[5],rid)
 if prev then
  local p=cjson.decode(prev)
  if p.strategy==strategy and p.symbol==symbol and p.side==side and
     p.owner==owner and p.clientid==clientid and p.digest==digest and
     p.epoch==epoch and p.approved==approved then
    if now>p.expires_at then return answer('REJECT','expired_replay') end
    return answer('READY','idempotent',{fence=p.fence,epoch=p.epoch,
         expires_at=p.expires_at,approved_notional=p.approved})
  end
  return answer('REJECT','identity_conflict')
 end
 if redis.call('HEXISTS',KEYS[4],strategy)==1 or
    redis.call('HEXISTS',KEYS[8],strategy)==1 then
  return answer('REJECT','strategy_busy')
 end
 if redis.call('HLEN',KEYS[4])+redis.call('HLEN',KEYS[8])>=2 then
  return answer('REJECT','portfolio_full')
 end
 -- In the SAME Redis transaction as fence issuance, sum ALL pending and
 -- quarantined synthetic exposure. No read-compute-write race across bots.
 -- Missing or malformed reserve records hard BLOCK; never skip them.
 local bound=tonumber(redis.call('GET',KEYS[9]))
 if not bound or bound<=0 or bound~=bound then
  return answer('REJECT','portfolio_budget_missing')
 end
 local used=0
 for _,key in ipairs({KEYS[4],KEYS[8]}) do
  local records=redis.call('HVALS',key)
  for _,raw in ipairs(records) do
   local ok,prior=pcall(cjson.decode,raw)
   if not ok or type(prior)~='table' or not tonumber(prior.approved)
      or tonumber(prior.approved)<=0 then
    return answer('REJECT','portfolio_reservation_corrupt')
   end
   used=used+tonumber(prior.approved)
  end
 end
 if used+approved>bound+0.0000001 then
  return answer('REJECT','portfolio_budget_exhausted',
                {used_notional=used,budget=bound})
 end
 local fence=redis.call('INCR',KEYS[6])
 local rec={request=rid,owner=owner,clientid=clientid,
  epoch=epoch,digest=digest,strategy=strategy,symbol=symbol,side=side,
  approved=approved,fence=fence,expires_at=now+ttl}
 redis.call('HSET',KEYS[4],strategy,cjson.encode(rec))
 redis.call('HSET',KEYS[5],rid,cjson.encode(rec))
 redis.call('XADD',KEYS[7],'*','action','RESERVE',
    'request',rid,'strategy',strategy,'fence',tostring(fence))
 return answer('READY','reserved_test_only',
    {fence=fence,epoch=epoch,expires_at=rec.expires_at,approved_notional=approved})
end
local raw=redis.call('HGET',KEYS[4],strategy)
if not raw then return answer('REJECT','pending_missing') end
local rec=cjson.decode(raw)
if rec.epoch~=epoch or rec.digest~=digest or rec.request~=rid or
   rec.owner~=owner or rec.clientid~=clientid or not ack or
   ack~=rec.fence then
 return answer('REJECT','reservation_fence_owner_conflict')
end
if action=='VALIDATE' then
 if now>rec.expires_at then return answer('REJECT','reservation_expired') end
 return answer('READY','final_safety_candidate_only',
    {fence=rec.fence,approved_notional=rec.approved})
end
if action=='QUARANTINE' then
 -- Uncertain submit stays sticky; never auto-release or permit re-entry.
 redis.call('HSET',KEYS[8],strategy,raw)
 redis.call('HDEL',KEYS[4],strategy)
 redis.call('SET',KEYS[1],'CLOSED')
 return answer('READY','frozen_for_independent_broker_reconciliation')
end
return answer('REJECT','unknown_action')
'''

def policy_decision(*,strategy:str,symbol:str,side:str,equity:float,
                    positions:list[PositionExposure],context_multiplier:float=1.,
                    portfolio_mode:str='NORMAL'):
    """Actual central Master calculation, forced non-production profile."""
    if not (math.isfinite(equity) and equity>0):
        raise ValueError('invalid_equity')
    master=build_enforce_dry_master()
    return master.evaluate_entry(
        request=EntryRiskRequest(strategy_id=strategy,symbol=symbol,side=side,
            requested_notional=equity*.5,market_context_multiplier=context_multiplier),
        state=PortfolioRiskState(equity_peak=equity,mode=portfolio_mode),
        portfolio_equity=equity,positions=positions)

class AtomicResearch:
    def __init__(self,r,prefix='research:stage26:joint'):
        self.r=r
        self.keys=[prefix+':gate',prefix+':epoch',prefix+':digest',
           prefix+':pending',prefix+':requests',prefix+':fence',
           prefix+':audit',prefix+':quarantine',prefix+':budget_cap']
    def action(self,action,*,epoch=0,digest='',request='',strategy='',symbol='',
               side='',owner='',client_order_id='',requested_notional=0,
               approved_notional=0,now=1000000,ttl=30000,fence=0):
        return json.loads(self.r.eval(LUA,len(self.keys),*self.keys,
         action,epoch,digest,request,strategy,symbol,side,owner,client_order_id,
         requested_notional,approved_notional,now,ttl,fence))
