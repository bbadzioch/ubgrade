from ubgrade.grading_base import GradingBase
from ubgrade.exam_code import ExamCode, covers_file

import os
import glob
import json
from time import sleep
from email.message import EmailMessage
import smtplib
import getpass
import pandas as pd



class EmailGradedExams(GradingBase):
    '''
    Class defining mathods for emailing graded exams to students.
    '''

    def __init__(self, template = None, main_dir = None, gradebook = None,  init_grading_data=False):
        '''
        :template:
            Name of a text file the the template of the email text. The file should be placed 
            in the main grading directory. The text can contain {placeholders}, enclosed in braces. 
            Each placeholder needs to be a name of a column of the gradebook. The message to each student 
            will be formatted by replacing each placeholder with the value of the corresponding column. 
            If template is None, an empty string will be used as the email text.

            If the first line of the template file starts with the string 'subject:', the reminder of this
            line will be used as the subject of the message.

         All other arguments are inherited from the GradingBase constructor.
        '''

        GradingBase.__init__(self, main_dir, gradebook, init_grading_data)

        # stmp server data
        self.smtp_server = "smtp.buffalo.edu"
        self.server_port = 465

        # if the server refuses to send more emails at some point, we wil pause
        # for this many seconds and then resume sending exams
        self.reconnect_period = 300

        gradebook_df =  pd.read_csv(self.gradebook)

        # check if the column with student email addresses is present in the gradebook
        if self.email_column not in gradebook_df.columns:
            gradebook_df[self.email_column] = ""
            gradebook_df.to_csv(self.gradebook, index=False)
            print("Email addresses missing in the gradebook, exiting")
            return None

        # check if the template file exists
        if template is None:
            self.template = ""
        elif os.path.isfile(os.path.join(self.main_dir, template)):
            with open(os.path.join(self.main_dir, template)) as foo:
                self.template = foo.read()
        else:
            print(f"File {template} does not exist, exiting.")
            return None


    @staticmethod
    def make_message(template_txt, subject, from_address, to_address, pdf_fname = None, **kwargs):
        '''
        Prepare the email message.

        :template_txt:
            String with the template of the email text.
        :subject:
            String with the subject of the message
        :from_address:
            The sender email address.
        :to_address:
            The recipient email address.
        :pdf_fname:
            The name of the pdf file which will be attached to the email. If None, the email will be 
            formatted without an attachement.  
        :**kwargs:
            Keyword arguments which will be used to replace placeholders in the template of
            the text of the email.

        Returns:
            EmailMessage object
        '''

        # get message text by replacing placeholders with values of the keyword arguments
        msg_text = template_txt.format(**kwargs)

        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = from_address
        msg['To'] = to_address

        msg['Content-Type'] = "text/plain; charset=utf-8"
        msg.set_content(msg_text)

        # add the pdf file as an attachment
        if pdf_fname is not None:
            with open(pdf_fname, 'rb') as f:
                content = f.read()
                msg.add_attachment(content, maintype='application/pdf', subtype='pdf', filename=os.path.basename(pdf_fname))

        body = msg.get_body()
        body.replace_header('Content-Type', 'text/plain; charset=utf-8')

        return msg


    @staticmethod
    def timer(seconds):
        """
        Countdown timer.

        :seconds:
            The number of seconds to count down from.
        """

        for i in range(seconds,0,-1):
            print("\rWill retry in {:3} seconds.".format(i), end='')
            sleep(1)
            sl = len("Will retry in {:3} seconds.".format(i))
            print("\r" + " "*sl + "\r", end='')


    def send_exams(self, send_sample= False, resend = False):
        '''
        Send emails

        :send_sample:
            Boolean. If true a single email message will be send with the recipient address set
            to be the same as the sender address. This can be used to test if messages are properly formatted
            before sending them to students. 
        :resend:
            Boolean. The function records in the grading data email addresses to which messages have been sent,
            and by default omits these addresses when the function is called again. Setting `resend` to `True`, 
            overrides this behavior, and emails are sent to every email address in the gradebook.
        '''

        if send_sample:
            print(f"Sending a sample message.\n")

        # get email addresses to which messages were previously sent
        grading_data = self.get_grading_data()
        emails_sent = set(grading_data["emails_sent"])

        # convert the gradebook into a list of dictionaries, one dictionary
        # for each gradebook row
        gradebook_df = pd.read_csv(self.gradebook)
        gradebook_df = gradebook_df[gradebook_df[self.qr_code_column].notnull()]
        gradebook_df = gradebook_df[gradebook_df[self.email_column].notnull()]
        gradebook_dict = gradebook_df.to_dict(orient='records')

        # get email subject and email text template
        template_lines = self.template.split("\n")
        if template_lines[0].lower().strip().startswith("subject:"):
            subject = template_lines[0][len("subject:"):].strip()
            template_txt = "\n".join(template_lines[1:])
        # if the first line of the template file does not contain
        # the subject, ask the user what the subject should be
        else:
            template_txt = "\n".join(template_lines)
            subject = input("Enter email's subject: ")
        template_txt  =  template_txt.strip()

        # get stmp server login info
        login_name = input("UB login name: ").strip()
        password = getpass.getpass(login_name + " password:")
        from_address = login_name + "@buffalo.edu"

        # prepare and send emails
        for record in gradebook_dict:
            pdf_fname = os.path.join(self.graded_dir, f"{record[self.qr_code_column]}.pdf")

            # get recipient email address
            email_str = str(record['email']).strip()
            if  '@' in email_str:
                to_address = record['email'].strip()
            else:
                to_address = email_str + "@buffalo.edu"

            # check is the message was previously sent
            #if (not send_sample) and (not resend) and (to_address in emails_sent):
            #    print(f"{to_address:30} *********** WAS SENT BEFORE, OMITTING")
            #    continue

            # check if pdf file exists, if it does not, skip
            if not os.path.isfile(pdf_fname):
                if not send_sample:
                    print(f"{to_address:30} *********** FILE {os.path.basename(pdf_fname)} NOT FOUND, OMITTING")
                continue

            if send_sample:
                to_address = from_address

            # format the email message
            msg = self.make_message(template_txt= template_txt,
                                    subject=subject,
                                    from_address = from_address,
                                    to_address = to_address,
                                    pdf_fname = pdf_fname,
                                    **record)

            # send email
            send_success = False
            while not send_success:

                try:
                    server = smtplib.SMTP_SSL(self.smtp_server, self.server_port)
                    server.login(login_name, password)
                    server.send_message(msg, from_addr = from_address, to_addrs = to_address)
                    print("{:30} *********** SENT".format(to_address))
                    server.quit()
                    send_success = True
                    sleep(0.1)
                except smtplib.SMTPException as ex:
                    if ex.__class__ == smtplib.SMTPAuthenticationError:
                         print("Login name or password incorrect, exiting")
                         return None
                    else:
                        print("{:30} *********** NOT SENT: {}".format(to_address, ex))
                        #pause before reattempting to send the message
                        self.timer(self.reconnect_period)

            if send_sample:
                break
            else:
                # save information that the email was sent;
                # we are saving it to the grading data file right away, in case
                # the program gets interrupted for some reason
                if send_success:
                    emails_sent.add(to_address)
                    grading_data = self.get_grading_data()
                    grading_data["emails_sent"] = list(emails_sent)
                    self.set_grading_data(grading_data)
        
        print("***FINISHED***")