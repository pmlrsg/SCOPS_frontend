#! /usr/bin/env python

###########################################################
# This file has been created by the NERC-ARF Data Analysis Node
# and is licensed under the GPL v3 Licence. A copy of this
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
    #this will be used in the future, uploads aren't working at the moment
    UPLOAD_FOLDER = flask_config.get('outputs', 'dem_upload')
    WEB_PROCESSING_FOLDER = flask_config.get('outputs', 'processing_base')
    STATUS_FILE_FOLDER = flask_config.get('outputs', 'status_folder')
    SEND_EMAIL = flask_config.get('details', 'email')
    SYMLINK_PATH = flask_config.get('symlinks', 'hyperspectral_symlinks')
    LOG_FILE = flask_config.get('outputs', 'logfile')
    SERVER_BASE = flask_config.get('details', 'server_base')
else:
    raise IOError("Config file web.cfg does not exist, please create this file. A template has been provided in web_template.cfg")

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

#set pixel sizes, these probably won't need to change ever
PIXEL_SIZES = arange(0.5, 7.5, 0.5)

#set up the logger, if running locally point it to stdout
if __name__ == '__main__':
    file_handler = logging.StreamHandler()
else:
    file_handler = logging.FileHandler(LOG_FILE)
    os.chmod(LOG_FILE, 0664)

formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)

@app.route('/dem_error/<projfolder>', methods=['GET', 'POST'])
@requires_auth
def dem_error(projfolder):
    issue = {'details':"The dem does not cover enough of the area",
             'projfolder':projfolder}
    return render_template("dem_error.html",
                   issue=issue)

@app.route('/dem_error/upload', methods=['POST'])
def reupload_dem():
    dem_name = None
    requestdict = request.form
    try:
        dem = request.files['file']
        app.logger.warning(dem)
        dem_name = secure_filename(dem.filename)
        dem_name = dem_name.replace(".dem","") + datetime.datetime.now().strftime('%Y%m%d%H%M%S') + ".dem"
        try:
            dem_hdr = request.files['header_file']
            dem_hdr_name = dem_name.replace('.dem','.hdr')
            dem_hdr.save(os.path.join(app.config['UPLOAD_FOLDER'], dem_hdr_name))
            os.chmod(os.path.join(app.config['UPLOAD_FOLDER'], dem_hdr_name), 0666)
        except:
            app.logger.info("no header file for dem " + dem_name)
        app.logger.warning(dem_name)
        dem_path = os.path.join(app.config['UPLOAD_FOLDER'], dem_name)
        app.logger.warning(os.path.join(app.config['UPLOAD_FOLDER'], dem_name))
        dem.save(os.path.join(app.config['UPLOAD_FOLDER'], dem_name))
        os.chmod(os.path.join(app.config['UPLOAD_FOLDER'], dem_name), 0666)
        app.logger.warning("success!")
    except Exception as e:
        app.logger.error(e)
        dem_path=None
    projfolder = requestdict['proj']
    config_file = glob.glob(os.path.join(WEB_PROCESSING_FOLDER,'processing',projfolder) + '/*.cfg')[0]
    config = ConfigParser.SafeConfigParser()
    config.read(config_file)
    if dem_name is not None and 'upload' in requestdict["optionsDemRadios"]:
        config.set('DEFAULT', "dem", requestdict["optionsDemRadios"])
        config.set('DEFAULT', "dem_name", os.path.join(app.config['UPLOAD_FOLDER'], dem_name))
    else:
        config.set('DEFAULT', "dem", requestdict["optionsDemRadios"])
    config.set('DEFAULT', 'has_error', 'False')
    config.set('DEFAULT', 'restart', 'True')
    config.write(open(config_file, 'w'))
    return render_template('success.html')

def confirm_email(config_name, project, email):
    """
    Sends a confirmation email to the email associated with a request, this
    contains a link specific to the config file being referenced.
    It will update the config file to show as confirmed=True when successful

    :param config_name:
    :param project:
    :param email:
    """
    confirmation_link = "%s/processor/confirm/%s?project=%s" % (SERVER_BASE, config_name, project)

    message = "You've received this email because your address was used to request processing from the NERC-ARF web" \
              " processor. If you did not do this please ignore this email.\n\n" \
              "Please confirm your email with the link below:\n" \
              "\n" \
              "%s\n\n" \
              "If you have any questions or issues accessing the above link" \
              " please email %s quoting the reference %s" % (confirmation_link, SEND_EMAIL, config_name)

    send_email(message, email, "NERC-ARF web processor confirmation email", SEND_EMAIL)


def validation(request):
    """
    Takes a dictionary of terms for config output and validates that the options are correct/don't pose a risk to our
    systems
    :param request: Config options dictionary
    :type request: dict

    :return: validation state either true or false
    :rtype: bool
    """
    # TODO make more checks, maybe come up with a brief black list, should focus whitelisting though
    validated = True
    for key in request:
        #these should all be numeric values
        if "_band" in key or "pixel_size" in key or "bound" in key or "year" in key or "julianday" in key:
            if math.isnan(float(request[key])):
                validated = False
        #these should either be on or not exist
        if "check" in key:
            if "on" not in request[key]:
                validated = False
        #convert to wkt then back again and compare, this will strip anything that isn't valid
        if "proj_string" in key:
            wktstring = grass_library.grass_location_to_wkt(request[key])
            projstring = grass_library.grass_location_to_proj4(wktstring)

            if request[key] not in projstring:
                validated = False
                flash('Please check this proj string is correct, it cannot be validated', 'proj_error')

        if ";" in request[key]:
            validated = False

    return validated


@app.route('/downloads/<projfolder>', methods=['GET', 'POST'])
@requires_auth
def download_proj(projfolder):
    """
    Takes a http request with the project folder and provides a download
    instance.

    :param projfolder:
    :return: http download
    """
    # TODO make this safer
    #stop naughty paths, we should probably tell them this isn't a very nice thing to do.
    if ".." in projfolder or projfolder.startswith('/'):
        abort(404)
    projfolder = WEB_PROCESSING_FOLDER + "processing/" + projfolder

    #if it doesn't exist it probably means  they are trying to access something
    #they shouldn't!
    if not os.path.exists(projfolder):
        return "The file you tried to access does not exist!"
    download_file = [x for x in glob.glob(projfolder + "/mapped/*.zip") if "bil" not in x][0]
    return send_from_directory(directory=os.path.dirname(download_file),
                               filename=os.path.basename(download_file),
                               mimetype='application/.zip',
                               attachment_filename=os.path.basename(download_file),
                               as_attachment=True)

@app.route('/downloads/<projfolder>/<line_name>', methods=['GET', 'POST'])
@requires_auth
def download_single_file(projfolder, line_name):
    #stop naughty paths, we should probably tell them this isn't a very nice thing to do.
    if ".." in projfolder or projfolder.startswith('/'):
        abort(404)

    projfolder=WEB_PROCESSING_FOLDER + "processing/" + projfolder
    if not os.path.exists(projfolder):
        return "The file you tried to access does not exist!"
    download_file = projfolder + "/mapped/" +line_name+"3b_mapped.bil.zip"
    return send_from_directory(directory=os.path.dirname(download_file),
                               filename=os.path.basename(download_file),
                               mimetype='application/zip',
                               attachment_filename=os.path.basename(download_file),
                               as_attachment=True)


@app.route('/confirm/<path:configname>', methods=['GET', 'POST'])
@requires_auth
def confirm_request(configname):
    """
    Receives request from user email which will then confirm the email address
    used

    :param configname: the project name/config file name that needs to be updated
    :type configname: str

    :return: string
    """
    app.logger.warning("confirm req")
    #build the config location
    configpath = CONFIG_OUTPUT + configname + ".cfg"
    config_file = ConfigParser.SafeConfigParser()

    #read the config and edit it
    config_file.read(configpath)
    config_file.set('DEFAULT', "confirmed", "True")
    config_file.write(open(configpath, 'w'))
    return render_template("confirmation.html")

@app.route('/kmlpage')
def kml_page(name=None):
    """
    simulates a kml page, doesn't contribute to the actual functioning of the
    site
    :param name:
    :return:
    """
    # TODO make kml pages link to jobrequest and remove this
    link_base = SERVER_BASE + "/processor/jobrequest?day=%s&year=%s&project=%s"
    return render_template('kml.html')


@app.route('/')
@app.route('/jobrequest', methods=['GET', 'POST'])
@requires_auth
def job_request(name=None, errors=None):
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
        if len(day) == 1:
            day = "00" + day
        elif len(day) == 2:
            day = "0" + day

        # check if the symlink for this day/year/proj code combo exists
        if sortie is None:
            symlink_name = proj_code + '-' + year + '_' + day
            app.logger.info("sortie is none")
        else:
            symlink_name = proj_code + '-' + year + '_' + day + sortie

        # this should (should) be where the kml is on web server, makes it annoying to test locally though
        path_to_symlink = SYMLINK_PATH + '/' + year + "/" + symlink_name
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
                               Error="The project you asked for does not seem to exist, check the link and try again.",
                               emailaddress=SEND_EMAIL)

    try:
        app.logger.info("folder = " + folder)
        hyper_delivery = glob.glob(folder + '/delivery/*hyperspectral*')
        app.logger.info(hyper_delivery)
    except:
        #if the hyperspectral delivery doesn't exist then we either haven't finished processing it or there is no
        # hyperspectral data available. The user can't access it.
        return render_template("404.html",
                               title="Delivery not found!",
                               Error="The delivery for this dataset could not be found, have you received confirmation of processing completion?",
                               emailaddress=SEND_EMAIL)

    # using the xml find the project bounds
    try:
        projxml = Etree.parse(glob.glob(hyper_delivery[0] + '/project_information/*project.xml')[0]).getroot()
    except:
        return render_template("404.html",
                               title="Delivery not found!",
                               Error="The delivery for this dataset could not be found, have you received confirmation of processing completion?",
                               emailaddress=SEND_EMAIL)
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
    utmzone = latlon_to_utm(float(bounds["n"]), float(bounds["e"]))

    # if it's britain we should offer UKBNG on the web page
    if utmzone[0] in [29, 30, 31] and utmzone[1] in 'N':
        britain = True
    else:
        britain = False

    # begin building the lines for output
    line_hdrs = [f for f in glob.glob(hyper_delivery[0] + '/flightlines/level1b/*.bil.hdr') if "mask" not in f]
    lines = []
    for line in line_hdrs:
        linehdr = hdr_reader(line)
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
    pixel = pixelsize(altitude, sensor)

    # round it to .5 since we don't need greater resolution than this
    pixel = round(pixel * 2) / 2

    # sort the lines so they look good on the web page
    lines = sorted(lines, key=lambda line: line["name"])

    # creates the webpage by handing vars into the template engine
    return render_template('requestform.html',
                           emailaddress=SEND_EMAIL,
                           flightlines=lines,
                           uk=britain,
                           pixel_sizes=PIXEL_SIZES,
                           optimal_pixel=pixel,
                           bounds=bounds,
                           name=name,
                           julian_day=day,
                           year=year,
                           sortie=sortie,
                           project_code=proj_code,
                           utmzone="UTM zone " + str(utmzone[0]) + str(utmzone[1]))


@app.route('/progress', methods=['POST'])
@requires_auth
def progress():
    """
    receives a post request from the jobrequest page and validates the input

    :return: html page
    :rtype: html
    """
    requestdict = request.form
    #checks the input things for a few naughty inputs we don't want (mainly shell injection)
    validated = validation(requestdict)
    if validated:
        lines = []
        #build a list of lines
        for key in requestdict:
            if "_line_check" in key:
                lines.append(key.strip("_line_check"))
        #for nicer formatting
        lines = sorted(lines)
        #create a config filename
        filename = requestdict["project"] + '_' + requestdict["year"] + '_' + requestdict[
           "julianday"] + '_' + datetime.datetime.now().strftime('%Y%m%d%H%M%S')
        dem_path = None
        print "poo!"
        save_dem = True
        if "optionsDemUploadRadios" in requestdict.keys():
            if "ftp_true" in requestdict["optionsDemUploadRadios"]:
                save_dem = False
        if save_dem:
            try:
                dem = request.files['file']
                app.logger.warning(dem)
                dem_name = secure_filename(dem.filename)
                dem_name = dem_name.replace(".dem","") + datetime.datetime.now().strftime('%Y%m%d%H%M%S') + ".dem"
                try:
                    dem_hdr = request.files['header_file']
                    dem_hdr_name = dem_name.replace('.dem','.hdr')
                    dem_hdr.save(os.path.join(app.config['UPLOAD_FOLDER'], dem_hdr_name))
                    os.chmod(os.path.join(app.config['UPLOAD_FOLDER'], dem_hdr_name), 0666)
                except:
                    app.logger.info("no header file for dem " + dem_name)
                app.logger.warning(dem_name)
                dem_path = os.path.join(app.config['UPLOAD_FOLDER'], dem_name)
                app.logger.warning(os.path.join(app.config['UPLOAD_FOLDER'], dem_name))
                dem.save(os.path.join(app.config['UPLOAD_FOLDER'], dem_name))
                os.chmod(os.path.join(app.config['UPLOAD_FOLDER'], dem_name), 0666)
                app.logger.warning("success!")
            except Exception as e:
                app.logger.error(e)
                dem_path=None
        #shove it out to the config folder
        filename = config_output(requestdict, lines=lines, filename=filename, dem_name=dem_path)
        #
        if 'bandratio' in requestdict:
            return redirect(url_for('.bandratiopage', configfile = filename, project=requestdict['project']))
        else:
            return redirect(url_for('submitted'))
    else:
        #we should send them either back to the job request page or failover to 404
        try:
            return redirect(url_for('job_request',
                                    day=requestdict['julianday'],
                                    year=requestdict['year'],
                                    project=requestdict['project'],
                                    errors=errors))
        except:
            return render_template('404.html',
                                   title='Validation Failed!',
                                   Error='Something went wrong validating your inputs')

@app.route('/success')
def submitted():
    """
    Returns the submitted page, to avoid resending of requests by the user
    :return:
    """
    return render_template('submitted.html')


def config_output(requestdict, lines, filename, dem_name=None):
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
    path_to_symlink = SYMLINK_PATH + '/' + requestdict["year"] + "/" + symlink_name
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
    configfile = open(CONFIG_OUTPUT + filename + '.cfg', 'w')
    try:
        config.write(configfile)
        os.chmod(CONFIG_OUTPUT + filename + '.cfg', 0666)
        confirm_email(filename, requestdict["project"], requestdict["email"])
        return filename
    except Exception as e:
        return 0


def progressweight(status):
    weight = 0
    stageprogress=0
    stage="Waiting to process"
    if "complete" in status:
        weight = 0
        stage = "Complete"
        stageprogress = 100
    elif ("waiting to zip" in status) or ("zipping" in status):
        weight = 5
        stage = "Zipping"
        stageprogress = 95
    if "aplmap" in status:
        weight = 50
        stage = "Mapping"
        stageprogress = 45
    elif "apltran" in status:
        weight = 15
        stage = "Translating"
        stageprogress = 30
    elif "aplcorr" in status:
        weight = 15
        stage = "Geo-correction"
        stageprogress = 15
    elif "aplmask" in status:
        weight = 15
        stage = "Masking"
        stageprogress = 0
    flag=False
    if "ERROR" in status:
        flag = True

    weight = float(weight)
    stageprogress = float(stageprogress)
    return stage, weight, stageprogress, flag

@app.route('/status/processingupdate/<projfolder>', methods=['GET'])
@requires_auth
def processingpageupdate(projfolder):
    lines, _, _ = processingpagedetails(projfolder)
    return jsonify(lines)

def processingpagedetails(projfolder):
    #TODO add job number
    projfolder_path = WEB_PROCESSING_FOLDER + "processing/" + projfolder
    config = ConfigParser.SafeConfigParser()
    config.read(glob.glob(projfolder_path + "/*.cfg")[0])
    project_code = config.get("DEFAULT", "project_code")
    equations = [x for x in config.items('DEFAULT') if "eq_" in x[0]]
    processing_details = {
       "dem": config.get("DEFAULT", 'dem'),
       "bounds": config.get("DEFAULT", "bounds"),
       "pixel_size": config.get("DEFAULT", "pixelsize"),
       "projection": config.get("DEFAULT", "projection"),
       "interpolation": config.get("DEFAULT", "interpolation"),
       "projstring": config.get("DEFAULT", "projstring"),
       "equations": equations
    }

    lines = collections.OrderedDict()
    linesfolder = os.listdir(projfolder_path + "/status/")
    linesfolder.sort()
    for line in linesfolder:
        zipbyte="MB"
        bytesize="MB"
        link = url_for('download_single_file', projfolder=projfolder, line_name=os.path.basename(line).replace("_status.txt",""), project=project_code)
        line = projfolder_path + "/status/" + line
        logfile = projfolder_path + "/logs/" + os.path.basename(line).replace("_status.txt", "_log.txt")
        progress = 0
        try:
            approx_percents = list(open(logfile, 'r'))[-6:]
        except IndexError as e:
            approx_percent = "0"
            progress = 0
        except IOError as e:
            #if we've gotten this far then this means the line is not being processed so we can just skip this iteration
            continue

        zipsize = 0
        zipfile_name = WEB_PROCESSING_FOLDER +'/processing/' + projfolder + '/mapped/' + os.path.basename(line).replace("_status.txt","3b_mapped.bil.zip")
        for approx_percent in approx_percents:
            if "Approximate percent complete:" in approx_percent:
                progress = [int(s) for s in approx_percent[-10:].split() if s.isdigit()][0]
                #if it's greater than 100 we picked up the wrong bit of the message
                if progress > 100:
                    progress = [int(s) for s in approx_percent[-16:].split() if s.isdigit()][0]
            elif os.path.exists(zipfile_name):
                #take it up to megabytes
                zipsize = os.path.getsize(zipfile_name)/1024/1024
                if zipsize > 500:
                    zipsize = zipsize / 1024
                    zipbyte="GB"
                zipsize = round(zipsize, 2)
                progress = 0
            else:
                progress = 0

        filesize=0

        for l in open(line):
            filebase = l.split(' ')[0]
            status = " ".join(l.split(' ')[2:])
        for l in open(logfile):
            if "megabytes" in l:
                logline = l.split()
                filesize = float(logline[logline.index("megabytes") - 1])
                if filesize > 500:
                    filesize = round((filesize / 1024), 2)
                    bytesize="GB"

        stage, weight, stageprogress, flag = progressweight(status)
        line_details = {
           "name": filebase,
           "stage": stage,
           "progress": stageprogress + ((progress / 100.0) * weight),
           "filesize": filesize,
           "bytesize": bytesize,
           "flag": flag,
           "link": link,
           "zipsize": zipsize,
           "zipbyte": zipbyte
        }
        lines[os.path.basename(line).replace("_status.txt", "")] = line_details
    return lines, processing_details, project_code

@app.route('/status/<path:projfolder>', methods=['GET'])
@requires_auth
def statuspage(projfolder):
    """
    Creates a status page for a submitted config file, this will show file sizes,
    total progress and download buttons for individual files.

    :param projfolder: folder path
    :return: rendered webpage
    """
    lines, processing_details, project_code = processingpagedetails(projfolder)
    return render_template('status.html',
                            lines=lines,
                            projfolder=projfolder,
                            processing_details=processing_details,
                            project_code=project_code)

@app.route('/bandratio/<configfile>', methods=['GET'])
@requires_auth
def bandratiopage(configfile):
    config_file = ConfigParser.SafeConfigParser()
    config_file.read(CONFIG_OUTPUT + configfile + ".cfg")
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
    path_to_symlink = SYMLINK_PATH + '/' + config_file.get('DEFAULT', 'year') + "/" + symlink_name
    folder = "/" + os.path.realpath(path_to_symlink).replace("/processing/kml_overview", '')
    hyper_delivery = glob.glob(folder + '/delivery/*hyperspectral*')
    linehdrpath = [f for f in glob.glob(hyper_delivery[0] + '/flightlines/level1b/*.bil.hdr') if "mask" not in f][0]
    linehdr = hdr_reader(linehdrpath)
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

@app.route('/bandratio/req', methods=['POST'])
@requires_auth
def bandratiorequest():
    #TODO send request to the ratio deamon, for the moment this sets in the config and is handled by web_qsub
    requestdict = request.form
    bandratiooutput(requestdict['source'], requestdict)
    return redirect(url_for('submitted'))

def bandratiooutput(configfile, requestdict):
    config_path = CONFIG_OUTPUT + configfile + ".cfg"
    config_file=ConfigParser.SafeConfigParser()
    config_file.read(config_path)
    if "lev1" in requestdict['lev1_mapped']:
        config_file.set('DEFAULT', 'bandratioset', "True")
    elif "mapped" in request['lev1_mapped']:
        config_file.set('DEFAULT', 'bandratiomappedset', "True")


    for key in requestdict:
        if "equation_flag" in key:
            print key
            eq_name = key.replace("equation_flag_","")
            print eq_name
            config_file.set('DEFAULT', "eq_"+ eq_name, requestdict[key])
            lines = []
            for key in requestdict:
                print key
                print key
                if eq_name in key and not "equation_flag_" in key:
                    print key
                    lines.append(key)
            if lines:
                for line in lines:
                    line_name = line.replace("_" + eq_name, '')
                    config_file.set(line_name, "eq_"+ eq_name, "True")

    config_file.write(open(config_path, 'w'))


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
    return ifov


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

if __name__ == '__main__':
    app.run(debug=True,
            host='0.0.0.0',
            threaded=True,
            port=5001)
