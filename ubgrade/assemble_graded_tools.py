from ubgrade.grading_base import GradingBase
from ubgrade.exam_code import ExamCode, covers_file
from ubgrade.helpers import merge_pdfs

import os
import glob
import io
import json
import tempfile
import shutil
import subprocess

import pandas as pd
import PyPDF2 as pdf

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF



class AssembleGradedExams(GradingBase):

    '''
    Class defining mathods that assemble graded exams by student.
    '''

    def __init__(self, main_dir = None, gradebook = None, init_grading_data=False):

        '''
        All arguments are inherited from the GradingBase constructor.
        '''

        GradingBase.__init__(self, main_dir, gradebook, init_grading_data)

        gradebook_df =  pd.read_csv(self.gradebook)

        # add the column for student email addresses if needed; it will need to be
        # populated in order to send the exams back to students
        if self.email_column not in gradebook_df.columns:
            gradebook_df[self.email_column] = ""
            gradebook_df.to_csv(self.gradebook, index=False)

        # flag indicating if flattening of pdf files can be performed
        self.can_flatten = True


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
        subprocess.call(['pdftops', fname, ps_fname])
        subprocess.call(['ps2pdf', ps_fname, fname])
        os.remove(ps_fname)



    def cover_page_grades(self, fname, table_data=None, output_file=None, flatten=False):

        '''
        Add score table to the cover page of an exam

        :fname:
            Name of the pdf file to add the score table to.
        :table_data:
            A dictionary with data to be inserted in the table.
            Keys of the dictionary will be used as labels of score boxes, and
            the corresponding values will be printed in the score boxes.
            If the dictionary has keys "grade" and "total" the corresponding
            values will be printed in red.
        :output_file:
            The name of the pdf file with the score table added. It None,
            fname prefixed with 't_' will be used.
        :flatten:
            Boolean. If True, an attempt will be made to flatten the output pdf file.
            This will work only if pdftops and ps2pdf are installed, otherwise this option
            will have no effect.
        '''

        if flatten and self.can_flatten:
            try:
                self.flatten_pdf(fname)
            except:
                self.can_flatten = False

        if output_file == None:
            head, tail = os.path.split(fname)
            output_file = os.path.join(head, "t_" + tail)


        # create pdf with the score table
        pdf_bytes = io.BytesIO()
        c = canvas.Canvas(pdf_bytes, pagesize=letter)

        num_boxes = len(table_data)
        page_w = 8.5*inch
        margin = 0.05*inch
        table_w = page_w - 2*margin
        table_h = 0.8*inch

        box_spacing = 0.06*inch
        # width of boxes will be adjusted depending on their number; for tables with
        # few score boxes the width will be fixed at 1.5 inch, otherwise boxes will be
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


    def mark_score(self, fname, score, max_score, output_file, flatten=False):

        '''
        Add a marker to the score table on an exam page indicating the score
        recorded on the page.

        :fname:
            Name of the pdf file with the page to add a marker to.
        :score:
            Recorded problem score for the page.
        :max_score:
            Maximum possible score for problem on the page.
        :output_file:
            The name of the pdf file that will be produced.
        :flatten:
            Boolean. If True, an attempt will be made to flatten the output pdf files.
            This will work only if pdftops and ps2pdf are installed, otherwise this option
            will have no effect.

        Returns:
            None
        '''

        if flatten and self.can_flatten:
            try:
                self.flatten_pdf(fname)
            except:
                self.can_flatten = False

        # if score is not an integer, or exceed the maximal score
        # that can be recorsed in the score table, just copy the source file.
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
        source.compressContentStreams()
        writer.addPage(source)

        # save the output file
        with open(output_file, "wb") as foo:
            writer.write(foo)


    def assemble_by_student(self, prob_labels = None, extras = None,  flatten = False):

        '''
        Assembles graded exam files by student, adding score tables to the exam
        covers and score marks to other pages.

        :prob_labels:
            If prob_labels is None (default) score boxes for each exam problem  will be 
            labeled according to page numbers, e.g. the label of the score for the problem 
            on page 3 will be "P3" (the cover page is page number 0). This can be customized 
            by assigning prob_labels to a dictionary whose keys are names of columns with 
            problem scores in the gradebook, and values are strings with labels of the 
            corresponding score boxes. 
        :extras:
            By default the score table on the cover page will contain scores for each
            exam problem, the total score, and the letter grade. extras is a dictionary
            which can be used to add additional data to the score table. The keys are
            names of gradebook columns that should be used. The values are strings which will
            be used as labels of score boxes in the score table.

        :flatten:
            Boolean. If True, an attempt will be made to flatten the output pdf files.
            This will work only if pdftops and ps2pdf are installed, otherwise this option
            will have no effect.
        '''

        if extras is None:
            extras = {}

        gradebook_df =  pd.read_csv(self.gradebook, converters={self.qr_code_column : str})

        # get graded exam files
        files = glob.glob(os.path.join(self.for_grading_dir, "*page_*.pdf"))

        # split the graded files into pages and save them to a temporary directory
        temp_dir = tempfile.mkdtemp()
        self.split_for_grading_files(dest_dir = temp_dir)

        covers = sorted([f for f in glob.glob(os.path.join(temp_dir, "*.pdf")) if ExamCode(f).is_cover()])
        prob_cols = sorted([c for c in gradebook_df.columns.tolist() if "page_" in c])

        if prob_labels is None:
            prob_labels = dict([ (p, f"P{p.split('_')[-1]}") for p in prob_cols] )


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
            scores = record[prob_cols]
            score_table_data = {}
            for k in prob_cols:
                score_table_data[prob_labels[k]] = format_scores(scores[k])

            for k in extras:
                score_table_data[extras[k]] =  format_scores(record[k])

            if self.total_column in record.columns:
                score_table_data["total"] =  format_scores(record[self.total_column].values[0])
            if self.grade_column in record.columns:
                score_table_data["grade"] = record[self.grade_column].values[0]

            # save the cover file with the added score table
            self.cover_page_grades(fname=cover_copy, table_data = score_table_data, output_file=cover, flatten=flatten)
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

            # pages with max_score = 0 do not have score tables
            if max_score > 0:
                page_copy = os.path.join(temp_dir, "copy_" + ex_code.base + ".pdf")
                shutil.copyfile(page, page_copy)
                qr = ex_code.get_exam_code()
                record = gradebook_df.loc[gradebook_df[self.qr_code_column] == qr]
                scores = record[prob_cols].values[0]
                # get page/problem number
                pagenum = ex_code.get_page_num()
                # get the recorded score for the page
                score = record[prob_cols][f"page_{pagenum}"]
                self.mark_score(fname = page_copy, score = score, max_score = max_score, output_file = page, flatten = flatten)
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

        # remove the temporary directory with individual exam pages
        shutil.rmtree(temp_dir)

        print("Graded exams ready." + 40*" ")
