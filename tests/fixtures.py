"""Synthetic documents mirroring the strategy doc's example: deed 185 m², EPC extension 32 m², plan 240 m²."""
import io
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

DEED = """VERKOOPAKTE
Verleden op 12/03/2026 voor notaris Peeters.
Verkoper: Jan Janssens
Koper: Els Maes
Pand gelegen te Kerkstraat 12, 9000 Gent.
Kadastraal: sectie A nummer 123/B.
Bewoonbare oppervlakte van 185 m².
Bouwjaar 1975.
"""
EPC = """Energieprestatiecertificaat (EPC)
Certificaatnummer 20240101-0001234
Adres: Kerkstraat 12, 9000 Gent
Energielabel: E
Energiescore 430 kWh/m²
Bruikbare vloeroppervlakte 240 m²
Uitbreiding van 32 m² (achterbouw)
Geldig tot 01/01/2034
Bouwjaar 1975
"""
ASB = """Asbestattest
Kerkstraat 12, 9000 Gent
Datum: 01/02/2026
Er werd asbest aangetroffen in de dakbedekking.
"""
ELEC = """Keuringsverslag elektrische installatie (AREI)
Adres: Kerkstraat 12, 9000 Gent
Datum van keuring: 05/05/2000
Installatie niet conform.
"""

def pdf(text: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    for line in text.splitlines():
        c.drawString(40, y, line); y -= 16
    c.save()
    return buf.getvalue()
