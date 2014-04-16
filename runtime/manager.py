from component import Component
from metadata import getContainerStatus, setContainerStatus, removeContainerMetadata
from proxy.portproxy import Proxy, Route
from util import report, fail, getDockerClient, ReportLevels

from collections import defaultdict

import docker
import psutil
import threading
import time
import logging
import containerutil

class RuntimeManager(object):
  """ Manager class which handles tracking of all the components and other runtime
      information.
  """
  def __init__(self, config, daemon_mode = False):
    # Logging.
    self.logger = logging.getLogger(__name__)

    # Whether gantry is running in daemon mode.
    self.daemon_mode = daemon_mode
    
    # The overall configuration.
    self.config = config
    
    # The proxy being used to talk to HAProxy.
    self.proxy = Proxy()
    
    # The components, by name.
    self.components = {}
    
    # Build the components map.
    for component_config in config.components:
      self.components[component_config.name] = Component(self, component_config)
    
    # Create the lock for the watcher thread and the notification event.
    self.watcher_lock = threading.Lock()
    self.watcher_event = threading.Event()

    # The set of containers watched. Must be accessed under the watcher_lock.
    # When the connections to the ports used by a container are not longer there,
    # then the container is stopped.
    self.containers_watched = []
    
    # Start the thread used to watch and stop containers that are no longer needed.
    self.watcher_thread = threading.Thread(target = self.checkProxy, args = [])
    self.watcher_thread.daemon = True
    self.watcher_thread.start()
    
  def getComponent(self, name):
    """ Returns the component with the given name defined or None if none. """
    if not name in self.components:
      return None
      
    return self.components[name]

  def adjustForUpdatingComponent(self, component, started_container):
    """ Adjusts the runtime for a component which has been started in the given
        container.
    """
    self.logger.debug('Adjusting runtime for updating component: %s', component.getName())
    self.updateProxy()
   
  def adjustForStoppingComponent(self, component):
    """ Adjusts the runtime for a component which has been stopped.
    """
    self.logger.debug('Adjusting runtime for stopped component: %s', component.getName())
    self.updateProxy()
    
  def findConnectionLessContainers(self, containers):
    """ Determines which containers no longer have any valid connections to the
        outside world.
    """

    # Build the set of active connections from all the running proxy processes.
    active_container_ips = set()
    connections = self.proxy.get_connections()

    for connection in connections:
      laddr = connection.laddr
      raddr = connection.raddr
      if not laddr or not raddr:
        continue
      
      active_container_ips.add(raddr[0])


    # For each draining container, if the port set contains one of the known mappings, then
    # the container is still being used.
    client = getDockerClient()
    connectionless = list(containers)
    for container in containers:
      if getContainerStatus(container) == 'draining':
        container_ip = containerutil.getContainerIPAddress(client, container)
        if container_ip in active_container_ips:
          connectionless.remove(container)

    return connectionless
        
  def checkProxy(self):
    """ Checks to see if a draining container can be shutdown. """
    counter = 0
    client = getDockerClient()
    while True:
      # Wait until something of interest is avaliable to check.
      self.watcher_event.wait()
      self.watcher_event.clear()
      
      while True:
        # Load the containers to check (under the lock).
        containers = None
        with self.watcher_lock:
          containers = list(self.containers_watched)
        
        # If none, we're done.
        if not containers:
          break
        
        # Find the containers that no longer need to be running. Any container with no
        # valid connections coming in and a status of 'draining', can be shutdown.
        report('Monitor check started', level = ReportLevels.BACKGROUND)
        containers_to_shutdown = self.findConnectionLessContainers(containers)
        if len(containers_to_shutdown) > 0:
          with self.watcher_lock:
            for container in containers_to_shutdown:
              self.containers_watched.remove(container)

          for container in containers_to_shutdown:
            setContainerStatus(container, 'shutting-down')
            report('Shutting down container: ' + container['Id'][0:12], level = ReportLevels.BACKGROUND)
            client.stop(container)
            removeContainerMetadata(container)
        
        # Determine how many residual containers are left over.
        difference = len(containers) - len(containers_to_shutdown)
        if difference > 0:
          report(str(difference) + ' additional containers to monitor. Sleeping for 10 seconds', level = ReportLevels.BACKGROUND)            
          time.sleep(10)
          counter = counter + 1
      
      report('Monitor check finished', level = ReportLevels.BACKGROUND)
      if not self.daemon_mode:
        # Quit now that we're done.
        return
    
  def updateProxy(self):
    """ Updates the proxy used for port mapping to conform to the current running container
        list.
    """
    client = getDockerClient()
    
    # Clear all routes in the proxy.
    # TODO: When this is in daemon mode, don't need do this. We could selectively
    # edit it instead.
    self.proxy.clear_routes()
    
    # Add routes for the non-draining containers and collect the draining containers to
    # watch.
    report('Finding running containers...', level = ReportLevels.EXTRA)
    draining_containers = []
    starting_containers = []
    
    for component in self.components.values():
      for container in component.getAllContainers(client):
        if getContainerStatus(container) != 'draining':
          container_ip = containerutil.getContainerIPAddress(client, container)
          starting_containers.append(container)
          for mapping in component.config.ports:
            route = Route(mapping.kind == 'http', mapping.external, container_ip,
                          mapping.container)
            self.proxy.add_route(route)
        else:
          draining_containers.append(container)

    # Commit the changes to the proxy.
    if draining_containers or starting_containers:
      report('Updating proxy...', level = ReportLevels.EXTRA)
      self.proxy.commit()
    else:
      report('Shutting down proxy...', level = ReportLevels.EXTRA)
      self.proxy.shutdown()
    
    # Mark the starting containers as running.
    for container in starting_containers:
      setContainerStatus(container, 'running')

    if draining_containers:
      report('Starting monitoring...', level = ReportLevels.EXTRA)
    
    # If there are any draining containers, add them to the watcher thread.
    with self.watcher_lock:
      self.containers_watched.extend(draining_containers)
    
    # Call the event to wakeup the watcher thread.
    if draining_containers:
      self.watcher_event.set()    
    
    # If in local mode, then wait until all the containers have drained. This
    # prevents the python debugger from shutting down, since the other threads
    # are all daemon threads.
    if not self.daemon_mode and draining_containers:
      while True:
        self.watcher_thread.join(10)
        if not self.watcher_thread.isAlive():
          break