import containerutil

from util import getDockerClient

import logging

class HealthCheck(object):
  """ Base class for all health checks. """
  def __init__(self):
    # Logging.
    self.logger = logging.getLogger(__name__)
  
  def run(self, container, report):
    """ Runs the given health check on the given container, returning True if it succeeds and
        false otherwise.
    """
    return False

  def getContainerIPAddress(self, container):
    """ Returns the IP address on which the container is running. """
    client = getDockerClient()
    return containerutil.getContainerIPAddress(client, container)
