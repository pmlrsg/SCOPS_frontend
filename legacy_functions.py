#! /usr/bin/env python

###########################################################
# This file has been created by ARSF Data Analysis Node and
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
import db_testing
import support_functions
from flask import current_app as app

from common_arsf.web_functions import requires_auth, send_email

def legacy_bandratiopage(configfile):
   config_file = ConfigParser.SafeConfigParser()
   config_file.read(os.path.join(support_functions.CONFIG_OUTPUT + configfile + ".cfg"))
   lines = []
   for section in config_file.sections():
      lines.append({ "name": section})
   try:
      sortie = config_file.get('DEFAULT', 'sortie')
   except ConfigParser.NoOptionError:
      sortie = None
   if sortie == "None":
      sortie=''
   try:
      symlink_name = config_file.get('DEFAULT', 'project_code') + '-' +  config_file.get('DEFAULT', 'year') + '_' + config_file.get('DEFAULT', 'julianday') + sortie
   except ConfigParser.NoOptionError:
      #if this hasn't worked we need to abort because the configfile cannot exist
      abort(404)

   # this should (should) be where the kml is on web server, makes it annoying to test locally though
   path_to_symlink = os.path.join(support_functions.SYMLINK_PATH, config_file.get('DEFAULT', 'year'), symlink_name)
   folder = "/" + os.path.realpath(path_to_symlink).replace("/processing/kml_overview", '')
   hyper_delivery = glob.glob(folder + '/delivery/*hyperspectral*')
   linehdrpath = [f for f in glob.glob(hyper_delivery[0] + '/flightlines/level1b/*.bil.hdr') if "mask" not in f][0]
   linehdr = support_functions.hdr_reader(linehdrpath)
   bands = linehdr['Wavelength']
   bands_fixed = []
   #TODO FIXME
   #these equations need updating depending on how many bands the input file has
   equationlist = [{'name' : 'ndvi','asString' : '(band253-band170)/(band253+band170)','asMathML' : '<mfrac><mrow><mi>band253</mi><mo>-</mo><mi>band170</mi></mrow><mrow><mi>band253</mi><mo>+</mo><mi>band170</mi></mrow></mfrac>' },
                   {'name' : 'ndbi','asString' : '(band460-band253)/(band460+band253)','asMathML' : '<mfrac><mrow><mi>band460</mi><mo>-</mo><mi>band253</mi></mrow><mrow><mi>band460</mi><mo>+</mo><mi>band253</mi></mrow></mfrac>'},
                   {'name' : 'ndwi','asString' : '(band281-band396)/(band281+band396)','asMathML' : '<mfrac><mrow><mi>band281</mi><mo>-</mo><mi>band396</mi></mrow><mrow><mi>band281</mi><mo>+</mo><mi>band396</mi></mrow></mfrac>'}]
   for enum, band in enumerate(bands):
      bands_fixed.append({'band_main':"band"+str(enum+1),
                          'band_full':"band"+str(enum+1)+"("+str(band)+"nm)"})
   return render_template('bandratio.html',
                           lines=lines,
                           equationlist=equationlist,
                           bands=bands_fixed,
                           configfile=configfile,
                           project=config_file.get('DEFAULT', 'project_code'))

def legacy_job_request(request, name=None, errors=None):
   """
   Receives a request from html with the day, year and required project code
   then returns a request page based on the data it finds in the proj dir

   :param name: placeholder
   :type name: str

   :return: job request html page
   :rtype: html
   """
   try:
      # input validation, test if these are numbers
      if not math.isnan(float(request.args["day"])):
         day = request.args["day"]
      else:
         raise
      if not math.isnan(float(request.args["year"])):
         year = request.args["year"]
      else:
         #if they aren't there is something wrong with the request
         raise

      # input validation, get rid of any potential paths the user may have used
      #it's used later on for file operations so we should make sure it is safe.
      proj_code = request.args["project"].replace("..", "_").replace("/", "_")

      # check if theres a sortie associated with the day
      try:
         sortie = request.args["sortie"]
      except:
         #if there isn't ignore it
         sortie = None

      # Need to add a 0 or two to day if it isn't long enough
      day = str(day)

      # need to convert day to 00# or 0## for string stuff
      day = day.zfill(3)

      # check if the symlink for this day/year/proj code combo exists
      if sortie is None:
         symlink_name = proj_code + '-' + year + '_' + day
         app.logger.info("sortie is none")
      else:
         symlink_name = proj_code + '-' + year + '_' + day + sortie

      # this should (should) be where the kml is on web server, makes it annoying to test locally though
      path_to_symlink = os.path.join(support_functions.SYMLINK_PATH, year, symlink_name)
      #in case we ever want to know what symlinks have been accessed...
      app.logger.info("location = " + path_to_symlink)
      if os.path.exists(path_to_symlink):
         app.logger.info(os.path.realpath(path_to_symlink))
         folder = "/" + os.path.realpath(path_to_symlink).replace("/processing/kml_overview", '')
      else:
         #this shouldn't fail, but there's always a chance
         raise
   except:
      #if there has been an error return an informative error then bail
      return render_template("404.html",
                             title="Project not found!",
                             Error="The project you asked for does not seem to exist, check the link and try again.")

   try:
      app.logger.info("folder = " + folder)
      hyper_delivery = glob.glob(folder + '/delivery/*hyperspectral*')
      app.logger.info(hyper_delivery)
   except:
      #if the hyperspectral delivery doesn't exist then we either haven't finished processing it or there is no
      # hyperspectral data available. The user can't access it.
      return render_template("404.html",
                             title="Delivery not found!",
                             Error="The delivery for this dataset could not be found, have you received confirmation of processing completion?")

   # using the xml find the project bounds
   try:
      projxml = Etree.parse(glob.glob(hyper_delivery[0] + '/project_information/*project.xml')[0]).getroot()
   except:
      return render_template("404.html",
                             title="Delivery not found!",
                             Error="The delivery for this dataset could not be found, have you received confirmation of processing completion?")
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

   # begin building the lines for output
   line_hdrs = [f for f in glob.glob(hyper_delivery[0] + '/flightlines/level1b/*.bil.hdr') if "mask" not in f]
   lines = []
   for line in line_hdrs:
      linehdr = support_functions.hdr_reader(line)
      waves = linehdr['Wavelength']
      bands=[]
      for enum, band in enumerate(waves):
         bands.append({"band_main": (enum + 1),
                       "band_full": str(enum+1)+"("+str(band)+"nm)"})
      linedict = {
         "name": os.path.basename(line)[:-10],
         "bandsmax": int(linehdr['bands']),
         "bands": bands
      }
      lines.append(linedict)

   # grab 2 random flightlines for sampling of altitude, any more is going to cause problems with speed
   #need this for the pixel size guesstimation
   sampled_nav = random.sample(glob.glob(hyper_delivery[0] + "/flightlines/navigation/*_nav_post_processed.bil"), 2)

   # we should base pixel size off the minimum
   altitude = dem_nav_utilities.get_min_max_from_bil_nav_files(sampled_nav)["altitude"]["min"]

   # for the moment just using fenix
   sensor = "fenix"

   # calculate pixelsize
   pixel = support_functions.pixelsize(altitude, sensor)

   # round it to .5 since we don't need greater resolution than this
   pixel = round(pixel * 2) / 2

   # sort the lines so they look good on the web page
   lines = sorted(lines, key=lambda line: line["name"])

   # creates the webpage by handing vars into the template engine
   return render_template('requestform.html',
                          flightlines=lines,
                          uk=britain,
                          pixel_sizes=support_functions.PIXEL_SIZES,
                          optimal_pixel=pixel,
                          bounds=bounds,
                          name=name,
                          julian_day=day,
                          year=year,
                          sortie=sortie,
                          project_code=proj_code,
                          utmzone="UTM zone " + str(utmzone[0]) + str(utmzone[1]))

def legacy_config_output(requestdict, lines, filename, dem_name=None):
   """
   Writes a config to the web processing configs folder, this will then be picked up by web_qsub

   :param requestdict: A request converted to immutable dict from the job request page
   :type requestdict: immutable dict

   :param lines: list of flightlines to be processed
   :type lines: list

   :param filename: config filename to write to
   :type filename: str

   :return: 1 on success
   :rtype: int
   """
   config = ConfigParser.SafeConfigParser()
   #build the default section
   config.set('DEFAULT', "julianday", requestdict["julianday"])
   config.set('DEFAULT', "year", requestdict["year"])
   config.set('DEFAULT', "sortie", requestdict["sortie"])
   config.set('DEFAULT', "project_code", requestdict["project"])
   config.set('DEFAULT', "projection", requestdict["projectionRadios"])

   if requestdict["sortie"] in "None":
      symlink_name = requestdict["project"] + '-' + requestdict["year"] + '_' + requestdict["julianday"]
      app.logger.info("sortie is none")
   else:
      symlink_name = requestdict["project"] + '-' + requestdict["year"] + '_' + requestdict["julianday"] + requestdict["sortie"]

   # this should (should) be where the kml is on web server, makes it annoying to test locally though
   path_to_symlink = os.path.join(support_functions.SYMLINK_PATH, requestdict["year"], symlink_name)
   #in case we ever want to know what symlinks have been accessed...
   app.logger.info("location = " + path_to_symlink)
   if os.path.exists(path_to_symlink):
      app.logger.info(os.path.realpath(path_to_symlink))
      folder = "/" + os.path.realpath(path_to_symlink).replace("/processing/kml_overview", '')

   config.set('DEFAULT', 'sourcefolder', folder)
   try:
      if requestdict['bandratio'] in "on":
         config.set('DEFAULT', "bandratio", "True")
      else:
         config.set('DEFAULT', "bandratio", "False")
   except:
      config.set('DEFAULT', "bandratio", "False")
   config.set('DEFAULT', "bandratioset", "False")
   config.set('DEFAULT', "bandratiomappedset", "False")
   config.set('DEFAULT', "bandratiolev1complete", "False")
   config.set('DEFAULT', "bandratiomappedcomplete", "False")
   config.set('DEFAULT', "has_error", "False")
   config.set('DEFAULT', 'restart', 'False')
   config.set('DEFAULT', 'ftp_dem', 'False')
   config.set('DEFAULT', 'ftp_dem_confirmed', 'False')

   #if the proj string exists do something about it
   try:
      config.set('DEFAULT', "projstring", requestdict["projString"])
   except:
      config.set('DEFAULT', "projstring", '')

   ftp_true = False
   if "optionsDemUploadRadios" in requestdict.keys():
      if "ftp_true" in requestdict["optionsDemUploadRadios"]:
         ftp_true = True

   if "upload" in requestdict["optionsDemRadios"] and ftp_true:
      config.set('DEFAULT', 'ftp_dem', 'True')
      config.set('DEFAULT', "dem", requestdict["optionsDemRadios"])
      config.set('DEFAULT', "dem_name", "")
   if dem_name is not None and 'upload' in requestdict["optionsDemRadios"]:
      config.set('DEFAULT', "dem", requestdict["optionsDemRadios"])
      config.set('DEFAULT', "dem_name", dem_name)
   else:
      config.set('DEFAULT', "dem", requestdict["optionsDemRadios"])
   #set processing bounds
   config.set('DEFAULT', "bounds",
              requestdict["bound_n"] + ' ' + requestdict["bound_e"] + ' ' + requestdict["bound_s"] + ' ' + requestdict["bound_w"])
   config.set('DEFAULT', "email", requestdict["email"])
   config.set('DEFAULT', "interpolation", requestdict["optionsIntRadios"])
   #pixel sizes need to be added as one field
   config.set('DEFAULT', "pixelsize", requestdict["pixel_size_x"] + ' ' + requestdict["pixel_size_y"])

   #both of these need to be false for the cron job to function correctly
   config.set('DEFAULT', "submitted", "False")
   config.set('DEFAULT', "confirmed", "False")
   config.set('DEFAULT', "status_email_sent", "False")

   #test masking
   mask_keys = [x for x in requestdict if 'mask' in x]
   mask_string = ''
   for key in mask_keys:
      if 'mask_none_check' in key:
         mask_string = "none"
         break
      elif 'mask_all_check' in key:
         mask_string = 'uomnrqabcdef'
         break
      else:
         mask_string += key[-1:]

   config.set('DEFAULT', "masking", mask_string)

   #add a section for each line to be processed
   for line in lines:
      config.add_section(str(line))
      if requestdict['%s_line_check' % line] in "on" or requestdict['process_all_lines'] in "on":
         config.set(str(line), 'process', 'true')
      else:
         config.set(str(line), 'process', 'false')
      config.set(str(line), 'band_range',
                 requestdict["%s_band_start" % line] + '-' + requestdict["%s_band_stop" % line])
   #write it out
   configfile = open(os.path.join(support_functions.CONFIG_OUTPUT, filename + '.cfg'), 'w')
   try:
      config.write(configfile)
      os.chmod(os.path.join(support_functions.CONFIG_OUTPUT, filename + '.cfg'), 0666)
      support_functions.confirm_email(filename, requestdict["project"], requestdict["email"])
      return filename
   except Exception as e:
      return 0