from component import Component
from metadata import getContainerStatus, setContainerStatus, removeContainerMetadata
from proxy.portproxy import Proxy, Route
from util import report, fail, getDockerClient, ReportLevels
from health.checks import buildTerminationSignal, buildHealthCheck

from collections import defaultdict
from Queue import Queue
from multiprocessing.pool import ThreadPool

import docker
import psutil
import threading
import time
import logging
import containerutil

class ComponentLinkInformation(object):
  """ Helper class which contains all runtime information about a component link. """
  def __init__(self, manager, component, link_config):
    # The component that exports the link.
    self.component = component

    # The configuration for the component link.
    self.link_config = link_config

    # The kind of the link.
    self.kind = 'http' if link_config.kind.lower() == 'http' else 'tcp'

    # The port of the link inside the running container.
    self.container_port = link_config.port

    # The address of the link under the proxy (None if the link is not running).
    self.address = None

    # The port of the link under the proxy (None if the link is not running).
    self.exposed_port = None

    # Whether the link is currently running.
    self.running = False

    # Lookup the runtime information for the link.
    client = getDockerClient()
    container = component.getPrimaryContainer()
    if container:
      container_ip = containerutil.getContainerIPAddress(client, container)

      self.address = client.inspect_container(container)['NetworkSettings']['Gateway'] # The host's IP address.
      self.exposed_port = link_config.getHostPort()
      self.running = True


class RuntimeManager(object):
  """ Manager class which handles tracking of all the components and other runtime
      information.
  """
  def __init__(self, config):
    # Logging.
    self.logger = logging.getLogger(__name__)

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

    # The set of containers which should be terminated by the terminating workers.
    self.containers_to_terminate = Queue()

    # Start the thread used to watch and stop containers that are no longer needed.
    self.pool = ThreadPool()

    # Place to collect the results of the monitor
    self.monitor_futures = Queue()

  def getComponent(self, name):
    """ Returns the component with the given name defined or None if none. """
    if not name in self.components:
      return None

    return self.components[name]

  def lookupComponentLink(self, link_name):
    """ Looks up the component link with the given name defined or None if none. """
    for component_name, component in self.components.items():
      defined_links = component.config.getDefinedComponentLinks()
      if link_name in defined_links:
        return ComponentLinkInformation(self, component, defined_links[link_name])

    return None

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


  def watchTermination(self, container, component):
    report('Monitor check started', level=ReportLevels.BACKGROUND)

    client = getDockerClient()

    # Send the termination signal(s) to the container
    signals = []

    for signal in component.config.termination_signals:
      signals.append((signal, buildTerminationSignal(signal)))

    report('Sending %s termination signals' % len(signals), component=component)

    for (config, signal) in signals:
      report('Sending termination signal: ' + config.getTitle(), component=component)
      result = signal.run(container, report)
      if not result:
        report('Termination signal failed', component=component)

    # Now wait until all of the termination conditions are met
    checks = []
    for check in component.config.termination_checks:
      checks.append((check, buildHealthCheck(check)))

    report('Waiting for %s termination checks' % len(checks), component=component)

    for (config, check) in checks:
      check_passed = False

      while not check_passed:
        report('Running termination check: ' + config.getTitle(), component=component)
        result = check.run(container, report)
        if not result:
          report('Termination check failed', component=component)

          report('Sleeping ' + str(config.timeout) + ' second(s)...', component=component)
          time.sleep(config.timeout)
        else:
          check_passed = True

    report('Monitor check finished', level=ReportLevels.BACKGROUND)

    setContainerStatus(container, 'shutting-down')
    report('Shutting down container: ' + container['Id'][0:12], level=ReportLevels.BACKGROUND)
    client.stop(container)
    removeContainerMetadata(container)


  def terminateContainer(self, container, component):
    """ Adds the given container to the list of containers which should be terminated.
    """
    report('Terminating container: %s' % container['Id'][:12], component=component)
    self.monitor_futures.put(self.pool.apply_async(self.watchTermination, (container, component)))


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
    report('Finding running containers...', level=ReportLevels.EXTRA)
    draining_containers = []
    starting_containers = []

    for component in self.components.values():
      for container in component.getAllContainers(client):
        if getContainerStatus(container) != 'draining':
          container_ip = containerutil.getContainerIPAddress(client, container)
          starting_containers.append(container)

          # Add the normal exposed ports.
          for mapping in component.config.ports:
            route = Route(mapping.kind == 'http', mapping.external, container_ip,
                          mapping.container)
            self.proxy.add_route(route)

          # Add the container link ports.
          for link in component.config.defined_component_links:
            route = Route(link.kind == 'http', link.getHostPort(), container_ip, link.port)
            self.proxy.add_route(route)
        else:
          draining_containers.append(container)

    # Commit the changes to the proxy.
    if draining_containers or starting_containers:
      report('Updating proxy...', level=ReportLevels.EXTRA)
      self.proxy.commit()
    else:
      report('Shutting down proxy...', level=ReportLevels.EXTRA)
      self.proxy.shutdown()

    # Mark the starting containers as running.
    for container in starting_containers:
      setContainerStatus(container, 'running')

  def join(self):
    self.pool.close()

    while not self.monitor_futures.empty():
      # If any of the futures threw and exception we'll get it now
      self.monitor_futures.get().get()

    self.pool.join()
