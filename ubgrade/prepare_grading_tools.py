from ubgrade.grading_base import GradingBase
from ubgrade.exam_code import ExamCode
from ubgrade.helpers import pdfpage2img, enhanced_qr_decode, merge_pdfs, rotate_pdf, detect_and_rotate
from ubgrade.missing_data_tools import get_missing_data

import os
import glob
import io
import json
import shutil
from datetime import datetime

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





class PrepareGrading(GradingBase):

    '''
    Class defining mathods used to prepare exams for grading.
    '''

    def __init__(self, maxpoints, main_dir = None, gradebook = None, init_grading_data=False, show_pnums = False):

        '''
        :maxpoints:
            A list with the maximal possible score of each exam page (except for the cover page). 
            Can be also given as an integer, if the maximal score for each problem is the same. 
            If a score corresponding to a page is 0, it indicates that this page will not be graded, 
            and that no score table should be added to it. 
        :show_pnums:
            Boolean. If True, then when person numbers are read from  exam cover pages, images showing the reading process
            will be displayes.

        The remaining arguments are inherited from the GradingBase constructor.
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
                shutil.copy(f, output_file)
                continue

            # get the maximum score for an exam page
            page_num = fcode.get_page_num()
            max_score = self.maxpoints[min(page_num-1, len(self.maxpoints)-1)]
            max_score_dict[page_num] = max_score

            # pages worth 0 points do not get score tables added
            if max_score == 0:
                shutil.copy(f, output_file)
                continue

            # add the score table
            self.draw_score_table(fname = f, output_file = output_file, points=max_score)
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


   
    def read_scans(self, scans):

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

        # create a temporary directory to store individual exam pages
        if not os.path.exists(self.pages_dir):
            os.makedirs(self.pages_dir)
        # create a directory there files assembled by problem and prepared for grading will be saved
        if not os.path.exists(self.for_grading_dir):
            os.makedirs(self.for_grading_dir)

        # read gradebook, add qr_code column if needed
        gradebook_df = pd.read_csv(self.gradebook, converters={self.pnum_column : str, self.qr_code_column : str})
        if self.qr_code_column not in gradebook_df.columns:
            gradebook_df[self.qr_code_column] = ""

        # writer object for collecting pages with missing data
        missing_data_writer = pdf.PdfFileWriter()

        # flag indicating if the file collecting pages with missing data already exists
        had_missing_file = os.path.isfile(self.missing_data_pages)

        # a list with information about pages with missing QR/person number data
        missing_data = self.get_grading_data()["missing_data"]

        # if a file with pages with missing data already exists, copy its
        # content to missing_data_writer; newly discovered pages with missing data
        # will be appened to it
        if had_missing_file:
            missing_data_file = open(self.missing_data_pages, 'rb')
            missing_data_pdf = pdf.PdfFileReader(missing_data_file)
            missing_data_writer.appendPagesFromReader(missing_data_pdf)

        # read scans; the file needs to remain open since pdf.PdfFileReader
        # uses directly this file object - it does not copy it to the memory
        with open(scans, 'rb') as f:
            scanned_pdf = pdf.PdfFileReader(f)
            num_pages = scanned_pdf.numPages

            # iterate over pages of the file
            for n in range(num_pages):

                # convert the page into a numpy array
                page = pdf.PdfFileWriter()
                page.addPage(scanned_pdf.getPage(n))
                page_image = pdfpage2img(page)

                # get QR code from the page
                try:
                    qr_list = enhanced_qr_decode(page_image)
                    qr_found = (len(qr_list) != 0)
                except:
                    qr_found = False
                  
                if qr_found:
                    qr = qr_list[0].data.decode('utf8')
                    qr_code = ExamCode(qr)
                else:
                    qr = None

                # if QR code was found and the page is not a cover page, 
                # save the  page as a pdf file, the file name is the QR code of the page
                # then contionue to the next page
                if qr_found and (not qr_code.is_cover()):
                    page_file = os.path.join(self.pages_dir, qr + ".pdf")
                    with open(page_file , 'wb') as f:
                        page.write(f)
                    print(qr + 40*" " + "\r", end="")
                    continue

                # if cover read the person number
                # also, attempt to read person number on pages where  
                # QR code was not found, so we can process them appropriately later
                else:
                    # read the person number
                    try:
                        pnum = self.read_bubbles(page_image)
                    except:
                        pnum = None

                    # check if the person number read is in the gradebook
                    pnum_found = (pnum is not None) and (pnum in gradebook_df[self.pnum_column].values)

                    if pnum_found:
                        print(f"person_number: {pnum}" + 40*" " + "\r", end="")
                
                # if we have found all data on a cover page, save the page and record the 
                # QR code in the gradebook
                # then contine to the next page
                if qr_found and qr_code.is_cover() and pnum_found:
                    # find the number of the row in the dataframe with the person number
                    i = np.flatnonzero(gradebook_df[self.pnum_column].values == pnum)[0]
                    # record the QR code of a student exam in the gradebook
                    gradebook_df.loc[i, self.qr_code_column] = qr_code.get_exam_code()
                    # save the exam page as a pdf file, the file name is the QR code of the page
                    page_file = os.path.join(self.pages_dir, qr + ".pdf")
                    with open(page_file , 'wb') as f:
                        page.write(f)
                    print(qr + 40*" " + "\r", end="")
                    continue
                
                # for pages with missing data, record page data 
                page_missing_data = self.page_missing_data.copy()
                page_missing_data["fname"] = os.path.basename(scans)
                page_missing_data["page"] = n
                page_missing_data["qr"] = qr if qr_found else None
                page_missing_data["pnum"] = pnum

                if page_missing_data not in missing_data:
                    missing_data.append(page_missing_data)
                    missing_data_writer.addPage(scanned_pdf.getPage(n))

        # if there are pages with missing data, save them
        if len(missing_data) > 0:
            temp_file = self.missing_data_pages + "_temp"
            with open(temp_file, 'wb') as f:
                missing_data_writer.write(f)
            if had_missing_file:
                missing_data_file.close()
                os.remove(self.missing_data_pages)
            os.rename(temp_file, self.missing_data_pages)
            grading_data = self.get_grading_data()
            grading_data["missing_data"] = missing_data
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
            if fcode.get_exam_name() == "":
                files_dir[f] = f"page_{fcode.get_page_num()}"
            else:
                files_dir[f] = f"{fcode.get_exam_name()}_page_{fcode.get_page_num()}"

        # create the set of page (or problem) numbers of the exam
        problems = set(files_dir.values())

        # this dictionary will record which pages are in each assembled pdf file
        page_lists = {}
        for n in problems:
            # list of pages with the problem n, sorted by QR codes
            f_n = [f for f in files_dir if files_dir[f] == n]
            f_n.sort()

            # save the assembled problem file
            output_fname = os.path.join(self.for_grading_dir, n + ".pdf")
            merge_pdfs(f_n , output_fname=output_fname)

            # record the list of pages in the assembled file
            page_lists[os.path.basename(output_fname)] = [os.path.basename(f) for f in f_n]

        #save the information about pages of the assembled files in the grading data json file
        grading_data = self.get_grading_data()
        grading_data["page_lists"] = page_lists
        self.set_grading_data(grading_data)



    def prepare_grading(self, files=None,  rotate=None, batch=False):

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
        :rotate:
            This argument can be an integer (a multiple of 90) giving the angle by which all pages 
            of pdf files should rotated clockwise to bring them to the correct orientation. If None, 
            the angle of rotation of each file will be automatically detected, using the assumption 
            that on a correctly oriented page the QR code is located in the upper right corner. 
            The automatic angle detection will check the angle of rotation for each pdf file separately, 
            but all pages in a given file will be rotated by the same angle.  
        :batch:
            Boolean. It True, pages with missing QR codes or person number will be recorded and 
            saved into a separate file, but there will be no attempt to ask the user to provide 
            the missing data. The missing data can be then added by the user at a later time, 
            by tunning this function again with batch=False. 

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

            # rotate pdf pages
            if rotate is None:
                detect_and_rotate(pdfin = fpath)
            else:
                rotate_pdf(angle = rotate, pdfin = fpath)

            self.read_scans(scans = fpath)
            processed.append(f)

        # get information about pages with missing QR/person number data
        if  (not batch) and  os.path.isfile(self.missing_data_pages):
            print(f"Reading file:  {os.path.basename(self.missing_data_pages)}\n")
            get_missing_data()


        print("Adding score tables..." + 40*" ")
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
            p = "is 1 page" if num_missing_data_pages == 1 else f"are {num_missing_data_pages} pages"
            print(f"There {p} with missing QR code or person number data.")
        else:
            print("All pages were processed successfully.")
