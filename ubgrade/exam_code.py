import os
import re

class ExamCode():

    '''
    Class defining methods for manipulating exam file names.
    '''

    def __init__(self, code):
        self.code = code
        self.head, self.tail = os.path.split(self.code)
        self.base, self.ext = os.path.splitext(self.tail)


    def valid(self):

        '''
        Check if the format of a QR code is valid, i.e. consist is a (possibly empty)
        prefix followed by CXXX-PXX where X denotes a digit. A code t_CXXX-PXX also valid
        to allow for names of files with a score table and an empty prefix.  
        '''

        tokens = self.base.split("-")
        if not len(tokens) >= 2:
            return False
        if re.match(r"^(t_)?C\d{3}$", tokens[-2]) and re.match(r"^P\d{2}$", tokens[-1]):
            return True
        else:
            return False


    def has_table(self):

        '''
        Checks if a given file name corresponds to a pdf file of an exam page
        with a score table added.
        '''
        
        return self.base.startswith("t_")


    def get_exam_code(self):

        '''
        Strips the page number from an exam page QR code, and returns the 
        remainig part identifying the exam copy.
        '''

        code =  "-".join(self.base.split("-")[:-1])
        if self.has_table():
            code = code[2:]
        return code

    def get_page_num(self):

        return self.base.split("-")[-1]

    def get_page_num_int(self):

        '''
        Returns an integer with the exam page number (page numbers staert at 0).
        '''

        return int(self.base.split("-")[-1][1:])

    def is_cover(self):

        '''
        Checks if a page is a cover page of an exam.
        '''

        return self.get_page_num_int() == 0

    def table_fname(self):

        '''
        A function which formats names of pdf files of exam pages with score tables.
        '''

        return os.path.join(self.head,  "t_" + self.tail)

    def get_exam_name(self):

        '''
        Get qr_prefix (exam copy nummber and page number striped)
        '''

        return "-".join(self.get_exam_code().split("-")[:-1])


    def assembled_page_fname(self):
        
        '''
        For a given QR code returns the name of the file 
        with assembled copies of a page of the exam which will 
        contain the page with this QR code. The name of the file 
        is obtained by stripping the exam copy number from the QR
        code. E.g. MTH309-C011-P03 becomes MTH309_page_3. 
        '''

        if self.get_exam_name() == "":
            return f"{self.base.split('-')[-1]}"
        else:
            return f"{self.get_exam_name()}-{self.base.split('-')[-1]}"



def covers_file(f):

    '''
    Given a name of a pdf file with with copies of an exam page, checks
    if it consists of cover pages
    '''

    return "P00.pdf" in os.path.basename(f)


