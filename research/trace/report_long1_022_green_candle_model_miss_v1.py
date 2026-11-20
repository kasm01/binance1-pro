"""Generate user-facing 44-window TRT report using frozen 1m audit JSON."""
import json
from pathlib import Path
R=Path(__file__).resolve().parents[2];OUT=R/'research/results'
x=json.loads((OUT/'LONG1_70_WINDOWS_GREEN_022_ARM_AND_MISSING_MODEL_20261120.json').read_text())
wanted=[w for w in x['windows'] if w['user_label']=='LONG_WANTED']
avoid=[w for w in x['windows'] if w['user_label']=='LONG_AVOID']
assert len(wanted)==44 and len(avoid)==26
s=x['group_unique_counts']['LONG_WANTED'];a=x['group_unique_counts']['LONG_AVOID']
lines=[
 '# LONG1 — 11–15 Kasım hedef pencerelerinde yeşil 1m ve %0,22 ARM taraması',
 '',
 '20 Kasım 2026 araştırma raporu. Europe/Istanbul; NEARUSDT Binance Futures.',
 'Bu rapor gerçek emir/giriş/kâr kilidi kanıtı değildir; üretim servisleri kapalı.',
 '',
 '## Tanımlar ve sayılar',
 '',
 '- Kullanıcının 70 aralığının 44 LONG_WANTED / 26 LONG_AVOID aralığı kullanıldı.',
 '- Bir mum yalnız açılışı ve 1m kapanışı bütünüyle aralık içindeyse sayıldı.',
 '- Yeşil mum: 1m CLOSE > OPEN.',
 '- %0,22 brüt ARM görülmesi: 3x * (HIGH / OPEN - 1) * 100 >= %0,22,',
 '  yani HIGH/OPEN fiyat artışı en az %0,073333...',
 '- Daha katı kapanış metriği: 3x * (CLOSE / OPEN - 1) * 100 >= %0,22.',
 '- Aynı dakika MODEL yok: arşivlenen 103 gerçek MODEL LONG olayından',
 '  aynı 1m kovasında bir tane bile kayıt yok. Başka zamanda',
 '  oluşmuş veya gözlenmemiş bir giriş niyeti dışlanmış sayılmaz.',
 '- Bu sayılar **gerçekte kaçırılmış pozisyon sayısı DEĞİL**;',
 '  yeşil mum sonucunu yalnız mum tamamlandıktan sonra öğrenebiliriz.',
 '- TP tetiklenmesi ve Binance reduce-only emir dolumu için',
 '  gerçek pozisyonun ne zaman açıldığı ve intraminute tick/ACK gerekir.',
 '- Aynı LONG_WANTED ile LONG_AVOID çakışan dilimlerde NO_TRADE.',
 '',
 '| Grup | Tam 1m mum | Yeşil mum | Yeşil HIGH >= ARM | Yeşil CLOSE >= ARM | HIGH ARM ama aynı dk MODEL yok | CLOSE ARM ama aynı dk MODEL yok |',
 '|---|---:|---:|---:|---:|---:|---:|',
 f"| LONG_WANTED | {s['fully_within_1m_candles']} | {s['green_1m_candles']} | {s['green_open_to_high_022_arms']} | {s['green_open_to_close_022_arms']} | {s['high_022_arm_no_long_model_same_minute']} | {s['close_022_arm_no_long_model_same_minute']} |",
 f"| LONG_AVOID | {a['fully_within_1m_candles']} | {a['green_1m_candles']} | {a['green_open_to_high_022_arms']} | {a['green_open_to_close_022_arms']} | {a['high_022_arm_no_long_model_same_minute']} | {a['close_022_arm_no_long_model_same_minute']} |",
 '',
 'Arşivde MODEL LONG bulunmayan 34 LONG_WANTED zaman aralığında',
 '**604 yeşil 1m HIGH/OPEN >= %0,22 ROI mumu** bulundu.',
 'Bu aralıklarda modelin hiç fırsat üretmediği şeklinde yorum',
 'yapılmamalı; yalnız saklanmış LONG MODEL geçişi bulunmadı.',
 '',
 '## 44 LONG_WANTED zaman aralığının tamamı',
 '',
 '| # | Başlangıç TRT | Bitiş TRT | Yeşil | HIGH ARM >= 0,22 | CLOSE ARM >= 0,22 | HIGH ARM + aynı dk MODEL yok | Kayıtlı MODEL olayları |',
 '|---:|---|---|---:|---:|---:|---:|---:|'
 ]
for w in wanted:
 c=w['counts']
 lines.append(f"| {w['window_number']} | {w['start_tr'][5:16]} | {w['end_tr'][5:16]} | {c['green_1m_candles']} | {c['green_open_to_high_022_arms']} | {c['green_open_to_close_022_arms']} | {c['high_022_arm_no_long_model_same_minute']} | {c['observed_long_model_events_on_candles']} |")
lines+=['','## Her dakika için tam OHLC/flow ve MODEL saatleri',
 '',
 'LONG1_70_WINDOWS_GREEN_022_ARM_AND_MISSING_MODEL_20261120.json:',
 'Her pencerenin green_open_to_high_022_details listesi şunları içerir:',
 '1m tam TRT açılış/kapanış saati, OPEN/HIGH/LOW/CLOSE,',
 'OPEN→HIGH ve OPEN→CLOSE brüt 3x ROI, 1m signed',
 'taker imbalance, aynı dakika MODEL olay zamanı/kararı,',
 'LONG_WANTED/LONG_AVOID çakışması ve ARM/ENTRY yetkisinin',
 'kanıtlanmadığı bilgisi. Yeşil ancak eşik altı mumlar da',
 'green_other_details içinde bulunur.',
 '',
 '## Maliyet ve yorum',
 '',
 'ARM %0,22; geri çekilme %0,10; varsayımsal roundtrip',
 'fee %0,24 ROI puanı olduğunda teorik net taban',
 '%0,22 - %0,10 - %0,24 = **-%0,12 ROI puanı**.',
 'Bu seviye kesin stop/çıkış değildir. Doğrudan düşen',
 'mumlarda ARM hiç tetiklenmez. Bir 1m yeşil mumu bilmek',
 'ancak kapanınca mümkündür; o mumun OPEN fiyatını',
 'geçmişte almış gibi saymak gerçekçi sinyal değildir.',
 '',
 '## Sonraki analiz için iki aşamalı sınıflama',
 '',
 '1. Bunların hangisi kapanmış 3m/5m piyasa bağlamı',
 '   olumlu iken bir SONRAKİ dakika Sniper/Entry koşullarını',
 '   geçiriyor? (Yeni MODEL/Intent oluşturmadan emir izni yok.)',
 '2. Hangilerinde sonraki 1/3/5 dakika momentum devam ediyor,',
 '   kâr kilidine erişim maliyet+slippage sonrasında mümkün?',
 '',
 'Model/Intent eksik soy bağlantısı nedeniyle 841 satır',
 'üzerinden gerçek botun 841 işlem kaçırdığı iddia edilemez.',
 'Üretim ayarı/Redis kayıtları/servisler değiştirilmedi.',
 '']
(OUT/'LONG1_70_WINDOWS_GREEN_022_ARM_AND_MODEL_ABSENCE_REPORT_20261120.md').write_text('\n'.join(lines))
print(json.dumps({'status':'PASS','wanted_windows_in_report':len(wanted),
 'avoid_windows_control':len(avoid),'wanted_green_high022':s['green_open_to_high_022_arms'],
 'wanted_green_close022':s['green_open_to_close_022_arms'],
 'wanted_no_same_minute_model_high022':s['high_022_arm_no_long_model_same_minute'],
 'no_real_orders':True},sort_keys=True))
