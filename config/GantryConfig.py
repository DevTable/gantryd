from object import CFObject, CFField
  
class _HealthCheck(CFObject):
  """ A single check to perform to verify that a component is ready to be
      pushed or is running properly.
  """
  kind = CFField('kind')
  id = CFField('id').default('')
  timeout = CFField('timeout').kind(int).default(1)

  def __init__(self):
    super(_HealthCheck, self).__init__('Health Check')
    
  def getTitle(self):
    """ Returns a descriptive title for the check. """
    if self.id != '':
      return self.id
    
    return self.kind
    
    
class _PortMapping(CFObject):
  """ A port mapping of an internal container port to the outside world. """
  external = CFField('external').kind(int)
  container = CFField('container').kind(int)
  kind = CFField('kind').default('tcp')

  def __init__(self):
    super(_PortMapping, self).__init__('Port Mapping')


class _Component(CFObject):
  """ A single gantry component. """
  name = CFField('name')
  repo = CFField('repo')
  tag = CFField('tag').default('latest')
  command = CFField('command').list_of(str).default([])
  user = CFField('user').default('')
  ports = CFField('ports').list_of(_PortMapping)
  ready_checks = CFField('readyChecks').list_of(_HealthCheck).default([])
  health_checks = CFField('healthChecks').list_of(_HealthCheck).default([])
  ready_timeout = CFField('readyTimeout').kind(int).default(10000)
    
  def __init__(self):
    super(_Component, self).__init__('Component')

  def getFullImage(self):
    """ Returns the full image ID for this component, of the form 'repo:tag' """
    return self.repo + ':' + self.tag
    
  def getUser(self):
    """ Returns the user under which to run the container or None if none. """
    if not self.user:
      return None
      
    return self.user
    
  def getCommand(self):
    """ Returns the command string to run on component startup or None if none. """
    if not self.command:
      return None
      
    return ' '.join(self.command)
  
  def getContainerPorts(self):
    """ Returns the ports exposed by this component. """
    return [p.container for p in self.ports]
    
  def getReadyCheckTimeout(self):
    """ Returns the maximum amount of time, in seconds, before ready checks time out. """
    return self.ready_timeout / 1000


class Configuration(CFObject):
  """ The overall gantry configuration. """
  components = CFField('components').list_of(_Component)
  
  def __init__(self):
    super(Configuration, self).__init__('Configuration')
    
  def lookupComponent(self, name):
    """ Looks up the component with the given name under this config. """    
    for component in self.components:
      if component.name == name:
        return component
    
    return None