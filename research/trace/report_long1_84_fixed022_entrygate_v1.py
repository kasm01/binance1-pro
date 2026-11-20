"""Read-only report: hard gross 0.22 TP and ex-ante feature guards."""
from pathlib import Path
import json
R=Path(__file__).resolve().parents[2];OUT=R/'research/results'
x=json.loads((OUT/'LONG1_AVOID84_FIXED_TP022_AND_PREENTRY_GATES_20261120.json').read_text())
lines=[
 '# LONG1: Üç ters giriş + 84 LONG_AVOID sabit %0,22 brüt TP testi',
 '',
 '20 Kasım 2026 araştırma. NEARUSDT USDT-M, 3x; sadece SHADOW.',
 'Kaynak: önceki katı LONG_AVOID 84 sanal giriş, 11–15 Kasım',
 'Binance aggTrade ZIP arşivinin 819.943 sıralı işlem basımı.',
 'Giriş NEXT 1m OPEN varsayımsal; 5m maksimum pozisyon.',
 'Sabit TP dokunma limit dolumu ideal varsayımdır.',
 'Stop fiyat -%2,99 kontrol edildi; 5m sonunda son ticaret',
 'basımıyla kapatma proxy. Gerçek emir defteri,',
 'maker/taker değişken ücret, funding, spread ve',
 'gerçek Binance conditional stop/dolum simülasyonu yok.',
 '',
 '## Sabit TP: gerçek net kâr mı?',
 '',
 'Önceki roundtrip notional ücret %0,08; 3x teminat ROI',
 'karşılığı **-%0,24 puan**. Sabit brüt %0,22 TP =',
 '**-%0,02 net ROI**, ek slippage/funding YOKKEN bile.',
 '500 USDT tam bot teminatında nominal -0,10 USDT',
 've 250 USDT tam bot teminatında -0,05 USDT.',
 'Bu tutar TP dolan pozisyon başına örnektir,',
 'bütün 84 pozisyonun toplamı değildir.',
 '',
 '| Sabit brüt TP (3x ROI) | TP’ye dokunan | Kazançlı | Zararlı | Toplam net ROI puanı |',
 '|---|---:|---:|---:|---:|'
]
for key in ('0.22','0.35','0.40','0.50','0.80','1.00'):
 a=x['fixed_tp_profiles'][key]['base']
 lines.append(f"| %{key.replace('.',',')} | {a.get('HARD_TP_TOUCH_IDEAL_FILL',0)} | {a['profitable']} | {a['loss']} | {a['net_roi_pp_sum']:+.5f} |")
lines+=['',
 'Not: TP ve net sonucu birbirine karıştırmayın.',
 'Bazı 0,35+ profillerinde TP görülmese de 5m sonunda',
 'kapatılan işlemler az miktarda pozitif olabilir.',
 'Bunların hiçbiri gerçek borsa emir dolumu kanıtı değil.',
 '',
 '## Üç özel giriş: giriş ANINDA bilinen değerler',
 '',
 '| Tarih-saat TRT | Body | Üst retrace | 1m flow | 3m flow | 3m fiyat return % | Önceki 5m return % | Sonraki en yüksek ROI % |',
 '|---|---:|---:|---:|---:|---:|---:|---:|']
for a in x['three_loss_examples']:
 f=a['pre_entry_asof_closed_1m_features']
 lines.append(f"| {a['entry_time_tr'][5:16].replace('T',' ')} | {f['body']:.3f} | {f['retrace']:.3f} | {f['flow1']:+.3f} | {f['flow3']:+.3f} | {f['r3']:+.3f} | {f['r5']:+.3f} | {a['maximum_gross_roi_5m_pp']:+.3f} |")
lines+=['',
 'Üç işlemde önceki kapalı 1m body / retrace ve',
 'katı 1m parametreleri geçiriliyor. Sonraki 5m',
 'MFE 0,086–0,096 ROI aralığında kalmış; sabit 0,22',
 'TP veya ilk 0,22 ARM tetiklenmiyor. Gelecek MFE',
 'girişte bilinemediği için zaman yasağı oluşturamaz.',
 '',
 '## Giriş öncesi aday guard karşılaştırması',
 '',
 'Gates sadece tamamlanmış 1m verilerinden türedi,',
 'kullanıcının sonradan işaretlediği WANTED/AVOID',
 'saatleri karar girdisi değil. Bu eşikler alternatif',
 'araştırma hipotezleridir, önerilmiş canlı sabit ayarlar',
 'DEĞİLDİR. Koşul eklemek yeni sinyal üretmez,',
 'yalnız var olan araştırma adaylarını azaltır.',
 '',
 '| Ön koşul | 3 kötü girişi eler mi? | AVOID 84 içinden reddedilen | Reddedilen eski kârlılar | WANTED 102 içinden reddedilen | 16 Kasım 61 içinden reddedilen |',
 '|---|---|---:|---:|---:|---:|'
]
for name,desc in (
 ('three_minute_flow_ge_0p25','3m flow en az +0,25'),
 ('five_minute_strength_ge_0p20pct','geçmiş 5m return en az +%0,20'),
 ('five_minute_strength_and_flow','her ikisi birden'),
 ('three_minute_return_le_0p30pct','3m fiyat return en fazla +%0,30'),
 ('three_minute_return_le_0p20pct','3m fiyat return en fazla +%0,20')):
 r=x['preentry_gate_screen'][name]
 av=r['avoid_84'];wanted=r['wanted_original_strict_book'];hold=r['holdout_nov16_original_strict_book']
 lines.append(f"| {desc} | {len(av['rejected_3_target_times'])}/3 | {av['rejected']} | {av['previous_net_win_rejected']} | {wanted['rejected']} | {hold['rejected']} |")
lines+=['',
 'Önemli karşılaştırma: 3m flow >=0,25 yalnız 18:28',
 've 19:27 örneklerini eler, 01:01 kalır. Beş dakika',
 'gücü >=%0,20 ve flow>=0,25 birlikte 3/3 kötü örneği',
 'eler ama **WANTED 102 adayın 60 tanesini** de eler.',
 'Bu ciddi fırsat kaybı demektir. Ayrıca eşikler bu',
 'örnekler görüldükten sonra seçildi: overfit riski!',
 '16 Kasım sonuçları aynı 84 girişin holdout performansı',
 'olarak kullanılamaz; orada yalnız mevcut ayrı 61',
 'STRICT araştırma adayına as-of sınıflama yapıldı.',
 '',
 '## Karar',
 '',
 '- **Sabit brüt %0,22 TP: NO-GO.** Ücret varsayımı',
 '  nedeniyle TP dolsa bile net kayıp üretir.',
 '- İstenen üç yanlış LONG için fiilen üretim ayarı',
 '  değiştirilmemeli: önce Contra-Trend + 3m/5m',
 '  kapanmış bağlam / yeni MODEL→Intent soy ağacı',
 '  ve gerçek Entry Confirmation sinyalinin yeniden',
 '  üretimi şart.',
 '- Bir test filtresi eklendiğinde yanlış AVOID azaltma',
 '  yanında WANTED kârlı fırsat kaybı da ölçülmeli.',
 '- İşlem yapmak için en az net komisyon + kayma',
 '  + güvenlik tamponu karşılayacak hedef gerekir;',
 '  yalnız ücretleri aşmak beklenen kâr garantisi değil.',
 '- Para tahsisi 4 botta 500, 8 botta 250 USDT',
 '  olarak plan; Risk Master aynı coinde tek pozisyon,',
 '  komisyon/maintenance rezervi ve stop güvenliği korunur.',
 '- Üretim ENV/servis/Redis değişmedi, gerçek emir yok.',
 '',
 'Kod: research/trace/replay_long1_84_fixed022_early_entry_gate_v1.py',
 'Test: research/trace/test_long1_84_fixed022_early_entry_gate_v1.py',
 'JSON: LONG1_AVOID84_FIXED_TP022_AND_PREENTRY_GATES_20261120.json',
 ''
]
p=OUT/'LONG1_AVOID84_FIXED_TP022_ENTRY_GUARD_REPORT_20261120.md'
p.write_text('\n'.join(lines).rstrip()+'\n')
print(json.dumps({'status':'PASS','sections':len(lines),'tp_022_net_after_fee':x['hard_tp_0p22_net_pp_after_fee'],
 'example_count':len(x['three_loss_examples']),'production_change':False},sort_keys=True))
