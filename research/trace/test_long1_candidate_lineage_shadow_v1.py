from research.trace.long1_candidate_lineage_shadow_v1 import candidate_shadow,lineage_from_signal
from orchestration.aggregator.aggregator import Aggregator
from orchestration.schemas.events import SignalEvent
signal=dict(event_id='uuid-source-1',_source_stream_id='1794845651904-0',
 symbol='NEARUSDT',interval='3m',side_candidate='long',price=3.0,
 model_score=.501,confidence_available=False,spread_available=False,liq_score_available=False,
 dedup_key='NEARUSDT|3m|long')
normalized=SignalEvent.normalize(signal)
normalized['_source_stream_id']=signal['_source_stream_id']
normalized['_score_total']=.501
agg=Aggregator.__new__(Aggregator)
agg.include_raw=False
old=agg._build_candidate_payload(normalized)
assert old['raw'] and 'source_signal_event_id' not in old and 'event_id' not in old['raw']
new=candidate_shadow(old,normalized)
assert new['lineage']['source_signal_event_id']=='uuid-source-1'
assert new['lineage']['source_signal_stream_id']=='1794845651904-0'
assert new['score_total']==old['score_total']
assert new['model_score']==old['model_score']
assert new['raw']==old['raw'] and new['symbol']==old['symbol']
assert new['lineage']['lineage_state']=='EXACT_SIGNAL_EVENT_ID_AND_STREAM_ID'
assert candidate_shadow(old,dict(normalized,model_close_id=998877))['lineage']['model_close_id']==998877
assert 'model_close_id' not in new['lineage']
assert lineage_from_signal(dict(normalized,event_id=''))['lineage_state']=='UNLINKED'
assert lineage_from_signal(dict(normalized,_source_stream_id='bad'))['lineage_state']=='UNLINKED'
assert lineage_from_signal({'dedup_key':'NEARUSDT|3m|long','model_score':.5})['lineage_state']=='UNLINKED'
print('PASS 11 source lineage tests with real aggregator compact-mode payload')
