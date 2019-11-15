import webbrowser
from flask import Flask, render_template, redirect, url_for
from flask_wtf import FlaskForm
from flask_bootstrap import Bootstrap
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired
import os
import pdf2image
import base64
import io
import json

from PIL import Image

import sys
sys.path.append("..")
import missing_data_tools as mdt

class Config(object):
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'bardzo-scisle-tajne'

class QRForm(FlaskForm):
    qr_code = StringField('Enter QR code')
    submit = SubmitField(label='Submit')
    skip = SubmitField(label='Skip')

class PnumForm(FlaskForm):
    pnum = StringField('Enter Person Number')
    submit = SubmitField(label='Submit')
    add = SubmitField(label='Add')
    skip = SubmitField(label='Skip')



def get_image(arr):
    img = Image.fromarray(arr)
    buffered = io.BytesIO()
    img.save(buffered, format="JPEG")
    img_str = base64.b64encode(buffered.getvalue()).decode("utf-8") 
    return img_str

    
app = Flask(__name__)
app.config.from_object(Config)
bootstrap = Bootstrap(app)



# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response



@app.route('/qr', methods=['GET', 'POST']) 
def qr_handler():

    global missing_pages, page

    form = QRForm()

    if form.validate_on_submit():
        if form.skip.data:
            qr = "s"
        else:
            qr = form.qr_code.data
        
        missing_pages.set_qr(qr)

        try:
            page = next(missing_pages) 
        except StopIteration:
            return redirect("/done")
        
        return redirect(f'/{page["missing_data"]}')
    
    if not missing_pages.finished:
        if page["missing_data"] == "pnum":
            return redirect(f'/{page["missing_data"]}')
        else:
            return render_template("qr_page.html", 
                                    title = f"QR code missing", 
                                    img_str= get_image(page["image"]), 
                                    source_page_num= page["page"], 
                                    source_file= page["fname"], 
                                    form=form)
    else:
        return redirect("/done")



@app.route('/pnum', methods=['GET', 'POST']) 
def pnum_handler():
    global missing_pages, page

    form = PnumForm()

    if form.validate_on_submit():
        if form.skip.data:
            pnum = "s"
        elif form.add.data:
            pnum = "add"
        else:
            pnum = form.pnum.data
        
        missing_pages.set_pnum(pnum)
        try:
            page = next(missing_pages) 
        except StopIteration:
            return redirect("/done")
        
        return redirect(f'/{page["missing_data"]}')
        
    if not missing_pages.finished:
        if page["missing_data"] == "qr":
            return redirect(f'/{page["missing_data"]}')
        else:
            form.pnum.data  = page["pnum"]
            return render_template("pnum_page.html", 
                                    title = f"Person number  missing", 
                                    img_str= get_image(page["image"]), 
                                    pnum = page["pnum"],
                                    source_page_num= page["page"], 
                                    source_file= page["fname"], 
                                    form=form)
    else:
        return redirect("/done")



@app.route('/done', methods=['GET'])
def finish_handler():

    return  render_template("prep_final.html", 
                            title = f"Completed", 
                            message = "All pages have been processed."
                            )

if __name__ == "__main__":
    missing_pages = mdt.MissingData(main_dir = "../unit_tests", gradebook = None)
    page = next(missing_pages)
    if not missing_pages.finished:
        url = f'http://127.0.0.1:5000/{page["missing_data"]}'
    else:
        url = 'http://127.0.0.1:5000/done'

    webbrowser.open(url)
    app.run(debug=True)

