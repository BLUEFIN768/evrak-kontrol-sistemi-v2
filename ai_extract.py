import re
import io
from typing import Optional, List, Tuple, Dict, Any
from datetime import datetime
try:
    import pypdf
except ImportError:
    pypdf = None
try:
    import pdfplumber
except ImportError:
    pdfplumber = None
from crew_core import Evidence

MONTH_MAP = {
    'OCA': 1, 'JAN': 1, 'SUB': 2, 'FEB': 2, 'MAR': 3, 'NIS': 4, 'APR': 4,
    'MAY': 5, 'HAZ': 6, 'JUN': 6, 'TEM': 7, 'JUL': 7, 'AGU': 8, 'AUG': 8,
    'EYL': 9, 'SEP': 9, 'EKI': 10, 'OCT': 10, 'KAS': 11, 'NOV': 11, 'ARA': 12, 'DEC': 12
}

def normalize_text(text: str) -> str:
    tr_map = str.maketrans("İIĞÜŞÖÇıiğüşöç", "IIGUSOCIIGUSOC")
    return text.translate(tr_map).upper()

def parse_dates_from_any_text(raw_text: str) -> List[Tuple[datetime, str]]:
    dates = []
    # 1. Standart Formatlar (DD.MM.YYYY, DD/MM/YYYY, YYYY-MM-DD)
    for m in re.finditer(r'\b(\d{1,2})[\./-](\d{1,2})[\./-](\d{4})\b', raw_text):
        d, mth, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            dates.append((datetime(y, mth, d), m.group(0)))
        except ValueError:
            pass

    # 2. Metinsel Tarihler (26 ARA/DEC 2029 vb.)
    for m in re.finditer(r'\b(\d{1,2})\s+([A-ZÇĞİÖŞÜa-zçğıöşü/]{3,15})\s+(\d{4})\b', raw_text):
        d = int(m.group(1))
        m_raw = m.group(2).upper()
        y = int(m.group(3))
        found_m = None
        for k, v in MONTH_MAP.items():
            if k in m_raw:
                found_m = v
                break
        if found_m:
            try:
                dates.append((datetime(y, found_m, d), m.group(0)))
            except ValueError:
                pass

    return dates

def extract_text_from_bytes(data: bytes, filename: str) -> str:
    extracted = ""
    if filename.lower().endswith(".pdf"):
        if pypdf:
            try:
                reader = pypdf.PdfReader(io.BytesIO(data))
                for page in reader.pages:
                    extracted += (page.extract_text() or "") + "\n"
            except Exception:
                pass
        if not extracted.strip() and pdfplumber:
            try:
                with pdfplumber.open(io.BytesIO(data)) as pdf:
                    for p in pdf.pages:
                        extracted += (p.extract_text() or "") + "\n"
            except Exception:
                pass
    elif filename.lower().endswith(".docx"):
        try:
            import docx
            doc = docx.Document(io.BytesIO(data))
            for p in doc.paragraphs:
                extracted += p.text + "\n"
            for t in doc.tables:
                for row in t.rows:
                    extracted += " | ".join(c.text.strip() for c in row.cells) + "\n"
        except Exception:
            pass
    elif filename.lower().endswith((".txt", ".csv")):
        try:
            extracted = data.decode("utf-8", errors="ignore")
        except Exception:
            pass
    return extracted

def parse_uab_pdf_local(pdf_bytes: bytes) -> Tuple[List[Evidence], Dict[str, str]]:
    evidences = []
    extracted_info = {"tckn": "", "cuzdan": "", "name": ""}
    
    text = extract_text_from_bytes(pdf_bytes, "uab.pdf")
    norm_text = normalize_text(text)

    # 1. TCKN
    tckn_match = re.search(r'(?:TCKN|T\.?C\.?\s*(?:KIMLIK|VATANDASLIK)?\s*(?:NO|NUMARASI)?|VATANDASLIK\s*NO(?:SU)?|KIMLIK\s*NO(?:SU)?)\s*[:\.\s\-]*([1-9]\d{10})\b', norm_text)
    if tckn_match:
        extracted_info["tckn"] = tckn_match.group(1)
    else:
        all_11 = re.findall(r'\b([1-9]\d{10})\b', norm_text)
        if all_11:
            extracted_info["tckn"] = all_11[0]

    # 2. Cüzdan No
    cuzdan_candidates = re.findall(r'(?:CUZDAN\s*(?:NO|NUMARASI)?|SICIL\s*(?:NO|NUMARASI)?)\s*[:=\.\s\-]+([A-Z0-9]+)', norm_text)
    for cand in cuzdan_candidates:
        cand = cand.strip()
        if re.fullmatch(r'[A-Z]{0,2}\d{5,10}', cand) and cand != extracted_info["tckn"]:
            extracted_info["cuzdan"] = cand
            break

    if not extracted_info["cuzdan"]:
        general_matches = re.findall(r'\b([A-Z]\d{6,9})\b', norm_text)
        for cand in general_matches:
            if cand != extracted_info["tckn"]:
                extracted_info["cuzdan"] = cand
                break

    # 3. İsim
    name_match = re.search(r'(?:ADI\s*SOYADI|AD\s*SOYAD|ISIM\s*SOYISIM)\s*[:\.\s\-]+([A-Z\s]{3,30})\b', norm_text)
    if name_match:
        extracted_info["name"] = name_match.group(1).split('\n')[0].strip().title()

    cuzdan_bitis = re.search(r'BITIS TARIHI.*?(\d{2}\.\d{2}\.\d{4})', norm_text)
    cuzdan_exp = None
    if cuzdan_bitis:
        try:
            cuzdan_exp = datetime.strptime(cuzdan_bitis.group(1), "%d.%m.%Y")
        except ValueError:
            pass

    if extracted_info["cuzdan"]:
        evidences.append(Evidence(
            code="SEAMAN_BOOK",
            document_no=extracted_info["cuzdan"],
            issue_date=None,
            expiry_date=cuzdan_exp,
            verified=True,
            raw_text=f"UAB Cüzdan (TCKN: {extracted_info['tckn']})"
        ))

    # STCW 5 Yıl Yenileme Kuralına Tabi Sertifikalar
    stcw_5_year_codes = [
        "FIRE_PREVENTION_AND_FIRE_FIGHTING",
        "PERSONAL_SURVIVAL_TECHNIQUES",
        "ELEMENTARY_FIRST_AID",
        "PERSONAL_SAFETY_AND_SOCIAL_RESPONSIBILITY",
        "SURVIVAL_CRAFT",
        "ADV_FIRE",
        "TANKER_BASIC",
        "TANKER_ADV_GAS",
        "TANKER_ADV_OIL",
        "TANKER_ADV_CHEM"
    ]

    # 4. SATIR BAZLI SERTİFİKA TARAMASI
    for line in text.splitlines():
        line_clean = line.strip()
        if not line_clean or any(k in line_clean.upper() for k in ["VATANDASLIK", "CUZDAN", "BARKOD", "SOYADI"]):
            continue

        dates = [d[0] for d in parse_dates_from_any_text(line_clean)]
        doc_no_m = re.search(r'\((\d{4}[-\d]+)\)', line_clean)
        doc_no = doc_no_m.group(1) if doc_no_m else "UAB-VERIFIED"
        norm_l = normalize_text(line_clean)

        code = None
        if "KOPRUUSTU KAYNAK" in norm_l or "BRM" in norm_l or "BTM" in norm_l:
            code = "BRM_BTM"
        elif "DENIZDE KISISEL CAN" in norm_l or "PST" in norm_l:
            code = "PERSONAL_SURVIVAL_TECHNIQUES"
        elif "TEMEL ILKYARDIM" in norm_l or "EFA" in norm_l:
            code = "ELEMENTARY_FIRST_AID"
        elif "YANGIN ONLEME" in norm_l or "FPFF" in norm_l:
            code = "FIRE_PREVENTION_AND_FIRE_FIGHTING"
        elif "PERSONEL GUVENLIGI" in norm_l or "PSSR" in norm_l:
            code = "PERSONAL_SAFETY_AND_SOCIAL_RESPONSIBILITY"
        elif "CANKURTARMA ARACLARI" in norm_l or "PSCRB" in norm_l:
            code = "SURVIVAL_CRAFT"
        elif "ILERI YANGIN" in norm_l or "AFF" in norm_l:
            code = "ADV_FIRE"
        elif "TIBBI BAKIM" in norm_l:
            code = "MEDICAL_CARE"
        elif "TIBBI ILK YARDIM" in norm_l:
            code = "MEDICAL_FIRST_AID"
        elif "ARPA" in norm_l:
            code = "ARPA"
        elif "RADAR" in norm_l:
            code = "RADAR"
        elif "ECDIS" in norm_l:
            code = "ECDIS_GENERIC"
        elif "GUVENLIK FARKINDALIK" in norm_l:
            code = "SECURITY_AWARENESS"
        elif "BELIRLENMIS GUVENLIK" in norm_l:
            code = "DESIGNATED_SECURITY"
        elif "GEMI GUVENLIK ZABITI" in norm_l or "SSO" in norm_l:
            code = "SSO"

        if code:
            iss_d, exp_d = None, None
            if len(dates) >= 2:
                dates.sort()
                iss_d = dates[0]
                exp_d = dates[-1]
            elif len(dates) == 1:
                iss_d = dates[0]
                if code in stcw_5_year_codes:
                    # STCW 5 Yıl Kuralı (Alınış + 5 Yıl)
                    try:
                        exp_d = datetime(iss_d.year + 5, iss_d.month, iss_d.day - 1 if iss_d.day > 1 else 1)
                    except ValueError:
                        exp_d = datetime(iss_d.year + 5, iss_d.month, 28)
                elif code in ["BRM_BTM", "RADAR", "ARPA", "ECDIS_GENERIC", "SECURITY_AWARENESS", "DESIGNATED_SECURITY", "SSO"]:
                    exp_d = None  # Süresiz
                else:
                    exp_d = cuzdan_exp

            evidences.append(Evidence(
                code=code,
                document_no=doc_no,
                issue_date=iss_d,
                expiry_date=exp_d,
                verified=True,
                raw_text=line_clean
            ))

    return evidences, extracted_info

def process_document(data: bytes, mime: str, provider_name: str, api_key: str, model_name: str, filename: str = "") -> List[Evidence]:
    """Harici evrakları (PDF, DOCX) fiilen ayrıştırır."""
    evidences = []
    text = extract_text_from_bytes(data, filename)
    norm_filename = normalize_text(filename)
    norm_text = normalize_text(text)

    # 1. Pasaport
    if any(k in norm_filename for k in ["PASAPORT", "PASSPORT", "PP"]) or "PASAPORT" in norm_text or "P<TUR" in text:
        doc_no = ""
        m_no = re.search(r'\b([UAC]\d{8})\b', norm_text)
        if m_no:
            doc_no = m_no.group(1)

        dates = parse_dates_from_any_text(text)
        unique_dates = sorted(list(set(d[0] for d in dates)))
        doc_dates = [d for d in unique_dates if d.year >= 2000]

        iss_d, exp_d = None, None
        if len(doc_dates) >= 2:
            iss_d = doc_dates[0]
            exp_d = doc_dates[-1]
        elif len(doc_dates) == 1:
            if doc_dates[0] > datetime.now():
                exp_d = doc_dates[0]
            else:
                iss_d = doc_dates[0]

        for line in text.splitlines():
            clean_l = line.strip().replace(" ", "")
            mrz = re.search(r'([UAC]\d{8}|\d{9})[A-Z0-9<]{4}(\d{6})\d[MF<](\d{6})', clean_l)
            if mrz:
                if not doc_no and mrz.group(1):
                    doc_no = mrz.group(1).replace("<", "")
                try:
                    ey, em, ed = int("20" + mrz.group(3)[0:2]), int(mrz.group(3)[2:4]), int(mrz.group(3)[4:6])
                    exp_d = datetime(ey, em, ed)
                except ValueError:
                    pass

        evidences.append(Evidence(
            code="PASSPORT",
            document_no=doc_no or filename.split(".")[0],
            issue_date=iss_d,
            expiry_date=exp_d,
            verified=True if (doc_no and exp_d) else False,
            raw_text=f"Pasaport ({filename})"
        ))
        return evidences

    # 2. Sağlık Raporu
    if any(k in norm_filename for k in ["SAGLIK", "MEDICAL", "FITNESS", "RAPOR"]) or "HUDUT VE SAHILLER" in norm_text:
        dates = [d[0] for d in parse_dates_from_any_text(text)]
        dates.sort()
        iss_d = dates[0] if len(dates) >= 1 else None
        exp_d = dates[-1] if len(dates) >= 2 else None
        if iss_d and not exp_d:
            try:
                exp_d = datetime(iss_d.year + 2, iss_d.month, iss_d.day)
            except ValueError:
                exp_d = datetime(iss_d.year + 2, iss_d.month, 28)

        evidences.append(Evidence(
            code="MEDICAL_CERT",
            document_no=filename.split(".")[0],
            issue_date=iss_d,
            expiry_date=exp_d,
            verified=True if exp_d else False,
            raw_text=f"Sağlık Raporu ({filename})"
        ))
        return evidences

    # 3. Yeterlik ve GMDSS
    if any(k in norm_filename for k in ["COC", "YETERLIK", "EHLIYET", "COMPETENCY"]):
        dates = [d[0] for d in parse_dates_from_any_text(text)]
        dates.sort()
        iss_d = dates[0] if dates else None
        exp_d = dates[-1] if len(dates) >= 2 else None
        evidences.append(Evidence(code="COMPETENCY", document_no=filename.split(".")[0], issue_date=iss_d, expiry_date=exp_d, verified=True if exp_d else False))
        return evidences

    if any(k in norm_filename for k in ["GMDSS", "GOC", "ROC"]):
        dates = [d[0] for d in parse_dates_from_any_text(text)]
        dates.sort()
        iss_d = dates[0] if dates else None
        exp_d = dates[-1] if len(dates) >= 2 else None
        evidences.append(Evidence(code="GMDSS", document_no=filename.split(".")[0], issue_date=iss_d, expiry_date=exp_d, verified=True if exp_d else False))
        return evidences

    # 4. Diğer Belgeler (Sarı Humma, Diploma, Adli Sicil vb.)
    dates = [d[0] for d in parse_dates_from_any_text(text)]
    iss_d = dates[0] if dates else None
    exp_d = dates[-1] if len(dates) >= 2 else None

    target_code = "UNKNOWN"
    if any(k in norm_filename for k in ["SARI", "YELLOW", "FEVER", "YF"]):
        target_code = "YELLOW_FEVER"
        exp_d = None
    elif any(k in norm_filename for k in ["SICIL", "CRIMINAL"]):
        target_code = "CRIMINAL_RECORD"
    elif any(k in norm_filename for k in ["DIPLOMA", "MEZUNIYET"]):
        target_code = "DIPLOMA"
        exp_d = None
    elif "ENDORSEMENT" in norm_filename:
        target_code = "ENDORSEMENT"

    evidences.append(Evidence(
        code=target_code,
        document_no=filename.split(".")[0],
        issue_date=iss_d,
        expiry_date=exp_d,
        verified=True if (iss_d or exp_d) else False,
        raw_text=filename
    ))
    return evidences
