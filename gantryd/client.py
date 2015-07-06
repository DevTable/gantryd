from runtime.manager import RuntimeManager
from config.GantryConfig import Configuration
from config.object import ConfigParseException

from gantryd.componentwatcher import ComponentWatcher
from gantryd.machinestate import MachineState
from gantryd.componentstate import ComponentState, STOPPED_STATUS, KILLED_STATUS
from gantryd.etcdpaths import getProjectConfigPath

from util import report, fail, ReportLevels

import etcd
import uuid
import atexit
import threading
import time
import socket
import json
import logging

REPORT_TTL = 60 # Report that this machine is running, every 60 seconds

class GantryDClient(object):
  """ A client in gantryd. """
  def __init__(self, etcdHost, projectName, etcdPort):
    self.project_name = projectName
    self.runtime_manager = None
    self.components = []
    self.is_running = False

    # Generate a unique ID for this machine/client.
    self.machine_id = str(uuid.uuid1())

    # Logging.
    self.logger = logging.getLogger(__name__)

    # Initialize the etcd client that we'll use.
    self.etcd_client = etcd.Client(host=etcdHost, port=etcdPort)

    # Initialize the thread used for reporting the status of this machine to etcd.
    self.reporting_thread = threading.Thread(target=self.reportMachineStatus, args=[])
    self.reporting_thread.daemon = True

  def getConfigJSON(self):
    """ Returns the project's config JSON or raises an exception if none. """
    # Lookup the project on etcd. If none, report an error.
    config_json = None
    try:
      self.logger.debug('Looking up configuration for project %s in etcd', self.project_name)
      config_json = self.etcd_client.get(getProjectConfigPath(self.project_name)).value
    except KeyError as k:
      self.logger.exception(k)
      fail('Unknown project ' + self.project_name, project=self.project_name)

    return config_json

  def getConfig(self):
    """ Returns the project's config or raises an exception if none. """
    config_json = self.getConfigJSON()

    # Parse the project's configuration and save it.
    try:
      self.config = Configuration.parse(config_json)
    except ConfigParseException as cpe:
      fail('Error parsing gantry config', project=self.project_name, exception=cpe)
    except Exception as e:
      self.logger.exception(e)

    return self.config

  def setConfig(self, config):
    """ Sets the project's config in etcd. """
    config_json = json.dumps(config)
    self.logger.debug('Updating configuration for project %s', self.project_name)
    self.etcd_client.set(getProjectConfigPath(self.project_name), config_json)

  def stopComponents(self, component_names):
    """ Tells all the given components on all systems to stop. """
    self.initialize(component_names)

    report('Marking components as stopped', project=self.project_name)
    for component in self.components:
      report('Marking component as stopped', project=self.project_name, component=component,
             level = ReportLevels.EXTRA)
      state = ComponentState(self.project_name, component, self.etcd_client)
      state.setStatus(STOPPED_STATUS)

  def killComponents(self, component_names):
    """ Tells all the given components on all systems to die. """
    self.initialize(component_names)

    report('Marking components as killed', project=self.project_name)
    for component in self.components:
      report('Marking component as killed', project=self.project_name, component=component,
             level = ReportLevels.EXTRA)
      state = ComponentState(self.project_name, component, self.etcd_client)
      state.setStatus(KILLED_STATUS)

  def markUpdated(self, component_names):
    """ Tells all the given components to update themselves. """
    self.initialize(component_names)

    report('Updating the image IDs on components', project=self.project_name)
    for component in self.components:
      image_id = component.getImageId()
      state = ComponentState(self.project_name, component, self.etcd_client)

      report('Component %s->%s' % (component.getName(), image_id[0:12]), project=self.project_name,
             component = component)
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


  def run(self, component_names):
    """ Runs the given components on this machine. """
    self.initialize(component_names)

    # Register a handler to remove this machine from the list when the daemon is
    # shutdown. The controller will also occasionally ping a machine to verify it
    # is present.
    self.logger.debug('Registering exit listener')
    atexit.register(self.handleExit)

    # Start the thread to register this machine as being part of the project.
    self.startReporter()

    # Start watcher thread(s), one for each component, to see when to update them.
    report('Gantryd running', project=self.project_name)
    for component in self.components:
      self.logger.debug('Starting component watcher for component: %s', component.getName())
      watcher = ComponentWatcher(component, self.project_name, self.machine_id, self.etcd_client)
      watcher.start()

    # And sleep until new stuff comes in.
    while True:
      time.sleep(1)


  ########################################################################

  def initialize(self, component_names):
    """ Initializes this client for working with the components given. """
    # Load the project configuration.
    self.getConfig()

    # Initialize the runtime manager.
    self.runtime_manager = RuntimeManager(self.config)

    # Find all the components for this machine.
    for component_name in component_names:
      component = self.runtime_manager.getComponent(component_name)
      if not component:
        fail('Unknown component named ' + component_name, project=self.project_name)

      self.components.append(component)

  def handleExit(self):
    """ Function executed when the Python system exits. This unregisters the machine in etcd. """
    self.is_running = False
    try:
      machine_state = MachineState(self.project_name, self.machine_id, self.etcd_client)
      machine_state.removeMachine()

      # Shut down the runtime manager if we have one
      if self.runtime_manager is not None:
        self.runtime_manager.join()

    except Exception as e:
      self.logger.exception(e)
      pass

  def startReporter(self):
    """ Starts reporting that this machine is running. """
    self.is_running = True
    self.reporting_thread.start()

  def reportMachineStatus(self):
    """ Reports that this machine has running components. """
    while self.is_running:
      # Perform the update.
      self.logger.debug('Reporting status for machine %s to etcd', self.machine_id)
      machine_state = MachineState(self.project_name, self.machine_id, self.etcd_client)
      machine_state.registerMachine([c.getName() for c in self.components], ttl=REPORT_TTL)

      # Sleep for the TTL minus a few seconds.
      time.sleep(REPORT_TTL - 5)


