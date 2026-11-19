"""Render offline LONG1 audit based on immutable replay results."""
from pathlib import Path
from collections import Counter
import json
ROOT=Path(__file__).resolve().parents[2]/'research/results'
p=json.loads((ROOT/'LONG1_TARGET_CONFLICT_SHADOW_PROFILE_SWEEP_20261119.json').read_text())
a=json.loads((ROOT/'LONG1_USER_WINDOWS_BROKER_RECONCILIATION_20261111_15_20261118.json').read_text())
f=json.loads((ROOT/'LONG1_ALL_MODEL_LONG_ROI_FIRST_TOUCH_20261111_15.json').read_text())['events']
w=json.loads((ROOT/'LONG1_WHALE_THRESHOLD_045_055_065_STAGE_SHADOW_20261119.json').read_text())
assert len(f)==103
d={}
for label in ('LONG_TARGET','LONG_AVOID','UNLABELLED','CONFLICT_NO_TRADE'):
 subset=[x for x in f if x['research_label']==label]
 d[label]=dict(n=len(subset),**Counter(x['horizons']['60']['status'] for x in subset))
assert d['LONG_TARGET']['TP_FIRST']==11
assert d['LONG_AVOID']['SL_FIRST']==6
assert d['LONG_AVOID']['TP_FIRST']==43
assert d['LONG_AVOID']['NEITHER']==21
assert w['veto_counts_by_threshold']=={'0.45':10,'0.55':10,'0.65':1}
path=ROOT/'LONG1_FULL_GATE_SETTINGS_TARGET_CONFLICT_REPLAY_20261119.md'
lines=[
'# LONG1 — tam giriş ayarları, hedef fırsatlar ve çakışma senaryosu',
'',
'**Dönem:** 11–15 Kasım 2026, yalnız LONG1 / NEARUSDT.',
'**Durum:** araştırma (shadow), canlı emir izni NO-GO, servisler başlatılmadı.',
'',
'## Gerçek mevcut LONG1 ayarları',
'',
'| Aşama | Etkin ayar | Risk ve gözlem |',
'|---|---|---|',
'| MODEL | Rolling quantile=0,965; minimum=0,491; lookback=480 | 11 hedef MODEL LONG kendi rolling eşiğinin üzerinde |',
'| Market Context | Adaptive enable=1; V2 ayrı shadow | V2 0 READY verdiği için canlı veto olarak kullanılamaz |',
'| Master whale | Contra veto=1; eşik=0,45 | Bazı hedef olaylarda Master karşı-whale olasılığı güçlü |',
'| SNIPER | 1m mum ilerleme aralığı %5–%60 | İki geç ve bir erken ret |',
'| ENTRY | kalite >=0,52; body >=0,15; retrace <=0,50; reject >=0,75 | Dört yönlü mum yok ve bir reversal ret |',
'| PENDING | Contra-Trend guard=1 | Bir yeniden kontrol bekledi |',
'| Risk | MASTER_MAX_POS=1, scale-in=0 | İki model olayında borsada LONG zaten açıktı |',
'| Lifecycle | dynamic_stop=1, catastrophic price=%3,5 | Araştırma 1m bariyer simülasyonu gerçek stopu taklit etmez |',
'| Final Safety | Shared Risk Master LIVE OPEN veto | **Değişmedi; NO-GO** |',
'',
'## Girişin neden kaçırıldığı',
'',
'- 44 hedef pencerenin 10 tanesinde 11 bağımsız MODEL LONG vardı;',
'  11/11 rolling model eşiğini geçti.',
'- 9 Trade Intent, 0 gerçek Binance açılışı.',
'- Dokuz niyetin terminal nedenleri: 1m yönlü mum eksikliği 4,',
'  Sniper erken 1, Sniper geç 2, güçlü 1m ters dönüş 1,',
'  PENDING recheck wait 1.',
'- İki MODEL olayı esnasında başka gerçek LONG zaten açıktı.',
'- 11 MODEL olayı için yakın TOP5 araştırma eşleşmesinde 18 satır var;',
'  eski MODEL→TOP5 kimlikleri EKSİK, eşleşme zaman + yuvarlanmış',
'  model skorudur; kesin sebep gibi kullanılmadı.',
'',
'### Gerçek Master whale fonksiyonunun araştırma çalıştırması',
'',
'| Whale karşı-yön eşiği | TOP5 test satırı | Veto edilen | Veto edilmeyen |',
'|---|---:|---:|---:|',
]
for threshold in ('0.45','0.55','0.65'):
 n=w['veto_counts_by_threshold'][threshold]
 lines.append(f'| {threshold} | {w["TOP5_rows_tested"]} | {n} | {w["TOP5_rows_tested"]-n} |')
lines.extend([
'',
'0,45→0,55 bu satırlarda fark yaratmıyor. 0,65 yalnız 1 veto',
'bırakıyor; gerçek 3m/5m trend dönüşü ve 1m teyit olmadan',
'bu ayar CANLI için güvenli değildir. Bu test yalnız',
'MasterExecutor whale fonksiyonunun sonucu; diğer risk/giriş',
'kapılarının tümünü geçtiğini göstermez.',
'',
'## 11 hedef model olayı üzerinde 1m fiyat yolu replay',
'',
'- Model gözleminden sonraki ilk tamamen kapanmış 1m mum kapanışı',
'  varsayımsal LONG giriş fiyatı; devamındaki 1m mumlardan',
'  sabit TP ilk temas vs %2,99 fiyat SL ilk temas.',
'- 3x kaldıraç, en fazla 60m bekleme; aynı mum TP ve SL görülürse',
'  STOP önceliği; bar eksikse CENSORED.',
'- Gidiş-dönüş notional masraf %0,08 tahmini, 3x ROI maliyeti',
'  0,24 yüzde puan; spread, slippage, BNB, funding, liquidation,',
'  gerçek Sniper/Entry Confirmation, native/dynamic stop yok.',
'- Kullanıcının geriye dönük LONG_TARGET pencerelerinden seçilen',
'  11 model olayıdır: geleceği bilen etiketle seçim yanlılığı var.',
'',
'| Shadow çıkış denemesi | 11 tekil olayda TP_FIRST | Tek pozisyonla varsayımsal açılış | Meşgulken atlanan | Net ROI puanı toplamı, hesap getirisi DEĞİL |',
'|---|---:|---:|---:|---:|'
])
names={'reference_fixed125_1m':'TP %1,25 / ilk tam mum',
 'shadow_fixed095_1m':'TP %0,95 / ilk tam mum',
 'shadow_fixed060_1m':'TP %0,60 / ilk tam mum',
 'reference_fixed125_delayed_1bar':'TP %1,25 / +1 tam mum gecikme',
 'reference_fixed125_delayed_2bar':'TP %1,25 / +2 tam mum gecikme'}
for key,v in p['profiles'].items():
 lines.append(f'| {names[key]} | {v["isolated_11_by_status"].get("TP_FIRST",0)} | '
  f'{v["sequential_single_position_opened"]} | {v["sequential_skipped_busy"]} | '
  f'{v["sequential_net_roi_pp_sum_not_capital_return"]:+.2f} |')
lines.extend([
'',
'Bunlar gerçek piyasa emirlerinin dolumları değildir. %1,25 TP',
'varsayımsal fiyat temasına göre uygulanmıştır; bu tablodan',
'aynı kalitede gerçek ENTRY/STOP performansı çıkarılamaz.',
'Gerçek 10 LONG pozisyonla bu farazi 9 pozisyonu birlikte',
'taşıyan hesap simülasyonu yapılmadı.',
'',
'## Tüm 103 model LONG üzerinde seçicilik maliyeti',
'',
'| Sonradan verilmiş etiket | Model sayısı | 60m TP_FIRST | 60m SL_FIRST | NEITHER |',
'|---|---:|---:|---:|---:|'
])
for label in ('LONG_TARGET','LONG_AVOID','UNLABELLED','CONFLICT_NO_TRADE'):
 z=d[label]
 lines.append(f'| {label} | {z["n"]} | {z.get("TP_FIRST",0)} | {z.get("SL_FIRST",0)} | {z.get("NEITHER",0)} |')
lines.extend([
'',
'LONG_AVOID 70 model olayında 43 sanal hedef, 6 sanal stop,',
'21 zaman içinde hedefsiz durum var. SL bariyeri 3x brüt',
'~-%8,97 ROI iken TP +%1,25. Kazanan oranını tek başına',
'optimize etmek, ödeme ve kuyruk riskini gözden kaçırır.',
'LONG_TARGET kullanıcı etiketi bir canlı alım izni DEĞİLDİR.',
'',
'## Çakışan yedi saat — tek MODEL için varsayımsal LONG kâr/zarar',
'',
])
c=p['conflict_isolated_fictitious_long']
lines.extend([
'- Yedi çakışma aralığının altısında MODEL LONG yok.',
'- 13 Kasım 18:36:13 TRT model skoru rolling eşiğinin üzerinde,',
'  fakat zaten 13 Kasım 17:51 açılmış gerçek LONG hâlâ açık.',
f'- Çakışmadaki bağımsız FARAZİ giriş: {c["entry_time_tr"]},',
f'  fiyat {c["entry_price"]:.3f} NEARUSDT.',
f'- %1,25 brüt TP ilk temas: {c["exit_time_tr"]}.',
f'- Masraf varsayımı sonrası teorik **+%{c["net_roi_pct_fee_illustration"]:.2f} ROI**.',
'- Gerçek borsa emri YOK, portföyde ek LONG sayısı **0**.',
'- Çakışma veto kuralı ve tek pozisyon limiti korundu;',
'  varsayımsal kâr gerekçesiyle çakışmaya izin verilmedi.',
'',
'## Gerçek açılmış 10 LONG pozisyonun tek tek sonuçları',
'',
'| Gerçek açılış TR | Kullanıcı etiketi | Gerçekleşmiş fiyat P&L USDT | Tahmini komisyon/funding sonrası USDT | 1m en iyi brüt 3x ROI |',
'|---|---|---:|---:|---:|',
])
for trade in a['trades']:
 roi=(trade.get('intratrade_public_1m') or {}).get('gross_3x_max_favorable_roi_pct')
 lines.append(f'| {trade["open_tr"][5:16].replace("T"," ")} | {trade["reference_label"]} | '
  f'{trade["realized_price_pnl_usdt"]:+.3f} | '
  f'{trade["net_usdt_indicative"]:+.3f} | '
  f'{("N/A" if roi is None else "%"+str(roi))} |')
lines.extend([
'',
'- Binance 27 fill, 20 market order, 10 LONG açılış/10 kapanış;',
'  8 pozitif fiyat P&L, 2 negatif fiyat P&L.',
f'- Gerçekleşmiş fiyat P&L {a["realized_pnl_usdt_exact"]:+.3f} USDT;',
f'  funding {a["total_funding_usdt_exact"]:+.8f} USDT;',
f'  yaklaşık BNB komisyonu {a["commission_usdt_hourly_estimate"]:.6f} USDT;',
f'  tahmini net {a["indicative_total_after_funding_and_commissions_usdt"]:+.3f} USDT.',
'- 4 gerçek LONG açılışı LONG_AVOID penceresine denk geliyor;',
'  ikisi zarar etti. Etiketsiz pencerede 6 gerçek açılış var.',
'',
'## Yalnız araştırmada değiştirilen ayarlar',
'',
'- research/staging/long1_research_only_settings_v1.json',
'  mevcut konfigürasyonun ve shadow adayın ayrı sürümünü tutuyor.',
'- Araştırma adayı: whale eşiği 0,55; Sniper maksimum mum',
'  ilerlemesi 0,60→0,75; Entry quality 0,52→0,48;',
'  retrace max 0,50→0,60; reject retrace 0,75 değişmeden.',
'- Bu 4 parametrenin gerçek Entry/Order sonuçları, geçmişte',
'  tam kaynak 1m kalite telemetrisi eksik olduğu için BU replayde',
'  doğrulanmadı. Whale 0,55 ayrı testte etkisiz.',
'- 0,65 whale yalnız agresif shadow araştırma adayıdır, otomatik',
'  canlı ayar değildir. Zıt whale veto, Contra-Trend, Stop,',
'  Risk Master, single-position ve exchange stop yetkileri korunmalı.',
'- Gerçek üretim .env ve işlem kodlarına DOKUNULMADI.',
'',
'## Sonraki araştırma',
'',
'1. LONG1 1m quality/body/retrace ve Sniper candle progress',
'   özelliklerini PENDING attempt ile giriş öncesi eksiksiz kaydet.',
'2. Bu özellikleri as-of mumlardan eski örneklemde yeniden kur;',
'   parametre sweep ile hem hedef, hem kaçın ve farklı',
'   out-of-sample günlerini aynı replay altında değerlendir.',
'3. Gerçek net maliyet, kâr kilidi ve 30 saniye dynamic stop',
'   sırasına yaklaşan konservatif yürütme modeli olmadan',
'   LONG açma kapılarını productionda gevşetme.',
'4. Çakışan niyetler için gerçek merkezi coordination fail-closed',
'   kuralını ayrıca test et. Araştırma kullanıcı saatlerini',
'   kalıcı canlı saat filtresine çevirmek yok.',
'',
'## Kanıt dosyaları',
'- LONG1_TARGET_CONFLICT_SHADOW_PROFILE_SWEEP_20261119.json',
'- LONG1_WHALE_THRESHOLD_045_055_065_STAGE_SHADOW_20261119.json',
'- LONG1_USER_WINDOWS_BROKER_RECONCILIATION_20261111_15_20261118.json',
'- research/staging/long1_research_only_settings_v1.json',
])
path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps({'status':'PASS','report':path.name,'target_model':11,
 'conflict_event':1,'real_broker_trades_reviewed':10,
 'parameter_changes_live':False,'orders_sent':0},sort_keys=True))
