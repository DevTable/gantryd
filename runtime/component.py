from threading import Thread, Event
from uuid import uuid4
from cStringIO import StringIO

from health.checks import runHealthCheck
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

  ######################################################################
  
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
    
    # Start a health check thread.
    healthcheck_thread = Thread(target = self.healthCheck, args=[container])
    healthcheck_thread.daemon = True
    healthcheck_thread.start()
    
    # Wait for the health thread to finish.
    healthcheck_thread.join(self.config.getReadyCheckTimeout())
    
    # If the thread is still alived, then our join timed out.
    if healthcheck_thread.isAlive():
      report('Timed out waiting for health checks. Stopping container...')
      client.stop(container)
      report('Container stopped')
      return None
    
    # Otherwise, the container is ready. Set it as starting.
    setContainerComponent(container, self.getName()) 
    setContainerStatus(container, 'starting')
    return container
    
  def healthCheck(self, container):
    """ Thread which performs health check(s) on a container. """
    start = time.time()
    while True:
      now = time.time()
      if now - start > self.config.getReadyCheckTimeout():
        # Timed out completely.
        return False
      
      # Try each check. If any fail, we'll sleep and try again.
      check_failed = None
      for check in self.config.ready_checks:
        report('Running health check: ' + check.getTitle())
        result = runHealthCheck(check, container, report)
        if not result:
          report('Health check failed')
          check_failed = check
          break
      
      if check_failed:
        report('Sleeping ' + str(check_failed.timeout) + ' second(s)...')
        time.sleep(check_failed.timeout)
      else:
        break
    
    return True
    
  def getAllContainers(self, client):
    """ Returns all the matching containers for this component. """
    containers = []
    for container in client.containers():
      if container['Image'] == self.config.getFullImage() or getContainerComponent(container) == self.getName():
        containers.append(container)

    return containers
      
  def createContainer(self, client):
    """ Creates a docker container for this component and returns it. """
    container = client.create_container(self.config.getFullImage(), self.config.getCommand(),
      ports = [str(p) for p in self.config.getContainerPorts()])
      
    return container
    
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
      
   