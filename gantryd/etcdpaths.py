GANTRYD_NAMESPACE = 'gantryd'
PROJECT_NAMESPACE = 'projects'
COMPONENT_NAMESPACE = 'components'
MACHINES_NAMESPACE = 'machines'

STATE_FILE = 'state'
CONFIG_FILE = 'config'

def buildPath(*args):
  return '/' + GANTRYD_NAMESPACE + '/' + '/'.join(args)

def getMachineStatePath(projectName, machineId):
  """ Returns the path for this machine in the etcd config for the project. """
  # gantryd/projects/{project}/machines/{machineid}/state
  return buildPath(PROJECT_NAMESPACE, projectName, MACHINES_NAMESPACE, machineId, STATE_FILE)
    
def getProjectConfigPath(projectName):
  """ Returns the path for this project's config in the etcd config. """
  # gantryd/projects/{project}/config
  return buildPath(PROJECT_NAMESPACE, projectName, CONFIG_FILE)

def getComponentStatePath(projectName, component):
  """ Returns the path for the given component under this project in the etcd config. """
  # gantryd/projects/{project}/components/{componentname}/state
  return buildPath(PROJECT_NAMESPACE, projectName, COMPONENT_NAMESPACE, component.getName(), STATE_FILE)
