#! /usr/bin/env python

###########################################################
# This file has been created by NERC-ARF Data Analysis Node and
# is licensed under the GPL v3 Licence. A copy of this
# licence is available to download with this file.
###########################################################
from __future__ import division

import sys
if sys.version_info[0] < 3:
    import ConfigParser
else:
    import configparser as ConfigParser
import glob
import xml.etree.ElementTree as Etree
import os
import datetime
import random
import math
import logging
import collections

from flask import Flask, send_from_directory
from flask import render_template, abort
from flask import request, redirect, url_for, flash
from flask import jsonify
from numpy import arange
from werkzeug.utils import secure_filename
from arsf_dem import dem_nav_utilities
from arsf_dem import grass_library
import legacy_functions


# Try to import NERC-ARF version of web_functions first.
try:
    from common_arsf.web_functions import requires_auth, send_email
# Fallback on internal version
except ImportError :
    from scops_web_functions import requires_auth, send_email

main_config_file = os.path.join(os.path.split(__file__)[0],'web.cfg')
if os.path.exists(main_config_file):
    flask_config = ConfigParser.SafeConfigParser()
    flask_config.read(main_config_file)
    CONFIG_OUTPUT = flask_config.get('outputs', 'config_output')
    UPLOAD_FOLDER = flask_config.get('outputs', 'dem_upload')
    WEB_PROCESSING_FOLDER = flask_config.get('outputs', 'processing_base')
    STATUS_FILE_FOLDER = flask_config.get('outputs', 'status_folder')
    SEND_EMAIL = flask_config.get('details', 'email')
    SYMLINK_PATH = flask_config.get('symlinks', 'hyperspectral_symlinks')
    LOG_FILE = flask_config.get('outputs', 'logfile')
    LEGACY_PAGE_GEN = not flask_config.getboolean('database', 'use_database')
    SKIP_CONFIRMATION = flask_config.getboolean('outputs', 'skip_confirmation')
    if not LEGACY_PAGE_GEN:
        DB = flask_config.get('database', 'db_location') if flask_config.get('database', 'db_location') != 'None' else None
        if DB is None:
            DB = os.path.join(os.path.split(__file__)[0], 'scops_db.db')
    SENSORS = {sensor.replace("sensor_",""): flask_config._sections[sensor] for sensor in flask_config.sections() if "sensor" in sensor}
    #set pixel sizes, these probably won't need to change ever
    PIXEL_SIZES = arange(0.5, 7.5, 0.5)
    USE_STATUS_DB = flask_config.getboolean('database', 'use_status_database')
    if USE_STATUS_DB:
        STATUS_DB_LOCATION = flask_config.get('database', 'status_database_location') if flask_config.get('database', 'status_database_location') != 'None' else None
        if not os.path.isfile(STATUS_DB_LOCATION):
            raise IOError("status database not in location specified {}".format(STATUS_DB_LOCATION))
else:
    raise IOError("Config file web.cfg does not exist, please create this file. A template has been provided in web_template.cfg")

def getifov(sensor):
    """
    Function for sensor ifov grabbing
    :param sensor: sensor name, fenix eagle or hawk
    :type sensor: str

    :return: ifov
    :rtype: float
    """
    if "fenix" in sensor:
        ifov = 0.001448623
    if "eagle" in sensor:
        ifov = 0.000645771823
    if "hawk" in sensor:
        ifov = 0.0019362246375
    if "owl" in sensor:
        ifov = 0.0010995574
    return ifov

def sensor_lookup(sensor_prefix):
    for sensor in SENSORS:
        if SENSORS[sensor]["prefix"] == sensor_prefix:
            return sensor

def pixelsize(altitude, sensor):
    """
    Works out the best pixelsize for a given sensor

    :param altitude: altitude in meters
    :type altitude: int
    :param sensor: sensor name, fenix eagle or hawk
    :type sensor: str

    :return: pixel_size, recommended to be rounded
    :rtype: float
    """
    return 2 * altitude * math.tan(getifov(sensor) / 2)

def hdr_reader(hdr_file_path):
    """
    Reads a header file and returns a dictionary of variables, would probably be
    worth including a variable list in future
    :param hdr_file_path: path to a header file
    :type hdr_file_path: str

    :return: hdr_dict, dictionary of variables
    :rtype: dict
    """
    hdr_dict={}
    for line_num, line in enumerate(open(hdr_file_path)):
        if '=' in line:
            if not '{' in line:
                line = line.replace('\n', '')
                var_name, var_val = line.split(' = ')
                hdr_dict[var_name] = var_val
            elif ('{' in line) and ('}' in line):
                line = line.replace('\n','')
                var_name, var_val = line.split(' = ')
                var_val = var_val.replace('{','').replace('}','')
                var_val = var_val.split(',')
                hdr_dict[var_name] = var_val
            elif '{' in line:
                list_var = [line.split('{')[-1].replace('\n','')]
                for seek_num, seek_line in enumerate(open(hdr_file_path)):
                    if (seek_num > line_num):
                        if '}' in seek_line:
                            break
                        else:
                            list_var.append(seek_line.replace('\n', ''))
                line = line.replace('\n', '')
                var_name, var_val = line.split(' = ')
                var_val = ''.join(list_var).strip('{}')
                hdr_dict[var_name] = var_val.split(',')
    return hdr_dict

def latlon_to_utm(lat,lon):
    zone = int(math.floor((((lon + 180) / 6) % 60))) + 1
    hem = 'N' if (lat > 0) else 'S'
    return zone, hem

def confirm_email(config_name, project, email):
    """
    Sends a confirmation email to the email associated with a request, this
    contains a link specific to the config file being referenced.
    It will update the config file to show as confirmed=True when successful

    :param config_name:
    :param project:
    :param email:
    """
    confirmation_link = url_for("confirm_request", configname = config_name, project = project)

    message = "You have received this email because your address was used to request processing from the ARSF web" \
              " processor. If you did not do this please ignore this email.\n\n" \
              "Please confirm your email with the link below:\n" \
              "\n" \
              "%s\n\n" \
              "If you have any questions or issues accessing the above link" \
              " please email arsf-processing@pml.ac.uk quoting the reference %s" % (confirmation_link, config_name)

    send_email(message, email, "ARSF confirmation email", SEND_EMAIL)
