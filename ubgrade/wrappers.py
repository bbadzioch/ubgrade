from ubgrade.prepare_grading_tools import PrepareGrading
from ubgrade.read_scores_tools import ReadScores
from ubgrade.assemble_graded_tools import AssembleGradedExams
from ubgrade.email_tools import EmailGradedExams



def prep_grading(maxpoints, main_dir = None, gradebook = None, rotate=None, batch=False, files=None,  init_grading_data=False):
    
    x = PrepareGrading(maxpoints = maxpoints, 
                       main_dir = main_dir, 
                       gradebook = gradebook, 
                       init_grading_data=init_grading_data)
    x.prepare_grading(files = files, rotate=rotate, batch = batch)



def read_scores(main_dir = None, gradebook = None, new_gradebook = None):
    
    x = ReadScores(main_dir = main_dir, gradebook = gradebook)
    x.get_scores(save=True, new_gradebook = new_gradebook)




def assemble_exams(main_dir = None, gradebook = None, prob_labels = None, extras = None, flatten = False):
    
    x = AssembleGradedExams(main_dir = main_dir, gradebook = gradebook) 
    x.assemble_by_student(prob_labels = prob_labels, extras = extras, flatten = flatten)



def send_exams(main_dir = None, gradebook = None, template = None, send_sample=False, resend = False):
    
    x = EmailGradedExams(main_dir = main_dir, template = template, gradebook = gradebook)
    x.send_exams(send_sample=send_sample, resend = resend)
