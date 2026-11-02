import openpyxl
from dataclasses import dataclass
from typing import Optional, List, Dict, Tuple
from datetime import datetime

@dataclass
class Evidence:
    code: str
    document_no: str
    issue_date: Optional[datetime] = None
    expiry_date: Optional[datetime] = None
    verified: bool = False
    raw_text: str = ""

@dataclass
class Result:
    code: str
    status: str
    message: str
    evidence_used: Optional[Evidence] = None

# 35-101 Matrisi Standart Satır - Kod Eşleşmesi
MATRIX_ROW_TO_CODE = {
    14: "COMPETENCY",
    16: "SEAMAN_BOOK",
    18: "PASSPORT",
    20: "MEDICAL_CERT",
    22: "YELLOW_FEVER",
    24: "GMDSS",
    26: "FIRE_PREVENTION_AND_FIRE_FIGHTING",
    28: "PERSONAL_SURVIVAL_TECHNIQUES",
    30: "ELEMENTARY_FIRST_AID",
    32: "PERSONAL_SAFETY_AND_SOCIAL_RESPONSIBILITY",
    34: "SURVIVAL_CRAFT",
    36: "SECURITY_AWARENESS",
    38: "DESIGNATED_SECURITY",
    40: "SSO",
    42: "SECURITY_FAMILIARIZATION",
    44: "ADV_FIRE",
    46: "MEDICAL_CARE",
    48: "MEDICAL_FIRST_AID",
    50: "TANKER_BASIC",
    52: "TANKER_ADV_GAS",
    54: "TANKER_BASIC_OIL_CHEM",
    56: "TANKER_ADV_OIL",
    58: "TANKER_ADV_CHEM",
    60: "RADAR",
    62: "ARPA",
    64: "BRM_BTM",
    66: "ERM",
    68: "NAV_WATCH",
    70: "ENG_WATCH",
    72: "HIGH_VOLTAGE",
    74: "ECDIS_GENERIC",
    76: "ECDIS_SPECIFIC",
    78: "SHIP_HANDLING",
    80: "CARGO_HANDLING",
    82: "ENDORSEMENT"
}

# Rütbe - Kolon İndeks Haritası (35-101 Row 9 Kesin Eşleşme)
RANK_TO_COLUMN_MAP = {
    "MASTER": 6,
    "CHIEF OFFICER": 7,
    "2ND OFFICER": 8,
    "3RD OFFICER": 9,
    "CHIEF ENGINEER": 10,
    "2ND ENGINEER": 11,
    "3RD ENGINEER": 12,
    "ELECTRICIAN": 13,
    "BOSUN": 14,
    "PUMPMAN": 15,
    "AB": 16,
    "ABLE SEAMAN": 16,
    "ABLE SEAFARER DECK": 16,
    "OS": 17,
    "O/S": 17,
    "ORDINARY SEAMAN": 17,
    "FITTER": 18,
    "OILER": 19,
    "ABLE SEAFARER ENGINE": 19,
    "MOTORMAN": 19,
    "WIPER": 20,
    "COOK": 21,
    "STEWARD": 22,
    "CADET": 23
}

def get_rank_column(rank_str: str) -> int:
    norm = rank_str.strip().upper()
    for key, col in RANK_TO_COLUMN_MAP.items():
        if key == norm or key in norm:
            return col
    return 6  # Varsayılan Master

def load_rules_from_excel(filepath: str, rank: str, is_tanker: bool = False) -> Dict[str, str]:
    """Excel 35-101 matrisinden rütbeye özel zorunlu (X) ve atamaya bağlı (D) kuralları çeker."""
    try:
        wb = openpyxl.load_workbook(filepath, data_only=True)
        ws = wb["DOC_MATRIX"] if "DOC_MATRIX" in wb.sheetnames else wb.active
        rank_col = get_rank_column(rank)
        
        rules = {}
        for row_idx, code in MATRIX_ROW_TO_CODE.items():
            req_val = ws.cell(row=row_idx, column=rank_col).value
            if req_val:
                req_str = str(req_val).strip().upper()
                if req_str in ["X", "D"]:
                    if "TANKER" in code and not is_tanker:
                        continue
                    rules[code] = req_str

        return rules
    except Exception as e:
        print(f"Kural okuma hatası: {e}")
        return {}

def _check_evidence_dates(evidence: Evidence) -> Tuple[str, str]:
    """ITF STCW 2010 Manila Kılavuzu standartlarına göre geçerlilik denetimi."""
    now = datetime.now()
    
    # 1. Sarı Humma Aşısı (Ömür boyu geçerli)
    if evidence.code == "YELLOW_FEVER":
        return "OK", "Geçerli (Süresiz)"

    # 2. BRM / BTM için 5 Yıl Şirket Kuralı (35-102)
    if evidence.code == "BRM_BTM" and evidence.issue_date:
        diff_years = (now - evidence.issue_date).days / 365.25
        if diff_years > 5:
            return "REVIEW", "5 Yıldan Eski - Yenileme Gerekebilir"
        return "OK", "Geçerli (Son 5 Yıl İçinde)"

    # 3. Süresi Dolmuş Belge Kontrolü
    if evidence.expiry_date:
        if evidence.expiry_date < now:
            return "EXPIRED", f"Süresi Dolmuş ({evidence.expiry_date.strftime('%d.%m.%Y')})"
        return "OK", "Geçerli"

    # 4. Sadece Alınış Tarihi Olan Süresiz Eğitimler
    if evidence.issue_date and not evidence.expiry_date:
        return "OK", "Geçerli (Süresiz)"

    return "REVIEW", "Tarih Bilgisi Doğrulanmalı"

def evaluate(evidences: List[Evidence], rank: str, excel_path: str, is_tanker: bool = False) -> List[Result]:
    """Seçili rütbeye göre evrakları karşılaştırır ve denetim sonuçlarını üretir."""
    rules = load_rules_from_excel(excel_path, rank, is_tanker)
    results = []

    ev_map: Dict[str, Evidence] = {ev.code: ev for ev in evidences}

    for req_code, rule_type in rules.items():
        evidence = ev_map.get(req_code)

        # Karşılıklı denklik: RADAR yoksa ARPA varsa kabul et
        if not evidence and req_code == "RADAR" and ev_map.get("ARPA"):
            evidence = ev_map.get("ARPA")

        if not evidence:
            if rule_type == 'D':
                results.append(Result(code=req_code, status="OK", message="Atamaya Bağlı - Belge Yok", evidence_used=None))
            else:
                results.append(Result(code=req_code, status="MISSING", message="Zorunlu Belge Eksik", evidence_used=None))
            continue

        status, msg = _check_evidence_dates(evidence)

        if status == "EXPIRED":
            results.append(Result(code=req_code, status="EXPIRED", message=msg, evidence_used=evidence))
            continue

        if not evidence.verified:
            results.append(Result(code=req_code, status="REVIEW", message="Orijinalden Doğrulanmalı", evidence_used=evidence))
            continue

        results.append(Result(code=req_code, status=status, message=msg, evidence_used=evidence))

    return results
