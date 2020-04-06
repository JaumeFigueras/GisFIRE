from ..GisFireSettings import GisFIRESettings

from qgis.core import QgsExpressionContextUtils

def isAGisFireProject(project):
    if (project is not None):
        scope = QgsExpressionContextUtils.projectScope(project)
        if (scope.hasVariable(GisFIRESettings.VERSION_VARIABLE_NAME)):
            return True
        else:
            return False

def getProjectVariable(project, variable):
    if (project is not None):
        scope = QgsExpressionContextUtils.projectScope(project)
        return scope.variable(variable)
    else:
        return None

def setProjectVariable(project, variable, value):
    if (project is not None):
        QgsExpressionContextUtils.setProjectVariable(project, variable, value)

def removeProjectVariable(project, variable):
    if (project is not None):
        QgsExpressionContextUtils.removeProjectVariable(project, variableº)
