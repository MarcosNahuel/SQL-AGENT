"""
Script para generar PDF del informe SQL-Agent
Usa fpdf2 para generar PDF directamente
"""
from fpdf import FPDF
from pathlib import Path
import re

# Paths
DOC_DIR = Path(__file__).parent
MD_FILE = DOC_DIR / "INFORME_SQL_AGENT.md"
PDF_FILE = DOC_DIR / "INFORME_SQL_AGENT.pdf"
SCREENSHOTS_DIR = DOC_DIR / "screenshots"


class PDFReport(FPDF):
    def __init__(self):
        super().__init__()
        self.add_page()
        # Usar fuente por defecto que soporte Unicode
        self.set_auto_page_break(auto=True, margin=15)

    def header(self):
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, 'SQL-Agent - Informe Tecnico', align='C', new_x='LMARGIN', new_y='NEXT')

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f'Pagina {self.page_no()}/{{nb}}', align='C')

    def chapter_title(self, title, level=1):
        if level == 1:
            self.set_font('Helvetica', 'B', 16)
            self.set_text_color(26, 26, 46)
            self.ln(10)
        elif level == 2:
            self.set_font('Helvetica', 'B', 14)
            self.set_text_color(22, 33, 62)
            self.ln(8)
        else:
            self.set_font('Helvetica', 'B', 12)
            self.set_text_color(26, 26, 46)
            self.ln(5)

        # Limpiar caracteres especiales
        title = self.clean_text(title)
        self.multi_cell(0, 8, title)

        if level <= 2:
            self.set_draw_color(67, 97, 238)
            self.line(10, self.get_y(), 200, self.get_y())
        self.ln(3)

    def body_text(self, text):
        self.set_font('Helvetica', '', 10)
        self.set_text_color(51, 51, 51)
        text = self.clean_text(text)
        self.multi_cell(0, 6, text)
        self.ln(2)

    def code_block(self, code):
        self.set_font('Courier', '', 8)
        self.set_fill_color(30, 30, 30)
        self.set_text_color(212, 212, 212)
        code = self.clean_text(code)

        # Dividir en lineas y limitar longitud
        lines = code.split('\n')
        for line in lines:
            if len(line) > 90:
                line = line[:87] + '...'
            self.cell(0, 5, line, fill=True, new_x='LMARGIN', new_y='NEXT')

        self.set_text_color(51, 51, 51)
        self.ln(3)

    def table_row(self, cells, header=False):
        if header:
            self.set_font('Helvetica', 'B', 9)
            self.set_fill_color(67, 97, 238)
            self.set_text_color(255, 255, 255)
        else:
            self.set_font('Helvetica', '', 9)
            self.set_fill_color(249, 249, 249)
            self.set_text_color(51, 51, 51)

        col_width = 190 / len(cells)
        for cell in cells:
            cell = self.clean_text(str(cell))
            if len(cell) > 30:
                cell = cell[:27] + '...'
            self.cell(col_width, 7, cell, border=1, fill=header, align='L')
        self.ln()

    def add_image_if_exists(self, image_path, width=180):
        if Path(image_path).exists():
            try:
                self.ln(5)
                self.image(str(image_path), w=width)
                self.ln(5)
            except Exception as e:
                self.body_text(f"[Imagen: {image_path}]")

    def clean_text(self, text):
        """Limpia caracteres Unicode no soportados"""
        # Reemplazar caracteres especiales
        replacements = {
            '\u2192': '->',  # flecha derecha
            '\u2190': '<-',  # flecha izquierda
            '\u2713': '[OK]',  # checkmark
            '\u2714': '[OK]',  # checkmark grueso
            '\u2715': '[X]',  # X
            '\u2716': '[X]',  # X gruesa
            '\u2022': '*',   # bullet
            '\u25cf': '*',   # circulo negro
            '\u25cb': 'o',   # circulo blanco
            '\u2500': '-',   # linea horizontal
            '\u2502': '|',   # linea vertical
            '\u250c': '+',   # esquina sup izq
            '\u2510': '+',   # esquina sup der
            '\u2514': '+',   # esquina inf izq
            '\u2518': '+',   # esquina inf der
            '\u251c': '+',   # T izq
            '\u2524': '+',   # T der
            '\u252c': '+',   # T arriba
            '\u2534': '+',   # T abajo
            '\u253c': '+',   # cruz
            '\u2550': '=',   # doble linea h
            '\u2551': '||',  # doble linea v
            '\u25b6': '>',   # triangulo derecha
            '\u25b2': '^',   # triangulo arriba
            '\u25bc': 'v',   # triangulo abajo
            '\u2026': '...', # ellipsis
            '\u201c': '"',   # comilla izq
            '\u201d': '"',   # comilla der
            '\u2018': "'",   # comilla simple izq
            '\u2019': "'",   # comilla simple der
            '\u2013': '-',   # en dash
            '\u2014': '--',  # em dash
            '\u2588': '#',   # bloque lleno
            '\u2591': '.',   # bloque claro
            '\u2592': ':',   # bloque medio
            '\u2593': '#',   # bloque oscuro
            '\u2610': '[ ]', # checkbox vacio
            '\u2611': '[x]', # checkbox marcado
            '\u2612': '[X]', # checkbox X
            '\u26a0': '[!]', # warning
            '\u2757': '[!]', # exclamation
            '\u2705': '[OK]', # check verde
            '\u274c': '[X]', # X roja
            '\u26d4': '[X]', # prohibido
            '\u2b50': '*',   # estrella
            '\u2764': '<3',  # corazon
            '\u231b': '[T]', # reloj arena
            '\u23f0': '[T]', # reloj
            '\u2699': '[G]', # engranaje
            '\u27a4': '>',   # flecha
            '\u2b06': '^',   # flecha arriba
            '\u2b07': 'v',   # flecha abajo
            '\u27a1': '->',  # flecha derecha
            '\u2b05': '<-',  # flecha izquierda
            '\u25aa': '*',   # cuadrado pequeno
            '\u25ab': 'o',   # cuadrado blanco
            '\u2796': '-',   # menos
            '\u2795': '+',   # mas
            '\u2716': 'x',   # multiplicar
            '\u2797': '/',   # dividir
            '━': '-',
            '─': '-',
            '│': '|',
            '┌': '+',
            '┐': '+',
            '└': '+',
            '┘': '+',
            '├': '+',
            '┤': '+',
            '┬': '+',
            '┴': '+',
            '┼': '+',
            '▶': '>',
            '▼': 'v',
            '█': '#',
            '░': '.',
            '✅': '[OK]',
            '❌': '[X]',
            '⚠': '[!]',
            '⏳': '[T]',
            '💡': '[i]',
        }

        for old, new in replacements.items():
            text = text.replace(old, new)

        # Eliminar cualquier otro caracter no ASCII
        text = text.encode('ascii', 'replace').decode('ascii')
        return text


def parse_markdown_to_pdf(md_content, pdf):
    """Parsea markdown y genera PDF"""
    lines = md_content.split('\n')
    in_code_block = False
    code_buffer = []
    in_table = False
    table_rows = []

    i = 0
    while i < len(lines):
        line = lines[i]

        # Code blocks
        if line.startswith('```'):
            if in_code_block:
                pdf.code_block('\n'.join(code_buffer))
                code_buffer = []
                in_code_block = False
            else:
                in_code_block = True
            i += 1
            continue

        if in_code_block:
            code_buffer.append(line)
            i += 1
            continue

        # Tables
        if '|' in line and not line.startswith('```'):
            cells = [c.strip() for c in line.split('|')[1:-1]]
            if cells and all(c.replace('-', '').replace(':', '') == '' for c in cells):
                # Es linea separadora de tabla
                i += 1
                continue
            if cells:
                if not in_table:
                    in_table = True
                    pdf.table_row(cells, header=True)
                else:
                    pdf.table_row(cells, header=False)
            i += 1
            continue
        else:
            in_table = False

        # Headers
        if line.startswith('# '):
            pdf.chapter_title(line[2:], level=1)
        elif line.startswith('## '):
            pdf.chapter_title(line[3:], level=2)
        elif line.startswith('### '):
            pdf.chapter_title(line[4:], level=3)
        elif line.startswith('#### '):
            pdf.chapter_title(line[5:], level=4)

        # Horizontal rule
        elif line.strip() in ['---', '***', '___']:
            pdf.ln(5)
            pdf.set_draw_color(200, 200, 200)
            pdf.line(10, pdf.get_y(), 200, pdf.get_y())
            pdf.ln(5)

        # Images
        elif '![' in line:
            match = re.search(r'!\[.*?\]\((.*?)\)', line)
            if match:
                img_path = DOC_DIR / match.group(1)
                pdf.add_image_if_exists(img_path)

        # Regular text
        elif line.strip():
            # Limpiar markdown inline
            text = re.sub(r'\*\*(.*?)\*\*', r'\1', line)  # bold
            text = re.sub(r'\*(.*?)\*', r'\1', text)      # italic
            text = re.sub(r'`(.*?)`', r'\1', text)        # inline code
            text = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', text)  # links

            # Bullets
            if text.strip().startswith('- ') or text.strip().startswith('* '):
                text = '  * ' + text.strip()[2:]
            elif re.match(r'^\d+\. ', text.strip()):
                text = '  ' + text.strip()

            pdf.body_text(text)

        i += 1


# Main
print("Generando PDF del informe...")

# Leer markdown
md_content = MD_FILE.read_text(encoding='utf-8')

# Crear PDF
pdf = PDFReport()
pdf.alias_nb_pages()

# Parsear y generar
parse_markdown_to_pdf(md_content, pdf)

# Guardar
pdf.output(str(PDF_FILE))

print(f"PDF generado: {PDF_FILE}")
print(f"Tamano: {PDF_FILE.stat().st_size / 1024:.1f} KB")
