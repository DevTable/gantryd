from threading import Thread, Event
from uuid import uuid4
from cStringIO import StringIO

from health.checks import buildHealthCheck
from metadata import getContainerStatus, setContainerStatus, removeContainerMetadata, getContainerComponent, setContainerComponent
from util import report, fail, getDockerClient

import os
import subprocess
import time
import logging
import select
import socket
import docker

logger = logging.getLogger(__name__)

class Component(object):
  """ A component that can be/is running. Tracks all the runtime information
      for a component.
  """
  
  def __init__(self, manager, config):    
    # The overall manager for components, which tracks global state.
    self.manager = manager

    # The underlying config for the component.
    self.config = config
  
  def getName(self):
    """ Returns the name of the component. """
    return self.config.name
  
  def isRunning(self):
    """ Returns whether this component has at least one running container. Note that
        this will return True for ALL possible containers of the component, including
        deprecated ones.
    """
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
    result = client.inspect_image(named_image)
    return result['id'] 
    
  def pullRepo(self):
    """ Attempts to pull the repo for this component. On failure, returns False. """
    try:
      client = getDockerClient()
      client.pull(self.config.repo, tag = self.config.tag)
    except Exception as e:
      return False
    
  def update(self):
    """ Updates a running instance of the component. Returns True on success and False
        otherwise.
    """
    client = getDockerClient()
    
    # Get the list of currently running container(s).
    existing_containers = self.getAllContainers(client)
    
    # Start the new instance.
    container = self.start()
    if not container:
      return False

    # Mark all the existing containers as draining.
    for existing in existing_containers:
      setContainerStatus(existing, 'draining')
    
    # Update the port proxy to redirect the external ports to the new
    # container.
    report('Redirecting traffic to new container')
    self.manager.adjustForUpdatingComponent(self, container)
    return True
    
  def stop(self, kill = False):
    """ Stops all containers for this component. """
    if not self.isRunning():
      return

    client = getDockerClient()

    # Mark all the containers as draining.
    report('Draining all containers...')
    for container in self.getAllContainers(client):
      setContainerStatus(container, 'draining')
    
    # Kill any associated containers if asked.
    if kill:
      for container in self.getAllContainers(client):
        report('Killing container ' + container['Id'][0:12])
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
    container = self.getPrimaryContainer()
    if not container:
      return False
      
    checks = []
    for check in self.config.health_checks:
      checks.append((check, buildHealthCheck(check)))

    for (config, check) in checks:
      report('Running health check: ' + config.getTitle())
      result = check.run(container, report)
      if not result:
        return False
        
    return True
    
  ######################################################################

  def readyCheck(self, container, timeout):
    """ Method which performs ready health check(s) on a container, returning whether
        they succeeded or not.
        
        container: The container running the component that will be checked.
        timeout: The amount of time after which the checks have timed out.
    """
    checks = []
    for check in self.config.ready_checks:
      checks.append((check, buildHealthCheck(check)))
    
    start = time.time()
    while True:
      now = time.time()
      if now - start > timeout:
        # Timed out completely.
        return False
      
      # Try each check. If any fail, we'll sleep and try again.
      check_failed = None
      for (config, check) in checks:
        report('Running health check: ' + config.getTitle())
        result = check.run(container, report)
        if not result:
          report('Health check failed')
          check_failed = config
          break
      
      if check_failed:
        report('Sleeping ' + str(check_failed.timeout) + ' second(s)...')
        time.sleep(check_failed.timeout)
      else:
        break
    
    return True
    
  def start(self):
    """ Starts a new instance of the component. Note that this does *not* update the proxy. """
    client = getDockerClient()
    
    # Ensure that we have the image. If not, we try to download it.
    self.ensureImage(client)
    
    # Start the instance with the proper image ID.
    container = self.createContainer(client)
    report('Starting container ' + container['Id'])
    client.start(container)
    
    # Health check until the instance is ready.    
    report('Waiting for health checks...')
    
    # Start a health check thread to determine when the component is ready.
    timeout = self.config.getReadyCheckTimeout()
    readycheck_thread = Thread(target = self.readyCheck, args=[container, timeout])
    readycheck_thread.daemon = True
    readycheck_thread.start()
    
    # Wait for the health thread to finish.
    readycheck_thread.join(self.config.getReadyCheckTimeout())
    
    # If the thread is still alived, then our join timed out.
    if readycheck_thread.isAlive():
      report('Timed out waiting for health checks. Stopping container...')
      client.stop(container)
      report('Container stopped')
      return None
    
    # Otherwise, the container is ready. Set it as starting.
    setContainerComponent(container, self.getName()) 
    setContainerStatus(container, 'starting')
    return container

  def getAllContainers(self, client):
    """ Returns all the matching containers for this component. """
    containers = []
    for container in client.containers():
      if container['Image'] == self.config.getFullImage() or getContainerComponent(container) == self.getName():
        containers.append(container)

    return containers
      
  def createContainer(self, client):
    """ Creates a docker container for this component and returns it. """
    command = self.getCommand()
    if not command:
      fail('No command defined in either gantry config or docker image for component ' + self.getName())
    
    container = client.create_container(self.config.getFullImage(), command,
      user = self.config.getUser(), ports = [str(p) for p in self.config.getContainerPorts()])
      
    return container
  
  def getCommand(self):    
    """ Returns the command to run or None if none found. """
    config_command = self.config.getCommand()
    if config_command:
      return config_command

    client = getDockerClient()
    named_image = self.config.getFullImage()
    result = client.inspect_image(named_image)
    container_cfg = result['container_config']
    if not 'Cmd' in container_cfg:
      return None
    
    return ' '.join(container_cfg['Cmd'])
  
  def ensureImage(self, client):
    """ Ensures that the image for this component is present locally. If not,
        we attempt to pull the image.
    """
    images = client.images(name = self.config.getFullImage())
    if not images or not len(images) > 0:
      try:
        client.pull(self.config.repo)
      except Exception as e:
        fail('Could not pull reoi ' + self.config.repo + ': ' + str(e))
      
   