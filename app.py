import streamlit as st
import io
import os
import zipfile
from datetime import datetime
from crew_core import Evidence, evaluate
from ai_extract import process_document, parse_uab_pdf_local
from fillers import fill_excel, fill_word

st.set_page_config(page_title="Evrak Kontrol & Onay", layout="wide", page_icon="⚓")

st.markdown("""
<style>
    .stApp { background-color: #f1f5f9; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
    .main-title { font-size: 26px; font-weight: 700; color: #0f172a; margin-bottom: 12px; }
    .section-title { font-size: 18px; font-weight: 600; color: #1e293b; margin-bottom: 10px; }
    .verify-msg { padding: 12px; border-radius: 8px; background-color: #dcfce7; color: #166534; border: 1px solid #bbf7d0; font-weight: 500; font-size: 14px; }
    .doc-row { background-color: #f8fafc; padding: 12px 16px; border-radius: 8px; border: 1px solid #e2e8f0; margin-bottom: 8px; }
    [data-testid="stVerticalBlockBorderWrapper"] { background-color: #ffffff; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
    .stButton > button { border-radius: 8px; font-weight: 600; width: 100%; transition: all 0.2s; }
</style>
""", unsafe_allow_html=True)

def check_password():
    if "password_correct" not in st.session_state: st.session_state["password_correct"] = False
    if not st.session_state["password_correct"]:
        st.markdown("### ⚓ Evrak Kontrol Portalı")
        pwd = st.text_input("Parola:", type="password")
        if st.button("Giriş Yap"):
            if pwd == st.secrets.get("APP_PASSWORD", "admin123"):
                st.session_state["password_correct"] = True
                st.rerun()
            else: st.error("Hatalı parola!")
        return False
    return True

if not check_password(): st.stop()

if "evidences" not in st.session_state: st.session_state.evidences = []
if "results" not in st.session_state: st.session_state.results = []
if "p_name" not in st.session_state: st.session_state.p_name = ""
if "p_rank" not in st.session_state: st.session_state.p_rank = "Master"
if "p_vessel" not in st.session_state: st.session_state.p_vessel = ""
if "is_tanker" not in st.session_state: st.session_state.is_tanker = False
if "operator_name" not in st.session_state: st.session_state.operator_name = "Admin"
if "auto_tckn" not in st.session_state: st.session_state.auto_tckn = ""
if "auto_cuzdan" not in st.session_state: st.session_state.auto_cuzdan = ""
if "uab_verified" not in st.session_state: st.session_state.uab_verified = False

st.markdown("<div class='main-title'>⚓ Evrak Kontrol & Onay (Auditing)</div>", unsafe_allow_html=True)

with st.container(border=True):
    st.markdown("<div class='section-title'>Personel Kimlik & Atama</div>", unsafe_allow_html=True)
    
    col_p1, col_p2, col_p3 = st.columns([1.5, 1.5, 1], gap="medium")
    with col_p1:
        p_name = st.text_input("Ad Soyad", key="p_name_input", value=st.session_state.p_name)
        p_rank = st.selectbox("Rütbe / Görev", ["Master", "Chief Officer", "2nd Officer", "3rd Officer", "Chief Engineer", "2nd Engineer", "Able Seafarer Engine", "Able Seaman", "Oiler"], key="p_rank_input")
    with col_p2:
        p_vessel = st.text_input("Gemi Adı", key="p_vessel_input")
        operator_name = st.text_input("Operatör Adı", key="operator_name_input", value=st.session_state.operator_name)
    with col_p3:
        st.markdown("<br>", unsafe_allow_html=True)
        is_tanker = st.checkbox("Gemi Tanker mi?", key="is_tanker_input")
    
    st.markdown("---")
    
    col_v1, col_v2 = st.columns([1, 1], gap="large")
    with col_v1:
        st.markdown("**Gemi Adamı Evrak Doğrulama (UAB)**")
        uab_file = st.file_uploader("UAB PDF Belgesini Yükle", type=["pdf"], key="uab_uploader")
        if uab_file and st.button("UAB Oku ve Doğrula", type="primary", use_container_width=True):
            with st.spinner("UAB Belgesi çözümleniyor..."):
                uab_evs, ext_info = parse_uab_pdf_local(uab_file.getvalue())
                if uab_evs or ext_info["tckn"] or ext_info["cuzdan"]:
                    # Mükerrerleri filtrele
                    existing_codes = {e.code for e in st.session_state.evidences}
                    for u_ev in uab_evs:
                        if u_ev.code not in existing_codes:
                            st.session_state.evidences.append(u_ev)
                    if ext_info["tckn"]: st.session_state.auto_tckn = ext_info["tckn"]
                    if ext_info["cuzdan"]: st.session_state.auto_cuzdan = ext_info["cuzdan"]
                    if ext_info.get("name") and not st.session_state.p_name: st.session_state.p_name = ext_info["name"]
                    st.session_state.uab_verified = True
                    st.rerun()

    with col_v2:
        st.markdown("**Gemi Adamı Kimlik Teyidi**")
        if st.session_state.uab_verified:
            st.markdown("""
            <div class='verify-msg'>
                ✅ <b>Doğrulama Başarılı!</b><br>
                Aşağıdaki kimlik bilgileri ile resmi sistemden teyit ediniz:
            </div>
            """, unsafe_allow_html=True)
            
            c_copy1, c_copy2 = st.columns(2)
            with c_copy1:
                st.code(st.session_state.auto_tckn, language="text")
                st.caption("TCKN")
            with c_copy2:
                st.code(st.session_state.auto_cuzdan, language="text")
                st.caption("Cüzdan No")
            
            st.link_button("🌐 UAB Sisteminde Teyit Et (gemiadami.uab.gov.tr)", "https://gemiadami.uab.gov.tr/verification", use_container_width=True)
        else:
            st.warning("⚠️ Lütfen işleme başlamadan önce sol kısımdan UAB belgesini okutup personeli doğrulayın.")

st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

# UAB DOĞRULANMADAN ALT KISIM GÖRÜNMEZ
if st.session_state.uab_verified:
    col_left, col_right = st.columns([6, 4], gap="medium")

    with col_left:
        with st.container(border=True):
            st.markdown("<div class='section-title'>Evrak Doğrulama Listesi</div>", unsafe_allow_html=True)
            st.markdown("**Harici Evrak Yükleme** (Pasaport, Sağlık, STCW vb.)")
            ext_files = st.file_uploader("Harici Evrakları Seç veya Sürükle", accept_multiple_files=True, key="ext_uploader")
            
            # Otomatik İşleme: Dosya kutuya atıldığı an sisteme eklenir
            if ext_files:
                for f in ext_files:
                    ev_list = process_document(f.getvalue(), f.type or "application/pdf", "local", "", "", f.name)
                    for single_ev in ev_list:
                        existing_idx = next((idx for idx, e in enumerate(st.session_state.evidences) if e.code == single_ev.code), None)
                        if existing_idx is not None:
                            # Eğer yeni evrak daha güncel/doğrulanmışsa güncelle
                            if single_ev.verified:
                                st.session_state.evidences[existing_idx] = single_ev
                        else:
                            st.session_state.evidences.append(single_ev)

            st.markdown("---")
            if not st.session_state.evidences:
                st.info("Henüz sisteme evrak aktarılmadı.")
            else:
                for i, ev in enumerate(st.session_state.evidences):
                    with st.container():
                        st.markdown("<div class='doc-row'>", unsafe_allow_html=True)
                        c_icon, c_info, c_btn1, c_btn2 = st.columns([1, 6, 2, 2])
                        with c_icon: st.markdown(f"### {'✅' if ev.verified else '📄'}")
                        with c_info:
                            iss_str = ev.issue_date.strftime("%d.%m.%Y") if ev.issue_date else "Belirtilmedi"
                            exp_str = ev.expiry_date.strftime("%d.%m.%Y") if ev.expiry_date else "Süresiz"
                            st.markdown(f"**{ev.code}**<br><small>No: {ev.document_no} | Alınış: {iss_str} | Bitiş: {exp_str}</small>", unsafe_allow_html=True)
                        with c_btn1:
                            if not ev.verified:
                                if st.button("Onayla", key=f"ok_{i}"):
                                    st.session_state.evidences[i].verified = True
                                    st.rerun()
                            else:
                                st.button("Onaylandı", key=f"ok_{i}", disabled=True)
                        with c_btn2:
                            if st.button("Sil", key=f"del_{i}"):
                                st.session_state.evidences.pop(i)
                                st.rerun()
                        st.markdown("</div>", unsafe_allow_html=True)

    with col_right:
        with st.container(border=True):
            st.markdown(f"<div class='section-title'>35-101 Matris Uygunluğu ({p_rank})</div>", unsafe_allow_html=True)
            excel_template_path = "templates/35-101.xlsx" if os.path.exists("templates/35-101.xlsx") else "35-101.xlsx"
            
            if os.path.exists(excel_template_path):
                st.session_state.results = evaluate(st.session_state.evidences, p_rank, excel_template_path, is_tanker)
                if st.session_state.results:
                    for r in st.session_state.results:
                        if r.status == "OK":
                            icon = "✅"
                            color = "#16a34a"
                            hint = "Geçerli"
                        elif r.status == "REVIEW":
                            icon = "🟡"
                            color = "#eab308"
                            hint = "Onay Bekliyor"
                        elif r.status == "EXPIRED":
                            icon = "⏰"
                            color = "#dc2626"
                            hint = "Süresi Dolmuş"
                        else:
                            icon = "❌"
                            color = "#dc2626"
                            hint = "Eksik"

                        st.markdown(f"""
                        <div style='display:flex; justify-content:space-between; align-items:center; border-bottom:1px solid #f1f5f9; padding:6px 0;'>
                            <span style='font-size:13px; font-weight:500; color:#334155;'>{r.code}</span>
                            <span><small style='color:{color}; font-size:11px; margin-right:6px;'>{hint}</small><span style='color:{color}; font-weight:bold; font-size:15px;'>{icon}</span></span>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    personel_info = {"name": p_name or "Personel", "rank": p_rank, "vessel": p_vessel or "Belirtilmedi", "date": datetime.now().strftime("%d.%m.%Y")}
                    try:
                        import tempfile
                        word_template = "templates/35-102.docx" if os.path.exists("templates/35-102.docx") else "35-102.docx"
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp_excel:
                            fill_excel(excel_template_path, tmp_excel.name, st.session_state.results, personel_info)
                            excel_path = tmp_excel.name
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp_word:
                            fill_word(word_template, tmp_word.name, st.session_state.results, personel_info, operator_name)
                            word_path = tmp_word.name
                        zip_buffer = io.BytesIO()
                        with zipfile.ZipFile(zip_buffer, "w") as zip_file:
                            zip_file.write(excel_path, f"35-101_{personel_info['name']}.xlsx")
                            zip_file.write(word_path, f"35-102_{personel_info['name']}.docx")
                        st.markdown("<br>", unsafe_allow_html=True)
                        st.download_button("📥 Word/Excel Raporu Üret (.ZIP)", data=zip_buffer.getvalue(), file_name=f"Evrak_Kontrol_{personel_info['name']}.zip", mime="application/zip", use_container_width=True, type="primary")
                    except Exception as e:
                        st.error(f"Dosya oluşturulurken hata: {str(e)}")
                else:
                    st.info("Kurallar matriste bulunamadı veya henüz evrak eklenmedi.")
            else:
                st.error("35-101.xlsx şablonu bulunamadı!")
