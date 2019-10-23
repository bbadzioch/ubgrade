import io
import numpy as np
import pdf2image
import PyPDF2 as pdf
import os
import pyzbar.pyzbar as pyz
import cv2


def pdfpage2img(pdf_page, dpi=200):

    '''
    Converts a single pdf page into an image.
    :pdf_page:
        A PdfFileWriter object.
    :dpi:
        Resolution of the image produced from the pdf.

    Returns:
        A numpy array with the image.
    '''

    pdf_bytes = io.BytesIO()
    pdf_page.write(pdf_bytes)
    pdf_bytes.seek(0)
    page_image = np.array(pdf2image.convert_from_bytes(pdf_bytes.read(), dpi = dpi)[0])
    pdf_bytes.close()

    return page_image


def extract_pages(inputpdf, fpage, lpage):

    '''
    Extracts specified range of pages from a PyPDF2 PdfFileReader object.

    :inputpdf:
        A PyPDF2 PdfFileReader object.
    :fpage:
        Page number of the first page to be extracted.
    :lpage:
        Page number of the last page to be extracted.

    Returns:
        PyPDF2 PdfFileWriter object containing extracted pages
    '''

    output = pdf.PdfFileWriter()
    for i in range(fpage-1,lpage-1):
        output.addPage(inputpdf.getPage(i))
    return output


def pdf2pages(fname, output_fname=None, output_directory = None):

    '''
    Splits a pdf file into files containing individual pages

    :fname:
        Name of the pdf file.
    :output_fname:
        If string, output files will be named output_fname_n.pdf where n is the page number.
        This argument can be also a function with signature f(fname, n, page) which returns a string.
        The page argument will be passed the PyPDF2 PdfFileWriter object with the n-th page of the pdf file.
        If output_fname is a function, output files will be named by return values of this function.
        Defaults to the name of the processed file.
    :output_directory:
        directory where output files will be saved. If the specified directory is does not exist it will
        be created. Defaults to the current working directory

    Returns:
        The list of file names created.
    '''

    # if no output_directory set it to the current directory
    if output_directory == None:
         output_directory = os.getcwd()
    # is specified directory does not exist create it
    if not os.path.isdir(output_directory):
        os.makedirs(output_directory)

    if output_fname == None:
        output_fname = os.path.basename(fname)[:-4]

    if type(output_fname) == str:
        def label(n, page):
            s = f"{output_fname}_{n}.pdf"
            return s
    else:
        def label(n, page):
            return output_fname(fname, n, page)

    source = pdf.PdfFileReader(open(fname, 'rb'))
    num_pages = source.numPages
    outfiles = []
    for n in range(num_pages):
        page = extract_pages(source, n+1, n+2)
        outfile_name = label(n, page)
        outfile_path = os.path.join(output_directory, outfile_name)
        with open(outfile_path , "wb") as f:
            page.write(f)
        outfiles.append(outfile_name)
    return outfiles


def merge_pdfs(files, output_fname="merged.pdf"):
    '''
    Merge pdf files into a single pdf file.

    :files:
        A list of pdf file names.
    :output_fname:
        File name of the merged pdf file.

    Returns:
        None
    '''

    output = pdf.PdfFileMerger()

    for f in files:
            output.append(f)
    with open(output_fname , "wb") as outpdf:
                output.write(outpdf)
    output.close()


def enhanced_qr_decode(img, xmax=5, ymax=5):
    '''
    Enhanced decoder of QR codes. Can help with reading QR codes in noisy images.
    If a QR code is not found in the original image, the function performs a series
    of morphological openings and closures on the image with various parametries in
    an attempty to enhance the QR code.

    :img:
        A numpy array encoding the image.
        Note: matrix entries must be unsigned integers in the range 0-255
    :xmax:
    :ymax:
        Maximal values of parameters for computing openings and closures on the image.

    Returns:
        A list of pyzbar objects with decoded QR codes. The list is empty if no codes
        were found.
    '''

    # read a QR code
    qr = pyz.decode(img)

    # if QR code is not found, modify the image and try again
    if len(qr) == 0:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)[1]
        for i, j in [(i, j) for i in range(1, xmax+1) for j in range(1, ymax+1)]:
            opened = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, np.ones((i, j)))
            opened = cv2.bitwise_not(opened)
            qr = pyz.decode(opened)
            if len(qr) != 0:
                break
            closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, np.ones((i, j)))
            closed = cv2.bitwise_not(closed)
            qr = pyz.decode(closed)
            if len(qr) != 0:
                break
    return qr
