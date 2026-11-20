"""Summarize fixed as-of strong-bull extension and false-positive side-effects."""
from pathlib import Path
from collections import Counter
import json
R=Path(__file__).resolve().parents[2];OUT=R/'research/results'
x=json.loads((OUT/'LONG1_WANTED_BULL_CONTEXT_EXTENSION_TEST_20261120.json').read_text())
d=x['development'];h=x['nov16_holdout']
extra=[r for r in d['all_candidates'] if r['source']=='BULL_CONTEXT_EXTRA']
cohorts={tag:[z for z in extra if z['cohort']==tag] for tag in ('LONG_WANTED','LONG_AVOID','UNLABELLED')}
stat={}
for k,v in cohorts.items():
 stat[k]={'additional_closed_1m_candidates':len(v),
 '5m_mfe_arm_022_seen':sum(z['arm022_after_entry'] for z in v),
 '5m_end_net_positive':sum(z['end_5m_net_roi_pp']>0 for z in v),
 'sum_5m_exit_roi_pp_all_candidates':round(sum(z['end_5m_net_roi_pp'] for z in v),6)}
x['development_extra_by_reference']=stat
x['no_go_reason']='Avoid cohort changes (+4 independent entries); Nov16 net ROI worse'
out=OUT/'LONG1_WANTED_BULL_CONTEXT_EXTENSION_TEST_20261120.json'
out.write_text(json.dumps(x,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
lines=[
 '# LONG1 — 651 yeşil mum yerine gerçek açılabilir aday araştırması',
 '',
 '20 Kasım 2026; 11–15 Kasım geliştirme ve kuralları hiç değiştirilmeden',
 '16 Kasım holdout. NEARUSDT Binance Futures. İŞLEM AÇMA YETKİSİ YOK.',
 '',
 '## Önce 651 sayısının anlamı',
 '',
 '651: LONG_WANTED etiketli pencerelerde OPEN→CLOSE hareketi',
 '3x kaldıraçla brüt en az %0,22 ROI olan yeşil **1m mum** sayısı.',
 '651 adet gerçek pozisyon, yeni MODEL/Intent ya da aynı coin',
 'tek pozisyon kuralıyla uyumlu 651 fırsat değildir. Bir mumun',
 'kapanışı bilindiğinde o mumun açılışından pozisyon almış',
 'olmak lookahead olur. Önceki taramada çakışan etiketlere ait',
 'mumlar ayrıca hesaba dahil edilebiliyordu.',
 '',
 '## Kademeli as-of profiller',
 '',
 'STRICT: kapanmış yeşil 1m brüt +%0,22; body>=0,22,',
 'retrace<=0,35, flow1>=0,03, 3m akış>0, 3m return>0,',
 'flow3 iyileşme>=0,08, return3 iyileşme>=0,10 yüzde',
 'puan, geçmiş 5 tamamlanmış 1m return>0.',
 '',
 'BULL_CONTEXT_EXTRA (sadece as-of güçlü yükseliş koşuluyla):',
 'geçmiş 5x1m return>=+%0,20, 3x1m return>=+%0,12;',
 'gövde>=0,18, retrace<=0,45, flow1>=0,01,',
 'flow3 iyileşme>=0,05, return3 iyileşme>=0,08;',
 '3m return ve flow yine pozitif. Hiçbir karar kuralı',
 'geçmiş LONG_WANTED/LONG_AVOID saat etiketini kullanmaz.',
 'Her aday kapanmış 1m sonrasında sonraki 1m OPEN ile',
 'sanal giriş, 5m sonu CLOSE ile sanal çıkıştır.',
 'Aynı coin en az 5m tek-pozisyon süreli kronolojik tarama.',
 'Retrospektif iki etiket çakışırsa araştırma NO_TRADE.',
 '',
 '## İstenen AVOID değişmezliği testi',
 '',
 '| Metrik | STRICT | STRICT + BULL_CONTEXT_EXTRA |',
 '|---|---:|---:|',
 f"| Geliştirme: sanal giriş | {d['book_strict']['entries']} | {d['book_strict_plus_bull_extra']['entries']} |",
 f"| Geliştirme: LONG_WANTED giriş | {d['book_strict']['cohorts'].get('LONG_WANTED',0)} | {d['book_strict_plus_bull_extra']['cohorts'].get('LONG_WANTED',0)} |",
 f"| **Geliştirme: LONG_AVOID giriş** | **{d['book_strict']['cohorts'].get('LONG_AVOID',0)}** | **{d['book_strict_plus_bull_extra']['cohorts'].get('LONG_AVOID',0)}** |",
 f"| Geliştirme 5m net toplam ROI puanı | {d['book_strict']['sum_net_roi_pp_at_5m_close']} | {d['book_strict_plus_bull_extra']['sum_net_roi_pp_at_5m_close']} |",
 f"| 16 Kasım holdout giriş | {h['book_strict']['entries']} | {h['book_strict_plus_bull_extra']['entries']} |",
 f"| **16 Kasım holdout toplam net ROI puanı** | **{h['book_strict']['sum_net_roi_pp_at_5m_close']}** | **{h['book_strict_plus_bull_extra']['sum_net_roi_pp_at_5m_close']}** |",
 '',
 'LONG_WANTED giriş sayısı +8 artsa da LONG_AVOID +4 artıyor;',
 'dolayısıyla kullanıcının AVOID oranları değişmeden kalması',
 'şartı bu profil için **SAĞLANMADI**. 16 Kasım bağımsız',
 'tarihte net sonuç da daha kötü. Bu profil PRODUCTION NO-GO.',
 '',
 'Geliştirme döneminde yalnız ek araştırma adayları:',
 '',
 '| Etiket (yalnız raporlama) | Ek kapalı mum aday | Sonraki 5m +%0,22 tepe | 5m sonu net pozitif |',
 '|---|---:|---:|---:|',
 ]
for k in ('LONG_WANTED','LONG_AVOID','UNLABELLED'):
 z=stat[k]
 lines.append(f"| {k} | {z['additional_closed_1m_candidates']} | {z['5m_mfe_arm_022_seen']} | {z['5m_end_net_positive']} |")
lines+=['',
 '## Yorum ve sonraki adım',
 '',
 'Güçlü geçmiş yükseliş bağlamı hem hedef hem de',
 'istenmeyen dönemlerde bulunabilir. Bu nedenle',
 'geriye dönük etiketlere göre iki ayrı canlı parametre',
 'profili seçmek piyasa koşulunu değil tarih bilgisini',
 'öğretir; overfit ve ileriye bakış sorunu oluşturur.',
 'İstenen AVOID değişmezliği, canlı parametre gevşetmesi',
 'ile bu çalışmada korunamadı. Orijinal canlı eşikler',
 've LONG_AVOID değerlendirmesi hiç değiştirilmedi.',
 'Geçmişte sadece LONG_WANTED etiketine izin veren',
 'oracle karşılaştırması ayrı yapılabilir; bu hiçbir',
 'şekilde canlı işlem kuralı olamaz.',
 '',
 'Gerçek MODEL→SIGNAL→CANDIDATE→INTENT bağlantısı',
 'kanıtlanmadan veya 1m Sniper/Entry, gerçek 5m',
 'Market Context, Whale ve ortak Risk Master olmadan',
 'bu sanal girişler üretim pozisyonuna dönüştürülemez.',
 '5m sonunda sabit sanal çıkış, gerçek ARM/TP kısmi',
 'dolumlarını yeniden üretmez; fee -0,24 ROI puanı,',
 'spread/slippage/funding ve gerçek stop ayrıca eksik.',
 '',
 'En güvenli sonraki yön: LONG_AVOID sonuçları',
 'değişmeyen, ileri tarih testinde de iyileşme',
 'gösteren ve yeni gerçek MODEL/Intent üreten',
 'ayrı, fail-closed research sinyal adayı. İzin',
 'vermeden üretim eşikleri değişmemeli.',
 '',
 'Kaynaklar:',
 '- research/trace/replay_long1_wanted_targeted_asof_shadow_v1.py',
 '- research/trace/report_long1_wanted_targeted_asof_shadow_v1.py',
 '- LONG1_WANTED_BULL_CONTEXT_EXTENSION_TEST_20261120.json',
 ]
(OUT/'LONG1_WANTED_BULL_CONTEXT_EXTENSION_REPORT_20261120.md').write_text('\n'.join(lines)+'\n')
print(json.dumps({'status':'PASS','extra_cohorts':stat,
 'wanted_delta':d['wanted_delta_book'],'avoid_delta':d['avoid_delta_book'],
 'holdout_worsening':h['book_strict_plus_bull_extra']['sum_net_roi_pp_at_5m_close']<h['book_strict']['sum_net_roi_pp_at_5m_close'],
 'production_authority':False},sort_keys=True))
