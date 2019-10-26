import os

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
        Strips the page number from an exam page QR code, and returns the 
        remainig part identifying the exam copy.
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
        A function which formats names of pdf files of exam pages with score tables.
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

    return "page_0.pdf" in os.path.basename(f)
