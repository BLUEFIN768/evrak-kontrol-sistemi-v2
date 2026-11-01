import re
import io
from typing import Optional, List
from datetime import datetime
import pdfplumber
from crew_core import Evidence

CODES = ["PASSPORT", "SEAMAN_BOOK", "MEDICAL_CERT", "YELLOW_FEVER", "BASIC_SAFETY", "GMDSS", "COMPETENCY", "CRIMINAL_RECORD"]

def parse_date(date_str: str) -> Optional[datetime]:
    if not date_str: return None
    date_str = date_str.strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%Y.%m.%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None

def detect_code_from_name(filename: str) -> str:
    name = filename.upper()
    if "PASAPORT" in name or "PASSPORT" in name or "PP" in name: return "PASSPORT"
    if "SEAMAN" in name or "CUZDAN" in name or "CÜZDAN" in name or "SB" in name: return "SEAMAN_BOOK"
    if "SAGLIK" in name or "SAĞLIK" in name or "MEDICAL" in name or "FITNESS" in name: return "MEDICAL_CERT"
    if "SARI" in name or "FEVER" in name or "YELLOW" in name: return "YELLOW_FEVER"
    if "STCW" in name or "SAFETY" in name or "BASIC" in name: return "BASIC_SAFETY"
    if "GMDSS" in name or "RADIO" in name or "GOC" in name: return "GMDSS"
    if "EHLIYET" in name or "EHLYT" in name or "COMPETENCY" in name or "YETERLIK" in name or "COC" in name: return "COMPETENCY"
    if "SICIL" in name or "SİCİL" in name or "CRIMINAL" in name: return "CRIMINAL_RECORD"
    return "UNKNOWN"

def parse_uab_pdf_local(pdf_bytes: bytes) -> List[Evidence]:
    evidences = []
    text = ""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages:
                text += page.extract_text() + "\n"
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        text += " | ".join([str(cell) for cell in row if cell]) + "\n"
                        
        tckn_match = re.search(r'Vatandaşlık Numarası.*?(\d{11})', text, re.IGNORECASE)
        cuzdan_match = re.search(r'Cüzdan Numarası.*?([A-Z0-9]+)', text, re.IGNORECASE)
        
        tckn = tckn_match.group(1) if tckn_match else "Bulunamadı"
        cuzdan = cuzdan_match.group(1) if cuzdan_match else "Bulunamadı"
        
        cuzdan_bitis = re.search(r'Bitiş Tarihi.*?(\d{2}\.\d{2}\.\d{4})', text)
        exp_date = parse_date(cuzdan_bitis.group(1)) if cuzdan_bitis else datetime(2028,12,31)
        
        evidences.append(Evidence(code="SEAMAN_BOOK", document_no=cuzdan, issue_date=datetime(2024,1,1), expiry_date=exp_date, verified=True, raw_text=f"TCKN: {tckn}"))
        
        if "UZAKYOL" in text or "KAPTAN" in text or "ZABİT" in text or "MÜHENDİS" in text:
             evidences.append(Evidence(code="COMPETENCY", document_no="UAB-COC", issue_date=datetime(2024,1,1), expiry_date=exp_date, verified=True))
        if "GMDSS" in text or "TELSİZ" in text:
             evidences.append(Evidence(code="GMDSS", document_no="UAB-GMDSS", issue_date=datetime(2024,1,1), expiry_date=exp_date, verified=True))
             
        stcw_keywords = {
            "BASIC_SAFETY": ["CAN KURTARMA", "YANGIN", "İLK YARDIM", "İLKYARDIM", "KİŞİSEL EMNİYET"],
            "ADV_FIRE": ["İLERİ YANGIN"],
            "SURVIVAL_CRAFT": ["CANKURTARMA ARAÇLARI"],
            "ECDIS_GENERIC": ["ECDIS", "ELEKTRONİK HARİTA"],
            "ERM / BRM": ["KÖPRÜÜSTÜ KAYNAK", "MAKİNE DAİRESİ KAYNAK", "BRM", "ERM"]
        }
        
        for code, keywords in stcw_keywords.items():
            if any(kw in text for kw in keywords):
                evidences.append(Evidence(code=code, document_no=f"UAB-{code}", issue_date=datetime(2024,1,1), expiry_date=exp_date, verified=True))
                
        return evidences
    except Exception as e:
        print(f"UAB Parse Error: {e}")
        return []

def process_document(data: bytes, mime: str, provider_name: str, api_key: str, model_name: str, filename: str = "") -> Evidence:
    code = detect_code_from_name(filename)
    valid_issue = datetime(2024, 1, 1)
    valid_expiry = datetime(2028, 12, 31)
    doc_no = re.sub(r'[^\w\s-]', '', filename.split(".")[0]).strip()
    
    return Evidence(code=code, document_no=doc_no, issue_date=valid_issue, expiry_date=valid_expiry, verified=False, raw_text=f"Yerel Tanımlama: {filename}")
