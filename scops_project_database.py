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
import re
import sqlite3
import json
import support_functions

# Try to import NERC-ARF version of web_functions first.
try:
    from common_arsf.web_functions import requires_auth, send_email
# Fallback on internal version
except ImportError :
    from scops_web_functions import requires_auth, send_email

FLIGHT_LIST = []

logger = logging.getLogger('scops_processing_page')

def create_db():
    conn = sqlite3.connect(support_functions.DB)
    c = conn.cursor()
    c.execute('''CREATE TABLE projects (id INTEGER PRIMARY KEY AUTOINCREMENT, uk BOOL, optimel_pixel FLOAT, north STRING, south STRING, east STRING, west STRING, julian_day INTEGER, year INTEGER, sortie STRING, project_code STRING, utmzone STRING, folder STRING)''')
    c.execute('''CREATE TABLE flightlines (id INTEGER PRIMARY KEY AUTOINCREMENT, proj_id INTEGER, optimel_pixel FLOAT, north STRING, south STRING, east STRING, west STRING, total_bands, name, sensor STRING, bands)''')
    conn.commit()
    c.close()

def insert_proj_to_db(project):
    conn = sqlite3.connect(support_functions.DB)
    c = conn.cursor()
    c.execute('INSERT INTO projects VALUES (NULL,?,?,?,?,?,?,?,?,?,?,?,?)', [project['uk'],
                                                                             project['optimal_pixel'],
                                                                             project['bounds']['n'],
                                                                             project['bounds']['s'],
                                                                             project['bounds']['e'],
                                                                             project['bounds']['w'],
                                                                             project['julian_day'],
                                                                             project['year'],
                                                                             project['sortie'],
                                                                             project['project_code'],
                                                                             project['utmzone'],
                                                                             project['folder']])
    conn.commit()
    c.close()
    return c.lastrowid

def insert_flightline_into_db(proj_id, line):
    conn = sqlite3.connect(support_functions.DB)
    c = conn.cursor()
    c.execute('INSERT INTO flightlines VALUES (NULL,?,?,?,?,?,?,?,?,?,?)', [proj_id,
                                                                        line['optimal_pixel'],
                                                                        line['bounds']['n'],
                                                                        line['bounds']['s'],
                                                                        line['bounds']['e'],
                                                                        line['bounds']['w'],
                                                                        line['bandsmax'],
                                                                        line['name'],
                                                                        line['sensor'],
                                                                        json.dumps(line['bands'])])
    conn.commit()
    c.close()

def list_projects():
    conn = sqlite3.connect(support_functions.DB)
    c = conn.cursor()
    c.execute("SELECT * FROM projects")
    out = c.fetchall()
    conn.commit()
    c.close()
    return out

def list_flightlines():
    conn = sqlite3.connect(support_functions.DB)
    c = conn.cursor()
    c.execute("SELECT * FROM flightlines")
    out = c.fetchall()
    conn.commit()
    c.close()
    return out

def get_project_from_db(year, day, sortie, project_code):
    if sortie == 'None':
        sortie = None
    conn = sqlite3.connect(support_functions.DB)
    c = conn.cursor()
    vals =  [year, day, sortie, project_code]
    c.execute("SELECT * FROM projects WHERE year IS ? AND julian_day IS ? AND sortie IS ? AND project_code IS ?", [str(year), str(day), sortie, project_code])
    project = c.fetchone()
    projectdict = {}
    keys = ["id", "uk", "optimal_pixel", "north", "south", "east", "west", "julian_day", "year", "sortie", "project_code", "utmzone", "folder"]
    for i, column in enumerate(project):
        projectdict[keys[i]] = column
    conn.commit()
    c.close()
    return projectdict

def get_project_flights(proj_db_id):
    conn = sqlite3.connect(support_functions.DB)
    c = conn.cursor()
    c.execute("SELECT * FROM flightlines WHERE proj_id IS ?", [proj_db_id])
    flightlines = c.fetchall()
    flightline_dicts = []
    #convert the output to dictionaries
    keys = ["id", "proj_id", "optimal_pixel", "north", "south", "east", "west", "bandsmax", "name", "sensor", "bands"]
    for flightline in flightlines:
        #create a dict to put values in
        f = {}
        for i, column in enumerate(flightline):
            if not i == 10:
                f[keys[i]] = column
            else:
                f[keys[i]] = json.loads(column)
        flightline_dicts.append(f)
    conn.commit()
    c.close()
    return flightline_dicts


def proj_folder_to_details(flight):
    try:
        flight = os.path.basename(flight)
        proj_regex = re.compile("([A-Za-z0-9]+_[0-9]+)-([0-9]{4})_([0-9]{3})([a-zA-Z])_")
        proj_code =  proj_regex.search(flight).group(1)
        year = proj_regex.search(flight).group(2)
        day = proj_regex.search(flight).group(3)
        sortie = proj_regex.search(flight).group(4)
    except:
        try:
            proj_regex = re.compile("([A-Za-z0-9]+_[0-9]+)-([0-9]{4})_([0-9]{3})_")
            proj_code =  proj_regex.search(flight).group(1)
            year = proj_regex.search(flight).group(2)
            day = proj_regex.search(flight).group(3)
            sortie = None
        except:
            logger.error("failed to find details")
            logger.error("flight")
            raise Exception
    return proj_code, year, day, sortie


def check_db_existence(flight):
    return False


def db_gen():
    years = range(2004, 2017)
    days = range(1, 365)
    #grab the project folders
    project_folders = []
    for year in years:
        year_projects = False
        for day in days:
            projs = glob.glob("/users/rsg/arsf/arsf_data/{}/flight_data/*/*{}_{}*".format(year, year, format(day, '03')))
            project_folders.extend(projs)
            year_projects = True

        if not year_projects:
            for day in days:
                projs = glob.glob("/users/rsg/arsf/arsf_data/{}/flight_data/*{}_{}*".format(year, year, format(day, '03')))
                project_folders.extend(projs)
    for flight in project_folders:
        if not check_db_existence(flight):
            try:
                record = db_gen_flight_record(flight)
                if record:
                    project, lines = (record)
                else:
                    continue
            except TypeError:
                continue
            except Exception as e:
                logger.error(e)
                logger.error("Record creation failed! {}".format(flight))
                continue
            proj_id = insert_proj_to_db(project)
            for line in lines:
                insert_flightline_into_db(proj_id, line)

def create_line_info(main_delivery):
    # grab 2 random flightlines for sampling of altitude, any more is going to cause problems with speed
    #need this for the pixel size guesstimation
    sampled_nav = random.sample(glob.glob(main_delivery[0] + "/flightlines/navigation/*_nav_post_processed.bil"), 2)

    # we should base pixel size off the minimum
    altitude = dem_nav_utilities.get_min_max_from_bil_nav_files(sampled_nav)["altitude"]["min"]

    # begin building the lines for output
    line_hdrs = [f for f in glob.glob(main_delivery[0] + '/flightlines/level1b/*.bil.hdr') if "mask" not in f]

    lines = []
    for line in line_hdrs:
        linehdr = support_functions.hdr_reader(line)
        waves = linehdr['Wavelength']
        bands=[]
        sensor = support_functions.sensor_lookup(os.path.basename(line)[0])
        # calculate pixelsize
        pixel = support_functions.pixelsize(altitude, sensor)
        # round it to .5 since we don't need greater resolution than this
        pixel = round(pixel * 2) / 2
        linexml = Etree.parse(glob.glob(main_delivery[0] + '/flightlines/line_information/' + os.path.basename(line)[:-10] + "*.xml")[0]).getroot()
        line_bounds = {
           'n': linexml.find('.//{http://www.isotc211.org/2005/gmd}northBoundLatitude').find(
              '{http://www.isotc211.org/2005/gco}Decimal').text,
           's': linexml.find('.//{http://www.isotc211.org/2005/gmd}southBoundLatitude').find(
              '{http://www.isotc211.org/2005/gco}Decimal').text,
           'e': linexml.find('.//{http://www.isotc211.org/2005/gmd}eastBoundLongitude').find(
              '{http://www.isotc211.org/2005/gco}Decimal').text,
           'w': linexml.find('.//{http://www.isotc211.org/2005/gmd}westBoundLongitude').find(
              '{http://www.isotc211.org/2005/gco}Decimal').text
        }
        for enum, band in enumerate(waves):
            bands.append({"band_main": (enum + 1),
                          "band_full": str(enum+1)+"("+str(band)+"nm)"})

        bands_key = [key for key in linehdr.keys() if "bands" in key][0]

        linedict = {
           "name": os.path.basename(line)[:-10],
           "optimal_pixel": pixel,
           "bounds": line_bounds,
           "bandsmax": int(linehdr[bands_key]),
           "bands": bands,
           "sensor" : sensor
        }
        lines.append(linedict)

    # sort the lines so they look good on the web page
    lines = sorted(lines, key=lambda line: line["name"])
    return lines

def db_gen_flight_record(folder):
    try:
        proj_code, year, day, sortie = proj_folder_to_details(folder)
    except:
        return False
    # Need to add a 0 or two to day if it isn't long enough
    day = str(day)

    # need to convert day to 00# or 0## for string stuff
    if len(day) == 1:
        day = "00" + day
    elif len(day) == 2:
        day = "0" + day

    # check if the symlink for this day/year/proj code combo exists
    if sortie is None:
        symlink_name = proj_code + '-' + year + '_' + day
    else:
        symlink_name = proj_code + '-' + year + '_' + day + sortie

    # this should (should) be where the kml is on web server, makes it annoying to test locally though
    path_to_symlink = os.path.join(support_functions.SYMLINK_PATH, year, symlink_name)

    try:
        hyper_delivery = glob.glob(folder + '/delivery/*hyperspectral*')
    except:
        #if the hyperspectral delivery doesn't exist then we either haven't finished processing it or there is no
        # hyperspectral data available. The user can't access it.
        logger.warning("no hyper delivery!")
        hyper_delivery = None

    try:
        thermal_delivery = glob.glob(folder + '/delivery/*owl*')
    except:
        #if the hyperspectral delivery doesn't exist then we either haven't finished processing it or there is no
        # hyperspectral data available. The user can't access it.
        logger.warning("no thermal delivery!")
        thermal_delivery = None

    if not hyper_delivery:
        main_delivery = thermal_delivery
    else:
        main_delivery = hyper_delivery

    # using the xml find the project bounds
    try:
        projxml = Etree.parse(glob.glob(main_delivery[0] + '/project_information/*project.xml')[0]).getroot()
    except:
        logger.error("projxml failed")
        logger.error(main_delivery)
        try:
            logger.info(glob.glob(main_delivery[0] + '/project_information/*project.xml'))
        except:
            pass
        logger.info(folder)
        return False
    #This is kind of gross but it's the best way to grab the full project bounds quickly, another option may be grabbing from the mapped header files
    bounds = {
       'n': projxml.find('.//{http://www.isotc211.org/2005/gmd}northBoundLatitude').find(
          '{http://www.isotc211.org/2005/gco}Decimal').text,
       's': projxml.find('.//{http://www.isotc211.org/2005/gmd}southBoundLatitude').find(
          '{http://www.isotc211.org/2005/gco}Decimal').text,
       'e': projxml.find('.//{http://www.isotc211.org/2005/gmd}eastBoundLongitude').find(
          '{http://www.isotc211.org/2005/gco}Decimal').text,
       'w': projxml.find('.//{http://www.isotc211.org/2005/gmd}westBoundLongitude').find(
          '{http://www.isotc211.org/2005/gco}Decimal').text
    }

    #TODO have per line bounds so the bounding box can be reduced intelligently

    # get the utm zone
    utmzone = support_functions.latlon_to_utm(float(bounds["n"]), float(bounds["e"]))

    # if it's britain we should offer UKBNG on the web page
    if utmzone[0] in [29, 30, 31] and utmzone[1] in 'N':
        britain = True
    else:
        britain = False

    lines = []
    if hyper_delivery:
        lines.extend(create_line_info(hyper_delivery))

    if thermal_delivery:
        lines.extend(create_line_info(thermal_delivery))

    pixels = [line["optimal_pixel"] for line in lines]

    pixel = sum(pixels)/len(pixels)

    # creates the webpage by handing vars into the template engine
    return {"uk" : britain,
           "optimal_pixel" : pixel,
           "bounds" : bounds,
           "julian_day": day,
           "year":year,
           "sortie":sortie,
           "project_code":proj_code,
           "utmzone" : "UTM zone " + str(utmzone[0]) + str(utmzone[1]),
           "folder" : folder}, lines

def db_update():
    """
    place holder, should search for new projects!
    """
    return True

if not os.path.isfile(support_functions.DB):
    create_db()
    db_gen()
else:
    db_update()
