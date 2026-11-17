#!/usr/bin/env python3
"""Read-only event-derived LONG1 contra guard FSM; no order authority or network requests."""
from __future__ import annotations
import argparse, collections, datetime as dt, json, re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
TRACE=ROOT/'research/results/LONG1_DECISION_TRACE_SHADOW.jsonl'
OUT=ROOT/'research/results/LONG1_CONTRA_FSM_SHADOW_TRANSITIONS_20261111.jsonl'
SUMMARY=ROOT/'research/results/LONG1_CONTRA_FSM_SHADOW_SUMMARY_20261111.json'
DISPATCH=re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d+) .*\[EXEC-EVENTS\] dispatch decision .*intent=([\w-]+)")
DECISION=re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d+) .*\[EXEC\]\[ENTRY-DECISION\] action=(\w+) reason=(\w+)")
FILLED=re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d+) .*\[EXEC\]\[OPEN\]\[COMMIT\] ")
def stamp(s):return dt.datetime.strptime(s,'%Y-%m-%d %H:%M:%S,%f').replace(tzinfo=dt.timezone.utc).timestamp()*1000
def events(path):
    res=[]
    with path.open(encoding='utf-8') as f:
        for line in f:
            try:
                v=json.loads(line)
                if isinstance(v,dict):res.append(v)
            except (ValueError,TypeError):continue
    return res
def native_decisions(log):
    dispatch=[];acts=[];fills=[]
    for line in log.open(errors='replace'):
        m=DISPATCH.search(line)
        if m:dispatch.append((stamp(m[1]),m[2]))
        m=DECISION.search(line)
        if m:acts.append((stamp(m[1]),m[2],m[3]))
        m=FILLED.search(line)
        if m:fills.append(stamp(m[1]))
    idx=0;res={}
    for when,action,reason in acts:
        while idx+1<len(dispatch) and dispatch[idx+1][0]<=when:idx+=1
        if dispatch and dispatch[idx][0]<=when and when-dispatch[idx][0]<=10_000:
            key=dispatch[idx][1]
            res[key]={'ts_ms':int(when),'action':action,'reason':reason,
                      'fill_observed_nearby':any(when<=v<=when+12_000 for v in fills)}
    return res
def classify(e):
    if e.get('stream')!='signals_stream_long1':return None
    if e.get('model',{}).get('side')!='LONG':return None
    sp=e.get('specialists') or {};market=sp.get('market_direction') or {};flow=sp.get('money_flow') or {}
    ok=market.get('quality')=='VALID' and flow.get('quality')=='VALID'
    dual=ok and market.get('direction')=='SHORT' and flow.get('direction')=='SHORT'
    return dict(score=e.get('model',{}).get('score'),gate=e.get('model',{}).get('rolling_gate'),
                model_action=e.get('advisory_action'),market=market.get('direction'),
                flow=flow.get('direction'),flow15=flow.get('flow15'),flow60=flow.get('flow60'),
                dual=dual,context_valid=ok)
def replay(trace, dec):
    state={};last_signal=None;trans=[];counter=collections.Counter()
    for e in trace:
        t=int(e.get('observed_at_ms') or 0)
        if not t and e.get('observed_at_utc'):
            t=int(dt.datetime.fromisoformat(e['observed_at_utc']).timestamp()*1000)
        if not t:continue
        sym=e.get('symbol') or 'NEARUSDT'
        p=state.get(sym)
        if p and t-p['opened_ms']>30*60000:
            trans.append(dict(ts_ms=t,type='EXPIRED_NO_PROVEN_READY',original_id=p['origin'],reason='ttl_30m'))
            counter['expired']+=1;state.pop(sym,None);p=None
        x=classify(e)
        if x is not None:
            if not x['context_valid']:
                counter['unverified_context']+=1;continue
            if x['dual'] and x['model_action']=='PENDING':
                if p is None:
                    state[sym]=dict(origin=e.get('candidate_id'),opened_ms=t,model_score=x['score'])
                    trans.append(dict(ts_ms=t,type='PENDING_CONTEXT_CONTRA',original_id=e.get('candidate_id'),
                                      market=x['market'],flow=x['flow'],flow15=x['flow15'],flow60=x['flow60'],
                                      model_score=x['score'],gate=x['gate'],order_authority='NONE'))
                    counter['pending_opened']+=1
                else:counter['pending_seen_again']+=1
            elif p is not None:
                if x['model_action']=='READY' and not x['dual']:
                    trans.append(dict(ts_ms=t,type='CONTEXT_ALIGNED_NOT_NATIVE_READY',original_id=p['origin'],
                                      candidate_id=e.get('candidate_id'),reason='native_exec_decision_required'))
                    counter['aligned_candidates_without_native_proof']+=1
                elif x['model_action']=='REJECT':
                    counter['rejected_candidate_during_pending']+=1
            last_signal=dict(ts_ms=t,candidate_id=e.get('candidate_id'),snapshot=x)
        elif e.get('stream')=='exec_events_stream_long1':
            for item in e.get('items') or []:
                if not isinstance(item,dict) or item.get('symbol')!='NEARUSDT':continue
                iid=item.get('intent_id');native=dec.get(iid)
                if native is None:
                    counter['intent_no_matched_decision']+=1;continue
                p=state.get(sym)
                transition=dict(ts_ms=t,type='NATIVE_ENTRY_DECISION_OBSERVED',intent_id=iid,
                                native_action=native['action'],native_reason=native['reason'],
                                native_fill_nearby=native['fill_observed_nearby'],
                                pending_original=p['origin'] if p else None,
                                same_completed_3m5m_proven=False,
                                revalidated_fresh_model_and_sniper_proven=False,
                                decision_authority='ADVISORY_ONLY',order_authority='NONE')
                # We cannot assume current context feature freshness at decision time or infer native 5m, so never promote.
                trans.append(transition);counter['native_decisions_matched']+=1
                if p:counter['native_decision_while_pending']+=1
    for sym,p in state.items():
        trans.append(dict(ts_ms=int(trace[-1].get('observed_at_ms') or p['opened_ms']),type='STILL_PENDING_UNVERIFIED',original_id=p['origin']))
        counter['pending_at_end']+=1
    return trans,counter
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--trace',type=Path,default=TRACE)
    ap.add_argument('--log',type=Path,default=ROOT/'logs/main.log')
    ap.add_argument('--out',type=Path,default=OUT)
    ap.add_argument('--summary',type=Path,default=SUMMARY)
    a=ap.parse_args()
    raw=events(a.trace);native=native_decisions(a.log);out,c=replay(raw,native)
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(''.join(json.dumps(e,ensure_ascii=False,separators=(',',':'))+'\n' for e in out))
    summary=dict(shadow_only=True,orders_sent=0,redis_writes=0,extra_market_api_calls=0,
                 source_events=len(raw),native_decisions_indexed=len(native),
                 transitions=len(out),counts=dict(c),warning='No native 3m/5m+model recomputation evidence: NO automatic READY/ORDER authority')
    a.summary.write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(summary,indent=2,ensure_ascii=False))
if __name__=='__main__':main()
