"""Render archived verification without network or production writes."""
from __future__ import annotations
import csv,json
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[2]/'research/results'
A='LONG1_USER_WINDOWS_BROKER_RECONCILIATION_20261111_15_20261118.json'
P='LONG1_USER_WINDOWS_FULL_AUDIT_20261111_15_20261118'
a=json.loads((ROOT/A).read_text())
def save(name,rows,columns):
 with (ROOT/(P+'_'+name+'.csv')).open('w',newline='',encoding='utf-8') as out:
  w=csv.DictWriter(out,fieldnames=columns,extrasaction='ignore',lineterminator='\n')
  w.writeheader();w.writerows(rows)
trades=[]
for x in a['trades']:
 row=dict(x);o=x.get('intratrade_public_1m') or {}
 row['mfe_3x_roi_pct']=o.get('gross_3x_max_favorable_roi_pct')
 row['mae_3x_roi_pct']=o.get('gross_3x_max_adverse_roi_pct')
 row['arm_levels_touched']=';'.join(str(v) for v in o.get('arm_levels_touched') or [])
 row['offline_r1_shadow_flag']=x['entry_context_telemetry']['shadow_contra_conjunction_risk_only']
 trades.append(row)
save('10_BROKER_TRADES',trades,
 ['index','open_tr','close_tr','reference_label','entry_qty_near','entry_price','exit_price',
  'leverage','realized_price_pnl_usdt','funding_usdt',
  'commission_usdt_indicative_hourly_bnb','net_usdt_indicative','gross_roi_pct',
  'net_roi_pct_indicative','mfe_3x_roi_pct','mae_3x_roi_pct',
  'arm_levels_touched','offline_r1_shadow_flag','shadow_outcome_present','exit_reason_shadow'])
save('112_INTENT_REASONS_ANON',a['all_112_intent_decisions_anonymized'],
 ['intent_marker_sha256_12','intent_time_tr','user_reference','decision_class',
 'evidence_reason','actual_binance_fill_order_verified','source_model_to_intent_exact_trace_available'])
save('70_USER_WINDOWS',a['window_coverage'],
 ['index','start_tr','end_tr','requested','model_long_count','intent_count','real_open_count'])
save('7_CONFLICT_WINDOWS',a['conflict_coverage'],
 ['start_tr','end_tr','model_long_count','intent_count','real_open_count','offline_window_policy'])
labels={'LONG_TARGET':'Açılmalı','LONG_AVOID':'Açılmamalı',
 'CONFLICT_NO_TRADE':'Çakışma','UNLABELLED':'Etiketsiz'}
lines=[
 '# LONG1 — 11–15 Kasım 2026 ortak saat pencereleri: eksiksiz açılış ve ret denetimi',
 '',
 'Bu çalışma Binance Futures salt-okunur gerçekleşme, income ve emir',
 'uç noktalarından, Redis geçmişinden ve kullanıcı referans dosyasından',
 'üretilmiştir. Canlı bot/parametre değişikliği veya emir gönderimi yoktur.',
 '',
 '## Tam huni ve tarihsel saat etiketleri',
 '',
 'Kullanıcı referansında 44 açılmalı ve 26 açılmamalı zaman penceresi var.',
 'Zıt etiketli 7 çakışma segmenti araştırmada kesin NO_TRADE/REJECT.',
 '',
 '| Etiket | SIGNAL Redis olayı | CANDIDATE | TOP5 | Trade Intent | Açılan | Açılmayan |',
 '|---|---:|---:|---:|---:|---:|---:|'
]
for label in ('LONG_TARGET','LONG_AVOID','CONFLICT_NO_TRADE','UNLABELLED'):
 st=a['stage_redis_stream_event_counts']
 vals=[st[x]['by_reference'].get(label,0) for x in
    ('signals_stream_long1','candidates_stream_long1','top5_stream_long1')]
 n=a['trade_intent_reference_counts'].get(label,0)
 opened=a['open_by_reference'].get(label,0)
 lines.append(f'| {labels[label]} | {vals[0]} | {vals[1]} | {vals[2]} | {n} | {opened} | {n-opened} |')
lines.extend([
 '| TOPLAM | 874 | 317 | 310 | 112 | 10 | 102 |',
 '',
 '103 bağımsız log MODEL LONG olayı ile 874 yayınlanmış SignalEvent',
 'aynı birim değildir. MODEL LONG referansı: 11 açılmalı, 70 açılmamalı,',
 '21 etiketsiz, 1 çakışma. Eski MODEL→SIGNAL tam trace ID zinciri eksik.',
 '112 Trade Intent ise 112 ayrı yürütme log bloğuyla kesin eşleşiyor;',
 '10 tanesi Binance orderId ve TradeIntent intent_id üzerinden kesin açılmıştır.',
 '',
 f'Açılmalı olan 44 pencerede açılış sayısı sıfır. {a["wanted_windows_with_model_long"]}',
 f'pencerede MODEL LONG, {a["wanted_windows_with_trade_intent"]} pencerede',
 'Trade Intent var. Açılmamalı 26 pencereden dördünde pozisyon açılmış.',
 'İşaretlenmemiş aralıkta altı pozisyon açılmış. Yedi çakışmada sıfır açılış.',
 '',
 '## Günlük işlem niyetleri ve gerçekleşmiş açılışlar',
 '',
 '| Gün (TR) | İşlem niyeti | Gerçek açılış | Açılmayan |',
 '|---|---:|---:|---:|',
])
for day,values in sorted(a['daily_funnel'].items()):
 intents=sum(v for k,v in values.items() if k.startswith('intent_'))
 op=sum(v for k,v in values.items() if k.startswith('open_'))
 lines.append(f'| {day} | {intents} | {op} | {intents-op} |')
lines.extend([
 '',
 '## Açılmayan 102 Trade Intent neden açılmadı?',
 '',
 '| Kaydedilmiş yürütme nedeni | Niyet |',
 '|---|---:|'
])
for reason,count in sorted(a['not_opened_reasons'].items(),key=lambda z:-z[1]):
 lines.append(f'| {reason} | {count} |')
lines.extend([
 '| TOPLAM | 102 |',
 '',
 'Açılmalı pencerelerin dokuz niyetindeki gerekçeler:'
])
for reason,count in sorted(a['not_opened_reasons_by_reference']['LONG_TARGET'].items(),key=lambda z:-z[1]):
 lines.append(f'- {reason}: {count}')
lines.extend([
 '',
 '## 11 bağımsız MODEL LONG: Açılmalı referansının karşıolgusal sınırı',
 '',
 'Açılmalı saatlerindeki 11 bağımsız MODEL LONG olayının tamamında',
 'eski Market Context 60m first-hit araştırması TP_FIRST gösteriyor.',
 'Bu bir gerçekleşmiş emir/nihai net kâr değildir: gerçek 1m giriş',
 'onayı, giriş fiyatı, intrabar sıra, native stop ve maliyetler dışarıda.',
 'Çakışma penceresindeki bir MODEL LONG olayı da TP_FIRST gösterse',
 'bile çakışma emri kesin REJECT olarak ele alınır.',
 '',
 '## Binance tarafından doğrulanan on LONG açılışı / kapanışı',
 '',
 '| Açılış TR | Referans | Kapanış TR | Gerçekleşmiş fiyat P&L USDT | Yaklaşık masraf sonrası USDT | 1m en yüksek brüt 3x ROI |',
 '|---|---|---|---:|---:|---:|'
])
for x in a['trades']:
 op=x['open_tr'][5:16].replace('T',' ')
 cl=x['close_tr'][5:16].replace('T',' ')
 mfe=x['intratrade_public_1m']['gross_3x_max_favorable_roi_pct']
 mfe_str='Yok' if mfe is None else f'%{mfe:.3f}'
 lines.append(f'| {op} | {labels[x["reference_label"]]} | {cl} | {x["realized_price_pnl_usdt"]:+.3f} | {x["net_usdt_indicative"]:+.3f} | {mfe_str} |')
lines.extend([
 '',
 'Sekiz kârlı fiyat kapanışı toplam +0,940 USDT; iki zararlı fiyat',
 'kapanışı toplam −0,992 USDT. Gerçekleşmiş fiyat P&L **−0,052 USDT**.',
 f'Binance funding **{a["total_funding_usdt_exact"]:+.8f} USDT**.',
 f'BNB komisyonu **{a["commission_bnb_exact"]:.8f} BNB**.',
 f'Tarihi BNBUSDT perpetual 1h kapanışıyla yaklaşık komisyon',
 f'**{a["commission_usdt_hourly_estimate"]:.6f} USDT**.',
 f'Masraflardan sonra yaklaşık **{a["indicative_total_after_funding_and_commissions_usdt"]:+.6f} USDT**.',
 'Komisyon dönüşümü yaklaşık olduğundan bu bir hesap özsermaye getiri',
 'raporu veya borsanın kesin USDT-net komisyon kaydı değildir.',
 '',
 '## Kaybeden iki işlem ve kâr kilidi için gözlem',
 ''
])
for x in a['trades']:
 if x['realized_price_pnl_usdt']>=0:continue
 c=x['entry_context_telemetry'];q=x['intratrade_public_1m']
 lines.extend([
 f'### {x["open_tr"]}',
 f'- Açılış LONG_AVOID saatinde, borsa fiyat P&L **{x["realized_price_pnl_usdt"]:+.3f} USDT**,',
 f'  yaklaşık masraf sonrası **{x["net_usdt_indicative"]:+.3f} USDT**.',
 f'- Giriş sırasında m3 upfrac={c["m3_up_frac3"]:.3f}, 3m ortalama return={c["m3_return_mean3"]:.6f};',
 f'  tamamlanmış flow15={c["completed_flow15"]:.4f}, flow60={c["completed_flow60"]:.4f}.',
 f'- Giriş ve çıkış dakikaları hariç tam 1m mumlarda en lehe brüt ROI',
 f'  **%{q["gross_3x_max_favorable_roi_pct"]:.3f}**, en aleyhe',
 f'  **%{q["gross_3x_max_adverse_roi_pct"]:.3f}**.',
 f'- ARM ilk-temas seviyeleri: {", ".join("%"+str(x) for x in q["arm_levels_touched"])}.',
 f'- Kapanış nedeni telemetrisi: {x["exit_reason_shadow"]}.',
 ''
 ])
lines.extend([
 'Her iki zararlı işlemde de pozisyon açılışında negatif 3m bağlamıyla',
 'negatif flow15 ve flow60 aynı anda bulunuyor. Geçmiş on işlemde',
 'bu bileşik R1-benzeri hipotetik filtre iki zararı, sıfır kârı işaretledi.',
 'Bu yalnız geriye dönük hipotezdir; canlı filtremiz değiştirilmedi.',
 '1m OHLC sıra/tick verisi olmadığından %0,60 ARM görülmesi',
 'gerçek trailing çıkış ve net kâr garantisi değildir.',
 '',
 '## Çakışan saatler: araştırma için kesin REJECT',
 '',
 '| Tarih-saat (TR) | MODEL LONG | Trade Intent | Gerçek OPEN |',
 '|---|---:|---:|---:|',
])
for x in a['conflict_coverage']:
 lines.append(f'| {x["start_tr"][5:16].replace("T"," ")} – {x["end_tr"][5:16].replace("T"," ")} | {x["model_long_count"]} | {x["intent_count"]} | {x["real_open_count"]} |')
lines.extend([
 '',
 'Çakışmada 6 SignalEvent, 2 Candidate ve 1 TOP5 var, ancak',
 'sıfır Trade Intent ve sıfır gerçek pozisyon. Geçmiş tarihli kullanıcı',
 'etiketleri canlı bir saat-yasağına dönüştürülmedi. Yeni aktif izin',
 'pencereleri çakışırsa merkezi koordinasyon katmanı NO_TRADE veto',
 'vermeli; bu kuralın ileriye dönük güvenli entegrasyonu ayrı çalışmadır.',
 '',
 '## Veri kalitesi ve sınırlar',
 '',
 '- Gerçek Binance: signed GET userTrades 27 fill; allOrders 20 FILLED MARKET;',
 '  income 45 kayıt; fiyat bazlı 10 tam LONG roundtrip.',
 '- Redis shadow 10 pozisyon açılışı, ancak 9 sonuç; eksik',
 '  13 Kasım 17:51 açılışının 22:28 SELL ile zararda kapandığı',
 '  Binance ile doğrulandı. Gerçek çıkış nedeni yine BELİRSİZ.',
 '- 112 intent log nedeni kesin dispatch bloğundan ve 10 açılış',
 '  Binance exchange orderId eşleşmesiyle raporlandı. 103 MODEL uzun',
 '  olayının 112 intent ile birer birer eşleştirilmesi yapılamıyor.',
 '- Pozisyon içindeki en yüksek/düşük fiyat yalnız tam 1m barların OHLC',
 '  değeridir; giriş/çıkış dakika high-low değerleri dışarıda ve',
 '  intrabar high/low sırası bilinmiyor.',
 '- Binance BNB komisyonunun gerçek vergi/maliyet dönüşümü USDT değil',
 '  BNB; USDT dönüşümü saatlik BNB perpetual kapanışından tahmindir.',
 '- Model eşikleri, Contra-Trend, Native Stop, merkezi Risk Master',
 '  ve canlı servisler değiştirilmedi, gerçek emir gönderilmedi.',
 '',
 '## Veri dosyaları',
 '- 10_BROKER_TRADES CSV: tek tek tüm gerçek işlemler, finans ve 1m yol.',
 '- 112_INTENT_REASONS_ANON CSV: eksik/açılmama gerekçeleri, UUID yerine hash.',
 '- 70_USER_WINDOWS CSV: işaretlenen tüm saatlerin olay sayısı.',
 '- 7_CONFLICT_WINDOWS CSV: çakışma aralıkları ve offline REJECT sonucu.',
 '- Ayrıntılı JSON: kullanıcı pencereleri, bütün 112 niyet, maliyet,',
 '  strateji huni istatistikleri ve test metadata.',
])
(ROOT/(P+'.md')).write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps({'status':'PASS','written_files':5,
 'trades':len(trades),'intents':len(a['all_112_intent_decisions_anonymized']),
 'user_windows':len(a['window_coverage']),'conflicts':len(a['conflict_coverage']),
 'no_order_calls':True},sort_keys=True))
