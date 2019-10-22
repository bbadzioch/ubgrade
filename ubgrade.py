import os
import subprocess
import re
import itertools
import glob
import io
import json
import tempfile
import shutil
from time import sleep

import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

import pyzbar.pyzbar as pyz
import cv2

import PyPDF2 as pdf
import pdf2image

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF


from email.message import EmailMessage
import smtplib
import getpass





class GradingBase():

    '''
    Base class establishing file and directory structure used in grading.
    '''

    def __init__(self, main_dir = None, gradebook = None, init_grading_data=False):
        '''
        Converts a single pdf page into an image.
        :main_dir:
            The main directory in which all grading files will be stored.
            Prior to the start of grading it should contain a subdirectory
            named 'scans' with with pdf files of scanned exams. If main_dir
            is None the current working directory will be used.
        :gradebook:
            A csv file used in grading. Prior to the start of grading it should
            contain at least one column with heading 'person_number' containing
            person numbers of students taking the exam. If gradebook is None,
            it will be assumed that the gradebook file is called gradebook.csv
            and it is located in main_dir.
        :init_grading_data:
            Bollean. If True, auxiliary files used in grading will be reset to the
            initial status, and the grading process will start from scratch.
        '''

        if main_dir is None:
            self.main_dir = os.getcwd()
        else:
            self.main_dir = main_dir

        # the directory with scanned exams
        self.scans_dir = os.path.join(self.main_dir, "scans")
        # a directory for temporary files used in the grading process
        self.pages_dir = os.path.join(self.main_dir, "pages")
        # a directory where pdf files prepared for grading will be stored
        self.for_grading_dir = os.path.join(self.main_dir, "for_grading")
        # a directory in which graded files, re-assembled by student will be saved
        self.graded_dir = os.path.join(self.main_dir, "graded")

        if gradebook is None:
            self.gradebook = os.path.join(self.main_dir, "gradebook.csv")
        else:
            self.gradebook = gradebook

        # a pdf file used for exam pages where user input us needed to get QR code or person number
        self.missing_data_pages = os.path.join(self.scans_dir, "missing_data.pdf")
        # a json file with data structures used in the grading process
        self.grading_data_jfile = os.path.join(self.main_dir, "grading_data.json")


        # initial structure of the data in the self.grading_data_jfile file:
        # maxpoints: a dictionary used for storing the maximal possible score for each exam problem
        # processed scans: a list which records which scanned files have been processed
        # page lists: when exams are assembled by problem, it records which file contains which exam pages and in which order
        # missing data: records which scanned pages require user input to get a QR code or person number
        # emails_sent: when graded exams are emailed to students, this list records which emails have been sent
        self.init_grading_data = {"maxpoints": {},
                                  "processed_scans": [],
                                  "page_lists" : {},
                                  "missing_data" : [],
                                  "emails_sent" : []
                                  }
        if init_grading_data:
            self.set_grading_data(self.init_grading_data)
            if os.path.isfile(self.missing_data_pages):
                 os.remove(self.missing_data_pages)


        # Columns of the self.gradebook file. The file must have the self.pnum_column to start the grading
        # process, and the self.email_column when the graded exams are being sent to students. The other
        # columns will be created automatically, if needed.
        self.pnum_column = "person_number"
        self.email_column = "email"
        self.qr_code_column = "qr_code"
        self.total_column = "total"
        self.grade_column = "grade"


        # dimensions of score tables embeded on the exam pages
        # page width
        self.page_w = 8.5*inch
        # margin of the score table
        self.table_margin = 0.05*inch
        # table height and width
        self.table_h = 0.5*inch
        self.table_w = self.page_w - 2*self.table_margin
        # size of score boxes
        self.box_size = 0.19*inch
        # spacing of score boxes
        self.box_spacing = 0.11*inch
        # distance between the leftmost score box and the left edge of the score table
        self.box_left_pad = 0.15*inch
        # position of the bottom of score boxes
        self.box_bottom = 0.28*inch
        # vertical position of the textline of score box labels
        self.text_label_bottom = 0.12*inch
        # spacing between the size of a score box and score mark inserted into the box
        self.mark_margin = 0.01*inch

    # functions used to read and write data from/to the self.grading_data_jfile file
    def get_grading_data(self):
        if os.path.isfile(self.grading_data_jfile):
            with open(self.grading_data_jfile) as foo:
                return json.load(foo)
        else:
            return self.init_grading_data

    def set_grading_data(self, data):
        with open(self.grading_data_jfile, 'w') as foo:
            json.dump(data, foo)


    def split_for_grading_files(self, dest_dir):
        '''
        When exams are assembled by problem, this function can be used to split them
        into individial pages, with file names reflecting the QR code on each page.

        :dest_dir:
            The directory where the pdf files with exam pages will be saved.
        '''

        files = glob.glob(os.path.join(self.for_grading_dir, "*_problem_*.pdf"))
        page_lists = self.get_grading_data()["page_lists"]

        for f in files:
            f_list = page_lists[os.path.basename(f)]
            def set_page_names(fname, n, page):
                return f_list[n]

            pdf2pages(f, output_fname=set_page_names, output_directory = dest_dir)



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
        If output_fname is a function, the output files will be named by return values of this function.
        Defaults to the name of the processed file.
    :output_directory:
        directory where output files will be saved. If the specified directory is does not exist it will
        be created. Defaults to the current working directory

    Returns:
        The list of file names created.

    Note: Page splitting seems to interfere with checkboxes embedded in pages.
    After splitting they can't be read, but if checkboxes are reselected they
    work again. Splitting pages using pdftk does not create this problem:
    os.system('pdftk merged.pdf burst > test.txt')
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
    If a QR code is not found in the original image the function performs a series
    of morphological opening and closures on the image with various parametries in
    an attempty to enhance the QR code.

    :img:
        A numpy array encoding the image.
        Note: matrix entries must be integers in the range 0-255
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



# This function is not needed for the grading purposes anymore
def compile_latex(source, output_file, output_directory = None):
    '''
    Compiles a given string with LaTeX code into pdf  and cleans up all
    auxiliary files created in the process. Requires pdflatex to work.

    :source:
        String with LaTeX code to be compiled.
    :output_file:
        Name of the pdf file to be produced.
    :output_directory:
        Name of the directory where the pdf file will be saved.
        If none given the current directory will be used. If the given directory
        does not exist, it will be created.

    Returns:
        A tuple consisting of the pdflatex subprocess return code and
    its stdout stream
    '''


    if output_directory == None:
        output_directory = os.getcwd()
    # create the output directory if needed
    if not os.path.isdir(output_directory):
            os.makedirs(output_directory)

    output_file = os.path.splitext(os.path.basename(output_file))[0]
    tex_file_path = os.path.join(output_directory, output_file + ".tex")
    with open(tex_file_path, "w") as f:
        f.write(source)

    #compile LaTeX
    latex_command = ["pdflatex", "-shell-escape", "-output-directory", output_directory, output_file + ".tex"]
    completed = subprocess.run(latex_command, capture_output = True)

    # clean up the auxiliary files created during LaTeX compilation
    for f in os.listdir(output_directory):
        fl = os.path.splitext(f)
        if fl[0] == output_file and fl[-1] in ['.tex', '.aux', '.log', '.gz', '.out']:
            os.remove(os.path.join(output_directory, f))

    return  completed.returncode, completed.stdout



def add_qr_codes(template, N, qr_prefix, output_file=None, output_directory = None, add_backpages = False):

    '''
    Produces pdf files with copies of an exam with QR codes identifying each page of each copy added.

    :tamplate:
        Name of the pdf file to make copies from.
    :N:
        Integer. The number of copies to be produced.
    :qr_prefix:
        Prefix of QR codes added to the pdf file pages. The QR code for each page
        will be (qr_prefix)_(copy number)_P(page number). (e.g. MTH309_002_P03, for
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

    # produce exam copies
    for n in range(1, N+1):

        source = pdf.PdfFileReader(open(template, 'rb'))
        print(f"Processing copy number: {n}\r", end="")
        writer = pdf.PdfFileWriter()

        if qr_prefix != "":
            qr_prefix = qr_prefix + "-"

        # iterate over exam pages
        for k in range(source.numPages):

            # create a pdf page with the QR code
            qr_string = f"{qr_prefix}{n:03}-P{k:02}"
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


class ExamCode():

    '''
    Class defining methods for manipulating exam file names.
    '''

    def __init__(self, code):
        self.code = code
        self.head, self.tail = os.path.split(self.code)
        self.base, self.ext = os.path.splitext(self.tail)

    def has_table(self):
        '''
        Checks if a given file name corresponds to a pdf file of an exam page
        with a score table added.
        '''
        return self.base.startswith("t_")


    def get_exam_code(self):
        '''
        Strips the page number from an exam page QR code, leaving out the part
        identifying the exam copy.
        '''
        code =  "-".join(self.base.split("-")[:-1])
        if self.has_table():
            code = code[2:]
        return code

    def get_page_num(self):
        '''
        Returns the part of the exam page QR code giving the exam page number.
        '''
        return int(self.base.split("-")[-1][1:])

    def is_cover(self):
        '''
        Checks if a page is a cover page of an exam.
        '''
        return self.get_page_num() == 0

    def table_fname(self):
        '''
        A function which formats names of pdf files with exam pages with added
        score tables.

        :name:
            Name of the pdf file with an exam page.
        '''
        return os.path.join(self.head,  "t_" + self.tail)

    def get_exam_name(self):
        '''
        Get qr_prefix (exam copy nummber and page number striped)
        '''
        return "-".join(self.get_exam_code().split("-")[:-1])



def covers_file(f):
    '''
    Given a name of a pdf file with with copies of an exam page, checks
    if it consists of cover pages
    '''
    return "problem_0.pdf" in os.path.basename(f)


class PrepareGrading(GradingBase):
    '''
    Class defining mathods used to prepare exams for grading.
    '''

    def __init__(self, maxpoints, main_dir = None, gradebook = None, init_grading_data=False, show_pnums = False):
        '''
        :maxpoints:
            A list with the maximal possible score of each exam problem. Can be also given as an integer, if the maximal
            score for each problem is the same.
        :show_pnums:
            Boolean. If True, then when person numbers are read from  exam cover pages, images showing the reading process
            will be displayes.

        The reamining arguments are inherited from the GradingBase constructor.
        '''

        GradingBase.__init__(self, main_dir, gradebook, init_grading_data)

        if type(maxpoints) != list:
            maxpoints = [maxpoints]
        self.maxpoints = maxpoints
        self.show_pnums = show_pnums



    def draw_score_table(self, fname, output_file=None, points=20):

        '''
        Adds score tables to pdf files.

        :fname:
            Name of the source pdf file. The score table will be added to each page of this file.
        :output_file:
            Name of the file to be produced. If None, the output file will be saved as t_fname.
        :points:
            Integer. The maximal score in the score table. Should be not more than 25 to fit all score boxes.

        Returns:
            None
        '''

        # if no name of the output file given, use the source file name
        if output_file == None:
            head, tail = os.path.split(fname)
            output_file = os.path.join(head, "t_" + tail)

        # if source pdf is rotated we need to adjust parameters for merging it with
        # the score table; rotations dictionary stores these parameters for all possible
        # rotation angles
        rotations = {0: {"rotation": 0, "tx": 0.2*inch, "ty": 0.6*inch},
                     90: {"rotation": 270, "tx": 0.2*inch, "ty": 11.1*inch},
                     180: {"rotation": 180, "tx": 8.5*inch, "ty": 11.1*inch},
                     270: {"rotation": 90, "tx": 8.5*inch, "ty": 0.6*inch}}

        # scaling factor for the source pdf;
        # note: if the scale factor is changed then the values of tx and ty in the rotations
        # dictionary may need to be adjusted as well
        scale = 0.95

        source_file = pdf.PdfFileReader(open(fname, 'rb'))
        writer = pdf.PdfFileWriter()

        # iterate over source pages
        for k in range(source_file.numPages):

            source = source_file.getPage(k)

            # make pdf with the score table
            pdf_bytes = io.BytesIO()
            c = canvas.Canvas(pdf_bytes, pagesize=letter)

            # draw background of the score table
            c.setLineWidth(.5)
            c.setStrokeColor("red")
            c.setFillColorRGB(1, 0.85, 0.85)
            c.rect(self.table_margin, self.table_margin, self.table_w, self.table_h, stroke=1, fill=1)

            #draw score boxes
            c.setFont('Helvetica', 10)
            c.setStrokeColor("black")
            for i in range(points+1):
                c.setFillColor("white")
                c.rect(self.table_margin + self.box_left_pad +i*(self.box_size + self.box_spacing),
                       self.box_bottom,
                       self.box_size,
                       self.box_size,
                       stroke=1, fill=1)
                c.setFillColor("black")
                c.drawCentredString(self.table_margin + self.box_left_pad +i*(self.box_size + self.box_spacing) + 0.5*self.box_size,
                                    self.text_label_bottom,
                                    str(i))
            c.save()
            score_pdf = pdf.PdfFileReader(pdf_bytes).getPage(0)

            # get rotation angle of the source pdf
            try:
                rot = int(source.get('/Rotate'))%360
            except:
                rot = 0

            # merge the score table with the source pdf and save it
            score_pdf.mergeRotatedScaledTranslatedPage(source, scale = scale, **rotations[rot], expand=False)
            writer.addPage(score_pdf)

        # save the output file
        with open(output_file, "wb") as foo:
                writer.write(foo)


    def add_score_tables(self):
        '''
        Adds score tables to pdf files with exam pages. The resulting files
        are saved in the self.pages_dir with names prefixed by 't_'.
        I also writes the information what is the maximal score for each exam
        problem into the json file with grading data.
        '''

        # select pdf files with exam pages which do not have a score table
        files = glob.glob(os.path.join(self.pages_dir, "*.pdf"))
        files = [f for f in files if not ExamCode(f).has_table()]
        files.sort()

        grading_data = self.get_grading_data()
        max_score_dict = grading_data["maxpoints"]

        # iterate over pdf file with exam pages
        for f in files:

            fcode = ExamCode(f)
            output_file = fcode.table_fname()

            # if cover page, just copy it
            if fcode.is_cover():
                shutil.copy(f, os.path.join(self.pages_dir, output_file))
                continue

            # get the maximum score for an exam page
            page_num = fcode.get_page_num()
            max_score = self.maxpoints[min(page_num-1, len(self.maxpoints)-1)]
            max_score_dict[page_num] = max_score

            # add the score table
            self.draw_score_table(fname = f, output_file = os.path.join(self.pages_dir,output_file), points=max_score)
            print(f"{fcode.base} -> Done\r", end="")

        # save the dictionary with maximal possible scores to grading data
        grading_data = self.get_grading_data()
        grading_data["maxpoints"] = max_score_dict
        self.set_grading_data(grading_data)

        print("Score tables added")


    def read_bubbles(self, img, dilx=(4,10), dily=(10, 4)):
        '''
        Reads person number from the bubble form on the exam cover page. In order
        for this function to work properly the rectangle with the bubble form must be
        detected as the countour with the largest area on the page. Preprocessing will
        remove light colors, so a light background etc. will not interfere with this.

        :img:
            A numpy array encoding an image of the cover page
        :show_plot:
            If True displays plots illustating the image analysis.
            Useful for troubleshooting.
        :dilx:
        :dily:
            Tuples of two integers. They are used to dilate the image, making edges thicker which
            can help to find the contour of the bubble form. Dilations specified by dilx and dily
            are applied to the image consecutively (x direction first, then y).

        Returns:
            An integer with the person number.
        '''


        def sort_corners(a):
            '''
            Given a 4x2 numpy array with coordinates of vertices
            of a rectangle, rearrange it, so that vertices appear
            in a clockwise order starting with the upper left.
            '''
            b = a.copy()
            ordering = [-1, -1, -1, -1]
            sa = np.sum(a,axis = 1)
            ordering[0] = np.argmin(sa)
            ordering[2] = np.argmax(sa)
            b[ordering[0]] = -1
            b[ordering[2]] = -1
            ordering[1] = np.argmax(b[:, 0])
            ordering[3] = np.argmax(b[:, 1])
            return a[ordering]


        if img.shape[2] > 3:
            img = img[:, :, :-1]
        if np.max(img) < 1.5:
            img = img*255
        img = img.astype("uint8")


        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)  # make grayscale
        gray= cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)[1]  #convert to binary
        gray = cv2.medianBlur(gray,5)  # blur to remove noise
        gray = cv2.Canny(gray, 75, 150) # find edges

        # thicken edges
        gray = cv2.dilate(gray, np.ones(dilx))
        gray = cv2.dilate(gray, np.ones(dily))
        gray = cv2.morphologyEx(gray, cv2.MORPH_OPEN, np.ones((5, 5)))


        # find the contour with the largest area
        cnts = cv2.findContours(gray.copy(), cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)[0]
        cnts = sorted(cnts, key=cv2.contourArea, reverse=True)
        frame = cnts[0][:, 0, :]
        peri = cv2.arcLength(frame, True)
        approx = cv2.approxPolyDP(frame, 0.02 * peri, True)

        # apply perspective transformation to rectify the image within the countour
        pts1 = sort_corners(np.array(approx[:, 0, :], dtype = "float32"))
        pts2 = np.float32([[0,0],[800,0],[800,900],[0,900]])
        transf = cv2.getPerspectiveTransform(pts1,pts2)
        straight = cv2.warpPerspective(img, transf, (800, 900))

        # convert the rectified image to binary
        dst = cv2.cvtColor(straight, cv2.COLOR_BGR2GRAY)
        dst= cv2.threshold(dst, 220, 255, cv2.THRESH_BINARY)[1]

        # arrays with limits for subdividing the straightened
        # image into rows and columns
        x = np.linspace(18, 780, 9).astype(int)
        y = np.linspace(165, 860, 11).astype(int)

        # for each column find the row number with the lowest average pixel value
        selected = []
        for i in range(len(x) - 1):
            g = [int(np.mean(dst[y[j]:y[j+1], x[i]:x[i+1]]))  for j in range(len(y)-1)]
            selected.append(g.index(min(g)))

        # plots, just to check how the image analysis went
        if self.show_pnums:
            plt.figure(figsize = (15, 5))
            plt.subplot(131)
            plt.xticks([])
            plt.yticks([])
            im = cv2.bitwise_not(gray)
            plt.imshow(im, cmap="gray")
            plt.fill(approx[:, 0, 0], approx[:, 0,  1], edgecolor='r', lw=3, fill=False)
            plt.subplot(132)
            plt.xticks([])
            plt.yticks([])
            plt.imshow(dst, cmap="gray")
            plt.subplot(133)
            plt.xticks([])
            plt.yticks([])
            plt.imshow(straight, cmap="gray")
            for i in range(len(x)-1):
                j = selected[i]
                plt.fill([x[i], x[i+1], x[i+1], x[i], x[i]],
                        [y[j], y[j], y[j+1], y[j+1], y[j]],
                        'r' , alpha = 0.3
                        )
            plt.show()

        person_number = sum([d*10**i for i, d in enumerate(selected[::-1])])
        return str(person_number)


    def missing_qr_handler(self, scans, page_num, page_image, get_missing_data):
        '''
        For a pdf page where QR code is not found, this function asks for user input.

        :scans:
            The name of the file with which the pdf page is a part of.
        :page_num:
            The page number of the pdf page within the scans file.
        :page_image:
            A numpy array with the image of the page.
        :get_missing_data:
            Boolean. If False do nothing.

        Returns:
            A tuple (qr, qr_found) where qr is either None or a string with the QR code of the page
            provided by the user. qr_found is a boolean, True if the user entered a QR code.
        '''

        if not get_missing_data:
            qr = None
            qr_found = False
            return qr, qr_found

        # display an image of the page
        plt.figure(figsize = (15,20))
        plt.imshow(page_image)
        plt.show()

        # input prompting for user feedback
        msg = "\n\n"
        msg += f"File: {scans}\n"
        msg += f"Page: {page_num}\n"
        msg += "QR code not found. \n\n"
        msg += "Enter the exam code or 's' to skip for now: "
        qr = input(msg)

        qr = qr.strip()
        if qr == "s":
            qr_found = False
        else:
            qr_found = True

        return qr, qr_found


    def missing_pnum_handler(self, pnum, gradebook_df, scans, page_num, page_image, get_missing_data, show_page):
        '''
        For a pdf page with exam cover the student person number was not correctly read this function asks for user input.

        :pnum:
            The person number read from the page. This function is called is when this number does not match any person
            number on the roster of students taking the exam.
        :gradebook_df:
            Pandas dataframe with person numbers of students takinmg the exam. Used to verify that the user entry matches
            one of these numbers. If the person number read from the exam page or provided by the user does not match
            any number in gradebook_df, the user will have an option to add the number to the dataframe.
        :scans:
            The name of the file with which the pdf page is a part of.
        :page_num:
            The page number of the pdf page within the scans file.
        :page_image:
            A numpy array with the image of the page.
        :get_missing_data:
            Boolean. If False do nothing.
        :show_page:
            Boolean. A flag indicating if the page should be displayed to the user. If it has been already once displayed
            to ask for the QR code, we don't need to display it again.

        Returns:
            A tuple (pnum, pnum_found, gradebook_df) where pnum is either None or a string with the person number, pnum_found
            if pnum is a person number listed in gradebook_df, and gradebook_df is the dataframe - possibly modified by adding
            a new person number.
        '''

        if not get_missing_data:
            pnum = None
            pnum_found = False
            return pnum, pnum_found, gradebook_df

        # display the page if needed
        if show_page:
            plt.figure(figsize = (15,20))
            plt.imshow(page_image)
            plt.show()

        # user prompt
        pnum_found = False
        while not  pnum_found:
            msg = "\n\n"
            msg += f"File: {scans}\n"
            msg += f"Page: {page_num}\n"
            msg += f"Person number has been read as: {pnum}.\n"
            msg += "This person number is not recognized.\n\n"
            msg += f"Enter person number, or 'add' to add {pnum} to the gradebook, or 's' to skip for now: "
            new_pnum = input(msg)
            new_pnum = new_pnum.strip()
            if new_pnum == "s":
                pnum = None
                pnum_found = False
                break
            elif new_pnum == "add":
                new_row = {self.pnum_column:[pnum]}
                new_row_df = pd.DataFrame(new_row)
                gradebook_df = gradebook_df.append(new_row_df, sort=False).reset_index().drop(columns = ["index"])
                pnum_found = True
                break
            else:
                pnum = new_pnum
                pnum_found = (pnum in gradebook_df[self.pnum_column].values)

        return pnum, pnum_found, gradebook_df



    def read_scans(self, scans, get_missing_data=False):
        '''
        Given a pdf file with scanned exams:
            - reads the QR code from each page
            - if the page is an exam cover page reads the person number
            - writes the exam code associated to the person number in the gradebook
            - saves each scanned page as an individual pdf file; the name of this file if the QR code of the page.
            - saves a file with pages where QR code or person number needs to be provided by the user in
              the directory with scnned files.

        :scans:
            The name of the pdf file to be processed.
        :get_missing_data:
            Boolean. If False, pages where a QR code or the person number cannot be read will quietly saved
            into a separate file, to be processed later. If True, every such page will prompt the user for
            manual input.

        Returns:
            None
        '''


        # create a temporary directory to store individial exam pages
        if not os.path.exists(self.pages_dir):
            os.makedirs(self.pages_dir)
        # create a directory there files assembled by problem and prepared for grading will be saved
        if not os.path.exists(self.for_grading_dir):
            os.makedirs(self.for_grading_dir)

        # flag indicating whether we are processing the file  collecting pages with missing QR/person number data
        processing_missing_data_file = ((os.path.realpath(scans) ==  os.path.realpath(self.missing_data_pages)))

        # read gradebook, add qr_code column if needed
        gradebook_df = pd.read_csv(self.gradebook, converters={self.pnum_column : str})
        if self.qr_code_column not in gradebook_df.columns:
            gradebook_df[self.qr_code_column] = ""

        # writer object for collecting pages with missing data
        missing_data_writer = pdf.PdfFileWriter()

        # flag indicating if the file collecting pages with missing data already exists
        had_missing_file = os.path.isfile(self.missing_data_pages)

        # a list where we will collect information about pages with missing data we encounter
        missing_data = []

        if not processing_missing_data_file:
            missing_data = self.get_grading_data()["missing_data"]
            # if a file with pages with missing data already exists, copy its
            # content to missing_data_writer; newly discovered pages with missing data
            # will be appened to it
            if had_missing_file:
                missing_data_file = open(self.missing_data_pages, 'rb')
                missing_data_pdf = pdf.PdfFileReader(missing_data_file)
                missing_data_writer.appendPagesFromReader(missing_data_pdf)
        # when processing a file with pages with missing data we will need a copy of
        # information about these pages
        else:
            previous_missing_data  = self.get_grading_data()["missing_data"]

        # read scans; the file needs to remind open since pdf.PdfFileReader
        # uses directly this file object - it does not copy it to the memory
        with open(scans, 'rb') as f:
            scanned_pdf = pdf.PdfFileReader(f)
            num_pages = scanned_pdf.numPages

            # iterate over pages of the file
            for n in range(num_pages):

                # flag indicating if the exam page is to be displayed
                # if data is missing
                show_page = True

                # convert the page into a numpy array
                page = pdf.PdfFileWriter()
                page.addPage(scanned_pdf.getPage(n))
                page_image = pdfpage2img(page)

                # get QR code from the page
                qr_list = enhanced_qr_decode(page_image)

                # check is a QR code was found on the page
                # if not found, call missing_qr_handler
                qr_found = (len(qr_list) != 0)
                if qr_found:
                    qr = qr_list[0].data.decode('utf8')
                else:
                    qr, qr_found = self.missing_qr_handler(scans = scans,
                                                            page_num = n+1,
                                                            page_image = page_image,
                                                            get_missing_data  = get_missing_data
                                                            )
                    show_page = False

                    # if qr code data is still missing, add the page to the missing data
                    # file, if meeded, and go to the next page
                    if not qr_found:
                        # if we are processing the missing data file we want to keep the information
                        # where the pages of this file originally came from
                        if processing_missing_data_file:
                            page_data = previous_missing_data[n]
                        else:
                            page_data = [os.path.basename(scans), n]
                        if page_data not in missing_data:
                            missing_data_writer.addPage(scanned_pdf.getPage(n))
                            missing_data.append(page_data)
                        continue

                # if qr code was found get person number (if cover page)
                qr_code = ExamCode(qr)
                # check if cover page, if so read the person number
                # and record the QR code in the gradebook
                if qr_code.is_cover():
                    # read the person number
                    pnum = self.read_bubbles(page_image)

                    # check if the person number read is in the gradebook
                    # if not found, call missing_pnum_handler
                    pnum_found = (pnum in gradebook_df[self.pnum_column].values)
                    if not pnum_found:
                        pnum, pnum_found, gradebook_df = self.missing_pnum_handler(pnum = pnum,
                                                                                   gradebook_df = gradebook_df,
                                                                                   scans = scans,
                                                                                   page_num = n+1,
                                                                                   page_image = page_image,
                                                                                   get_missing_data = get_missing_data,
                                                                                   show_page = show_page
                                                                                   )
                        if not pnum_found:
                            # if we are processing the missing data file we want to keep the information
                            # where the pages of this file originally came from
                            if processing_missing_data_file:
                                page_data = previous_missing_data[n]
                            else:
                                page_data = [os.path.basename(scans), n]
                            if page_data not in missing_data:
                                missing_data_writer.addPage(scanned_pdf.getPage(n))
                                missing_data.append(page_data)
                            continue

                    print(f"person_number: {pnum}\r", end="")

                    # find the number of the row in the dataframe with the person number
                    i = np.flatnonzero(gradebook_df[self.pnum_column].values == pnum)[0]
                    # record the QR code of a student exam in the gradebook
                    gradebook_df.loc[i, self.qr_code_column] = qr_code.get_exam_code()

                # save the exam page as a pdf file, the file name is the QR code of the page
                page_file = os.path.join(self.pages_dir, qr + ".pdf")
                with open(page_file , 'wb') as f:
                    page.write(f)
                    print(qr + "\r", end="")

        # save the missing pages file or remove if empty
        if missing_data_writer.getNumPages() > 0:
            temp_file = self.missing_data_pages + "_temp"
            with open(temp_file, 'wb') as f:
                missing_data_writer.write(f)
            if had_missing_file:
                if not processing_missing_data_file:
                    missing_data_file.close()
                os.remove(self.missing_data_pages)
            os.rename(temp_file, self.missing_data_pages)
            grading_data = self.get_grading_data()
            grading_data["missing_data"] = missing_data
            self.set_grading_data(grading_data)

        # if there are no pages with missing data:
        else:
            if had_missing_file:
                os.remove(self.missing_data_pages)
            grading_data = self.get_grading_data()
            grading_data["missing_data"] = []
            self.set_grading_data(grading_data)

        # save the gradebook
        gradebook_df.to_csv(self.gradebook, index=False)



    def assemble_by_problem(self):
        '''
        Assembles pages of exam copies into files, one file containing
        all copies of a given page. Pages within each file are sorted
        according to their QR codes.
        The information about QR codes of pages in each file is recorded
        in the grading data json file.

        Returns:
            None.
        '''


        files = glob.glob(os.path.join(self.pages_dir, "*.pdf"))
        # list of pdf file with score tables
        files = [f for f in files if ExamCode(f).has_table()]

        # directory whose keys are file names, and the value is the page number of a file.
        files_dir = {}
        for f in files:
            fcode = ExamCode(f)
            # get the page number
            files_dir[f] = fcode.get_page_num()

        # create the set of page (or problem) numbers of the exam
        problems = set(files_dir.values())

        # this dictionary will record which pages are in each assembled pdf file
        page_lists = {}
        for n in problems:
            # list of pages with the problem n, sorted by QR codes
            f_n = [f for f in files_dir if files_dir[f] == n]
            f_n.sort()

            # qr prefix of the exam
            exam_name = ExamCode(f_n[0]).get_exam_name()

            if exam_name == "":
                output = f"problem_{n}"
            else:
                output = f"{exam_name}_problem_{n}"

            # save the assembled problem file
            output_fname = os.path.join(self.for_grading_dir, output + ".pdf")
            merge_pdfs(f_n , output_fname=output_fname)

            # record the list of pages in the assembled file
            page_lists[os.path.basename(output_fname)] = [os.path.basename(f) for f in f_n]

        #save the information about pages of the assembled files in the grading data json file
        grading_data = self.get_grading_data()
        grading_data["page_lists"] = page_lists
        self.set_grading_data(grading_data)



    def prepare_grading(self, files=None):

        '''
        Prepares exams for grading:
        - It creates directories "pages", "for_grading", and "graded" in
            the main grading directory (if they don't exists yet).
        - It reads scanned pdf files in the "scans" directory using the read_scans
            function.
        - It adds a score table to each page of the exam directory using the add_score_tables
            function.
        - It assembles problem for grading and places them in the "for_grading" directory
            using the assemble_by_problem function.
        - At the end the "pages" directory is removed, since it is not needed anymore.


        :files:
            Specify which files in the scans directory should be processed.
            - If None all files will be processed, except for the ones that were already processed on
            previous runs of this function.
            - If 'all' all files will be processed without exceptions.
            - If a list, only files on the list will be processed.

        Returns:
            None
        '''

        # create the pages directory if needed for storing individual exam pages if needed
        if not os.path.exists(self.pages_dir):
            os.makedirs(self.pages_dir)

        # get a list of scanned files that have been previously processed
        processed_scans = self.get_grading_data()["processed_scans"]
        # if the file with pages with missing data exists we will skip it, to handle it separately
        processed_scans.append(os.path.basename(self.missing_data_pages))
        processed_scans_set = set(processed_scans)

        # get the list of files to be processed
        if files is None:
            file_list = set([os.path.basename(f) for f in set(glob.glob(os.path.join(self.scans_dir, "*.pdf")))])
            file_list = list(file_list.difference(processed_scans_set))
        elif files == "all":
            file_list = [os.path.basename(f) for f in set(glob.glob(os.path.join(self.scans_dir, "*.pdf")))]
            if os.path.basename(self.missing_data_pages) in file_list:
                file_list.remove(os.path.basename(self.missing_data_pages))
            processed_scans_set = set()
        elif type(files) == list:
            file_list = [os.path.basename(f) for f in files]

        file_list.sort()

        print("Reading scanned files...")

        # list collecting names of processed files
        processed = []

        # iterate over scanned files, getting QR codes and person numbers
        # files with data missing are collected in the self.missing_data_pages
        # file, to be processed later
        for f in file_list:
            print(f"Reading file:  {f}")
            fpath = os.path.join(self.scans_dir, f)
            if not os.path.exists(fpath):
                print(f"File {f} not found, omitting.")
                continue
            self.read_scans(scans = fpath, get_missing_data=False)
            processed.append(f)

        # get information about pages with missing QR/person number data
        if  os.path.isfile(self.missing_data_pages):
            print(f"Reading file:  {os.path.basename(self.missing_data_pages)}\n")
            self.read_scans(scans = self.missing_data_pages, get_missing_data=True)


        print("Adding score tables...")
        self.add_score_tables()

        # We are assuming that we are adding new pages to files with exam problems
        # that may have been already partially graded. This will reassemble these
        # problem files so that new pages are added and the already existing
        # pages are unchanged.
        self.split_for_grading_files(dest_dir = self.pages_dir)
        print("Assembling files for grading...")
        self.assemble_by_problem()

        print("Finishing...")
        # record information which scanned files has been processed
        grading_data = self.get_grading_data()
        num_missing_data_pages = len(grading_data["missing_data"])
        grading_data["processed_scans"] = list(set(processed_scans_set).union(processed))
        self.set_grading_data(grading_data)

        # remove the pages directory, it is not needed anymore
        shutil.rmtree(self.pages_dir)

        print("\nGrading files ready.")
        if num_missing_data_pages > 0:
            print(f"There are {num_missing_data_pages} with missing QR codes or person number data")
        else:
            print("All pages were processed successfully.")




class ReadScores(GradingBase):
    '''
    Class defining mathods that read and record scores from graded exams.
    '''

    @staticmethod
    def read_problem_scores(fname, maxpoints, treshold = 250):
        '''
        Reads scores from score table embedded in pages of a pdf file.
        It assumes that the file consists of copies of the same problem,
        which have the same maximal point value.

        :fname:
            The name of the pdf file.
        :maxpoints:
            The maximum point value of the graded problems.
        :treshold:
            Integer value for detecting if a box of the score table is checked
            or not. Each score box is white, so when it us unmarked the mean of its
            pixel values is 255. If the mean read from the pdf is below the treshhold
            we count the score box as marked

        Returns:
            A list of scores, one for each pdf page. If no marked score boxes are detected
            on a page, the value of the list for the page will be "NONE". If multiple marked
            boxes are detected, the value of the list for the page will be "MULTI" followed by
            the list of the read scores.
        '''

        pages = pdf2image.convert_from_path(fname)
        # row and column offset of the first score box in the score table
        row_offset = 2110
        col_offset = 44

        # shift from the left edge of one score box to the next one
        box_shift = 60
        # width and height of a score box
        box_size = 30

        #list of scores
        scores = []
        for page in pages:
            img = np.array(page)
            score_table = []
            # iterate over score boxes in the score table
            for i in range(maxpoints+1):
                x = col_offset + i*box_shift
                box = img[row_offset : row_offset + box_size, x : x + box_size, :]
                if box.mean() < treshold:
                    score_table.append(i)

            if len(score_table) == 1:
                scores.append(score_table[0])
            elif len(score_table) == 0:
                scores.append("NONE")
            else:
                scores.append("MULTI: " + str(score_table))
        return scores


    def get_scores_df(self):
        '''
        Reads scores from graded pdf files with exam problems.

        Returns:
            Pandas dataframe with exam scores. Rows are indexed with exam codes,
            columns with problem numbers. A "NONE" value in the dataframe indicates
            that no score has been detected. A "MULTI" value indicates that multiple
            scores for the same problem have been detected and gives the list of these
            values.
        '''

        # get files with exam problems, skip the file with exam covers
        files = glob.glob(os.path.join(self.for_grading_dir, "*problem_*.pdf"))
        files = sorted([f for f in files if not covers_file(f)])


        grading_data = self.get_grading_data()
        #  the list with max score for each problem
        maxpoints = grading_data["maxpoints"]
        # the directory with lists with exam codes for each problem
        page_lists = grading_data["page_lists"]

        # dictionary for recording problem scores; records of the form
        # prob_n : list of scores for prob_n
        score_dict = {}

        # iterate over exam problem files
        for fname in files:
            basename = os.path.basename(fname)
            print(f"Processing: {basename}\r", end="")

            basename = os.path.basename(fname)
            # page/problem number
            page_num = (os.path.splitext(basename)[0]).split("_")[-1]
            # maximal possible score for the problem
            problem_max = maxpoints[page_num]

            # read problem scores
            score_list = self.read_problem_scores(fname = fname, maxpoints = problem_max)

            # associate problem scores with exam codes
            pages = [ExamCode(f).get_exam_code() for f in  page_lists[basename]]
            if len(pages) != len(score_list):
                return None
            score_dict_page = {p:s for (p,s) in zip(pages, score_list)}
            score_dict["prob_" + page_num] = score_dict_page

        # conver the scores dictionary into dataframe with rows indexed by exam QR codes and
        # colmns labeled prob_n where n is the problem numnber
        scores_df = pd.DataFrame(score_dict)

        return scores_df


    def get_scores(self, save = False, new_gradebook = None):
        '''
        records exam scores in a gradebook with student data

        :save:
            Boolean. If True the the gradebook data will be saved to a csv file.
        :new_gradebook:
            The name of the csv file to save the data. If None, the data will be saved
            to self.gradebook.

        Returns:
            A tuple of (scores_df, new_gradebook_df) pandas dataframes. scores_df contains
            problem scores indexed by exam QR codes.  new_gradebook_df contains exams scores
            merged with student data reasd from self.gradebook.
        '''


        if new_gradebook is None:
            new_gradebook = self.gradebook
        else:
            save = True
            new_gradebook = os.path.join(self.main_dir, os.path.basename(new_gradebook))

        # read exam scores
        scores_df = self.get_scores_df()

        problem_cols = scores_df.columns.tolist()
        # add a column with total score for each exam; since some rows may contain
        # "NONE" and "MULTI" values we need to skip over them
        scores_temp = scores_df.applymap(lambda x : pd.to_numeric(x,errors='coerce'))
        scores_df[self.total_column] = scores_temp[problem_cols].sum(axis=1).astype("int")

        # drop exam scores from the gradebook, to avoid duplicated columns
        gradebook_df = pd.read_csv(self.gradebook)
        for col in problem_cols + [self.total_column]:
            try:
                gradebook_df.drop(columns = col, inplace=True)
            except KeyError:
                continue

        # merge the gradebook data with exam scores
        new_gradebook_df = pd.merge(gradebook_df, scores_df, how = "left",  left_on = self.qr_code_column, right_index = True)
        new_gradebook_temp = new_gradebook_df.applymap(lambda x : pd.to_numeric(x,errors='coerce'))
        new_gradebook_df[self.total_column] = new_gradebook_temp[problem_cols].sum(axis=1).astype("int")

        # insert the grade column if needed, for recording letter grades by the instructor
        if self.grade_column not in new_gradebook_df.columns:
            new_gradebook_df[self.grade_column] = ""

        # save to a csv file
        if save:
            new_gradebook_df.to_csv(new_gradebook, index=False)
        
        print("Exam scores ready" + 40*" ")
        return scores_df, new_gradebook_df



class AssembleGradedExams(GradingBase):
    '''
    Class defining mathods that assemble graded exams by student.
    '''

    def __init__(self, main_dir = None, gradebook = None, init_grading_data=False):
        '''
        All rguments are inherited from the GradingBase constructor.
        '''

        GradingBase.__init__(self, main_dir, gradebook, init_grading_data)

        gradebook_df =  pd.read_csv(self.gradebook)

        # add the column for student email addresses if needed; it will need to be
        # populated in order to send the exams back to students
        if self.email_column not in gradebook_df.columns:
            gradebook_df[self.email_column] = ""
            gradebook_df.to_csv(self.gradebook, index=False)


    @staticmethod
    def cover_page_grades(fname=None, table_data=None, output_file=None):
        '''
        Add score table to the cover page of an exam

        :fname:
            Name of the pdf file to add the score table to.
        :table_data:
            A dictionary with data to be inserted in the table.
            Keys of the dictinary will be used as labels of score boxes,
            the corresponding values will be printed in score boxes.
            If the dictionary has keys "grade" and "total" the corresponding
            values will be printed in red.
        :output_file:
            The name of the pdf file with the score table added. It None,
            fname prefixed with 't_' will be used.
        '''

        if output_file == None:
            head, tail = os.path.split(fname)
            output_file = os.path.join(head, "t_" + tail)


        # make pdf with the score table
        pdf_bytes = io.BytesIO()
        c = canvas.Canvas(pdf_bytes, pagesize=letter)

        num_boxes = len(table_data)
        page_w = 8.5*inch
        margin = 0.05*inch
        table_w = page_w - 2*margin
        table_h = 0.8*inch

        box_spacing = 0.06*inch
        # width of boxes will be adjusted depending on their number; for tables with
        # few score boxes the width will be fixed at 1.5 inch, otherwise boxed will be
        # sized to fill the width of the score table.
        box_w = min(1.5*inch, (table_w - box_spacing)/num_boxes  - box_spacing)
        box_h = 0.35*inch
        box_top_pad = 0.1*inch
        box_bottom = (table_h + margin) - box_h - box_top_pad
        text_label_bottom = box_bottom - 0.2*inch
        text_data_bottom = box_bottom + 0.11*inch
        label_font_size = 10 if num_boxes < 14 else 9

        # draw background of the score table
        c.setLineWidth(.5)
        c.setStrokeColor("red")
        c.setFillColorRGB(1, 0.85, 0.85)
        c.rect(margin, margin, table_w, table_h, stroke=1, fill=1)

        # draw score table
        c.setFillColor("white")
        for k, key in enumerate(table_data):
            # draw score box
            box_left = box_spacing + margin + k*(box_spacing + box_w)
            c.setFillColor("white")
            c.setStrokeColor("black")
            c.setLineWidth(0.75)
            c.rect(box_left, box_bottom, box_w, box_h, stroke=1, fill=1)
            # print score box label
            c.setFont('Helvetica', label_font_size)
            c.setFillColor("black")
            c.drawCentredString(box_left + 0.5*box_w, text_label_bottom, str(key).upper())
            # print score box content
            color = "red" if str(key).upper() in ["GRADE", "TOTAL"] else "black"
            c.setFillColor(color)
            c.setFont('Courier', 16)
            c.drawCentredString(box_left + 0.5*box_w, text_data_bottom, str(table_data[key]))
        c.save()

        score_pdf = pdf.PdfFileReader(pdf_bytes).getPage(0)
        source = pdf.PdfFileReader(open(fname, 'rb')).getPage(0)
        # read rotation angle of the source pdf file
        try:
            rot = (360-int(source.get('/Rotate')))%360
        except:
            rot = 0
        writer = pdf.PdfFileWriter()
        scale = 1
        # if the source pdf is rotated we need to adjust parameters for merging it with
        # the score table; rotations dictionary stores these parameters for all possible
        # rotation angles
        rotations = {0: {"rotation": 0, "tx": 0*inch, "ty": 0*inch},
                    90: {"rotation": 270, "tx": 0*inch, "ty": 8.5*inch},
                    180: {"rotation": 180, "tx": 8.5*inch, "ty": 11*inch},
                    270: {"rotation": 90, "tx": 11*inch, "ty": 0*inch}}
        # merge the source pdf with the score table
        source.mergeRotatedScaledTranslatedPage(score_pdf, scale = scale, **rotations[rot], expand=False)
        writer.addPage(source)

        # save the output file
        with open(output_file, "wb") as foo:
            writer.write(foo)


    def mark_score(self, fname, score, max_score, output_file):
        '''
        Add a marker to the score table on an exam page indicating the score
        recorded for the page.

        :fname:
            Name of the pdf file with the page to add a marker to.
        :score:
            Recorded problem score for the page
        :max_score:
            Maximum possible score for problem on the page.
        :output_file:
            The name of the pdf file with the score table added.

        Returns:
            None
        '''

        # if score is not an integer, or exceed the maximal score
        # that can be recorsed in the score table, just copy the file.
        try:
            score = int(score)
        except:
            score = None

        if score is None or score > max_score:
            shutil.copy(fname, output_file)
            return None

        # draw the marker
        pdf_bytes = io.BytesIO()

        c = canvas.Canvas(pdf_bytes, pagesize=letter)
        c.setLineWidth(.5)
        # backdround marker square
        c.setStrokeColor("black")
        c.setFillColor("white")
        c.rect(self.table_margin + self.box_left_pad + score*(self.box_size + self.box_spacing),
            self.box_bottom,
            self.box_size,
            self.box_size,
            stroke=1,
            fill=1)
        # foreground marker square
        c.setFillColorRGB(0.5, 0, 0)
        c.rect(self.table_margin + self.box_left_pad + score*(self.box_size + self.box_spacing) + self.mark_margin,
            self.box_bottom + self.mark_margin,
            self.box_size - 2*self.mark_margin,
            self.box_size - 2*self.mark_margin,
            stroke=0,
            fill=1)
        # marker label with the score
        c.setFont('Helvetica-Bold', 10)
        c.setFillColor("white")
        c.drawCentredString(self.table_margin + self.box_left_pad + score*(self.box_size + self.box_spacing) + 0.5*self.box_size,
                            self.box_bottom + 5*self.mark_margin,
                            str(score))
        c.save()

        mark_pdf = pdf.PdfFileReader(pdf_bytes).getPage(0)

        source = pdf.PdfFileReader(open(fname, 'rb')).getPage(0)

        # get rotation of the source pdf file
        try:
            rot = (360-int(source.get('/Rotate')))%360
        except:
            rot = 0
        writer = pdf.PdfFileWriter()
        scale = 1
        # if the source pdf is rotated we need to adjust parameters for merging it with
        # the score table; rotations dictionary stores these parameters for all possible
        # rotation angles
        rotations = {0: {"rotation": 0, "tx": 0*inch, "ty": 0*inch},
                    90: {"rotation": 270, "tx": 0*inch, "ty": 8.5*inch},
                    180: {"rotation": 180, "tx": 8.5*inch, "ty": 11*inch},
                    270: {"rotation": 90, "tx": 11*inch, "ty": 0*inch}}
        # merge the source pdf with the score table
        source.mergeRotatedScaledTranslatedPage(mark_pdf, scale = scale, **rotations[rot], expand=False)
        writer.addPage(source)

        # save the output file
        with open(output_file, "wb") as foo:
            writer.write(foo)



    @staticmethod
    def flatten_pdf(fname):
        '''
        This function can be used to flatten pdf, making anotations added in the
        grading process non-editable. It needs pdftops and ps2pdf to work.

        :fname:
            The file to be flatten. The flattened file will have the same name.

        Returns:
            None
        '''
        ps_fname = os.path.splitext(fname)[0] + ".ps"
        c1 = f'pdftops "{fname}"  "{ps_fname}"'
        c2 = f'ps2pdf "{ps_fname}" "{fname}"'
        os.system(c1)
        os.system(c2)
        os.remove(ps_fname)


    def assemble_by_student(self, extras = None, flatten = False):
        '''
        Assembles graded exam files by student, adding score tables to the exam
        covers and score marks to other pages.

        :extras:
            By default the score table on the cover page will contain scores for each
            exam problem, the total score, and the letter grade. extras is a dictionary
            which can be used to add additional data to the score table. The values are
            names of gradebook columns that should be used. The keys are strings which will
            used as labels of a score boxes in the score table.

        :flatten:
            Boolean. If True, an attempt will be made to flatted the output pdf files.
            This will work only if pdftops and ps2pdf are installed, otherwise this option
            will have no effect.
        '''

        if extras is None:
            extras = {}

        gradebook_df =  pd.read_csv(self.gradebook)

        # get graded exam files
        files = glob.glob(os.path.join(self.for_grading_dir, "*_problem_*.pdf"))

        # split the graded files into pages and save them to a temporary directory
        temp_dir = tempfile.mkdtemp()
        self.split_for_grading_files(dest_dir = temp_dir)

        covers = sorted([f for f in glob.glob(os.path.join(temp_dir, "*.pdf")) if ExamCode(f).is_cover()])
        prob_cols = sorted([c for c in gradebook_df.columns.tolist() if "prob_" in c])

        # a function for formatting numerical score table entries
        def format_scores(n):
            try:
                s = str(int(n))
            except:
                s = "--"
            return s

        # add score tables to exam covers
        print(f"Adding score tables..." + 40*" ")
        for cover in covers:
            ex_code = ExamCode(cover)
            print(f"{ex_code.get_exam_code()}\r", end="")
            cover_copy = os.path.join(temp_dir, "copy_" + ex_code.base + ".pdf")
            shutil.copyfile(cover, cover_copy)
            qr = ex_code.get_exam_code()
            record = gradebook_df.loc[gradebook_df[self.qr_code_column] == qr]
            scores = record[prob_cols].values[0]
            score_table_data = {}
            for k in range(len(scores)):
                score_table_data[k+1] = format_scores(scores[k])
            if self.total_column in record.columns:
                score_table_data["total"] =  format_scores(record[self.total_column].values[0])
            if self.grade_column on record.columns:
                score_table_data["grade"] = record[self.grade_column].values[0]

            for k in extras:
                score_table_data[k] =  format_scores(record[extras[k]].values[0])

            # save the cover file with the added score table
            self.cover_page_grades(fname=cover_copy, table_data = score_table_data, output_file=cover)
            os.remove(cover_copy)

        print(f"Score tables added." + 40*" ")

        pages = sorted([f for f in glob.glob(os.path.join(temp_dir, "*.pdf")) if not ExamCode(f).is_cover()])
        maxpoints = self.get_grading_data()["maxpoints"]

        # add score marks to exam pages
        print(f"Adding score marks..." + 40*" ")
        for page in pages:

            ex_code = ExamCode(page)
            print(f"{ex_code.base}\r", end="")

            max_score = maxpoints[str(ex_code.get_page_num())]

            page_copy = os.path.join(temp_dir, "copy_" + ex_code.base + ".pdf")
            shutil.copyfile(page, page_copy)
            qr = ex_code.get_exam_code()
            record = gradebook_df.loc[gradebook_df[self.qr_code_column] == qr]
            scores = record[prob_cols].values[0]
            # get page/problem number
            pagenum = ex_code.get_page_num()
            # get the recorded score for the page
            score = scores[pagenum -1]
            self.mark_score(fname = page_copy, score = score, max_score = max_score, output_file = page)
            os.remove(page_copy)
        print(f"Score marks added." + 40*" ")


        print("Assembling exams...")
        files = glob.glob(os.path.join(temp_dir, "*.pdf"))
        # set of exam codes identifying exam copies
        codes = set(ExamCode(f).get_exam_code() for f in files)

        # create directory to store graded exams, assembled by student
        if not os.path.exists(self.graded_dir):
            os.makedirs(self.graded_dir)

        # assemble graded exams
        for exam_code in codes:
            print(f"{exam_code}\r", end="")
            exam_pages = [f for f in files if ExamCode(f).get_exam_code() == exam_code]
            exam_pages.sort()
            output_fname = os.path.join(self.graded_dir, exam_code + ".pdf")
            merge_pdfs(exam_pages, output_fname=output_fname)

        exam_files = glob.glob(os.path.join(self.graded_dir, "*.pdf"))

        if flatten:
            try:
                for f in exam_files:
                    self.flatten_pdf(f)
            except:
                pass

        # remove the temporary directory with individual exam pages
        shutil.rmtree(temp_dir)

        print("Graded exams ready." + 40*" ")



class EmailGradedExams(GradingBase):
    '''
    Class defining mathods for emailing graded exams to students.
    '''

    def __init__(self, template = None, main_dir = None, gradebook = None,  init_grading_data=False):
        '''
        :template:
            Name of a text file the the template of the email text. The file should be placed 
            in the main grading directory. The text can contain {placeholders}, enclosed in braces. 
            Each placeholder needs to be a name of a column of the gradebook. The message to each student 
            will be formatted by replacing each placeholder by the value of the corresponding column, in 
            the row corresponding to the student. If template is None, an empty string will be used as 
            the email text.

            If the first line of the template file starts with the string 'subject:', the reminder of this
            line will be used as the subject of the message.

         All other arguments are inherited from the GradingBase constructor.
        '''

        GradingBase.__init__(self, main_dir, gradebook, init_grading_data)

        # stmp server data
        self.smtp_server = "smtp.buffalo.edu"
        self.server_port = 465

        # if the server refuses to send more emails at some point, we wil pause
        # for this many seconds and then resume sending exams
        self.reconnect_period = 300

        gradebook_df =  pd.read_csv(self.gradebook)

        # check if the column with student email addresses is present in the gradebook
        if self.email_column not in gradebook_df.columns:
            gradebook_df[self.email_column] = ""
            gradebook_df.to_csv(self.gradebook, index=False)
            print("Email addresses missing in the gradebook, exiting")
            return None

        # check if the template file exists
        if template is None:
            self.template = ""
        elif os.path.isfile(os.path.join(self.main_dir, template)):
            with open(os.path.join(self.main_dir, template)) as foo:
                self.template = foo.read()
        else:
            print(f"File {template} does not exist, exiting.")
            return None


    @staticmethod
    def make_message(template_txt, subject, from_address, to_address, pdf_fname, **kwargs):
        '''
        Prepare the email message

        :template_txt:
            String the the template of the email text.
        :subject:
            String with the subject of the message
        :from_address:
            The sender email address.
        :to_address:
            The recipient email address.
        :pdf_fname:
            The name of the pdf files which will be attached to the email
        :**kwargs:
            Keyword arguments which will be used to replace placeholders in the template of
            the text of the email.

        Returns:
            EmailMessage object
        '''

        # get message text by replacing placeholders with values of the keyword arguments
        msg_text = template_txt.format(**kwargs)

        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = from_address
        msg['To'] = to_address

        msg['Content-Type'] = "text/plain; charset=utf-8; format=flowed"
        msg.set_content(msg_text)

        # add the pdf file as an attachment
        with open(pdf_fname, 'rb') as f:
            content = f.read()
            msg.add_attachment(content, maintype='application/pdf', subtype='pdf', filename=os.path.basename(pdf_fname))

        body = msg.get_body()
        body.replace_header('Content-Type', 'text/plain; charset=utf-8; format=flowed')

        return msg


    @staticmethod
    def timer(seconds):
        """
        Countdown timer.

        :seconds:
            The number of seconds to count down from.
        """

        for i in range(seconds,0,-1):
            print("\rWill retry in {:3} seconds.".format(i), end='')
            sleep(1)
            sl = len("Will retry in {:3} seconds.".format(i))
            print("\r" + " "*sl + "\r", end='')


    def send_exams(self, send_sample= False, resend = False):
        '''
        Send emails

        :send_sample:
            Boolean. If true a single email message will be send with the recipient address set
            to be the same as the sender address. Can be used to test if messages are properly formatted.
        :resend:
            Boolean. The function records in the grading data to which email addresses messages have been sent already,
            and by default omits these addresses when the function is called again. Setting `resend` to `True`, 
            overrides this behavior, and emails are sent to every email address in the gradebook.
        '''

        if send_sample:
            print(f"Sending a sample message.\n")

        # get email addresses to which messages were previously sent
        grading_data = self.get_grading_data()
        emails_sent = set(grading_data["emails_sent"])

        # convert the gradebook into a list of dictionaries, one dictionary
        # for each gradebook row
        gradebook_df = pd.read_csv(self.gradebook)
        gradebook_df = gradebook_df[gradebook_df[self.qr_code_column].notnull()]
        gradebook_dict = gradebook_df.to_dict(orient='records')

        # get email subject and email text template
        template_lines = self.template.split("\n")
        if template_lines[0].lower().strip().startswith("subject:"):
            subject = template_lines[0][len("subject:"):].strip()
            template_txt = "\n".join(template_lines[1:]).strip()
        # is the first line of the template file does not contain
        # the subject, ask the user what the subject should be
        else:
            template_txt = "\n".join(template_lines).strip()
            subject = input("Enter email's subject: ")

        # get stmp server login info
        login_name = input("UB login name: ").strip()
        password = getpass.getpass(login_name + " password:")
        from_address = login_name + "@buffalo.edu"

        # prepare and send emails
        for record in gradebook_dict:
            pdf_fname = os.path.join(self.graded_dir, f"{record[self.qr_code_column]}.pdf")

            # get recipient email address
            if  '@' in record['email']:
                to_address = record['email'].strip()
            else:
                to_address = record['email'].strip() + "@buffalo.edu"

            # check is the message was previously sent
            if (not send_sample) and (not resend) and (to_address in emails_sent):
                print(f"{to_address:30} *********** WAS SENT BEFORE, OMITTING")
                continue

            # check if pdf file exists, if it does not, skip
            if not os.path.isfile(pdf_fname):
                if not send_sample:
                    print(f"{to_address:30} *********** FILE {os.path.basename(pdf_fname)} NOT FOUND, OMITTING")
                continue

            if send_sample:
                to_address = from_address

            # format the email message
            msg = self.make_message(template_txt= template_txt,
                                    subject=subject,
                                    from_address = from_address,
                                    to_address = to_address,
                                    pdf_fname = pdf_fname,
                                    **record)

            # send email
            send_success = False
            while not send_success:
                try:
                    server = smtplib.SMTP_SSL(self.smtp_server, self.server_port)
                    server.login(login_name, password)
                except smtplib.SMTPAuthenticationError:
                    print("Login name or password incorrect, exiting")
                    return None
                try:
                    server.send_message(msg, from_addr = from_address, to_addrs = to_address)
                except smtplib.SMTPException as ex:
                    print("{:30} *********** NOT SENT: {}".format(to_address, ex))
                    #pause before reattempting to send the message
                    self.timer(self.reconnect_period)
                else:
                    print("{:30} *********** SENT".format(to_address))
                    send_success = True
                    server.quit()
                    sleep(0.1)
            if send_sample:
                break
            else:
                # save information that the email was sent
                # we are saving it to the grading data file right away, in case
                # the program gets interrupted for some reason
                if send_success:
                    emails_sent.add(to_address)
                    grading_data = self.get_grading_data()
                    grading_data["emails_sent"] = list(emails_sent)
                    self.set_grading_data(grading_data)
        
        print("***FINISHED***")




#wrappers

def prepare_grading(maxpoints, main_dir = None, gradebook = None, init_grading_data=False, files=None):
    
    x = PrepareGrading(maxpoints = maxpoints, 
                       main_dir = main_dir, 
                       gradebook = gradebook, 
                       init_grading_data=init_grading_data)
    x.prepare_grading(files = files)


def read_scores(main_dir = None, gradebook = None, new_gradebook = None):
    
    x = ReadScores(main_dir = main_dir, gradebook = gradebook)
    x.get_scores(save=True, new_gradebook = new_gradebook)



def assemble_exams(main_dir = None, gradebook = None, extras = None, flatten = False):
    
    x = AssembleGradedExams(main_dir = main_dir, gradebook = gradebook) 
    x.assemble_by_student(extras = extras, flatten = flatten)


def send_exams(main_dir = None, gradebook = None, template = None, send_sample=False, resend = False):
    
    x = EmailGradedExams(main_dir = main_dir, template = template, gradebook = gradebook)
    x.send_exams(send_sample=send_sample, resend = resend)
