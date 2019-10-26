from ubgrade.grading_base import GradingBase
from ubgrade.exam_code import ExamCode, covers_file

import os
import glob
import io
import json
import shutil

import pandas as pd
import numpy as np
import pdf2image



class ReadScores(GradingBase):

    '''
    Class defining mathods that read and record scores from graded exams.
    '''

    @staticmethod
    def read_problem_scores(fname, maxpoints, treshold = 250):

        '''
        Reads scores from score tables embedded in pages of a pdf file.
        It is assumed that the file consists of copies of the same problem,
        which have the same maximal point value.

        :fname:
            The name of the pdf file.
        :maxpoints:
            The maximum point value of the graded problems.
        :treshold:
            Integer value for detecting if a box of the score table is checked
            or not. Each score box is white, so when it is unmarked, the mean of its
            pixel values is 255. If the mean read from the pdf is below the treshhold
            we count the score box as marked

        Returns:
            A list of scores, one for each pdf page. If no marked score boxes are detected
            on a page, the entry the list for the page will be "NONE". If multiple marked
            boxes are detected, the value of the list for the page will be "MULTI" followed by
            the list of detected scores.
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
        files = glob.glob(os.path.join(self.for_grading_dir, "*page_*.pdf"))
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
            if problem_max > 0:
                score_list = self.read_problem_scores(fname = fname, maxpoints = problem_max)

                # associate problem scores with exam codes
                pages = [ExamCode(f).get_exam_code() for f in  page_lists[basename]]
                if len(pages) != len(score_list):
                    return None
                score_dict_page = {p:s for (p,s) in zip(pages, score_list)}
                score_dict["page_" + page_num] = score_dict_page

        # conver the scores dictionary into dataframe with rows indexed by exam QR codes and
        # colmns labeled prob_n where n is the problem numnber
        scores_df = pd.DataFrame(score_dict)

        return scores_df


    def get_scores(self, save = False, new_gradebook = None):

        '''
        Records exam scores in a gradebook with student data.

        :save:
            Boolean. If True, the the gradebook data will be saved to a csv file.
        :new_gradebook:
            The name of the csv file to save the data. If None, the data will be saved
            to self.gradebook.

        Returns:
            A tuple (scores_df, new_gradebook_df) of pandas dataframes. scores_df contains
            problem scores indexed by exam QR codes.  new_gradebook_df contains exams scores
            merged with student data read from self.gradebook.
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
        gradebook_df = pd.read_csv(self.gradebook, converters={self.qr_code_column : str})
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
        
        # rearrange columns, so that the grade column comes last
        cols = new_gradebook_df.columns.tolist()
        cols.remove(self.grade_column)
        cols.append(self.grade_column)
        new_gradebook_df = new_gradebook_df[cols]


        # save to a csv file
        if save:
            new_gradebook_df.to_csv(new_gradebook, index=False)

        print("Exam scores ready" + 40*" ")
        return scores_df, new_gradebook_df
