"""Client-layout contract transcribed from the five October 2026 source workbooks.

These headings intentionally retain the customer's spelling, ordering and blanks.
Never silently create a grade or destination mapping: surface unmatched trips on
an audit sheet and mark export incomplete.
"""
from __future__ import annotations
import re

# Material Wise Dispatch Repor 2026-27.xlsx > Oct-26 > B2:N2
MATERIAL_COLUMNS = [
    "C.Fines(55-58)", "C.Fines(58-60)", "C.Fines(60-62)",
    "S.Fines(51-55)", "S.Fines(55-58)", "S.Fines(58-60)",
    "S.Fines(60-62)", "S.Fines(62-65)", "S.Fines(65-68)",
    "5-18mm(55-58)", "5-18mm(58-60)", "5-18mm(60-62)", "5-18mm(62-65)",
]

# Despatch Report Oct-2026.xlsx > DESTINATION WISE > B3:U3
CAPTIVE_MATERIALS = [
    "C.Fines(58-60)", "C.Fines(60-62)", "S.Fines(55-58)",
    "S.Fines(58-60)", "S.Fines(60-62)", "S.Fines(62-65)",
    "S.Fines(65-68)",
]
NON_CAPTIVE_MATERIALS = [
    "C.Fines(55-58)", "C.Fines(58-60)", "C.Fines(60-62)",
    "S.Fines(51-55)", "S.Fines(55-58)", "S.Fines(58-60)",
    "S.Fines(60-62)", "S.Fines(62-65)", "S.Fines(65-68)",
    "5-18mm(55-58)", "5-18mm(58-60)", "5-18mm(60-62)",
    "18-40mm(62-65)",
]

# Destination Wise Report Oct-26.xlsx, Oct-26 row 2/3/4.
# Group positions are odd 0-based, with 41 trip/quantity pairs (B:CI).
BUYER_STARTS = {
    0: "Self",
    9: "PANKAJINI INTERNATIONAL PRIVATE LIMITED",
    13: "Bhusan Power and Steel Ltd.",
    16: "SHYAMPURIA DEVELOPERS AND TRADERS LLP",
    19: "ORISSA METALIKS PVT LTD [UNIT II ]",
    22: "MS BAITARANI ORE MOVERS",
    23: "SNN MINERALS",
    24: "STEELOGRAPH ASCENDERS",
    25: "Prabhu Sponge (P) Ltd.",
    28: "PH ASSOCIATES PRIVATE LIMITED",
    33: "S N N MINERALS PRIVATE LIMITED",
    37: "GLOBAL MARKETING",
    38: "Shri Jagannath Steels & Power Ltd",
    40: "Sri Balaji Metallics Pvt Ltd",
    41: "DNA MINERALS PVT LTD",
}
# Explicit list includes the original 41 material buckets plus two customer
# continuation buckets; fill positions are kept stable, never reordered.
DESTINATION_BUCKETS = [
    # customer, destination, original material (each two Excel columns)
    ("Self","Bhubaneswar","S.Fines(55-58)"),
    ("Self","Dabuna","C.Fines(58-60)"),
    ("Self","Dabuna","C.Fines(60-62)"),
    ("Self","Dabuna","S.Fines(52-55)"),
    ("Self","Dabuna","S.Fines(55-58)"),
    ("Self","Dabuna","S.Fines(58-60)"),
    ("Self","Dabuna","S.Fines(60-62)"),
    ("Self","Dabuna","S.Fines(62-65)"),
    ("Self","Dabuna","S.Fines(65-68)"),
    ("PANKAJINI INTERNATIONAL PRIVATE LIMITED","PDPB RLY SDG","C.Fines(55-58)"),
    ("PANKAJINI INTERNATIONAL PRIVATE LIMITED","Jamuria(W.B)","S.Fines(55-58)"),
    ("PANKAJINI INTERNATIONAL PRIVATE LIMITED","Phuljhar","C.Fines(55-58)"),
    ("PANKAJINI INTERNATIONAL PRIVATE LIMITED","Phuljhar","S.Fines(55-58)"),
    ("Bhusan Power and Steel Ltd.","Thelkoloi(Sambalpur)","S.Fines(58-60)"),
    ("Bhusan Power and Steel Ltd.","Thelkoloi(Sambalpur)","5-40mm(55-58)"),
    ("Bhusan Power and Steel Ltd.","Thelkoloi(Sambalpur)","C.Fines(58-60)"),
    ("SHYAMPURIA DEVELOPERS AND TRADERS LLP","Barbil RLY SDG","5-40mm(60-62)"),
    ("SHYAMPURIA DEVELOPERS AND TRADERS LLP","Barbil RLY SDG","5-40mm(58-60)"),
    ("SHYAMPURIA DEVELOPERS AND TRADERS LLP","MJBB RLY SDG","5-40mm(55-58)"),
    ("ORISSA METALIKS PVT LTD [UNIT II ]","Belkundi RLY SDG","C.Fines(55-58)"),
    ("ORISSA METALIKS PVT LTD [UNIT II ]","Belkundi RLY SDG","S.Fines(55-58)"),
    ("ORISSA METALIKS PVT LTD [UNIT II ]","Belkundi RLY SDG","S.Fines(58-60)"),
    ("MS BAITARANI ORE MOVERS","Hatgamharia","5-40mm(60-62)"),
    ("SNN MINERALS","Chandil(Saraikela)","5-40mm(60-62)"),
    ("STEELOGRAPH ASCENDERS","PDPB RLY SDG","5-40mm(60-62)"),
    ("Prabhu Sponge (P) Ltd.","Jhagarpur(SNG)","5-40mm(55-58)"),
    ("Prabhu Sponge (P) Ltd.","Jhagarpur(SNG)","5-40mm(58-60)"),
    ("Prabhu Sponge (P) Ltd.","Jhagarpur(SNG)","5-40mm(60-62)"),
    ("PH ASSOCIATES PRIVATE LIMITED","Palaspanga","5-18mm(55-58)"),
    ("PH ASSOCIATES PRIVATE LIMITED","Palaspanga","5-18mm(60-62)"),
    ("PH ASSOCIATES PRIVATE LIMITED","Uliburu, SJSPL","5-18mm(60-62)"),
    ("PH ASSOCIATES PRIVATE LIMITED","Kuarmunda(SNG)","5-18mm(60-62)"),
    ("PH ASSOCIATES PRIVATE LIMITED","Sukruli","5-18mm(60-62)"),
    ("S N N MINERALS PRIVATE LIMITED","Mohitpur(SINI)","5-40mm(55-58)"),
    ("S N N MINERALS PRIVATE LIMITED","Mohitpur(SINI)","5-40mm(60-62)"),
    ("S N N MINERALS PRIVATE LIMITED","Tuidungri(Chandil)","5-40mm(58-60)"),
    ("S N N MINERALS PRIVATE LIMITED","Tuidungri(Chandil)","5-40mm(60-62)"),
    ("GLOBAL MARKETING","RATURIA-WB","5-40mm(58-60)"),
    ("Shri Jagannath Steels & Power Ltd","Uliburu(SJSPL)","C.fines(55-58)"),
    ("Shri Jagannath Steels & Power Ltd","Uliburu(SJSPL)","S.Fines(55-58)"),
    ("Sri Balaji Metallics Pvt Ltd","KHAIRBONDH(SNG)","5-40mm(60-62)"),
    ("DNA MINERALS PVT LTD","Chandil","5-18mm(60-62)"),
    ("DNA MINERALS PVT LTD","Ramgarh","5-40mm(58-60)"),
    # Approved AMNS 28-Oct report identifies these actual destinations.
    # Do not silently treat Saraikela as Chandil; both get separate columns.
    ("S N N MINERALS PRIVATE LIMITED","TUIDUNGRI (SARAIKELA)","5-18mm(60-62)"),
    ("DNA MINERALS PVT LTD","TUIDUNGRI (SARAIKELA)","5-18mm(60-62)"),
]
assert len(DESTINATION_BUCKETS) == 45

TRANSPORTERS_26_OCT = [
    "M/S  FIRST CHOICE CARRIER",
    "M/S MAA KUANRI LOADING & TRANSPORT",
    "Ms PDSL AND SONS PRIVATE LIMITED",
    "MS RK ASSOCIATES PVT LTD",
    "MS SWAPNESWAR TRANS WORLD",
    "OMM HARIOM TRANSPORT",
    "RIDHICON LOGISTICS PRIVATE LIMITED",
]


def normalized(value):
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower().replace("&amp;", "&"))


def material_normalized(s, as_of=None):
    s = normalized(s)
    # October source E-Passes still called this 5-40mm while client report
    # material and 26 Oct AMNS buyer-wise reports use 5-18mm.
    if as_of and as_of.year == 2026 and as_of.month == 10 and s.startswith("540mm"):
        s = "518mm" + s[5:]
    return s


def destination_bucket_index(trip):
    buyer = normalized(trip.buyer)
    dest = normalized(trip.destination)
    mat = material_normalized(trip.material_grade, trip.report_date)

    # Client synonym map is limited to verified Oct-2026 permit/source pairs.
    if buyer == normalized("Self") and dest == normalized("Dabuna"):
        matches = [(i, x) for i, x in enumerate(DESTINATION_BUCKETS)
                   if normalized(x[0]) == buyer and normalized(x[1]) == dest
                   and material_normalized(x[2], trip.report_date) == mat]
        return matches[0][0] if matches else None
    if buyer == normalized("S N N MINERALS PRIVATE LIMITED.") and dest == "chandil" and mat == normalized("5-18mm(60-62)"):
        return 23
    if buyer == normalized("PH ASSOCIATES PRIVATE LIMITED"):
        if dest in ("uliburu", normalized("Uliburu, SJSPL")) and mat == normalized("5-18mm(60-62)"):
            return 30
        if dest == "kuarmunda" and mat == normalized("5-18mm(60-62)"):
            return 31
    for i, (customer, destination, grade) in enumerate(DESTINATION_BUCKETS):
        if (normalized(customer) == buyer and normalized(destination) == dest
                and material_normalized(grade, trip.report_date) == mat):
            return i
    return None


def is_captive(trip):
    return normalized(trip.buyer) == "self"


def classified_material(trip):
    return material_normalized(trip.material_grade, trip.report_date)
