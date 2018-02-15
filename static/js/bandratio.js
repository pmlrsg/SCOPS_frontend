function getDOM(xmlstring) {
    parser=new DOMParser();
    return parser.parseFromString(xmlstring, "text/xml");
}

function remove_tags(node) {
    var result = "";
    var nodes = node.childNodes;
    var tagName = node.tagName;

    if (!nodes.length) {
        if (node.nodeValue == "π") result = "pi";
        else if (node.nodeValue == "·") result = "*";
        else if (node.nodeValue == " ") result = "";
        else if (node.nodeValue == "×") result = "*"
        else result = node.nodeValue;
    } else if (tagName == "mo" && node.nodeValue == "×") {
        result = "("+remove_tags(nodes[0])+")*("+remove_tags(nodes[1])+")";
    } else if (tagName == "mfrac") {
        result = "("+remove_tags(nodes[0])+")/("+remove_tags(nodes[1])+")";
    } else if (tagName == "msup") {
        result = "("+remove_tags(nodes[0])+")**("+remove_tags(nodes[1])+"))";

    } else for (var i = 0; i < nodes.length; ++i) {
        result += remove_tags(nodes[i]);
    }

    if (tagName == "mfenced") result = "("+result+")";
    if (tagName == "msqrt") result = "Math.sqrt("+result+")";

    return result;
}

function stringifyMathML(mml) {
   xmlDoc = getDOM(mml);
   return remove_tags(xmlDoc.documentElement);
}

function add_eq(force) {
   document.getElementById("eq_name_container").className = document.getElementById("eq_name_container").className.replace(/(\s|^)'has-error'(\s|$)/, ' ')
   eq_name = document.getElementById("eq_name").value.replace(/ /g,"_");
   if (eq_name.length > 1) {
      mathml = org.mathdox.formulaeditor.FormulaEditor.getEditorByTextArea('formula1').getMathML();
      success = eq_test(stringifyMathML(mathml).replace(/band/g, ''))
      if (force == true) {
         success = true
      }
      if (success === true) {
         var listdiv = document.getElementById("eq_list");
         var elementexists = document.getElementById(eq_name)
         var new_eq = document.createElement('a');
         if (elementexists != null) {
            elementexists.getElementsByClassName('mathml')[0].innerHTML = mathml
            document.getElementById('equation_flag_' + eq_name).value = stringifyMathML(mathml)
         } else {
            new_eq.id = eq_name
            new_eq.setAttribute('href', '#');
            new_eq.setAttribute('class', 'list-group-item')
            new_eq.innerHTML = "<h5 class='list-group-item-heading'>" + eq_name + "</h5>" + "<div style='display:none' class='mathml'>"+ mathml +"</div>";
            listdiv.appendChild(new_eq);
            line_list = document.getElementById("line_list")
            for (var i = 0; i < line_list.children.length; i++){
               line_name = line_list.children[i].getElementsByTagName('h4')[0].innerHTML
               line_list.children[i].innerHTML += "<label id='"+eq_name+"_label'><input type='checkbox' id='" + line_name + "_" + eq_name + "' name='" + line_name + "_" + eq_name + "'> " + eq_name + "</label>";
            }
            document.getElementById('equations').innerHTML += "<input type='hidden' name='equation_flag_"+eq_name+"' id=name='equation_flag_"+eq_name+"' value='"+ stringifyMathML(mathml) +"'>"
            document.getElementById('algorithm_all_checks').innerHTML += "<label id='"+eq_name+"_label'><input type='checkbox' id='"+ eq_name +"'> "+eq_name + "</label>";
         }
      } else {
         if (document.getElementById('eq_error') == null) {
            var errordiv = document.createElement('div');
            errordiv.id = "eq_error";
            errordiv.className = "alert alert-dismissable alert-danger";
            errordiv.innerHTML = '<button type="button" class="close" data-dismiss="alert">×</button><strong>The input equation did not evaluate to a number, are you sure it is valid? If you are certain it works click "force" <button class="btn btn-info" onclick=add_eq(force=true) data-dismiss="alert">force</button></strong>'
            document.getElementById("eq_name_container").appendChild(errordiv)
            return false;
         }
      }
   } else {
      document.getElementById("eq_name_container").className += " has-error"
   }
}

function eq_test(eq) {
   try {
      console.log(eq);
      test = typeof eval(eq)
   } catch (err) {
      test = "failure"
   }
   if (test === "number") {
      success = true
   } else {
      success = false
   }
   return success
}

function remove_eq() {
   var selected = eq_list.getElementsByClassName("active")[0].id
   eqtaglist = document.querySelectorAll('[id*="'+selected+'"]')
   for (var i = 0; i < eqtaglist.length; i++){
      eqtaglist[i].innerHTML='';
      eqtaglist[i].remove();
   }
}

function edit_eq() {
   var eq_list = document.getElementById("eq_list")
   var selected = eq_list.getElementsByClassName("active")[0]
   document.getElementById("eq_name").value=selected.id
   mathml = selected.getElementsByClassName("mathml")[0].innerHTML
   org.mathdox.formulaeditor.FormulaEditor.getEditorByTextArea("formula1").loadMathML(mathml);
   org.mathdox.formulaeditor.FormulaEditor.getEditorByTextArea("formula1").redraw();

}

function new_eq() {
   document.getElementById("eq_name").value = ""
   org.mathdox.formulaeditor.FormulaEditor.getEditorByTextArea("formula1").loadMathML(mathml);
   org.mathdox.formulaeditor.FormulaEditor.getEditorByTextArea("formula1").redraw();
}

function band_input(band) {
   var editor = org.mathdox.formulaeditor.FormulaEditor.getEditorByTextArea("formula1");
   for (var i = 0, len = band.length; i < len; i++) {
      var position = editor.cursor.position;
      var index = editor.cursor.position.index;
      position.row.insert(index, position.row.newSymbol(band[i]))
      editor.cursor.moveRight();
      editor.redraw()
      editor.save()
   }
}

function all_check() {
   check_list = document.getElementById('algorithm_all_checks').querySelectorAll("input[type='checkbox']");
   for (var i = 0; i < check_list.length; i++) {
         line_checks = document.getElementById('line_list').querySelectorAll('[id*=_' +check_list[i].id+']');
         for (var j = 0; j < line_checks.length; j++) {
            if (check_list[i].checked) {
               line_checks[j].checked = true;
            } else {
               line_checks[j].checked = false;
            };
         };
      };
   check_list = document.getElementById('plugins_all_checks').querySelectorAll("input[type='checkbox']");
   for (var i = 0; i < check_list.length; i++) {
         line_checks = document.getElementById('line_list').querySelectorAll('[id*=' +check_list[i].id+']');
         console.log(line_checks);
         for (var j = 0; j < line_checks.length; j++) {
            if (check_list[i].checked) {
               line_checks[j].checked = true;
            } else {
               line_checks[j].checked = false;
            };
         };
      };

   };
