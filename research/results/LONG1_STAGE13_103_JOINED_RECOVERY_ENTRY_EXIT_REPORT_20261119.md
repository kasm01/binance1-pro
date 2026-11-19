# LONG1 Stage13 — 3m/5m Contra recovery + kapanmış 1m giriş + maliyetli çıkış

19 Kasım 2026; NEARUSDT Futures, yalnız LONG1. Shadow research.
**Servisler OFF, canlı emir NO-GO.** SHORT1 veya canlı env değiştirilmedi.

## Veri ve kesin bilgi sınırı
- SHA256 doğrulanmış Binance arşivinin 8640 tam 1m mumu ve 11–15
  Kasım dönemindeki 103 gerçek MODEL LONG zaman damgası.
- Stage12'nin tamamlanmış 3m/5m mumlarla oluşturulmuş Contra
  toparlanma araştırma proxy göstergesi kullanıldı. Bu, geçmiş
  botun Combined Context / Whale değerleriyle birebir aynı değildir.
- Contra origin için en fazla 30m sonra toparlanma aranır.
  Bu, gerçek orijinal PENDING durumunun o ana kadar yaşadığı
  veya yeni MODEL/intent üretildiği anlamına GELMEZ.
- Entry için önceden dondurulan strict_recovery:
  en çok 5 tamamlanmış 1m yeniden kontrol; body/range >=0,22;
  üst retrace <=0,35; 1m signed taker flow >=0,03;
  3m flow iyileşme >=0,08; 3m fiyat iyileşme >=0,10
  yüzde puan; 3m fiyat ve signed taker flow pozitif.
- Giriş kararı yalnız tamamlanmış mumdan; gelecek barın
  OPEN fiyatına sanal fill uygulanır. Gelecek mum high/low
  hiçbir giriş kararında kullanılmaz.
- Gerçek partial 1m Sniper/Entry Confirmation, yeni intent,
  whale ve ortak Risk Master geçişi yeniden üretilmedi.
  READY burada yalnız araştırma sinyali demektir.

## 103 sinyalin karar hunisi

| Araştırma kararı | MODEL sayısı |
|---|---:|
| 30m içinde Contra 3m/5m toparlanması yok | 29 |
| Toparlanma sonrası 5 kapalı 1m giriş onayı bulunamadı | 40 |
| RESEARCH_READY_NO_REAL_INTENT | 32 |
| Rolling MODEL gate red | 1 |
| Çakışma origin REJECT | 1 |
| TOPLAM | 103 |

32 READY: 7 LONG_TARGET, 18 LONG_AVOID, 7 UNLABELLED.
**Tüm gerçek emir ve yeni model/intent kimlik yetkileri belirsiz;
bu araştırmada gerçek OPEN yetkisi verilmiş olay sayısı sıfır.**

## Tek pozisyon senaryoları

3x; TP brüt +%1,25 ROI; fiyat stop %2,99;
maksimum 60 dakika; gidiş-dönüş notional ücret %0,08
yaklaşık 0,24 ROI puanı. Hibrit altı ARM / geri çekilme:
0,60/0,10; 0,95/0,15; 1,20/0,15;
1,65/0,20; 2,00/0,20; 2,50/0,20.
Hibrit, tam mum CLOSE ile tetiklenir ve sonraki
1m OPEN fiyatına varsayımsal fill alır.

| Tek-sanal-pozisyon hesap | Sabit TP | Hibrit + sabit TP |
|---|---:|---:|
| Araştırma READY | 32 | 32 |
| Açılabilen farazi LONG | 18 | 18 |
| TP ile çıkış | 13 | 11 |
| Trailing next-open | 0 | 2 |
| TIMEOUT 60m | 5 | 5 |
| SL | 0 | 0 |
| LONG_TARGET açılan | 2 | 2 |
| LONG_AVOID açılan | 11 | 11 |
| UNLABELLED açılan | 5 | 5 |
| Net ROI puanı toplamı | +2,5265 | +0,7370 |

Bu puanlar gerçek sermaye getirisi, gerçekleşmiş Binance
emri veya USDT kârı DEĞİLDİR. Orijinal tarihsel broker LONG
açıkken yeni sanal LONG'a izin verilmezse sabit TP
16 açılış / +1,7565 puan ve hibrit
16 açılış / -0,0330 puan çıkıyor. Ayrı duyarlılık testidir.

## Maliyet stres testi

| İşlem başı ek ROI maliyeti | Sabit TP toplam | Hibrit toplam |
|---|---:|---:|
| 0,00 | +2,5265 | +0,7370 |
| 0,05 | +1,6265 | -0,1630 |
| 0,10 | +0,7265 | -1,0630 |
| 0,15 | -0,1735 | -1,9630 |
| 0,20 | -1,0735 | -2,8630 |

Break-even ek maliyet sabit TP için yaklaşık
0,1404 ROI puanı/işlem; hibritte yalnız 0,0409.
Bu sayılar gerçek spread veya slippage ölçümü değil,
mevcut sonucun hassasiyetini gösteren varsayımsal stres.

## Fırsatların kaçırılması ve sonraki aşama
11 LONG_TARGET olayının 7'si araştırma READY gösteriyor,
yalnız 2'si tek sanal pozisyon sıralamasında açılıyor.
15 Kasım 00:18 sinyalinin Contra proxy recovery'si
yaklaşık 00:28 TRT civarına kaydı. O anda önceki
native 1m PENDING'in sürmesi veya yeni niyet doğması
kanıtlanmadı; gelecekteki toparlanmadan geriye giriş
yetkisi çıkarılmamalı.

Gerçek yeni intent kimliği, full 3m/5m context,
aynı zamandaki partial 1m Entry ve Sniper,
merkezi risk kontrolü ve broker dolum/maliyetleri
ortak trace'e bağlanmadan production threshold veya
kâr kilidi değiştirilemez. Çakışmalar NO_TRADE.

## Yeniden üretim
- research/trace/replay_long1_stage13_joined_asof_103_v1.py
- research/trace/test_long1_stage13_joined_asof_v1.py
- LONG1_STAGE13_103_JOINED_RECOVERY_ENTRY_EXIT_20261119.json

Hiç gerçek Binance ORDER, üretim Redis yazımı,
bot servisi başlatma, canlı ayar düzenleme veya
SHORT1 değişikliği yapılmadı.
