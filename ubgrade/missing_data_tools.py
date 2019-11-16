from ubgrade.grading_base import GradingBase
from ubgrade.exam_code import ExamCode
from ubgrade.helpers import pdfpage2img, insert_pdf_page, delete_pdf_page
import os
import io
import json
import shutil
import datetime
import bisect 

import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import cv2
import PyPDF2 as pdf
import pdf2image


def get_qr(page):

    '''
    Asks the user to provide QR code for an exam page.
    
    :page:
        A dictionary with exam page data returned by 
        the MissingData.get_page_data method.

    Returns:
        A sting with the QR code entered by the user. 
    '''

    # display an image of the page
    plt.figure(figsize = (15,20))
    plt.imshow(page["image"])
    plt.show()

    # ask for QR code            
    msg = "\n\n" + 30*"-" + "\n"
    msg += f"File: {page['fname']}\n"
    msg += f"Page: {page['page'] + 1}\n"
    msg += "QR code not found. \n\n"
    msg += "Enter the QR code or 's' to skip for now: "
    qr = input(msg).strip()

    # check is user input is valid, if not try again
    while not (qr == 's' or  ExamCode(qr).valid()):          
        msg = "\n\n" + 30*"-" + "\n"
        msg += f"The code you entered '{qr}' is not valid. \n\n"
        msg += "Enter the QR code or 's' to skip for now: "
        qr = input(msg).strip()

    return qr


def get_pnum(page):

    '''
    Asks the user to provide person number for an exam page.
    
    :page:
        A dictionary with exam page data returned by 
        the MissingData.get_page_data method

    Returns:
        A sting with the person number entered by the user. 
    '''

    # display an image of the page
    plt.figure(figsize = (15,20))
    plt.imshow(page["image"])
    plt.show()

    # ask for person number
    msg = "\n\n" + 30*"-" + "\n"
    msg += f"File: {page['fname']}\n"
    msg += f"Page: {page['page'] + 1}\n"
    pnum = page['pnum']
    if pnum is None:
        msg += "Person number has not been found on this page\n\n" 
        msg += f"Enter person number, or 's' to skip for now: "
    else:
        msg += f"Person number has been recorded as: {pnum}.\n"
        msg += "This person number is not listed in the gradebook.\n\n"
        msg += f"Enter person number, or 'add' to add {pnum} to the gradebook, or 's' to skip for now: "
    new_pnum = input(msg)
    new_pnum = new_pnum.strip()

    return new_pnum


def get_missing_data(main_dir = None, gradebook = None):

    '''
    Processes the pdf file with pages missing QR code or person number. 
    
    :main_dir:
        The main grading directory.  If  None the current working 
        directory will be used.
    :gradebook:
            A csv file used in grading. Must be locates in the main 
            gragind directory. 

    Returns:
        An integer indicating the number of skipped pages, which 
        will have data missing after this function is finished. 
    '''

    # counter of skipped pages
    page_num = 0 

    while True:
        # exceptions will be raised if either the missing data page does not exists 
        # (i.e. all pages have complete data), or page_num exceeds the number of 
        # pages in the missing data pdf (which means that all missing data pages 
        # have been processed)
        try:
            # get the first non-skipped page with missing data
            page = MissingData(main_dir = main_dir, gradebook = gradebook, page=page_num)
        except (NoMissingDataFile, NoSuchMissingPage):
            break

        page_data = page.get_page_data()
        # if page_data is None, there is no data missing
        if page_data is None:
            continue

        if page_data["missing_data"] == "qr":
            qr = get_qr(page_data)
            # if the page is skipped, go to the next one
            if qr == "s":
                page_num += 1
                continue
            else:
                page.set_qr(qr)

        elif page_data["missing_data"] == "pnum":
            pnum = get_pnum(page_data)
            # if the page is skipped, go to the next one
            if pnum == "s":
                page_num += 1
                continue
            else:
                page.set_pnum(pnum)

        page.record_page()

    # page_num will give the number of skipped pages
    return page_num


class NoMissingDataFile(Exception):
    '''
    Raised if there is no missing data file. 
    '''
    pass


class NoSuchMissingPage(Exception):
    '''
    Raised if the page number passed to MissingData constructor 
    exceeds the number of pages in the missing data file. 
    '''
    pass


class MissingData(GradingBase):
    
    '''
    Class defining properties and methods used to process a page with missing data. 
    '''

    def __init__(self, main_dir = None, gradebook = None, page=0):

        '''
        :page:
            The number of a page of the pdf file with missing data pages 
            to be processed (page numbers start with 0)
        
        All other arguments are inherited from the GradingBase constructor.
        '''

        GradingBase.__init__(self, main_dir, gradebook, init_grading_data = False)

        # number of the page currently being processed
        self.page_num = page

        # if there is no pdf file wih exam pages with missing data, raise an exception
        if not os.path.isfile(self.missing_data_pages):
            raise NoMissingDataFile("File {self.missing_data_pages} not found.")

        # read properties of the processed page
        self.missing_data = self.get_grading_data()["missing_data"]
        if self.page_num >= len(self.missing_data):
            raise NoSuchMissingPage(f"Invalid page number {self.page_num}. The number of pages in the file f{self.missing_data_pages} is {len(self.missing_data)}.")

        self.page_data = self.missing_data[self.page_num]
        self.qr = self.page_data["qr"]
        self.pnum  = self.page_data["pnum"]
        self.origin_page_num = self.page_data['page']
        self.origin_fname = self.page_data['fname']

        # get pdf of the page
        self.missing_data_file = open(self.missing_data_pages, 'rb')
        self.missing_data_reader = pdf.PdfFileReader(self.missing_data_file)
        if self.page_num >= self.missing_data_reader.numPages:
            raise NoSuchMissingPage(f"Invalid page number {self.page_num}. The number of pages in the file f{self.missing_data_pages} is {len(self.missing_data)}.")
        self.pdf_page = self.missing_data_reader.getPage(self.page_num)
        self.pdf_page_writer = pdf.PdfFileWriter()
        self.pdf_page_writer.addPage(self.pdf_page)

        # read gradebook, add qr_code column if needed
        self.gradebook_df = pd.read_csv(self.gradebook, converters={self.pnum_column : str, self.qr_code_column : str})
        if self.qr_code_column not in self.gradebook_df.columns:
            self.gradebook_df[self.qr_code_column] = ""



    def valid_pnum(self, pnum):
        
        '''
        Checks if the value of pnum corresponds to 
        a person number listed ts in the gradebook
        '''

        return (pnum is not None) and (pnum in self.gradebook_df[self.pnum_column].values)


    def data_is_complete(self):
        
        '''
        Checks if the all data for the current page 
        (QR code and - for a cover page - person number) is known.
        '''
        
        if (self.qr is None):
            return False
        elif not ExamCode(self.qr).is_cover():
            return True
        elif self.valid_pnum(self.pnum):
            return True
        else:
            return False
    

    def set_qr(self, qr):

        '''
        Sets the value of the QR code.  
        '''
        
        self.qr = qr


    def set_pnum(self, pnum):

        '''
        Sets the value of the person number
        '''

        # if pnum = "add", the value of self.pnum is added to the gradebook
        # together with a timestamp indicating when it was added
        if pnum == "add":
            if self.pnum_time_column not in self.gradebook_df.columns:
                self.gradebook_df[self.pnum_time_column] = ""
            now = datetime.datetime.now()
            dt_string = now.strftime("%d/%m/%Y %H:%M:%S")
            new_row = {self.pnum_column:[self.pnum], self.pnum_time_column: [dt_string]}
            new_row_df = pd.DataFrame(new_row)
            self.gradebook_df = self.gradebook_df.append(new_row_df, sort=False).reset_index().drop(columns = ["index"])
        else:
            self.pnum = pnum


    def record_page(self):
        
        '''
        If all page data is known, this function remmoves the page from the missing data file, 
        and adds it to the files assembled for grading. For an exam cover page, it also records 
        the QR code in the gradebook. 
        
        If some page data is missing, the values of self.pnum and self.qr are recorded in the 
        grading data. 
        '''

        grading_data = self.get_grading_data()
        page_lists = grading_data["page_lists"]
        missing_data = grading_data["missing_data"]

        if self.data_is_complete():

            if ExamCode(self.qr).is_cover():
                # find the number of the row in the dataframe with the person number
                i = np.flatnonzero(self.gradebook_df[self.pnum_column].values == self.pnum)[0]
                # record the QR code of a student exam in the gradebook
                self.gradebook_df.loc[i, self.qr_code_column] = ExamCode(self.qr).get_exam_code()

            # move the page from missing pages to assembled pages, and record it in the grading data
            assembled_fname = ExamCode(self.qr).assembled_page_fname() + ".pdf"
            page_fname = f"t_{self.qr}.pdf"

            if assembled_fname in page_lists:  
                index = bisect.bisect(page_lists[assembled_fname], page_fname)
                insert_pdf_page(os.path.join(self.for_grading_dir, assembled_fname), page= self.pdf_page, index=index)
                page_lists[assembled_fname].insert(index, f"t_{self.qr}.pdf")
            else:
                with open(os.path.join(self.for_grading_dir, assembled_fname), "wb") as f:
                    self.pdf_page_writer.write(f)
                page_lists[assembled_fname] = [page_fname]

            self.missing_data_file.close()
            delete_pdf_page(self.missing_data_pages, index=self.page_num)
            missing_data.pop(self.page_num)
        else: 
            # if some data is missing, record self.pnum and self.qr with the missing data
            missing_data[self.page_num]["pnum"] = self.pnum
            missing_data[self.page_num]["qr"] = self.qr


        #save grading data
        grading_data["missing_data"] = missing_data
        grading_data["page_lists"] = page_lists
        self.set_grading_data(grading_data)

        # save the gradebook
        self.gradebook_df.to_csv(self.gradebook, index=False)


    def get_page_data(self):

        '''
        If the page data is complete, this function records the page, moving 
        the page from missing date file to an assembled for grading file and 
        returns None.  Otherwise it returns a dictionary with page data. 
        '''

        if self.data_is_complete():
                self.record_page()
                return None

        if self.qr is None:
            return {"missing_data" : "qr", 
                    "page" : self.page_data['page'], 
                    "fname" : self.page_data['fname'],
                    "image" : pdfpage2img(self.pdf_page_writer)
                    }
        
        return {"missing_data" : "pnum", 
                    "pnum" : self.pnum,
                    "page" : self.page_data['page'], 
                    "fname" : self.page_data['fname'],
                    "image" : pdfpage2img(self.pdf_page_writer)
                    }