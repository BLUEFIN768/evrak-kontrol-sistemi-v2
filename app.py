import streamlit as st
import io
import os
from datetime import datetime
from crew_core import Evidence, evaluate
from ai_extract import process_document, parse_uab_pdf_local
from fillers import fill_excel, fill_word

st.set_page_config(page_title="SeaReady Compliance", layout="wide", page_icon="⚓")

# Gizlilik ve Şifre Kontrolü
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if not st.session_state["password_correct"]:
        st.markdown("### ⚓ Evrak Kontrol Portalı'na Giriş Yapın")
        pwd = st.text_input("Sistem Parolası:", type="password")
        if st.button("Giriş"):
            if pwd == st.secrets.get("APP_PASSWORD", "admin123"):
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("Hatalı parola!")
        return False
    return True

if not check_password():
    st.stop()

# Üst Başlık (Dashboard Stili)
col_title, col_user = st.columns([4, 1])
with col_title:
    st.title("⚓ Evrak Kontrol Portalı v2")
with col_user:
    st.markdown("<br>👤 **Kullanıcı:** Admin", unsafe_allow_html=True)
st.markdown("---")

tab1, tab2, tab3, tab4 = st.tabs(["📋 1. Personel", "📁 2. Evrak Yükle", "⚙️ 3. Kontrol (Dashboard)", "📥 4. Çıktı Al"])

if "evidences" not in st.session_state:
    st.session_state.evidences = []
if "results" not in st.session_state:
    st.session_state.results = []
if "uab_loaded" not in st.session_state:
    st.session_state.uab_loaded = False

# --- SEKME 1: PERSONEL BİLGİLERİ ---
with tab1:
    st.subheader("Personel Kimlik & Atama Bilgileri")
    col1, col2 = st.columns(2)
    with col1:
        p_name = st.text_input("Ad Soyad", value="")
        p_tckn = st.text_input("TCKN", value="")
        p_cuzdan = st.text_input("Cüzdan No", value="")
    with col2:
        p_rank = st.selectbox(
            "Rütbe / Görev",
            ["Master", "Chief Officer", "2nd Officer", "3rd Officer", "Chief Engineer", "2nd Engineer", "Able Seafarer Engine", "Able Seaman", "Oiler"]
        )
        p_vessel = st.text_input("Gemi Adı", value="")
        is_tanker = st.checkbox("Gemi Tanker mi?", value=False)
        operator_name = st.text_input("Operatör Adı (İmza için)", value="")

# --- SEKME 2: EVRAK YÜKLEME ---
with tab2:
    st.subheader("UAB Doğrulama & Harici Evraklar")
    
    col_uab, col_ext = st.columns(2)
    
    with col_uab:
        st.markdown("#### 1. UAB Doğrulama Çıktısı (Türk Personel)")
        st.info("UAB VERIFY belgesini yükleyin. STCW ve Yeterlikleri otomatik doğrular.")
        uab_file = st.file_uploader("UAB Belgesi (PDF)", type=["pdf"], key="uab_uploader")
        if uab_file and st.button("UAB Oku ve Aktar", use_container_width=True):
            with st.spinner("UAB Belgesi yerel olarak çözümleniyor..."):
                uab_evidences = parse_uab_pdf_local(uab_file.getvalue())
                if uab_evidences:
                    st.session_state.evidences.extend(uab_evidences)
                    st.session_state.uab_loaded = True
                    st.success(f"✅ {len(uab_evidences)} adet belge UAB'den başarıyla çıkarıldı.")
                else:
                    st.error("UAB Belgesi okunamadı.")
                    
    with col_ext:
        st.markdown("#### 2. Harici Evraklar (Yabancı / Diğer)")
        st.info("Pasaport, Sağlık Raporu, Sarıhumma vb. UAB harici belgeleri yükleyin.")
        uploaded_files = st.file_uploader(
            "Harici Evrak Yükle", 
            type=["jpg", "png", "jpeg", "pdf"],
            accept_multiple_files=True,
            key="main_uploader"
        )
        if uploaded_files and st.button("Harici Evrakları Aktar", use_container_width=True):
            count = 0
            for up_file in uploaded_files:
                file_bytes = up_file.getvalue()
                mime_type = up_file.type or "application/pdf"
                ev = process_document(
                    data=file_bytes, mime=mime_type, provider_name="local", api_key="", model_name="", filename=up_file.name
                )
                if not any(e.code == ev.code and e.verified for e in st.session_state.evidences):
                    st.session_state.evidences.append(ev)
                    count += 1
            st.success(f"✅ {count} adet harici evrak anında sisteme aktarıldı.")

# --- SEKME 3: KONTROL VE ONAY (SeaReady Dashboard Style) ---
with tab3:
    st.subheader("Evrak Kontrol & Onay Paneli")
    
    total_docs = len(st.session_state.evidences)
    verified_docs = sum(1 for e in st.session_state.evidences if e.verified)
    pending_docs = total_docs - verified_docs
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric(label="📄 Toplam Evrak", value=total_docs)
    m2.metric(label="✅ Doğrulanan", value=verified_docs)
    m3.metric(label="⚠️ Bekleyen Onay", value=pending_docs)
    
    if st.session_state.uab_loaded:
        m4.metric(label="🇹🇷 UAB Entegrasyonu", value="Aktif")
    else:
        m4.metric(label="🌐 Yabancı / Manuel", value="Aktif")

    st.markdown("---")
    
    if not st.session_state.evidences:
        st.info("Henüz yüklenmiş evrak bulunmuyor. Lütfen 2. sekmeden dosyaları aktarın.")
    else:
        st.markdown("#### Yüklenen Belgeler")
        for i, ev in enumerate(st.session_state.evidences):
            col_icon, col_info, col_btn = st.columns([1, 6, 2])
            with col_icon:
                st.markdown(f"## {'✅' if ev.verified else '⚠️'}")
            with col_info:
                exp = ev.expiry_date.strftime("%d.%m.%Y") if ev.expiry_date else "Süresiz"
                st.markdown(f"**{ev.code}**")
                st.markdown(f"Belge No: `{ev.document_no}` | Bitiş: {exp}")
            with col_btn:
                if not ev.verified:
                    if st.button("Orijinali Onayla", key=f"verify_{i}", use_container_width=True):
                        st.session_state.evidences[i].verified = True
                        st.rerun()
                else:
                    st.button("Onaylandı", key=f"verified_{i}", disabled=True, use_container_width=True)
            st.markdown("---")
            
    if st.button(f"🚀 Kuralları İşlet ve Değerlendir ({p_rank})", type="primary", use_container_width=True):
        excel_template_path = "templates/35-101.xlsx" if os.path.exists("templates/35-101.xlsx") else "35-101.xlsx"
        if not os.path.exists(excel_template_path):
            st.error(f"Hata: Kural kaynağı {excel_template_path} bulunamadı!")
        else:
            try:
                st.session_state.results = evaluate(
                    evidences=st.session_state.evidences, 
                    rank=p_rank, 
                    excel_path=excel_template_path, 
                    is_tanker=is_tanker
                )
                st.success(f"{p_rank} için kurallar başarıyla işletildi. '4. Çıktı Al' sekmesine geçebilirsiniz.")
                
                st.markdown("#### Matris Uygunluk Sonuçları")
                for r in st.session_state.results:
                    if r.status == "OK":
                        st.success(f"**{r.code}**: {r.message}")
                    elif r.status in ["REVIEW", "EXPIRED", "MISSING"]:
                        st.error(f"**{r.code}**: {r.message} ({r.status})")
            except Exception as e:
                st.error(f"Değerlendirme sırasında hata oluştu: {str(e)}")

# --- SEKME 4: ÇIKTI AL ---
with tab4:
    st.subheader("Evrak Raporlarını İndir")
    st.write("Doldurulmuş resmi formları (35-101 & 35-102) diske yazmadan güvenle indirebilirsiniz.")
    
    personel_info = {
        "name": p_name or "Personel", 
        "rank": p_rank, 
        "vessel": p_vessel or "Belirtilmedi", 
        "date": datetime.now().strftime("%d.%m.%Y")
    }
    
    if st.button("Excel ve Word Dosyalarını Hazırla", type="primary"):
        if not st.session_state.results:
            st.warning("Önce 'Kontrol' sekmesinden kuralları işletmeniz gerekiyor.")
        else:
            excel_template = "templates/35-101.xlsx" if os.path.exists("templates/35-101.xlsx") else "35-101.xlsx"
            word_template = "templates/35-102.docx" if os.path.exists("templates/35-102.docx") else "35-102.docx"
            
            if not os.path.exists(excel_template) or not os.path.exists(word_template):
                st.error("Hata: Şablon klasöründe 35-101.xlsx veya 35-102.docx bulunamadı!")
            else:
                try:
                    excel_io = io.BytesIO()
                    word_io = io.BytesIO()
                    
                    fill_excel(excel_template, excel_io, st.session_state.results, personel_info)
                    fill_word(word_template, word_io, st.session_state.results, personel_info, operator_name or "Yetkili")
                    
                    st.success("🎉 Tüm raporlar başarıyla üretildi!")
                    
                    col_dl1, col_dl2 = st.columns(2)
                    with col_dl1:
                        st.download_button("📥 35-101 İndir (Excel Matris)", data=excel_io.getvalue(), file_name=f"35-101_{personel_info['name']}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
                    with col_dl2:
                        st.download_button("📥 35-102 İndir (Word Rapor)", data=word_io.getvalue(), file_name=f"35-102_{personel_info['name']}.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", use_container_width=True)
                
                except Exception as e:
                    st.error(f"Dosya oluşturulurken hata: {str(e)}")
