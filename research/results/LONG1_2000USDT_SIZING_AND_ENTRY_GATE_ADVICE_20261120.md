# LONG1 — 2000 USDT bakiyeyle giriş parametreleri ve risk karşılaştırması

20 Kasım 2026. NEARUSDT LONG1, as-of araştırma. Gerçek işlem yok.
Yalnız önceki Stage13 ve 70 kullanıcı zaman penceresi dondurulmuş sonuçları.

## MODEL skor bulgusu
11 LONG_TARGET MODEL olayının 11'i mevcut rolling gate'i geçmiş.
70 LONG_AVOID MODEL olayının 69'u da aynı eşiği geçmiş.
Median skor: TARGET 0,499859 / AVOID 0,499700.
Model gate alt sınırını düşürmek LONG_WANTED içindeki 34
MODEL sinyali olmayan pencereye kendiliğinden yeni MODEL sağlamaz;
karar verimliliğini azaltabilir.

## Giriş parametreleri araştırma hipotezi
Mevcut strict research profili:
5 kapalı 1m recheck; body>=0,22; retrace<=0,35;
1m signed flow>=0,03; 3m flow iyileşme>=0,08;
3m fiyat return iyileşme>=0,10 yüzde puan.
Denenecek ikinci profil (ONAYLANMIŞ DEĞİL):
8 kapalı 1m recheck; body>=0,18; retrace<=0,45;
1m signed flow>=0,01; 3m flow iyileşme>=0,05;
3m fiyat iyileşme>=0,10 yüzde puan korunur.
Bu eşikler başka 11–15 Kasım verilerinde optimize edilip
canlı uygulanmamalı; ayrı ileri tarih holdout ve aynı
LONG_AVOID / conflict değerlendirmesi şart. Risk Master veto,
15m/5m market authority, fresh MODEL/Intent, native stop
ve tek-pozisyon koşulları korunur.

## 2000 USDT banka/bakiye senaryosu
Hesap 2000 USDT; 3x; teminat fraksiyonu hesabın sabit
yüzdesi; roundtrip notional fee %0,08 (ROI -0,24 puan);
brüt TP +1,25 ROI puan; stop fiyatta -%2,99
(3x ROI -8,97 puan). Tümü simüle edilmiştir.
Slippage, funding, likidasyon ve native stop fill yok.

| Hesap teminat oranı | Teminat | Notional | TP net | Stop net | Stop / hesap |
|---|---:|---:|---:|---:|---:|
| %5 | 100 | 300 | +1,01 | -9,21 | %0,4605 |
| %10 | 200 | 600 | +2,02 | -18,42 | %0,9210 |
| %20 | 400 | 1200 | +4,04 | -36,84 | %1,8420 |
| %48 | 960 | 2880 | +9,696 | -88,416 | %4,4208 |

18 farazi tek-pozisyon Stage13 sabit TP net ROI puan toplamı:
+2,5265, hibrit +0,7370. Örnek başlangıç
teminatı sabit ve bileşik kazanç yok:
%10 kullanımda +5,053 ve +1,474 USDT;
%48 kullanımda +24,2544 ve +7,0752 USDT.
Gerçek tarihsel broker-open veto duyarlılığı:
16 giriş, fixed +1,7565 puan, hibrit -0,0330 puan.
%10 kullanımda +3,513 ve -0,066 USDT;
%48 kullanımda +16,8624 ve -0,3168 USDT.
Bunlar gerçekleşmiş kâr veya cüzdan getirisi değildir.

Sabit +1,01 net TP / -9,21 net STOP
asimetrisinde yalnız TP veya SL çıkışı varsa
başabaş başarı olasılığı 9,21/(9,21+1,01)=
yaklaşık %90,1. 60m TIMEOUT ve diğer fill davranışları
gerçek başarı eşiğini değiştirir.

## Karar
- 2000 USDT ile mevcut bot daha fazla iyi sinyal üretmez.
- %48 margin+3x tek stopta hesabı ~%4,42 etkiler;
  deneysel sistem için aşırı risk.
- Araştırma ve ileride izinli dry-run için %5–10
  margin fraksiyonunu kıyaslamak daha ihtiyatlıdır.
- Yalnız 34 kaçırılan LONG_WANTED penceredeki model
  yokluğunu giderecek aday/neutral-watch mekanizması
  ve as-of giriş teyidi yeni araştırma konusu.
- Kullanıcı saatleri canlı whitelist yapılmamalı; gerçek
  piyasa durumuna göre fırsat seçilmeli.
- Üretim env, real risk, entry/exit, SHORT1 değişmedi.

Yeniden hesaplama:
PYTHONPATH=. ./venv/bin/python research/trace/report_long1_2000usdt_settings_sensitivity_v1.py
Sayısal kaynak:
LONG1_2000USDT_RISK_SIZE_AND_GATE_DIAGNOSTIC_20261120.json
