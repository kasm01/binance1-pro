# LONG1 gerçek MODEL olayları — kaynak zinciri ve kapı kanıtı

24 Kasım 2026 denetimi. NEARUSDT LONG1. Arşivdeki
MODEL verisi 11–15 Kasım'a ait. Gerçek emir YOK.

## 103 MODEL olayının Stage13 araştırma kararları

| Karar | Adet |
|---|---:|
| CONTRA_WAIT_30M | 29 |
| ENTRY_PENDING_EXPIRED | 40 |
| RESEARCH_READY_NO_REAL_INTENT | 32 |
| MODEL_GATE | 1 |
| CONFLICT_ORIGIN | 1 |
| TOPLAM | 103 |

Bunlar gerçek arşiv MODEL olaylarıdır; Stage13 kararları
research-only as-of 3m/5m/1m proxy'dir, canlı ENTRY
ve Risk Master yetkisi değildir. 32 research READY =
32 gerçek OPEN değildir. Hiçbir READY'de güncel tam
MODEL→SIGNAL→CANDIDATE→Intent parent kimliği,
kısmi 1m ENTRY, Whale ve gerçek fill doğrulanmadı.

## LONG_AVOID kohortu — 70 arşiv MODEL olayı

| Karar | Adet |
|---|---:|
| CONTRA_WAIT_30M | 28 |
| ENTRY_PENDING_EXPIRED | 23 |
| MODEL_GATE | 1 |
| RESEARCH_READY_NO_REAL_INTENT | 18 |
| TOPLAM | 70 |

LONG_TARGET 11 MODEL: 4 ENTRY_PENDING_EXPIRED,
7 RESEARCH_READY_NO_REAL_INTENT.
UNLABELLED 21 MODEL: 1 CONTRA_WAIT_30M,
13 ENTRY_PENDING_EXPIRED, 7 RESEARCH_READY_NO_REAL_INTENT.
Çakışma: 1 CONFLICT_ORIGIN.
LONG_WANTED/LONG_AVOID geçmiş kullanıcı etiketleri
raporlama içindir, canlı tarih/saat izin listesi olamaz.

## Tarihsel parent zinciri durumu

Önceki Stage17 saklanan Redis kayıtlarında 2473 signal,
894 candidate, 285 LONG trade-intent vardı. Tam kaynak
aday stream ID ile doğrulanmış intent sayısı 0;
285 intent NOT_PROVEN. Bu eski intentlerin gerçek
olmadığı anlamına GELMEZ. Yeni kaynak kimliği alanları
eski kayıtlarda eksik olabilir. Zaman, fiyat ve skor
benzerliği gerçek parent bağı yerine kullanılmadı.

Bugün Stage18 ileriye dönük salt-okunur sorgusu:
0 yeni Intent, cursor değişmedi, eski kayıtları tekrar
indirmedi. Redis XADD/SET, Binance API ve gerçek emir yok.
Servisler kapalı kalıyor; yeni MODEL oluşmuş gibi
gösterilmiyor.

## 84 sentetik AVOID işlemin nedenini yorumlama

Sabit brüt %0,35 TP modelinde kaybeden 48 sentetik
işlemden 2'sinin aynı dakikasında gerçek MODEL olayı
gözlenmiş. İki Stage13 research kararı da
CONTRA_WAIT_30M. Bu onları gerçek emir yapmaz.
Diğer 46 kayıp sentetik girişin aynı dakikasında
arşiv MODEL bulunmuyor; bu bütün gerçek piyasa
model çıktılarının eksiksiz arşivlendiği anlamına
gelmediğinden "asla MODEL yoktu" iddiası değildir.

Entry Confirmation canlı code body ve retrace
hesabı partial-1m'de yapılır. Kapanmış 1m araştırma
filtresiyle aynı değildir. Live OPEN izleri olmadan
Entry Confirmation'u suçlayamayız.

## Güvenlik kararı — üretim NO-GO

Model Score Gate eşiğini rastgele yükseltme veya
Contra/PENDING gevşetme yok. Önce gerçek model_id,
signal stream ID, candidate stream ID, Intent ID ve
kapanmış 3m/5m as-of Market Context kaynaklarının
canlı zincirde tutarlı taşındığını kanıtla.
Entry Confirmation kısmi mum READY/PENDING ve
Risk Master/broker flat/final safety kanıtları olmadan
OPEN olamaz. LONG1/SHORT1 güvenliği korunur,
LONG2–4/SHORT2–4 çoğaltılmayacak.
Yeni gerçek event yalnız servisler bilinçli biçimde
başlatılınca beklenebilir; kendiliğinden açma yok.

## Kod ve test

research/trace/audit_long1_103_model_gate_evidence_matrix_v1.py
research/trace/test_long1_103_model_gate_evidence_matrix_v1.py
research/results/LONG1_103_REAL_MODEL_GATE_EVIDENCE_MATRIX_20261124.json
