from runtime.manager import RuntimeManager
from config.GantryConfig import Configuration

from gantryd.componentwatcher import ComponentWatcher
from gantryd.machinestate import MachineState
from gantryd.componentstate import ComponentState, STOPPED_STATUS, KILLED_STATUS
from gantryd.etcdpaths import getProjectConfigPath

from util import report, fail

import etcd
import uuid
import atexit
import threading
import time
import socket
import json

REPORT_TTL = 60 # Report that this machine is running, every 60 seconds
  
class GantryDClient(object):
  """ A client in gantryd. """
  def __init__(self, etcdHost, projectName):
    self.etcd_client = etcd.Client(host = etcdHost)
    self.project_name = projectName
    
    self.runtime_manager = None
    self.components = []
    self.is_running = False

    self.machine_id = str(uuid.uuid1())

    self.reporting_thread = threading.Thread(target = self.reportMachineStatus, args = [])
    self.reporting_thread.daemon = True

  def getConfigJSON(self):
    """ Returns the project's config JSON or raises an exception if none. """
    # Lookup the project on etcd. If none, report an error.
    config_json = None
    try:
      config_json = self.etcd_client.get(getProjectConfigPath(self.project_name)).value
    except KeyError:
      fail('Unknown project ' + self.project_name)

    return config_json
    
  def getConfig(self):
    """ Returns the project's config or raises an exception if none. """
    config_json = self.getConfigJSON()

    # Parse the project's configuration and save it.
    try:
      self.config = Configuration.parse(config_json)
    except Exception as e:
      fail('Error parsing gantry config: ' + str(e))
      
    return self.config
    
  def setConfig(self, config):
    """ Sets the project's config in etcd. """
    config_json = json.dumps(config)
    self.etcd_client.set(getProjectConfigPath(self.project_name), config_json)
    
  def stopComponents(self, componentNames):
    """ Tells all the given components on all systems to stop. """
    self.initialize(componentNames)

    report('Marking components as stopped')
    for component in self.components:
      state = ComponentState(self.project_name, component, self.etcd_client)
      state.setStatus(STOPPED_STATUS)

  def killComponents(self, componentNames):
    """ Tells all the given components on all systems to die. """
    self.initialize(componentNames)

    report('Marking components as killed')
    for component in self.components:
      state = ComponentState(self.project_name, component, self.etcd_client)
      state.setStatus(KILLED_STATUS)
    
  def markUpdated(self, componentNames):
    """ Tells all the given components to update themselves. """
    self.initialize(componentNames)

    report('Updating the image IDs on components')
    for component in self.components:
      image_id = component.getImageId()
      state = ComponentState(self.project_name, component, self.etcd_client)

      report('Component ' + component.getName() + ' -> ' + image_id[0:12])
      state.setReadyStatus(image_id)      
    
  def listStatus(self):
    """ Lists the status of all components in this project. """
    self.getConfig()
    self.initialize([c.name for c in self.config.components])
    
    print "%-20s %-20s %-20s" % ('COMPONENT', 'STATUS', 'IMAGE ID')
    for component in self.components:
      state = ComponentState(self.project_name, component, self.etcd_client).getState()
      status = ComponentState.getStatusOf(state)
      imageid = ComponentState.getImageIdOf(state)
      print "%-20s %-20s %-20s" % (component.getName(), status, imageid)
      
    
  def run(self, componentNames):
    """ Runs the given components on this machine. """
    self.initialize(componentNames)
 
    # Register a handler to remove this machine from the list when the daemon is
    # shutdown. The controller will also occasionally ping a machine to verify it
    # is present.
    atexit.register(self.handleExit)
    
    # Start the thread to register this machine as being part of the project.
    self.startReporter()
    
    # Start watcher thread(s), one for each component, to see when to update them.
    report('Gantryd running')
    for component in self.components:
      watcher = ComponentWatcher(component, self.project_name, self.machine_id, self.etcd_client)
      watcher.start()
    
    # And sleep until new stuff comes in.
    while True:
      time.sleep(1)


  ########################################################################
  
  def initialize(self, componentNames):
    """ Initializes this client for working with the components given. """
    # Load the project configuration.
    self.getConfig()
      
    # Initialize the runtime manager.
    self.runtime_manager = RuntimeManager(self.config, daemon_mode = True)
    
    # Find all the components for this machine.
    for componentName in componentNames:
      component = self.runtime_manager.getComponent(componentName)
      if not component:
        fail('Unknown component named ' + componentName)
        
      self.components.append(component)

  def handleExit(self):
    """ Function executed when the Python system exits. This unregisters the machine in etcd. """
    self.is_running = False
    try:
      machine_state = MachineState(self.project_name, self.machine_id, self.etcd_client)
      machine_state.removeMachine()
    except:
      pass
      
  def startReporter(self):
    """ Starts reporting that this machine is running. """
    self.is_running = True
    self.reporting_thread.start()
      
  def reportMachineStatus(self):
    """ Reports that this machine has running components. """
    while self.is_running:
      # Perform the update.
      machine_state = MachineState(self.project_name, self.machine_id, self.etcd_client)
      machine_state.registerMachine([c.getName() for c in self.components], ttl = REPORT_TTL)
      
      # Sleep for the TTL minus a few seconds.
      time.sleep(REPORT_TTL - 5)
    
      
