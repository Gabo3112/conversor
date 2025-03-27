import tkinter as tk
from tkinter import filedialog, messagebox
import xml.etree.ElementTree as ET
import os
import sys
import subprocess
from PyPDF2 import PdfReader
from tkinter import simpledialog

# ReportLab
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF

def resource_path(relative_path):
    """ Obtiene la ruta absoluta al recurso, funciona para desarrollo y para PyInstaller """
    try:
        # PyInstaller crea una carpeta temporal y almacena la ruta en _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

# Variable global para almacenar la data parseada del XML
parsed_data = None

def parse_xml(xml_path):
    """
    Parsea el archivo XML UBL y retorna un diccionario con datos importantes:
    """
    namespaces = {
        'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
        'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
        'ext': 'urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2'
    }
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except Exception as e:
        messagebox.showerror("Error", f"No se pudo parsear el XML: {e}")
        return None

    data = {}
    # Número y fecha/hora
    data['invoice_number'] = root.find('./cbc:ID', namespaces).text if root.find('./cbc:ID', namespaces) is not None else "N/A"
    data['issue_date'] = root.find('./cbc:IssueDate', namespaces).text if root.find('./cbc:IssueDate', namespaces) is not None else ""
    data['issue_time'] = root.find('./cbc:IssueTime', namespaces).text if root.find('./cbc:IssueTime', namespaces) is not None else ""

    # Tipo de documento (Boleta o Factura)
    invoice_type_code = root.find('./cbc:InvoiceTypeCode', namespaces)
    if invoice_type_code is not None:
        if invoice_type_code.text == '01':
            data['tipo_documento'] = "FACTURA"
        elif invoice_type_code.text == '03':
            data['tipo_documento'] = "BOLETA"
        else:
            data['tipo_documento'] = "DESCONOCIDO"
    else:
        data['tipo_documento'] = "DESCONOCIDO"

    # Monto en letras
    note_elem = root.find('./cbc:Note[@languageLocaleID="1000"]', namespaces)
    if note_elem is not None:
        # Suele venir con "SON: SETENTA Y 00/100 SOLES"
        data['monto_letras'] = note_elem.text.strip()
    else:
        data['monto_letras'] = ""

    # Total (PayableAmount)
    total_elem = root.find('.//cac:LegalMonetaryTotal/cbc:PayableAmount', namespaces)
    data['total'] = total_elem.text if total_elem is not None else "0.00"

    # Subtotal (LineExtensionAmount en LegalMonetaryTotal)
    line_ext_elem = root.find('.//cac:LegalMonetaryTotal/cbc:LineExtensionAmount', namespaces)
    data['subtotal'] = line_ext_elem.text if line_ext_elem is not None else "0.00"

    # Calcular IGV como el 18% del subtotal
    try:
        subtotal = float(data['subtotal'])
        #data['igv'] = f"{subtotal * 0.18:.2f}"  # Calcula el 18% del subtotal y lo formatea a 2 decimales
    except ValueError:
        data['igv'] = "0.00"  # Si no se puede convertir a float, se asigna "0.00"

    # Emisor
    supplier_name_elem = root.find('.//cac:AccountingSupplierParty//cbc:RegistrationName', namespaces)
    data['supplier'] = supplier_name_elem.text if supplier_name_elem is not None else "N/A"
    supplier_ruc_elem = root.find('.//cac:AccountingSupplierParty//cac:PartyIdentification/cbc:ID', namespaces)
    data['supplier_ruc'] = supplier_ruc_elem.text if supplier_ruc_elem is not None else ""
    address_elem = root.find('.//cac:AccountingSupplierParty//cac:PartyLegalEntity//cac:RegistrationAddress//cac:AddressLine//cbc:Line', namespaces)
    data['direccion_emisor'] = address_elem.text if address_elem is not None else "Dirección no especificada"

    # Cliente
    customer_name_elem = root.find('.//cac:AccountingCustomerParty//cbc:RegistrationName', namespaces)
    data['nombre_cliente'] = customer_name_elem.text if customer_name_elem is not None else "N/A"
    customer_doc_elem = root.find('.//cac:AccountingCustomerParty//cac:PartyIdentification/cbc:ID', namespaces)
    data['documento_cliente'] = customer_doc_elem.text if customer_doc_elem is not None else ""
    data['direccion_cliente'] = "No disponible"  # o parsear si viene en el XML

    # Items
    data['items'] = []
    invoice_lines = root.findall('.//cac:InvoiceLine', namespaces)
    for invoice_line in invoice_lines:
        qty_elem = invoice_line.find('./cbc:InvoicedQuantity', namespaces)
        quantity = qty_elem.text if qty_elem is not None else "1"

        desc_elem = invoice_line.find('.//cac:Item/cbc:Description', namespaces)
        description = desc_elem.text if desc_elem is not None else "Sin descripción"

        line_total_elem = invoice_line.find('./cbc:LineExtensionAmount', namespaces)
        line_total = line_total_elem.text if line_total_elem is not None else "0.00"

        # Valor unitario (generalmente <cac:Price>/<cbc:PriceAmount>)
        price_elem = invoice_line.find('./cac:Price/cbc:PriceAmount', namespaces)
        valor_unitario = price_elem.text if price_elem is not None else "0.00"

        item = {
            'quantity': quantity,
            'description': description,
            'valor_unitario': valor_unitario,
            'line_total': line_total
        }
        data['items'].append(item)

    return data

def seleccion_archivo(entry_xml, vista_previa):
    """
    Permite seleccionar el archivo XML y muestra un resumen en 'vista_previa'.
    """
    global parsed_data
    ruta_xml = filedialog.askopenfilename(
        title="Seleccionar archivo XML",
        filetypes=(("Archivos XML", "*.xml"), ("Todos los archivos", "*.*"))
    )
    if ruta_xml:
        entry_xml.delete(0, 'end')
        entry_xml.insert(0, ruta_xml)
        data = parse_xml(ruta_xml)
        if data:
            parsed_data = data
            # Construimos un texto de ejemplo para la vista previa
            lines = []
            lines.append(f"EMISOR: {data['supplier']} (RUC: {data['supplier_ruc']})")
            lines.append(f"DIRECCIÓN: {data['direccion_emisor']}")
            lines.append(f"COMPROBANTE: {data['invoice_number']}")
            lines.append(f"FECHA: {data['issue_date']}   HORA: {data['issue_time']}")
            lines.append(f"CLIENTE: {data['nombre_cliente']}")
            lines.append("-" * 50)
            lines.append("ITEMS:")
            for i, item in enumerate(data['items'], start=1):
                lines.append(f"{i}) {item['quantity']} x {item['description']} => {item['line_total']}")
            lines.append("-" * 50)
            lines.append(f"TOTAL: S/ {data['total']}")
            
            vista_previa.delete(1.0, 'end')
            vista_previa.insert('end', "\n".join(lines))
        else:
            vista_previa.delete(1.0, 'end')
            vista_previa.insert('end', "No se pudo extraer el contenido del XML.")

def generar_ticket_personalizado(data, pdf_path, logo_path=None):
    """
    Genera un PDF en formato ticket (~80mm de ancho).
    Incluye datos de empresa, cliente, ítems, totales, IGV, monto en letras, etc.
    """
    ticket_width = 80 * mm
    ticket_height = 250 * mm  

    c = canvas.Canvas(pdf_path, pagesize=(ticket_width, ticket_height))
    y = ticket_height - 5 * mm  # Margen superior

    # 1) Logo y nombre de la institución
    if logo_path and os.path.isfile(logo_path):
        logo_width = 20 * mm  # Ajusta el tamaño del logo
        logo_height = 20 * mm
        c.drawImage(
            logo_path,
            3 * mm,  # Posición X (5mm desde el borde izquierdo)
            y - logo_height,  # Posición Y
            logo_width,
            logo_height,
            preserveAspectRatio=True,
            anchor='nw'
        )
        # Dibujar el nombre al lado del logo
        c.setFont("Helvetica-Bold", 10)
        c.drawString(22 * mm, y - 50, "I.E.P FREDERICK MAYER")
        y -= (logo_height + 6 * mm)  # Ajustar la posición Y para el resto del contenido

    # 2) Nombre de la empresa, RUC, dirección
    #c.setFont("Helvetica-Bold", 9)
    #c.drawCentredString(ticket_width / 2, y, data.get('supplier','NOMBRE DE EMPRESA'))
    #y -= 12

    c.setFont("Helvetica", 8)
    c.drawCentredString(ticket_width / 2, y, f"RUC: {data.get('supplier_ruc','')}")
    y -= 10

    c.drawCentredString(ticket_width / 2, y, data.get('direccion_emisor',''))
    y -= 10

    # 2.1) Tipo de documento (Boleta o Factura)
    c.drawCentredString(ticket_width / 2, y, f"Tipo: {data.get('tipo_documento','DESCONOCIDO')}")
    y -= 10

    # 3) Teléfono (placeholder)
    c.drawCentredString(ticket_width / 2, y, "Teléfono: 000000000")
    y -= 15

    # Línea separadora
    c.line(5 * mm, y, ticket_width - 5 * mm, y)
    y -= 10

    # 4) Fecha, caja, cajero, ticket nro
    fecha = data.get('issue_date','')
    hora = data.get('issue_time','')
    c.setFont("Helvetica", 7)
    c.drawCentredString(ticket_width / 2, y, f"Fecha: {fecha} {hora}")
    y -= 10
    c.drawCentredString(ticket_width / 2, y, "Caja Nro: 1")  # placeholder
    y -= 10
    c.drawCentredString(ticket_width / 2, y, "Cajero: admin")  # placeholder
    y -= 10
    c.drawCentredString(ticket_width / 2, y, f"TICKET NRO: {data.get('invoice_number','')}")
    y -= 15

    # Línea separadora
    c.line(5 * mm, y, ticket_width - 5 * mm, y)
    y -= 10

    # 5) Datos del cliente
    c.setFont("Helvetica-Bold", 7)
    c.drawString(5 * mm, y, "Cliente:")
    c.setFont("Helvetica", 7)
    c.drawString(20 * mm, y, data.get('nombre_cliente',''))
    y -= 10

    c.setFont("Helvetica-Bold", 7)
    c.drawString(5 * mm, y, "Documento:")
    c.setFont("Helvetica", 7)
    c.drawString(25 * mm, y, data.get('documento_cliente',''))
    y -= 10

    c.setFont("Helvetica-Bold", 7)
    c.drawString(5 * mm, y, "Dirección:")
    c.setFont("Helvetica", 7)
    c.drawString(20 * mm, y, data.get('direccion_cliente',''))
    y -= 15

    # Línea separadora
    c.line(5 * mm, y, ticket_width - 5 * mm, y)
    y -= 10

    # 6) Cabecera de detalle de ítems
    c.setFont("Helvetica-Bold", 7)
    c.drawString(5 * mm, y, "Cant.")  # Columna de cantidad
    c.drawString(20 * mm, y, "Descripción")  # Columna de descripción
    c.drawRightString(ticket_width - 5 * mm, y, "Importe")  # Columna de importe
    y -= 10

    c.line(5 * mm, y, ticket_width - 5 * mm, y)
    y -= 8

    # 7) Detalle de ítems
    c.setFont("Helvetica", 7)
    for item in data.get('items', []):
        qty = item.get('quantity','1')
        desc = item.get('description','')
        line_total = item.get('line_total','0.00')

        # Cantidad
        c.drawString(5 * mm, y, qty)

        # Descripción (dividida en varias líneas si supera el límite de caracteres)
        max_chars_per_line = 26  # Límite de caracteres por línea
        desc_lines = [desc[i:i+max_chars_per_line] for i in range(0, len(desc), max_chars_per_line)]

        # Dibujar la primera línea de la descripción y el importe
        if desc_lines:
            c.drawString(20 * mm, y, desc_lines[0])  # Primera línea de la descripción
            c.drawRightString(ticket_width - 5 * mm, y, line_total)  # Importe alineado a la derecha
            y -= 8  # Espacio entre líneas de descripción

        # Dibujar las líneas restantes de la descripción (si las hay)
        for line in desc_lines[1:]:
            c.drawString(20 * mm, y, line)  # Líneas adicionales de la descripción
            y -= 5  # Espacio entre líneas de descripción

        y -= 10  # Espacio entre ítems

    # Línea separadora
    y -= 5
    c.line(5 * mm, y, ticket_width - 5 * mm, y)
    y -= 10

    # 8) Subtotal, IGV, Total
    c.setFont("Helvetica-Bold", 7)

    c.drawString(5 * mm, y, "SUBTOTAL:")
    c.drawRightString(ticket_width - 5 * mm, y, data.get('subtotal','0.00'))
    y -= 10

    c.drawString(5 * mm, y, "IGV (18%):")
    c.drawRightString(ticket_width - 5 * mm, y, data.get('igv','0.00'))
    y -= 10

    c.drawString(5 * mm, y, "TOTAL:")
    c.drawRightString(ticket_width - 5 * mm, y, data.get('total','0.00'))
    y -= 15

    # 9) Monto en letras
    c.setFont("Helvetica", 7)
    monto_letras = data.get('monto_letras','')
    if monto_letras:
        c.drawString(5 * mm, y, f"{monto_letras}")
        y -= 15

    # Línea separadora
    c.line(5 * mm, y, ticket_width - 5 * mm, y)
    y -= 15

    # 10) Mensaje final
    c.setFont("Helvetica", 6)
    c.drawCentredString(ticket_width / 2, y, "** Precios de productos incluyen impuestos **")
    y -= 10
    c.drawCentredString(ticket_width / 2, y, "Gracias por su compra")
    y -= 10

    c.showPage()
    c.save()

def guardar_ticket(vista_previa):
    global parsed_data
    if not parsed_data:
        messagebox.showwarning("Advertencia", "No hay datos parseados para generar el ticket.")
        return

    # Obtener ruta del escritorio del usuario
    desktop_path = os.path.join(os.path.expanduser("~"), "Desktop", "PDFTicket")

    # Crear la carpeta si no existe
    if not os.path.exists(desktop_path):
        os.makedirs(desktop_path)

    # Construir nombre de archivo con formato: NUMERODOC_NOMBRECLIENTE_FECHA.pdf
    default_filename = f"{parsed_data.get('invoice_number', 'TICKET')}_{parsed_data.get('nombre_cliente', 'CLIENTE')}_{parsed_data.get('issue_date', 'FECHA')}.pdf"
    
    # Ruta completa con la carpeta por defecto
    ruta_pdf_ticket = os.path.join(desktop_path, default_filename)

    #logo_path = resource_path("logo_FMayer.png")
    logo_path = resource_path("FMayer.png")


    try:
        # Generar el PDF ticket
        generar_ticket_personalizado(parsed_data, ruta_pdf_ticket, logo_path=logo_path)  # Cambia la ruta del logo
        messagebox.showinfo("Éxito", f"PDF ticket guardado en:\n{ruta_pdf_ticket}")
    except Exception as e:
        messagebox.showerror("Error", f"No se pudo generar el ticket: {e}")

def visualizar_pdf():
    """
    Permite seleccionar un PDF y visualizar su contenido.
    """
    ruta_pdf = filedialog.askopenfilename(
        title="Seleccionar archivo PDF",
        filetypes=(("Archivos PDF", "*.pdf"), ("Todos los archivos", "*.*")),
        initialdir=os.path.join(os.path.expanduser("~"), "Desktop", "PDFTicket")
    )
    if ruta_pdf:
        try:
            reader = PdfReader(ruta_pdf)
            contenido = ""
            for page in reader.pages:
                contenido += page.extract_text()
            ventana_contenido = tk.Toplevel()
            ventana_contenido.title("Contenido del PDF")
            texto_contenido = tk.Text(ventana_contenido, wrap='word')
            texto_contenido.insert('end', contenido)
            texto_contenido.pack(fill='both', expand=True)
            #ICONO
            ventana_contenido.iconbitmap(resource_path("icono.ico"))

            # Botón de imprimir
            boton_imprimir = tk.Button(ventana_contenido, text="Imprimir", command=lambda: imprimir_pdf(ruta_pdf))
            boton_imprimir.pack()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo leer el PDF: {e}")

def imprimir_pdf(ruta_pdf):
    """
    Abre un diálogo de impresión para imprimir el PDF seleccionado.
    """
    try:
        subprocess.Popen(['start', '', ruta_pdf], shell=True)
    except Exception as e:
        messagebox.showerror("Error", f"No se pudo abrir el diálogo de impresión: {e}")

def main():
    """
    Interfaz principal.
    """
    root = tk.Tk()
    root.title("Conversor de XML a PDF Ticket")
    root.geometry("600x400")

    # ICONO
    root.iconbitmap(resource_path("icono.ico"))
    # root.iconbitmap("icono.ico")
    
    label_xml = tk.Label(root, text="Seleccionar archivo XML:")
    label_xml.grid(row=0, column=0, padx=10, pady=10)

    entry_xml = tk.Entry(root, width=40)
    entry_xml.grid(row=0, column=1, padx=10, pady=10)

    # Vista previa (muestra un texto resumen de los datos del XML)
    vista_previa = tk.Text(root, wrap='word', height=15, width=70)
    vista_previa.grid(row=2, column=0, columnspan=3, padx=10, pady=10)

    # Botón para buscar XML
    button_seleccionar = tk.Button(
        root, 
        text="Buscar XML", 
        command=lambda: seleccion_archivo(entry_xml, vista_previa)
    )
    button_seleccionar.grid(row=1, column=2, padx=10, pady=10)

    # Botón para guardar ticket
    button_guardar = tk.Button(
        root, 
        text="Guardar PDF ticket", 
        command=lambda: guardar_ticket(vista_previa)
    )
    button_guardar.grid(row=3, column=0, padx=10, pady=10)

    # Botón para visualizar PDF
    button_visualizar_pdf = tk.Button(
        root,
        text="Visualizar PDF",
        command=visualizar_pdf
    )
    button_visualizar_pdf.grid(row=3, column=2, padx=10, pady=10)

    root.mainloop()

if __name__ == "__main__":
    main()