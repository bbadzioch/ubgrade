from ubgrade.helpers import pdf2pages

import os
import json
import glob
import shutil
from reportlab.lib.units import inch


class GradingBase():

    '''
    Base class establishing file and directory structure used in grading.
    '''

    def __init__(self, main_dir = None, gradebook = None, init_grading_data=False):

        '''
        :main_dir:
            The main directory in which all grading files are stored.
            Prior to the start of grading it should contain a subdirectory
            named 'scans' with with pdf files of scanned exams. If main_dir
            is None the current working directory will be used.
        :gradebook:
            A csv file used in grading. This file must be located in the main 
            grading directory. Prior to the start of grading it should
            contain at least one column with heading 'person_number' containing
            person numbers of students taking the exam. The header row should be 
            the first row of the file. If gradebook is None, it will be assumed that 
            the gradebook file is called gradebook.csv. 
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
            gradebook = os.path.basename(gradebook)
            self.gradebook = os.path.join(self.main_dir, gradebook)

        # a pdf file used for exam pages where user input us needed to get QR code or person number
        self.missing_data_pages = os.path.join(self.scans_dir, "missing_data.pdf")
        # a json file with data structures used in the grading process
        self.grading_data_jfile = os.path.join(self.main_dir, "grading_data.json")


        # data structure for recording information about pages with 
        # missing/misread QR codes and person numbers 
        self.page_missing_data = {"fname": None, 
                                  "page": None, 
                                  "qr": None, 
                                  "pnum": None
                                  }


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
            # remove grading data
            self.set_grading_data(self.init_grading_data)
            # remove missing pages
            if os.path.isfile(self.missing_data_pages):
                 os.remove(self.missing_data_pages)
            # remove the directory with individual exam pages
            if os.path.isdir(self.pages_dir):
                shutil.rmtree(self.pages_dir)


        # Columns of the self.gradebook file. The file must have the self.pnum_column to start the grading
        # process, and the self.email_column when the graded exams are being sent to students. The other
        # columns will be created automatically, if needed.
        self.pnum_column = "person_number"
        self.email_column = "email"
        self.qr_code_column = "qr_code"
        self.total_column = "total"
        self.grade_column = "grade"
        self.pnum_time_column = "person_num_added"


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

        page_lists = self.get_grading_data()["page_lists"]

        for f in page_lists:
            f_list = page_lists[f]
            fname = os.path.join(self.for_grading_dir, f)
            def set_page_names(fname, n, page):
                return f_list[n]

            pdf2pages(fname, output_fname=set_page_names, output_directory = dest_dir)
