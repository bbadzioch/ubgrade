from ubgrade.grading_base import GradingBase
from ubgrade.exam_code import ExamCode
from ubgrade.helpers import pdfpage2img
import os
import io
import json
import shutil
import datetime

import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import cv2
import PyPDF2 as pdf
import pdf2image


def get_qr(page):

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
    return qr


def get_pnum(page):

    # display an image of the page
    plt.figure(figsize = (15,20))
    plt.imshow(page["image"])
    plt.show()

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

    missing = MissingData(main_dir = None, gradebook = None)
    
    while True:
        page = missing.get_missing_page()
        if missing.finished:
            break
        if page["missing_data"] == "qr":
            qr = get_qr(page)
            missing.set_qr(qr) 
        elif page["missing_data"] == "pnum":
            pnum = get_pnum(page)
            missing.set_pnum(pnum)

    return len(missing.new_missing_data)


class MissingData(GradingBase):


    def __init__(self, main_dir = None, gradebook = None):

        GradingBase.__init__(self, main_dir, gradebook, init_grading_data = False)

        if not os.path.isfile(self.missing_data_pages):
            raise Exception("File {self.missing_data_pages} not found.")
        
        if not os.path.exists(self.pages_dir):
            os.makedirs(self.pages_dir)

        # read gradebook, add qr_code column if needed
        self.gradebook_df = pd.read_csv(self.gradebook, converters={self.pnum_column : str, self.qr_code_column : str})
        if self.qr_code_column not in self.gradebook_df.columns:
            self.gradebook_df[self.qr_code_column] = ""


        # read pdf with missing data
        self.missing_data_file = open(self.missing_data_pages, 'rb')
        self.missing_data_pdf = pdf.PdfFileReader(self.missing_data_file)

        # a list with information about pages with missing QR/person number data
        self.missing_data = self.get_grading_data()["missing_data"]

        # writer object for collecting pages with missing data
        self.new_missing_data_writer = pdf.PdfFileWriter()

        # a list for recording information about pages that will be skipped by the user
        self.new_missing_data = []
        
        self.num_pages = self.missing_data_pdf.numPages
        self.current_page_num = 0
        self.finished = (self.current_page_num >= self.num_pages)

        self.set_page_data()


    def set_page_data(self):
        self.page_data = self.missing_data[self.current_page_num]
        self.qr = self.page_data["qr"]
        self.pnum  = self.page_data["pnum"]
        self.pdf_page = pdf.PdfFileWriter()
        self.pdf_page.addPage(self.missing_data_pdf.getPage(self.current_page_num))


    def next_page(self):
        self.current_page_num += 1 
        if self.current_page_num >= self.num_pages:
            self.finished = True
        else:
            self.set_page_data()

        
    def valid_pnum(self):
        return (self.pnum is not None) and (self.pnum in self.gradebook_df[self.pnum_column].values)


    def data_is_complete(self):
        if (self.qr is None):
            return False
        elif not ExamCode(self.qr).is_cover():
            return True
        elif self.valid_pnum():
            return True
        else:
            return False
    

    def write_page(self):

        if ExamCode(self.qr).is_cover():
            # find the number of the row in the dataframe with the person number
            i = np.flatnonzero(self.gradebook_df[self.pnum_column].values == self.pnum)[0]
            # record the QR code of a student exam in the gradebook
            self.gradebook_df.loc[i, self.qr_code_column] = ExamCode(self.qr).get_exam_code()

        page_file = os.path.join(self.pages_dir, self.qr + ".pdf")
        with open(page_file , 'wb') as f:
            self.pdf_page.write(f)


    def cleanup(self):

        # if there are pages with missing data, save them
        if len(self.new_missing_data) > 0:
            temp_file = self.missing_data_pages + "_temp"
            with open(temp_file, 'wb') as f:
                self.new_missing_data_writer.write(f)

            self.missing_data_file.close()
            os.remove(self.missing_data_pages)
            os.rename(temp_file, self.missing_data_pages)
        else: 
            self.missing_data_file.close()
            os.remove(self.missing_data_pages)

        #save grading data
        grading_data = self.get_grading_data()
        grading_data["missing_data"] = self.new_missing_data
        self.set_grading_data(grading_data)

        # save the gradebook
        self.gradebook_df.to_csv(self.gradebook, index=False)

    
    def set_new_missing_data(self):
        self.new_missing_data_writer.addPage(self.missing_data_pdf.getPage(self.current_page_num))
        self.new_missing_data.append(self.page_data)


    def set_qr(self, qr):
        # if page is skipped record it in new missing data
        if qr == "s":
            self.set_new_missing_data()
            self.next_page()
        else:
            self.qr = qr


    def set_pnum(self, pnum):
        # if page is skipped record it in new missing data
        if pnum == "s":
            self.set_new_missing_data()
            self.next_page()

        elif pnum == "add":
            if self.pnum_time_column not in self.gradebook_df.columns:
                self.gradebook_df[self.pnum_time_column] = ""
            now = datetime.datetime.now()
            dt_string = now.strftime("%d/%m/%Y %H:%M:%S")
            new_row = {self.pnum_column:[self.pnum], self.pnum_time_column: [dt_string]}
            new_row_df = pd.DataFrame(new_row)
            self.gradebook_df = self.gradebook_df.append(new_row_df, sort=False).reset_index().drop(columns = ["index"])
        
        else:
            self.pnum = pnum
            

    def get_missing_page(self):

        if self.finished:
            self.cleanup()
            return None

        while True:
            if self.data_is_complete():
                self.write_page()        
                self.next_page()
                if self.finished:
                    self.cleanup()
                    return None
            else:
                break


        if self.qr is None:
            return {"missing_data" : "qr", 
                    "page" : self.page_data['page'], 
                    "fname" : self.page_data['fname'],
                    "image" : pdfpage2img(self.pdf_page)
                    }
        
        else:
            return {"missing_data" : "pnum", 
                    "pnum" : self.pnum,
                    "page" : self.page_data['page'], 
                    "fname" : self.page_data['fname'],
                    "image" : pdfpage2img(self.pdf_page)
                    }