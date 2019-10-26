import os
import io
import PyPDF2 as pdf


from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF



def make_exams(template, N, qr_prefix, output_file=None, output_directory = None, add_backpages = False):

    '''
    Produces pdf files with copies of an exam with QR codes identifying each page of each copy added.

    :tamplate:
        Name of the pdf file to make copies from.
    :N:
        Integer. The number of copies to be produced.
    :qr_prefix:
        Prefix of QR codes added to the pdf file pages. The QR code for each page
        will be (qr_prefix)_C(copy number)_P(page number). (e.g. MTH309_C002_P03, for
        the 3rd page of the second copy of the exam with qr_prefix="MTH309").
        If qr_prefix is an empty string, QR codes will have the form (copy number)_P(page number)
        (e.g. 002_P03).
    :output_file:
        Name of the pdf files to be produced; these files will be named
        output_file_n.pdf where n is the number of the exam copy.
        If  output_file is None, the name of the template file name is used.
    :output_directory:
        Name of the directory where the pdf files will be saved.
        If None, the current directory will be used. If the given directory
        does not exist, it will be created.
    :add_backpages:
        Adds back pages to the pdf file with a message that these pages will not
        be graded. This is intended for two-sided printing.

    Returns:
        None
    '''

    if output_directory == None:
        output_directory = os.getcwd()
    # create the output directory if needed
    if not os.path.isdir(output_directory):
        os.makedirs(output_directory)

    # if no name of the output file, use the template file name
    if output_file == None:
        output_file = os.path.basename(template)
    output_file = os.path.splitext(output_file)[0]

    if qr_prefix != "":
        qr_prefix = qr_prefix + "-"

    # produce exam copies
    for n in range(1, N+1):

        source = pdf.PdfFileReader(open(template, 'rb'))
        print(f"Processing copy number: {n}\r", end="")
        writer = pdf.PdfFileWriter()

        # iterate over exam pages
        for k in range(source.numPages):

            # create a pdf page with the QR code
            qr_string = f"{qr_prefix}C{n:03}-P{k:02}"
            pdf_bytes = io.BytesIO()

            c = canvas.Canvas(pdf_bytes, pagesize=letter)
            c.setFont('Courier', 11.5)
            c.setFillColor("black")
            c.drawRightString(6.6*inch,9.54*inch, qr_string)

            qr_code = qr.QrCodeWidget(qr_string, barLevel = "H")
            bounds = qr_code.getBounds()
            width = bounds[2] - bounds[0]
            height = bounds[3] - bounds[1]
            d = Drawing(transform=[80./width,0,0,80./height,0,0])
            d.add(qr_code)
            renderPDF.draw(d, c, 6.65*inch, 9.4*inch)
            c.save()

            # merge the QR code page with the exam page
            qr_pdf = pdf.PdfFileReader(pdf_bytes).getPage(0)
            page = source.getPage(k)
            page.mergePage(qr_pdf)
            writer.addPage(page)

            # create and add back pages if needed
            if  add_backpages:
                back_str1 = "THIS PAGE WILL NOT BE GRADED"
                back_str2 = "USE IT FOR SCRATCHWORK ONLY"
                back_bytes = io.BytesIO()
                back = canvas.Canvas(back_bytes, pagesize=letter)
                back.setFont('Helvetica', 12)
                back.setFillColor("black")
                back.drawCentredString(4.25*inch, 8*inch, back_str1)
                back.drawCentredString(4.25*inch, 7.8*inch, back_str2)
                back.save()
                back_pdf = pdf.PdfFileReader(back_bytes).getPage(0)
                writer.addPage(back_pdf)

        # save an exam copy
        destination  = os.path.join(output_directory, f"{output_file}_{n:03}.pdf")
        with open(destination, "wb") as foo:
            writer.write(foo)

    print("QR coded files ready." + 40*" ")
