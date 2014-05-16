import containerutil

from util import getDockerClient

import logging


class ContainerSignal(object):
  def __init__(self):
    # Logging.
    self.logger = logging.getLogger(__name__)

  def getContainerIPAddress(self, container):
    """ Returns the IP address on which the container is running. """
    client = getDockerClient()
    return containerutil.getContainerIPAddress(client, container)


class TerminationSignal(ContainerSignal):
  """ Base class for all termination signals. """
  def run(self, container, report):
    """ Sends the termination signal to the given container, returning True if it succeeds.
    """
    return False


class HealthCheck(ContainerSignal):
  """ Base class for all health checks. """  
  def run(self, container, report):
    """ Runs the given health check on the given container, returning True if it succeeds and
        false otherwise.
    """
    return False
