"""
Presiyometre Deney Raporu - Web Versiyonu (Render.com)
"""
from flask import Flask, render_template, request, url_for
import os
import uuid
import random


app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


def basinc_dagilimi(max_bar):
    """
    Deney basıncı dağılımını hesaplar.
    - ≤ 20 bar: 1'er bar artış (0, 1, 2, ..., max_bar) → max 21 satır
    - > 20 bar: Her zaman 21 satır (20 kademe). Önce 1'er, sonda 2'şer artış.
      Örnek: 22 bar → 0,1,...,18,20,22  |  25 bar → 0,1,...,15,17,19,21,23,25
    """
    max_bar = int(max_bar)
    
    if max_bar <= 20:
        # 1'er bar artış, max_bar+1 satır
        return [i for i in range(max_bar + 1)]
    else:
        # Her zaman 21 satır (kademe 0 dahil = 21 satır, 20 adım)
        # a adet 1-bar + b adet 2-bar = 20 adım, toplam = a + 2b = max_bar
        # a + b = 20 → a = 40 - max_bar, b = max_bar - 20
        b = max_bar - 20  # 2-bar adım sayısı
        a = 20 - b        # 1-bar adım sayısı
        
        if a < 0:
            # Çok yüksek bar değerleri: orantılı dağılım
            basinc = [0]
            current = 0
            for step in range(20):
                remaining_steps = 20 - step - 1
                remaining_bar = max_bar - current
                if remaining_steps == 0:
                    current = max_bar
                else:
                    current += int(round(remaining_bar / (remaining_steps + 1)))
                basinc.append(current)
            basinc[-1] = max_bar
            return basinc
        
        basinc = [0]
        current = 0
        # Önce 1'er bar adımlar
        for _ in range(a):
            current += 1
            basinc.append(current)
        # Sonra 2'şer bar adımlar
        for _ in range(b):
            current += 2
            basinc.append(current)
        
        return basinc


def interpolate(x, x_table, y_table):
    """Lineer interpolasyon yapar."""
    if x <= x_table[0]:
        return y_table[0]
    if x >= x_table[-1]:
        return y_table[-1]
    for i in range(len(x_table) - 1):
        if x_table[i] <= x <= x_table[i + 1]:
            ratio = (x - x_table[i]) / (x_table[i + 1] - x_table[i])
            return y_table[i] + ratio * (y_table[i + 1] - y_table[i])
    return y_table[-1]


# Kalibrasyon tabloları (SK.xls'den alınmış varsayılan değerler)
# Hacim Düzeltmesi: Basınç (kg/cm²) → Düzeltme (cm³)
HACIM_DUZ_BASINC = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 15, 20]
HACIM_DUZ_DEGER = [0, 1, 1, 2, 3, 4, 5, 6, 6, 7, 8, 9, 8, 7, 8, 10]

# Mebran Düzeltmesi: Hacim (cm³) → Basınç (kg/cm²)
MEBRAN_HACIM = [15, 80, 140, 200, 250, 300, 350, 400, 480, 650]
MEBRAN_BASINC = [0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25]

# BAR → Elastisite Modülü tablosu (bar: (base_value, tolerance))
ELASTISITE_TABLE = {
    5: (50, 10), 6: (60, 10), 7: (70, 10), 8: (80, 10),
    9: (90, 10), 10: (100, 10), 11: (110, 10), 12: (120, 10),
    13: (130, 10), 14: (150, 20), 15: (170, 20),
    16: (200, 30), 17: (230, 30), 18: (260, 30),
    19: (300, 40), 20: (340, 40), 21: (380, 40), 22: (420, 40), 23: (460, 40),
    24: (500, 50), 25: (550, 50), 26: (600, 50), 27: (650, 50),
    28: (700, 50), 29: (750, 50), 30: (800, 50),
}


def get_elastisite_modulu(max_bar):
    """BAR-Elastisite tablosundan Elastisite Modülü değerini döndürür."""
    max_bar = int(max_bar)
    if max_bar in ELASTISITE_TABLE:
        base, tolerance = ELASTISITE_TABLE[max_bar]
        # Tolerans aralığında rastgele değer
        return base + random.randint(-tolerance, tolerance)
    elif max_bar < 5:
        # 5 altı için en düşük değeri kullan
        base, tolerance = ELASTISITE_TABLE[5]
        return base + random.randint(-tolerance, tolerance)
    else:
        # 30 üstü için en yüksek değeri kullan
        base, tolerance = ELASTISITE_TABLE[30]
        return base + random.randint(-tolerance, tolerance)


def get_pi_pf_indices(max_bar, n):
    """
    Max bar değerine göre Pi ve Pf indekslerini belirler.
    n = son kademe indeksi (kademe_sayisi - 1)
    
    Kurallar (0 noktasından itibaren sayılır, 0 = 1. nokta):
    - 4-5-6 bar: Pi = index 2, Pf = n-1 (sondan bir önceki)
    - 7-8 bar: Pi = index 3, Pf = n-1 (sondan bir önceki)
    - 9-10-11-12 bar: Pi = index 3, Pf = n-2 (sondan 3. nokta)
    - 13-14-15-16-17 bar: Pi = index 3, Pf = n-3 (sondan 4. nokta)
    - 18-30 bar: Pi = index 3, Pf = n-5 (sondan 6. nokta)
    """
    max_bar = int(max_bar)
    
    if max_bar <= 6:
        idx_i = min(2, n)
        idx_f = n - 1
    elif max_bar <= 8:
        idx_i = min(3, n)
        idx_f = n - 1
    elif max_bar <= 12:
        idx_i = min(3, n)
        idx_f = n - 2
    elif max_bar <= 17:
        idx_i = min(3, n)
        idx_f = n - 3
    else:  # 18-30
        idx_i = min(3, n)
        # Pf sondan 3-5. nokta arası
        offset = random.choice([0, 0, 1, 1, 2])  # genelde sondan 3-4, bazen 5
        idx_f = n - 3 - offset
    
    # Güvenlik: idx_f en az idx_i + 1 olmalı
    idx_f = max(idx_f, idx_i + 1)
    # idx_f son noktayı geçmemeli
    idx_f = min(idx_f, n)
    
    return idx_i, idx_f


def hesapla_hidrostatik_basinc(deney_basinci, manometre_yuk):
    """Hidrostatik Basınç = Deney Basıncı + Manometre Yüksekliği / 10"""
    return deney_basinci + manometre_yuk / 10.0


def hesapla_hacim_duzeltmesi(hidrostatik_basinc):
    """Hacim Düzeltmesi - kalibrasyon tablosundan interpolasyon"""
    return round(interpolate(hidrostatik_basinc, HACIM_DUZ_BASINC, HACIM_DUZ_DEGER))


def hesapla_mebran_duzeltmesi(duzeltilmis_hacim):
    """Mebran Düzeltmesi - kalibrasyon tablosundan interpolasyon (Hacim→Basınç)"""
    return interpolate(duzeltilmis_hacim, MEBRAN_HACIM, MEBRAN_BASINC)


def hacim_olcer_verisi(kademe_sayisi, sifir_vol, max_bar=20):
    """
    Hacim ölçer okuması - presiyometre S-eğrisi şeklinde veri üretir.
    3 fazlı: 
      Faz 1 (kademe 0 → idx_pi): Dik yükseliş (ilk temas - hacmin ~60%'ı)
      Faz 2 (idx_pi → idx_pf): Yavaş lineer artış (psödo-elastik bölge, ~25%)
      Faz 3 (idx_pf → n): Hızlı artış (plastik bölge, ~15%)
    """
    sifir_vol = int(sifir_vol)
    if kademe_sayisi <= 1:
        return [0]
    
    n = kademe_sayisi - 1
    idx_pi, idx_pf = get_pi_pf_indices(max_bar, n)
    
    # Faz dağılımları
    vol_faz1 = sifir_vol * 0.55   # İlk fazda toplam hacmin %55'ine ulaş
    faz2_toplam = random.randint(40, 75)  # Psödo-elastik bölge: max 75 cm³ artış
    vol_faz2 = vol_faz1 + faz2_toplam
    vol_faz3 = sifir_vol           # Son faz sonunda %100
    
    values = [0]
    
    # Faz 1: Dik yükseliş (0 → idx_pi)
    for i in range(1, idx_pi + 1):
        ratio = i / idx_pi
        val = int(vol_faz1 * (1 - (1 - ratio) ** 2))
        noise = random.randint(-5, 5)
        val = max(values[-1] + 10, val + noise)
        values.append(min(val, int(vol_faz1)))
    
    # Faz 2: Neredeyse yatay artış (idx_pi → idx_pf), toplam 50-100 cm³
    faz2_steps = idx_pf - idx_pi
    if faz2_steps > 0:
        faz2_start = values[-1]
        faz2_range = faz2_toplam
        for i in range(1, faz2_steps + 1):
            ratio = i / faz2_steps
            val = int(faz2_start + faz2_range * ratio)
            noise = random.randint(-2, 2)
            val = max(values[-1] + 1, val + noise)
            values.append(min(val, int(vol_faz2)))
    
    # Faz 3: Pf sonrası ivmelenen artış (sona doğru belirgin dikleşme)
    faz3_steps = n - idx_pf
    if faz3_steps > 0:
        faz3_start = values[-1]
        faz3_range = vol_faz3 - faz3_start
        for i in range(1, faz3_steps + 1):
            ratio = i / faz3_steps
            curve_val = ratio ** 1.5
            val = int(faz3_start + faz3_range * curve_val)
            val = max(values[-1] + 10, val)
            values.append(min(val, sifir_vol))
    
    # Son değer tam sifir_vol olsun
    if len(values) > 0:
        values[-1] = sifir_vol
    
    # Kademe sayısı tutarlılığı
    while len(values) < kademe_sayisi:
        values.append(sifir_vol)
    values = values[:kademe_sayisi]
    
    return values


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/rapor', methods=['POST'])
def rapor():
    # Logo yükleme
    logo_url = '/static/logo.png'  # varsayılan
    logo_file = request.files.get('logo_dosya')
    if logo_file and logo_file.filename:
        ext = os.path.splitext(logo_file.filename)[1]
        safe_name = f"logo_{uuid.uuid4().hex[:8]}{ext}"
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_name)
        logo_file.save(save_path)
        logo_url = f'/static/uploads/{safe_name}'

    # İmza yükleme (opsiyonel)
    imza_url = ''
    imza_file = request.files.get('imza_dosya')
    if imza_file and imza_file.filename:
        ext = os.path.splitext(imza_file.filename)[1]
        safe_name = f"imza_{uuid.uuid4().hex[:8]}{ext}"
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_name)
        imza_file.save(save_path)
        imza_url = f'/static/uploads/{safe_name}'

    # Firma bilgisi
    firma_adi = request.form.get('firma_adi', 'HAN İNŞAAT & MÜHENDİSLİK')

    # Footer bilgileri
    footer = {
        'sorumlu_adi': request.form.get('sorumlu_adi', ''),
        'sorumlu_unvan': request.form.get('sorumlu_unvan', ''),
        'sicil_no': request.form.get('sicil_no', ''),
        'adres': request.form.get('adres', ''),
        'iletisim': request.form.get('iletisim', ''),
    }

    # Genel bilgiler
    genel = {
        'proje_adi': request.form.get('proje_adi', ''),
        'musteri_adi': request.form.get('musteri_adi', ''),
        'proje_numarasi': request.form.get('proje_numarasi', ''),
        'sonda_capi': request.form.get('sonda_capi', '76'),
        'sifir_vol_hacim': request.form.get('sifir_vol_hacim', '535'),
        'manometre_yuksekligi': request.form.get('manometre_yuksekligi', '0.60'),
        'presiyometre_turu': request.form.get('presiyometre_turu', 'Menard GC'),
        'deney_tarih': request.form.get('deney_tarih', ''),
    }

    # Kuyu ve derinlik bilgilerini topla
    kuyu_sayisi = int(request.form.get('kuyu_sayisi', 1))
    raporlar = []

    for i in range(1, kuyu_sayisi + 1):
        kuyu_adi = request.form.get(f'kuyu_{i}_adi', f'SK-{i}')
        derinlikler_str = request.form.get(f'kuyu_{i}_derinlikler', '')
        derinlikler = [d.strip() for d in derinlikler_str.split(',') if d.strip()]

        # Derinlik arttıkça EM artmalı: her derinlik için EM önceden hesapla
        em_values = []
        for idx, derinlik in enumerate(derinlikler):
            max_basinc = int(request.form.get(f'kuyu_{i}_basinc_{idx}', 20))
            em_values.append(get_elastisite_modulu(max_basinc))
        # Aynı kuyu içinde sırala: sığdan derine artan EM
        em_values.sort()

        for idx, derinlik in enumerate(derinlikler):
            rapor_data = dict(genel)
            rapor_data['kuyu_no'] = kuyu_adi
            rapor_data['deney_derinligi'] = derinlik
            
            # Her derinlik için ayrı max basınç (yeni form yapısı)
            max_basinc = int(request.form.get(f'kuyu_{i}_basinc_{idx}', 20))
            
            # Basınç dağılımı hesapla
            basinc_listesi = basinc_dagilimi(max_basinc)
            kademe_sayisi = len(basinc_listesi)
            
            # Hacim ölçer verisi üret
            sifir_vol = int(genel.get('sifir_vol_hacim', 535))
            hacim_listesi = hacim_olcer_verisi(kademe_sayisi, sifir_vol, max_basinc)
            
            # Manometre yüksekliği
            manometre_yuk = float(genel.get('manometre_yuksekligi', 0.60))
            
            # Tablo verisi oluştur - tüm sütunları hesapla
            rapor_data['tablo'] = []
            for k in range(kademe_sayisi):
                deney_bas = basinc_listesi[k]
                hacim_okuma = hacim_listesi[k]
                
                # 1. Hidrostatik Basınç
                hidrost = hesapla_hidrostatik_basinc(deney_bas, manometre_yuk)
                
                # 2. Hacim Düzeltmesi
                hacim_duz = hesapla_hacim_duzeltmesi(hidrost)
                
                # 3. Düzeltilmiş Hacim
                duz_hacim = hacim_okuma - hacim_duz
                
                # 4. Mebran Düzeltmesi
                mebran_duz = hesapla_mebran_duzeltmesi(duz_hacim)
                
                # 5. Düzeltilmiş Basınç
                duz_basinc = hidrost - mebran_duz
                
                rapor_data['tablo'].append({
                    'kademe': k,
                    'basinc': f"{deney_bas:.2f}",
                    'hacim': hacim_okuma,
                    'hidrost': f"{hidrost:.2f}",
                    'hacim_duz': hacim_duz,
                    'duz_hacim': duz_hacim,
                    'mebran_duz': f"{mebran_duz:.2f}",
                    'duz_basinc': f"{duz_basinc:.2f}",
                })
            
            # Tablo her zaman 21 satır olsun (kademe 0-20)
            SABIT_SATIR_SAYISI = 21
            while len(rapor_data['tablo']) < SABIT_SATIR_SAYISI:
                rapor_data['tablo'].append({
                    'kademe': '',
                    'basinc': '',
                    'hacim': '',
                    'hidrost': '',
                    'hacim_duz': '',
                    'duz_hacim': '',
                    'mebran_duz': '',
                    'duz_basinc': '',
                })
            
            # ===== BELİRLENEN DEĞERLER HESAPLA =====
            n = kademe_sayisi - 1  # son kademe indeksi
            
            # Limit Basınç = son kademenin Düzeltilmiş Basıncı
            limit_basinc = float(rapor_data['tablo'][n]['duz_basinc'])
            
            # Pi, Pf indekslerini bar seviyesine göre belirle
            idx_i, idx_f = get_pi_pf_indices(max_basinc, n)
            
            pi = float(rapor_data['tablo'][idx_i]['duz_basinc'])
            vi = rapor_data['tablo'][idx_i]['duz_hacim']
            pf = float(rapor_data['tablo'][idx_f]['duz_basinc'])
            vf = rapor_data['tablo'][idx_f]['duz_hacim']
            
            # Hesaplamalar
            delta_p = pf - pi
            delta_v = vf - vi
            vm = (vi + vf) / 2.0
            v0 = sifir_vol
            
            # Elastisite Modülü: derinlik arttıkça artan sıralı değer
            em = em_values[idx]
            
            # Net Limit Basınç = PL* - Pi
            net_limit = limit_basinc - pi
            
            # E / PL = EM / Net Limit Basınç
            e_pl = em / net_limit if net_limit != 0 else 0
            
            rapor_data['sonuclar'] = {
                'limit_basinc': f"{limit_basinc:.2f}",
                'elastisite': f"{em:.2f}",
                'pi': f"{pi:.2f}",
                'vi': int(vi),
                'pf': f"{pf:.2f}",
                'vf': int(vf),
                'delta_p': f"{delta_p:.2f}",
                'delta_v': int(delta_v),
                'net_limit': f"{net_limit:.2f}",
                'e_pl': f"{e_pl:.2f}",
            }
            rapor_data['max_basinc'] = max_basinc
            
            raporlar.append(rapor_data)

    return render_template('rapor.html',
                           raporlar=raporlar,
                           toplam=len(raporlar),
                           mode='web',
                           firma_adi=firma_adi,
                           logo_url=logo_url,
                           imza_url=imza_url,
                           footer=footer)


if __name__ == '__main__':
    app.run(debug=False, port=5000)
