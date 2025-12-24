"""
Date Parser - Extraccion de fechas de lenguaje natural en espanol

Este modulo parsea expresiones de fechas en espanol y las convierte
a rangos de fechas ISO (date_from, date_to).

Ejemplos:
- "diciembre 2024" -> ("2024-12-01", "2024-12-31")
- "ultimo mes" -> (hace 30 dias, hoy)
- "ayer" -> (ayer, ayer+1)
- "esta semana" -> (lunes, domingo+1)
"""
import re
from datetime import date, timedelta
from typing import Tuple, Optional
from calendar import monthrange


# Mapeo de meses en espanol a numero
SPANISH_MONTHS = {
    "enero": 1, "ene": 1,
    "febrero": 2, "feb": 2,
    "marzo": 3, "mar": 3,
    "abril": 4, "abr": 4,
    "mayo": 5, "may": 5,
    "junio": 6, "jun": 6,
    "julio": 7, "jul": 7,
    "agosto": 8, "ago": 8,
    "septiembre": 9, "sep": 9, "sept": 9,
    "octubre": 10, "oct": 10,
    "noviembre": 11, "nov": 11,
    "diciembre": 12, "dic": 12,
}

# Mapeo de trimestres
QUARTERS = {
    "q1": (1, 3), "primer trimestre": (1, 3), "1er trimestre": (1, 3),
    "q2": (4, 6), "segundo trimestre": (4, 6), "2do trimestre": (4, 6),
    "q3": (7, 9), "tercer trimestre": (7, 9), "3er trimestre": (7, 9),
    "q4": (10, 12), "cuarto trimestre": (10, 12), "4to trimestre": (10, 12),
}


def _get_month_range(year: int, month: int) -> Tuple[str, str]:
    """Retorna el rango de fechas para un mes completo."""
    first_day = date(year, month, 1)
    last_day_num = monthrange(year, month)[1]
    last_day = date(year, month, last_day_num)
    # date_to es exclusivo, asi que sumamos 1 dia
    return first_day.isoformat(), (last_day + timedelta(days=1)).isoformat()


def _get_quarter_range(year: int, quarter_start: int, quarter_end: int) -> Tuple[str, str]:
    """Retorna el rango de fechas para un trimestre."""
    first_day = date(year, quarter_start, 1)
    last_day_num = monthrange(year, quarter_end)[1]
    last_day = date(year, quarter_end, last_day_num)
    return first_day.isoformat(), (last_day + timedelta(days=1)).isoformat()


def extract_date_range(question: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extrae un rango de fechas de una pregunta en espanol.

    Args:
        question: Pregunta del usuario en lenguaje natural

    Returns:
        Tupla (date_from, date_to) en formato ISO, o (None, None) si no hay fechas

    Ejemplos:
        >>> extract_date_range("ventas de diciembre 2024")
        ('2024-12-01', '2025-01-01')

        >>> extract_date_range("que paso ayer")
        ('2024-12-22', '2024-12-23')  # si hoy es 23/12

        >>> extract_date_range("hola como estas")
        (None, None)
    """
    q = question.lower().strip()
    today = date.today()

    # === PATRONES RELATIVOS ===

    # "hoy"
    if re.search(r'\bhoy\b', q):
        return today.isoformat(), (today + timedelta(days=1)).isoformat()

    # "ayer"
    if re.search(r'\bayer\b', q):
        yesterday = today - timedelta(days=1)
        return yesterday.isoformat(), today.isoformat()

    # "esta semana"
    if re.search(r'\besta\s+semana\b', q):
        # Lunes de esta semana
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=7)
        return start_of_week.isoformat(), end_of_week.isoformat()

    # "semana pasada" / "ultima semana"
    if re.search(r'\b(semana\s+pasada|ultima\s+semana|últimas?\s+semana)\b', q):
        start_of_last_week = today - timedelta(days=today.weekday() + 7)
        end_of_last_week = start_of_last_week + timedelta(days=7)
        return start_of_last_week.isoformat(), end_of_last_week.isoformat()

    # "este mes"
    if re.search(r'\beste\s+mes\b', q):
        return _get_month_range(today.year, today.month)

    # "mes pasado" / "ultimo mes"
    if re.search(r'\b(mes\s+pasado|ultimo\s+mes|último\s+mes)\b', q):
        if today.month == 1:
            return _get_month_range(today.year - 1, 12)
        else:
            return _get_month_range(today.year, today.month - 1)

    # "ultimos N dias"
    match = re.search(r'\b[uú]ltimos?\s+(\d+)\s+d[ií]as?\b', q)
    if match:
        days = int(match.group(1))
        start = today - timedelta(days=days)
        return start.isoformat(), (today + timedelta(days=1)).isoformat()

    # "ultimas N semanas"
    match = re.search(r'\b[uú]ltimas?\s+(\d+)\s+semanas?\b', q)
    if match:
        weeks = int(match.group(1))
        start = today - timedelta(weeks=weeks)
        return start.isoformat(), (today + timedelta(days=1)).isoformat()

    # === PATRONES ABSOLUTOS ===

    # "diciembre 2024" o "diciembre de 2024" (con año explícito)
    for month_name, month_num in SPANISH_MONTHS.items():
        pattern = rf'\b{month_name}\s+(?:de\s+)?(\d{{4}})\b'
        match = re.search(pattern, q)
        if match:
            year = int(match.group(1))
            return _get_month_range(year, month_num)

    # "diciembre" o "en diciembre" (sin año - usa año actual)
    for month_name, month_num in SPANISH_MONTHS.items():
        pattern = rf'\b(?:en\s+)?{month_name}\b'
        match = re.search(pattern, q)
        if match:
            # Verificar que no haya un año después (ya manejado arriba)
            after_match = q[match.end():]
            if not re.match(r'\s*(?:de\s+)?\d{4}', after_match):
                return _get_month_range(today.year, month_num)

    # "2024" solo (ano completo) - solo si es el unico numero de 4 digitos
    match = re.search(r'\b(20\d{2})\b', q)
    if match and not any(m in q for m in SPANISH_MONTHS.keys()):
        # Verificar que no sea parte de otra expresion
        year = int(match.group(1))
        # Solo si mencionan "ano" o "year"
        if re.search(r'\b(a[ñn]o|year)\b', q):
            return f"{year}-01-01", f"{year + 1}-01-01"

    # Trimestres: "Q4 2024", "cuarto trimestre 2024"
    for quarter_name, (q_start, q_end) in QUARTERS.items():
        pattern = rf'\b{quarter_name}\s+(?:de\s+)?(\d{{4}})\b'
        match = re.search(pattern, q)
        if match:
            year = int(match.group(1))
            return _get_quarter_range(year, q_start, q_end)

    # "del 1 al 15 de diciembre 2024"
    pattern = r'\bdel?\s+(\d{1,2})\s+al?\s+(\d{1,2})\s+de\s+(\w+)(?:\s+(?:de\s+)?(\d{4}))?\b'
    match = re.search(pattern, q)
    if match:
        day_start = int(match.group(1))
        day_end = int(match.group(2))
        month_name = match.group(3).lower()
        year = int(match.group(4)) if match.group(4) else today.year

        if month_name in SPANISH_MONTHS:
            month_num = SPANISH_MONTHS[month_name]
            start = date(year, month_num, day_start)
            end = date(year, month_num, day_end) + timedelta(days=1)
            return start.isoformat(), end.isoformat()

    # "15 de diciembre" o "15 de diciembre 2024" (dia especifico)
    pattern = r'\b(\d{1,2})\s+de\s+(\w+)(?:\s+(?:de\s+)?(\d{4}))?\b'
    match = re.search(pattern, q)
    if match:
        day = int(match.group(1))
        month_name = match.group(2).lower()
        year = int(match.group(3)) if match.group(3) else today.year

        if month_name in SPANISH_MONTHS and 1 <= day <= 31:
            month_num = SPANISH_MONTHS[month_name]
            try:
                specific_date = date(year, month_num, day)
                return specific_date.isoformat(), (specific_date + timedelta(days=1)).isoformat()
            except ValueError:
                pass  # Dia invalido para el mes

    # === EVENTOS ESPECIALES ===

    # "cyber monday" / "black friday" - asumimos fechas tipicas de noviembre
    if re.search(r'\b(cyber\s*monday|black\s*friday)\b', q):
        # Buscar ano en la pregunta
        year_match = re.search(r'\b(20\d{2})\b', q)
        year = int(year_match.group(1)) if year_match else today.year
        # Cyber Monday/Black Friday suele ser ultima semana de noviembre
        # Retornamos todo noviembre para ser inclusivos
        return _get_month_range(year, 11)

    # === FALLBACK ===
    # Si no encontramos fechas especificas, retornamos None
    return None, None


def format_date_context(date_from: Optional[str], date_to: Optional[str]) -> str:
    """
    Formatea el contexto de fechas para mostrar al LLM.

    Args:
        date_from: Fecha inicio ISO
        date_to: Fecha fin ISO

    Returns:
        String descriptivo del rango
    """
    if not date_from or not date_to:
        return "ultimos 30 dias"

    try:
        d_from = date.fromisoformat(date_from)
        d_to = date.fromisoformat(date_to) - timedelta(days=1)  # Ajustar exclusividad

        # Mismo dia
        if d_from == d_to:
            return f"{d_from.strftime('%d/%m/%Y')}"

        # Mismo mes
        if d_from.year == d_to.year and d_from.month == d_to.month:
            if d_from.day == 1 and d_to.day == monthrange(d_to.year, d_to.month)[1]:
                # Mes completo
                month_names = {
                    1: "enero", 2: "febrero", 3: "marzo", 4: "abril",
                    5: "mayo", 6: "junio", 7: "julio", 8: "agosto",
                    9: "septiembre", 10: "octubre", 11: "noviembre", 12: "diciembre"
                }
                return f"{month_names[d_from.month]} {d_from.year}"

        return f"{d_from.strftime('%d/%m/%Y')} a {d_to.strftime('%d/%m/%Y')}"

    except Exception:
        return f"{date_from} a {date_to}"


# Test rapido
if __name__ == "__main__":
    test_cases = [
        "ventas de diciembre 2024",
        "cuales fueron las ventas de ayer",
        "productos vendidos esta semana",
        "reporte del ultimo mes",
        "ventas de los ultimos 7 dias",
        "que paso el 15 de noviembre 2024",
        "resultados del Q4 2024",
        "como me fue en el cyber monday 2024",
        "hola como estas",  # Sin fecha
    ]

    print("=== Test de Date Parser ===\n")
    for q in test_cases:
        date_from, date_to = extract_date_range(q)
        context = format_date_context(date_from, date_to)
        print(f"Q: {q}")
        print(f"   -> {date_from} a {date_to}")
        print(f"   -> Contexto: {context}\n")
