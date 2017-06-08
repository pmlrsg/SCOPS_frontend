#!/usr/bin/env python
#-*- coding:utf-8 -*-

###########################################################
# This file has been created by the NERC-ARF Data Analysis Node
# and is licensed under the GPL v3 Licence. A copy of this
# licence is available to download with this file.
###########################################################

import os
import smtplib

from flask import request, Response, Flask
from functools import wraps
from email.mime.text import MIMEText

#Path to CSV file containing passwords
#format is:
#project_code,password
#Assume file is under /usr/local/share/scops_passwords.csv
PASSWORD_FILE = '/usr/local/share/scops_passwords.csv'

###########################################################################
# Simple authentication
###########################################################################
def check_auth(username, password, projcode):
    """
    This function is called to check if a username password combination is valid.
    Uses PASSWORD_FILE.
    """
    auth = False
    if not os.path.isfile(PASSWORD_FILE):
        raise IOError('Could not find SCOPS password file. Expected file\n:'
                      '{}'.format(PASSWORD_FILE))
    for pair in open(PASSWORD_FILE):
        username_auth, password_auth = pair.strip("\n").split(",")
        if username == username_auth and password == password_auth and projcode == username_auth:
            auth = True
    return auth


def authenticate(realm):
    """
    Sends a 401 response that enables basic auth, you must specify your realm
    e.g. https://nerc-arf-dan.pml.ac.uk/status/edit.php would be in the status realm
    """
    return Response(
       'Could not verify your access level for that URL.\n'
       'You have to login with proper credentials', 401,
       {'WWW-Authenticate': 'Basic realm="%s"' % realm})


def requires_auth(f):
    """
    Decorator for authentication, call @requires_auth on a function and it will ask for a log in/password
    You must include a project in the request or it will not authenticate (and will error)
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        try:
            project = request.args["project"]
        except:
            project = request.form["project"]
        if not auth or not check_auth(auth.username, auth.password, project):
            return authenticate(realm=project)
        return f(*args, **kwargs)
    return decorated

###########################################################################
# Email sender
###########################################################################

def send_email(message, receive, subject, sender):
    """
    Sends an email using smtplib
    """
    msg = MIMEText(message)
    msg['From'] = sender
    msg['To'] = receive
    msg['Subject'] = subject

    mailer = smtplib.SMTP('localhost')
    mailer.sendmail(sender, [receive], msg.as_string())
