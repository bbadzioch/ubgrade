# ubgrade

This package contains scripts  automating some tasks related to preparation
and grading of exams.

Installation:

```
pip install ubgrade
```

Import:

```
import ubgrade
```


## 1. Exam Preparation

**1.1.** Use LaTeX exam template file [`exam_template.tex`](https://raw.githubusercontent.com/bbadzioch/ubgrade/master/ubgrade/exam_template.tex)  to prepare the exam.
The cover page of the template should be left unchanged, aside from editing
the title, date, and exam instructions. The format of the remaining
pages can be changed as needed, but the top margin should be set to at least
1.5 inches to leave enough space for a QR code.

<img src="https://raw.githubusercontent.com/bbadzioch/ubgrade/master/exam_template.png" style="display:block; margin-left:auto; margin-right:auto; margin-bottom:20px; margin-top:20px; width: 150px;">

**1.2.** Once the exam is compiled to a pdf file, use the function
`ubgrade.make_exams` to produce copies of the exam with QR codes embedded
in each page. The signature of this functions is as follows:

```
ubgrade.make_exams(template, N, qr_prefix, output_file=None, output_directory = None, add_backpages = False)
```

* `template`:  Name of the pdf file with the exam.

* `N`: The number of copies of the exam that are to be produced.  

* `qr_prefix`: Prefix of QR codes to be added to the exam pages. The QR code for each page will be of the form
`(qr_prefix)_C(copy number)_P(page number)`. (e.g. `MTH309_C002_P03`, for the 3rd page of the second copy of
the exam with `qr_prefix ="MTH309"`).

* `output_file`: Name of pdf files to be produced; these files will be named `output_file_n.pdf` where `n`
is the number of the exam copy. If `output_file` is None, the name of the template file will be used.

* `output_directory`: Name of the directory where the produced pdf files will
be saved. If None, the current directory will be used. If the given directory
does not exist, it will be created.

* `add_backpages`: Boolean. If `True` back pages will be added to the produced pdf files, with a message that these
pages will not be graded. This is intended for two-sided printing of the exam files.


## 2. Preparation for grading

**2.1.** After the exam has been administered scan exam copies to pdf files.
For best results use photo/text scanner setting. Black and white low resulution
scans may create problems. The scanned exam pages can be oriented sideways or
upside down. The orientation will be adjusted as needed, provided that all pages
in any given scanned file have the same orientation (different orientation in
different files is fine).

**2.2.** Create a directory (which we will subsequently call *the main grading directory*)
in which all grading files will reside. Inside this directory create a subdirectory
named `scans` and place the scanned pdf files there.

**2.3.** Create a csv file with the roster of students taking the exam. This file
should have at least two columns. The column with the heading `person_number`
should be populated with person numbers of students taking the exam. The column
with the heading `email` should contain email addresses of students (which will
be needed to send graded exams back to students). Columns with other data
(student names etc.) can be included as well. The header row should be the first
row of the csv file. Place the file in the main grading directory. We will refer
to this file as *the gradebook file*.

**2.4.** Use the function `ubgrade.prep_grading` to prepare grading files.
The signature of this function is as follows:

```
ubgrade.prep_grading(maxpoints, main_dir = None, gradebook = None, rotate = None, batch = False, files = None, init_grading_data = False)
```

* `maxpoints`: A list with the maximal possible score of each exam page.
This argument can be also given as an integer, if all pages have the same
maximal score. If the maximal possible score corresponding to a page is 0,
it indicates that the page will not be graded: there will be no score table
added to it etc.

* `main_dir`:  The main grading directory. If not specified the current directory will be used.

* `gradebook`: The name of the gradebook file. This file needs to be located in
the main grading directory. If `None` it will be assumed that the file name
is `gradebook.csv`

* `rotate`: This argument can be an integer (a multiple of 90) giving
the angle by which all pages of pdf files should rotated clockwise to bring them
to the correct orientation. If `None` (default), the angle of rotation of each file will be
automatically detected, using the assumption that on a correctly oriented page
the QR code is located in the upper right corner. The  automatic angle detection
will check the angle of rotation for each pdf file separately, but all pages in
a given file will be rotated by the same angle.  

* `batch`: Boolean. By default, if the function encounters pages where QR code
or person number which be read, it will ask the user to enter this
data. If `batch = True`, the function will instead quietly process all pages.
Pages with missing data will be assembled into a separate pdf file, which can
be processed at a later time by running this function again with `batch = False`.  

* `files`: This argument specifies which files in the `scans` subdirectory should
be processed. If `None` (default) all files will be processed, except for the ones that
were already processed during previous runs of the function. This is what one should want
in most cases. If `files = "all"` all files will be processed, without exceptions.
The value of this argument can be also a list of file names, explicitly specifying which
files in the `scans` subdirectory should be processed.

* `init_grading_data`: Boolean. If `True` it will reset metadata used by the function,
in effect starting the preparation of grading files from scratch. Should be set to `False`
(default) except in cases of some mishaps.

This function performs the following tasks:

* It reads QR codes and person numbers from exam pages. If a QR code is
unreadable, or if a person number read does not correspond to any person number
listed in the gradebook file, the function will ask the user for input.
* It adds to the gradebook file a new column `qr_code` which lists exam QR codes
associated with person numbers.
* It adds a score table to each exam page (except for the cover page).
* It assembles exam pages with score tables into new files, each file
containing all copies of a given page of the exam. These files are saved in
the `for_grading` subdirectory of the main grading directory.
* The function will also create a file `grading_data.json` in the main
grading directory, with some data which will be needed later on. Do not delete
this file.

## 3. Grading

Use some pdf annotation software to grade the pdf files. Mark the score for
each problem in the score table. The script reading these scores is quite
sensitive, so there is no need to cover the entire score box, a small mark
to indicate the problem score will be fine. Do not rename the files. After
grading is completed, place them back in the `for_grading` subdirectory of the
main grading directory.


## 4. Recording scores

Use the function `ubgrade.read_scores` to read and record exam scores.
The signature of this function is as follows:

```
ubgrade.read_scores(main_dir = None, gradebook = None, new_gradebook = None)
```

* `main_dir`:  The main grading directory. If not specified the current directory will be used.

* `gradebook`: The name of the gradebook file. This file needs to be located in
the main grading directory. If `None` it will be assumed that the file name
is `gradebook.csv`.

* `new_gradebook`: The name of the csv file where the exam scores are to be
saved. If `None` the `gradebok` file will be used.

This function will copy all content of the `gradebook` file (person numbers, QR codes etc.) to `new_gradebook`.
It will also create a column in the `new_gradebook` for each exam problem, and record problem scores.
If no score mark is detected on an exam page, the corresponding entry in `new_gradebook` will be `"NONE"`.
If marks in two (or more) score boxes of a score table are detected, the corresponding entry will be `"MULTI"`
followed by a list of marked score boxes. The function also creates a column `total` with total exam scores,
and a column `grade` which is intended to be populated with exam letter grades by the instructor. Either of these
columns can be deleted if they are not to be reported to students (e.g. delete the `grade` column if there
are no letter grades for the exam).


## 5. Returning graded exams to students

**5.1.** The csv file with exam scores can be modified as needed, by adding letter grades, columns with some bonus
or extra credit points etc. It can be further populated with data which will be used to format emails sent to
students. For example, if an email to a student is supposed to use the first name of the student ("Dear Ann" etc.),
then a column listing first names will be needed.

**5.2.** Use the function `ubgrade.assemble_exams` to add score tables with problem
scores, total scores, letter grades, and possibly other data to exam cover
pages, and to assemble the exams by student.  
The signature of this function is as follows:

```
ubgrade.assemble_exams(main_dir = None, gradebook = None, prob_labels = None, extras = None)
```

* `main_dir`: The main grading directory. If not specified the current directory will be used.

* `gradebook`: The name of the gradebook file. This file needs to be located in
the main grading directory. If `None` it will be assumed that the file name
is `gradebook.csv`

* `prob_labels`: By default the score box of the cover page score table corresponding to a given exam page
will be labeled using the number of the page. For example, the score box for page 3 will be labeled "P3"
(the cover page is page 0). This can be customized  by assigning to prob_labels a dictionary whose keys are
names of columns with problem scores in the gradebook, and values are strings with labels of the
corresponding score boxes.

* `extras`: By default the score table on the cover page will contain scores for exam problems, the total score, and the
letter grade (provided that columns `total` and `grade` exist in the gradebook). `extras` is a dictionary which can be used to
add additional data to the score table. The dictionary keys are names of gradebook columns that should be used. The values are
strings which will used as labels of score boxes in the score table.

The pdf files produced by this function will be saved in the `graded` subdirectory of the main grading directory.

**5.3.** Use the function `ubgrade.send_exams` for email graded exams to students.
The signature of this function is as follows:

```
ubgrade.send_exams(main_dir = None, gradebook = None, template = None, send_sample = False, resend = False)
```

* `main_dir`:  The main grading directory. If not specified the current directory will be used.

* `gradebook`: The name of the gradebook file. This file needs to be located in
the main grading directory. If `None` it will be assumed that the file name
is `gradebook.csv`

* `template`: Name of a text file with the template of the text of emails.
This file needs to be located in the main grading directory. The text can contain `{placeholders}`, enclosed in braces.
Each placeholder needs to be a name of a column of the gradebook.
The message to each student will be formatted by replacing each placeholder with the value from the corresponding column.
If template is `None`, an empty string will be used as the email text.
If the first line of the template file starts with the string `subject:` then the reminder of this line will be
used as the subject of the message. If the file does not specify the subject, the function will prompt the user
to provide one.

* `send_sample`: Boolean. If `True` a single email message will be send with the recipient address set to be the same as the
sender address. This can be used to test if messages are properly formatted before sending them to students.

* `resend`: Boolean. Email addresses to which messages have been sent are recorded, and by default omitted when
the function is called again. Setting `resend` to `True` overrides this behavior, and emails are sent to every
email address in the gradebook.

Note that this function will send emails only to students for whom graded exam files are found.


## Version changes

**0.1.7**
- Bug fix.

**0.1.6**
- Added autorotation of scanned pdf files.
- Bug fix: all files with the same exam page number were being saved in the same file for grading,
  irrespective of the root of their QR code. This is fixed now.
- Tools for handling pages with missing QR codes or person number rewritten and moved to a separate file.

**0.1.5**
- Reliability improvements in email tools.

**0.1.4**
- Added an option to indicate which pages should be skipped from grading by setting their maximal score to 0.
- Added an option to batch process files to prepare them for grading.
- `qr_prefix` can be now an empty string.
- Restructured `prepare_grading_tools` to simplify processing pages with missing data.
- Some bug fixes.
