from threading import Thread, Event

from health.checks import buildHealthCheck
from metadata import (getContainerStatus, setContainerStatus, removeContainerMetadata,
                      getContainerComponent, setContainerComponent)
from util import report, fail, getDockerClient, ReportLevels

import time
import logging

class Component(object):
  """ A component that can be/is running. Tracks all the runtime information
      for a component.
  """
  def __init__(self, manager, config):
    # Logging.
    self.logger = logging.getLogger(__name__)

    # The overall manager for components, which tracks global state.
    self.manager = manager

    # The underlying config for the component.
    self.config = config

  def getName(self):
    """ Returns the name of the component. """
    return self.config.name

  def lookupExportedComponentLink(self, link_name):
    """ Looks up the exported component link with the given name and returns it or None if none. """
    pass

  def isRunning(self):
    """ Returns whether this component has at least one running container. Note that
        this will return True for ALL possible containers of the component, including
        deprecated ones.
    """
    self.logger.debug('Checking if component %s is running', self.getName())
    client = getDockerClient()
    return len(self.getAllContainers(client)) > 0

  def getPrimaryContainer(self):
    """ Returns the container for this component that is not marked as draining or None if
        none.
    """
    client = getDockerClient()
    for container in self.getAllContainers(client):
      if getContainerStatus(container) != 'draining':
        return container

    return None

  def getImageId(self):
    """ Returns the docker ID of the image used for this component. Note that this
        will *not* return the *named* image, but rather the full UUID-like ID.
    """
    client = getDockerClient()
    named_image = self.config.getFullImage()
    self.logger.debug('Finding image ID for component %s with named image %s', self.getName(), named_image)
    result = client.inspect_image(named_image)
    return result['id']

  def pullRepo(self):
    """ Attempts to pull the repo for this component. On failure, returns False. """
    try:
      self.logger.debug('Attempting to pull repo for component %s: %s:%s', self.getName(), self.config.repo, self.config.tag)
      client = getDockerClient()
      client.pull(self.config.repo, tag=self.config.tag)
    except Exception as e:
      self.logger.exception(e)
      return False

  def update(self):
    """ Updates a running instance of the component. Returns True on success and False
        otherwise.
    """
    self.logger.debug('Updating component %s', self.getName())
    client = getDockerClient()

    # Get the list of currently running container(s).
    existing_containers = self.getAllContainers(client)
    existing_primary = self.getPrimaryContainer()

    # Start the new instance.
    container = self.start()
    if not container:
      return False

    # Mark all the existing containers as draining.
    for existing in existing_containers:
      setContainerStatus(existing, 'draining')

    # Update the port proxy to redirect the external ports to the new
    # container.
    report('Redirecting traffic to new container', component=self)
    self.manager.adjustForUpdatingComponent(self, container)

    # Signal the existing primary container to terminate
    if existing_primary is not None:
      self.manager.terminateContainer(existing_primary, self)

    return True

  def stop(self, kill=False):
    """ Stops all containers for this component. """
    if not self.isRunning():
      return

    self.logger.debug('Stopping component %s', self.getName())
    client = getDockerClient()

    # Mark all the containers as draining.
    report('Draining all containers...', component=self)
    for container in self.getAllContainers(client):
      setContainerStatus(container, 'draining')
      self.manager.terminateContainer(container, self)

    # Kill any associated containers if asked.
    if kill:
      for container in self.getAllContainers(client):
        report('Killing container ' + container['Id'][:12], component=self)
        client.kill(container)
        removeContainerMetadata(container)

    # Clear the proxy and rebuild its routes for the running components.
    self.manager.adjustForStoppingComponent(self)

  def getContainerInformation(self):
    """ Returns the container status information for all containers. """
    client = getDockerClient()
    information = []

    for container in self.getAllContainers(client):
      information.append((container, getContainerStatus(container)))

    return information

  def isHealthy(self):
    """ Runs the health checks on this component's container, ensuring that it is healthy.
        Returns True if healthy and False otherwise.
    """
    self.logger.debug('Checking if component %s is healthy...', self.getName())
    container = self.getPrimaryContainer()
    if not container:
      self.logger.debug('No container running for component %s', self.getName())
      return False

    checks = []
    for check in self.config.health_checks:
      checks.append((check, buildHealthCheck(check)))

    for (config, check) in checks:
      report('Running health check: ' + config.getTitle(), component=self)
      result = check.run(container, report)
      if not result:
        report('Health check failed', component=self)
        return False

    self.logger.debug('Component %s is healthy', self.getName())
    return True

  ######################################################################

  def readyCheck(self, container, timeout):
    """ Method which performs ready health check(s) on a container, returning whether
        they succeeded or not.

        container: The container running the component that will be checked.
        timeout: The amount of time after which the checks have timed out.
    """
    self.logger.debug('Checking if component %s is ready...', self.getName())
    checks = []
    for check in self.config.ready_checks:
      checks.append((check, buildHealthCheck(check)))

    start = time.time()
    while True:
      now = time.time()
      if now - start > timeout:
        # Timed out completely.
        self.logger.debug('Component %s ready checks have timed out')
        return False

      # Try each check. If any fail, we'll sleep and try again.
      check_failed = None
      for (config, check) in checks:
        report('Running health check: ' + config.getTitle(), component=self)
        result = check.run(container, report)
        if not result:
          report('Health check failed', component=self)
          check_failed = config
          break

      if check_failed:
        report('Sleeping ' + str(check_failed.timeout) + ' second(s)...', component=self)
        time.sleep(check_failed.timeout)
      else:
        break

    return True

  def start(self):
    """ Starts a new instance of the component. Note that this does *not* update the proxy. """
    client = getDockerClient()
    self.logger.debug('Starting container for component %s', self.getName())

    # Ensure that we have the image. If not, we try to download it.
    self.ensureImage(client)

    # Start the instance with the proper image ID.
    container = self.createContainer(client)
    report('Starting container ' + container['Id'][:12], component=self)

    if self.config.privileged:
      report('Container will be run in privileged mode', component=self)

    client.start(container, binds=self.config.getBindings(container['Id']),
                 privileged=self.config.privileged)

    # Health check until the instance is ready.
    report('Waiting for health checks...', component=self)

    # Start a health check thread to determine when the component is ready.
    timeout = self.config.getReadyCheckTimeout()
    readycheck_thread = Thread(target=self.readyCheck, args=[container, timeout])
    readycheck_thread.daemon = True
    readycheck_thread.start()

    # Wait for the health thread to finish.
    readycheck_thread.join(self.config.getReadyCheckTimeout())

    # If the thread is still alived, then our join timed out.
    if readycheck_thread.isAlive():
      report('Timed out waiting for health checks. Stopping container...', component=self)
      client.stop(container)
      report('Container stopped', component=self)
      return None

    # Otherwise, the container is ready. Set it as starting.
    setContainerComponent(container, self.getName())
    setContainerStatus(container, 'starting')
    return container

  def getAllContainers(self, client):
    """ Returns all the matching containers for this component. """
    containers = []
    for container in client.containers():
      if (container['Image'] == self.config.getFullImage() or
          getContainerComponent(container) == self.getName()):
        containers.append(container)

    return containers

  def calculateEnvForComponent(self):
    """ Calculates the dict of environment variables for this component. """
    links = self.config.getComponentLinks()
    environment = self.config.getEnvironmentVariables()

    for link_alias, link_name in links.items():
      component_link_info = self.manager.lookupComponentLink(link_name)
      if not component_link_info:
        fail('Component link %s not defined on any component' % link_name, component=self)
        return None

      if not component_link_info.running:
        info = (link_name, component_link_info.component.getName())
        fail('Component link "%s" cannot be setup: Component "%s" is not running' % info,
             component=self)
        return None

      # Component link env var format:
      #   THEALIAS_CLINK=tcp://{hostip}:{hostport}
      #   THEALIAS_CLINK_6379_TCP=tcp://{hostip}:{hostport}
      #   THEALIAS_CLINK_6379_TCP_PROTO=tcp
      #   THEALIAS_CLINK_6379_TCP_ADDR={hostip}
      #   THEALIAS_CLINK_6379_TCP_PORT={hostport}

      prefix = link_alias.upper() + '_CLINK'
      prefix_with_port = prefix + '_' + str(component_link_info.container_port)
      full_prefix = prefix_with_port + ('_HTTP' if component_link_info.kind == 'http' else '_TCP')
      full_uri = '%s://%s:%s' % (component_link_info.kind, component_link_info.address,
                                 component_link_info.exposed_port)

      environment[prefix] = full_uri
      environment[full_prefix] = full_uri
      environment[full_prefix + '_PROTO'] = component_link_info.kind
      environment[full_prefix + '_ADDR'] = component_link_info.address
      environment[full_prefix + '_PORT'] = component_link_info.exposed_port

    return environment

  def createContainer(self, client):
    """ Creates a docker container for this component and returns it. """
    command = self.getCommand()
    if not command:
      fail('No command defined in either gantry config or docker image for component ' +
           self.getName(), component=self)

    self.logger.debug('Starting container for component %s with command %s', self.getName(),
                      command)
    container = client.create_container(self.config.getFullImage(), command,
                                        user=self.config.getUser(),
                                        volumes=self.config.getVolumes(),
                                        ports=[str(p) for p in self.config.getContainerPorts()],
                                        environment=self.calculateEnvForComponent())

    return container

  def getCommand(self):
    """ Returns the command to run or None if none found. """
    config_command = self.config.getCommand()
    if config_command:
      return config_command

    client = getDockerClient()
    named_image = self.config.getFullImage()
    result = client.inspect_image(named_image)
    container_cfg = result['config']
    if not 'Cmd' in container_cfg:
      return None

    return ' '.join(container_cfg['Cmd'])

  def ensureImage(self, client):
    """ Ensures that the image for this component is present locally. If not,
        we attempt to pull the image.
    """
    images = client.images(name=self.config.getFullImage())
    if not images or not len(images) > 0:
      try:
        client.pull(self.config.repo)
      except Exception as e:
        fail('Could not pull repo ' + self.config.repo, component=self, exception=str(e))
