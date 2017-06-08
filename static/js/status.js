function update_status(project_string, project_code) {
   var xhttp;
   if (window.XMLHttpRequest) {
      xhttp = new XMLHttpRequest();
   } else {
      // code for IE6, IE5
      xhttp = new ActiveXObject("Microsoft.XMLHTTP");
   }
   xhttp.onreadystatechange = function() {
      if (xhttp.readyState === 4 && xhttp.status === 200) {
         page_deets = xhttp.response;
         for(var key in page_deets){
            line = document.getElementById(key)
            document.getElementById(key + "_file_size").innerHTML = "Unzipped size: "+page_deets[key]["filesize"]+" " +page_deets[key]["bytesize"]
            if (page_deets[key]["flag"]) {
               document.getElementById(key + "_status_ind").innerHTML = "ERROR: "+page_deets[key]["stage"]
            } else {
               document.getElementById(key + "_status_ind").innerHTML = "Stage: "+page_deets[key]["stage"]
            }
            document.getElementById(key + "_compressed_size").innerHTML = "Compressed download size: "+page_deets[key]["zipsize"]+" "+page_deets[key]["zipbyte"]
            document.getElementById(key + "_progress_indicator").style["width"]=page_deets[key]["progress"]+"%"
            if (page_deets[key]["flag"]) {
               document.getElementById(key + "_progress_bar").className = document.getElementById(key + "_progress_bar").className.replace("active","")
               document.getElementById(key + "_download_btn").className = document.getElementById(key + "_download_btn").className.replace("active","")
               if (!(document.getElementById(key + "_progress_indicator").className.indexOf("progress-bar-danger") > -1)) {
                  document.getElementById(key + "_progress_indicator").className += " progress-bar-danger"
               }
            } else {
               if (!(document.getElementById(key + "_progress_bar").className.indexOf("active") > -1)) {
                  document.getElementById(key + "_progress_bar").className += " active"
               }
               document.getElementById(key + "_progress_bar").className = document.getElementById(key + "_progress_bar").className.replace("active","")
            }
            if (page_deets[key]["stage"] == "Complete") {
               document.getElementById(key + "_progress_bar").className = document.getElementById(key + "_progress_bar").className.replace("active","")
               if (!(document.getElementById(key + "_download_btn").className.indexOf("active") > -1)) {
                  document.getElementById(key + "_download_btn").className = document.getElementById(key + "_download_btn").className.replace("disabled","")
                  document.getElementById(key + "_download_btn").className += " active"
               }
            } else {
               if (!(document.getElementById(key + "_progress_bar").className.indexOf("active") > -1)) {
                  document.getElementById(key + "_progress_bar").className += " active"
               }
            }
         }
      }
   };
   xhttp.open("get", "processingupdate/"+ project_string +"?&project="+project_code, true)
   xhttp.responseType = 'json'
   xhttp.send()
}
