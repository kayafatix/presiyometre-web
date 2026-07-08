"""
Presiyometre Deney Raporu - HTML/PDF Web Uygulaması
"""
from flask import Flask, render_template, request, url_for
import os
import sys
import uuid
import random


def resource_path(relative_path):
    """PyInstaller ile paketlendiğinde dosya yollarını doğru çözer."""
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


app = Flask(__name__,
            template_folder=resource_path('templates'),
            static_folder=resource_path('static'))
app.config['UPLOAD_FOLDER'] = os.path.join(resource_path('static'), 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


def basinc_dagilimi(max_bar):
    """
    Deney basıncı dağılımını hesaplar.
    - ≤ 20 bar: 1'er bar artış (0, 1, 2, ..., max_bar)
    - > 20 bar: 20 kademeye sığdırılır — önce 1'er, sonra 2'şer artış
    """
    max_bar = int(max_bar)
    
    if max_bar <= 20:
        # 1'er bar artış, max_bar+1 satır
        return [i for i in range(max_bar + 1)]
    else:
        # 20 kademeye sığdır (kademe 0 dahil = 20 satır, 19 artış)
        # a adet 1-bar + b adet 2-bar = 19 adım, toplam = a + 2b = max_bar
        # a + b = 19 → a = 38 - max_bar, b = max_bar - 19
        b = max_bar - 19  # 2-bar adım sayısı
        a = 19 - b        # 1-bar adım sayısı
        
        # Eğer a < 0 ise, 3'er bar adımlar da gerekir
        if a < 0:
            # 3-bar adımlar ekle: a1 + a2 + a3 = 19, a1 + 2*a2 + 3*a3 = max_bar
            # Basit çözüm: mümkün olduğunca 2-bar, kalanı 3-bar
            basinc = [0]
            current = 0
            for step in range(19):
                remaining_steps = 19 - step - 1
                remaining_bar = max_bar - current
                if remaining_steps == 0:
                    current = max_bar
                else:
                    increment = remaining_bar / (remaining_steps + 1)
                    if increment <= 2:
                        current += int(round(increment))
                    else:
                        current += int(round(increment))
                basinc.append(current)
            basinc[-1] = max_bar  # Son değer tam olsun
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


def hesapla_hidrostatik_basinc(deney_basinci, manometre_yuk):
    """Hidrostatik Basınç = Deney Basıncı + Manometre Yüksekliği / 10"""
    return deney_basinci + manometre_yuk / 10.0


def hesapla_hacim_duzeltmesi(hidrostatik_basinc):
    """Hacim Düzeltmesi - kalibrasyon tablosundan interpolasyon"""
    return round(interpolate(hidrostatik_basinc, HACIM_DUZ_BASINC, HACIM_DUZ_DEGER))


def hesapla_mebran_duzeltmesi(duzeltilmis_hacim):
    """Mebran Düzeltmesi - kalibrasyon tablosundan interpolasyon (Hacim→Basınç)"""
    return interpolate(duzeltilmis_hacim, MEBRAN_HACIM, MEBRAN_BASINC)


def hacim_olcer_verisi(kademe_sayisi, sifir_vol):
    """
    Hacim ölçer okuması - presiyometre S-eğrisi şeklinde veri üretir.
    3 fazlı: 
      Faz 1 (kademe 0 → 3): Dik yükseliş (ilk temas - hacmin ~60%'ı)
      Faz 2 (kademe 3 → n-2): Yavaş lineer artış (psödo-elastik bölge, ~25%)
      Faz 3 (kademe n-2 → n): Hızlı artış (plastik bölge, ~15%)
    """
    sifir_vol = int(sifir_vol)
    if kademe_sayisi <= 1:
        return [0]
    
    n = kademe_sayisi - 1
    idx_pi = min(3, n)       # Pi noktası (faz 1 sonu)
    idx_pf = max(n - 1, idx_pi + 1)  # Pf noktası (faz 2 sonu)
    
    # Faz dağılımları
    vol_faz1 = sifir_vol * 0.60   # İlk fazda toplam hacmin %60'ına ulaş
    vol_faz2 = sifir_vol * 0.85   # İkinci faz sonunda %85
    vol_faz3 = sifir_vol           # Son faz sonunda %100
    
    values = [0]
    
    # Faz 1: Dik yükseliş (0 → idx_pi)
    for i in range(1, idx_pi + 1):
        ratio = i / idx_pi
        # Hızlı başlayıp yavaşlayan eğri
        val = int(vol_faz1 * (1 - (1 - ratio) ** 2))
        noise = random.randint(-5, 5)
        val = max(values[-1] + 10, val + noise)
        values.append(min(val, int(vol_faz1)))
    
    # Faz 2: Yavaş lineer artış (idx_pi → idx_pf)
    faz2_steps = idx_pf - idx_pi
    if faz2_steps > 0:
        faz2_start = values[-1]
        faz2_range = vol_faz2 - faz2_start
        for i in range(1, faz2_steps + 1):
            ratio = i / faz2_steps
            val = int(faz2_start + faz2_range * ratio)
            noise = random.randint(-3, 3)
            val = max(values[-1] + 2, val + noise)
            values.append(min(val, int(vol_faz2)))
    
    # Faz 3: Hızlı artış (idx_pf → n)
    faz3_steps = n - idx_pf
    if faz3_steps > 0:
        faz3_start = values[-1]
        faz3_range = vol_faz3 - faz3_start
        for i in range(1, faz3_steps + 1):
            ratio = i / faz3_steps
            # Hızlanan eğri
            val = int(faz3_start + faz3_range * (ratio ** 0.5))
            val = max(values[-1] + 5, val)
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
            hacim_listesi = hacim_olcer_verisi(kademe_sayisi, sifir_vol)
            
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
            
            # ===== BELİRLENEN DEĞERLER HESAPLA =====
            n = kademe_sayisi - 1  # son kademe indeksi
            
            # Limit Basınç = son kademenin Düzeltilmiş Basıncı
            limit_basinc = float(rapor_data['tablo'][n]['duz_basinc'])
            
            # Pi, Vi = Kademe 3 (elastik bölge başlangıcı)
            idx_i = min(3, n)
            pi = float(rapor_data['tablo'][idx_i]['duz_basinc'])
            vi = rapor_data['tablo'][idx_i]['duz_hacim']
            
            # Pf, Vf = Sondan 2. kademe (elastik bölge sonu)
            idx_f = max(n - 1, idx_i + 1)
            pf = float(rapor_data['tablo'][idx_f]['duz_basinc'])
            vf = rapor_data['tablo'][idx_f]['duz_hacim']
            
            # Hesaplamalar
            delta_p = pf - pi
            delta_v = vf - vi
            vm = (vi + vf) / 2.0
            v0 = sifir_vol
            
            # Elastisite Modülü: EM = 2.66 × (V₀ + Vm) × ΔP / ΔV
            if delta_v != 0:
                em = 2.66 * (v0 + vm) * delta_p / delta_v
            else:
                em = 0
            
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
            
            raporlar.append(rapor_data)

    return render_template('rapor.html',
                           raporlar=raporlar,
                           toplam=len(raporlar),
                           mode=os.environ.get('DEPLOY_MODE', 'desktop'),
                           firma_adi=firma_adi,
                           logo_url=logo_url,
                           footer=footer)


if __name__ == '__main__':
    import webbrowser
    import threading

    print("=" * 50)
    print("  Presiyometre Deney Raporu Uygulaması")
    print("  http://localhost:5000")
    print("=" * 50)

    # Exe olarak çalıştırıldığında tarayıcıyı otomatik aç
    if getattr(sys, 'frozen', False):
        threading.Timer(1.5, lambda: webbrowser.open('http://localhost:5000')).start()

    app.run(debug=False, port=5000)
