from object import CFObject, CFField
from util import pickUnusedPort
from runtime.metadata import getComponentField, setComponentField

class _HealthCheck(CFObject):
  """ A single check to perform to verify that a component is ready to be
      pushed or is running properly.
  """
  kind = CFField('kind')
  id = CFField('id').default('')
  timeout = CFField('timeout').kind(int).default(3)

  def __init__(self):
    super(_HealthCheck, self).__init__('Health Check')
    
  def getTitle(self):
    """ Returns a descriptive title for the check. """
    if self.id != '':
      return self.id
    
    return self.kind


class _TerminationSignal(CFObject):
  """ A single signal that is sent to a component when the component should shut
      itself down.
  """
  kind = CFField('kind')
  id = CFField('id').default('')
  timeout = CFField('timeout').kind(int).default(3)

  def __init__(self):
    super(_TerminationSignal, self).__init__('Termination Signal')
    
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


class _VolumeBinding(CFObject):
  """ A port mapping of an internal container port to the outside world. """
  external = CFField('external')
  volume = CFField('volume')

  def __init__(self):
    super(_VolumeBinding, self).__init__('Volume Binding')


class _DefinedComponentLink(CFObject):
  """ A network link exported by a component. """
  port = CFField('port').kind(int)
  name = CFField('name')
  kind = CFField('kind').default('tcp')
  
  def __init__(self):
    super(_DefinedComponentLink, self).__init__('Component Link')
    
  def getHostPort(self):
    """ Returns the port used by the component link on the host. """
    key = 'link-' + self.name + '-port'
    port = getComponentField(self.parent.name, key, 0)
    if not port:
      port = pickUnusedPort()
      setComponentField(self.parent.name, key, port)

    return port
    

class _RequiredComponentLink(CFObject):
  """ A network link required by a component. """
  name = CFField('name')
  alias = CFField('alias')
  
  def __init__(self):
    super(_RequiredComponentLink, self).__init__('Required Component Link')


class _Component(CFObject):
  """ A single gantry component. """
  name = CFField('name')
  repo = CFField('repo')
  tag = CFField('tag').default('latest')
  command = CFField('command').list_of(str).default([])
  user = CFField('user').default('')
  ports = CFField('ports').list_of(_PortMapping).default([])
  bindings = CFField('bindings').list_of(_VolumeBinding).default([])
  ready_checks = CFField('readyChecks').list_of(_HealthCheck).default([])
  health_checks = CFField('healthChecks').list_of(_HealthCheck).default([])
  ready_timeout = CFField('readyTimeout').kind(int).default(10000)
  termination_signals = CFField('terminationSignals').list_of(_TerminationSignal).default([])
  privileged = CFField('privileged').kind(bool).default(False)
  defined_component_links = CFField('defineComponentLinks').list_of(_DefinedComponentLink).default([])
  required_component_links = CFField('requireComponentLinks').list_of(_RequiredComponentLink).default([])
    
  connection_check = _HealthCheck().build({'kind': 'connection'})
  termination_checks = CFField('terminationChecks').list_of(_HealthCheck).default([connection_check])

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
    """ Returns the full set of ports exposed by this component. """
    return set([p.container for p in self.ports] + [l.port for l in self.defined_component_links])
    
  def getReadyCheckTimeout(self):
    """ Returns the maximum amount of time, in seconds, before ready checks time out. """
    return self.ready_timeout / 1000

  def getVolumes(self):
    """ Returns the volumes exposed by this component. """
    return [binding.volume for binding in self.bindings]

  def getBindings(self):
    """ Returns the volumes exposed by this component. """
    return {binding.external: binding.volume for binding in self.bindings}

  def getDefinedComponentLinks(self):
    """ Returns the dict of defined components links. """
    return {l.name: l for l in self.defined_component_links}
    
  def getComponentLinks(self):
    """ Returns a dict of aliases for component links required, with the values being the links' names. """
    return {l.alias: l.name for l in self.required_component_links}


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