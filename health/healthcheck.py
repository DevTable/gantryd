from util import report, fail, getDockerClient

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
    
  def getLocalPort(self, container, container_port):
    """ Returns the port on the local system for the given container port or 0 if none. """
    client = getDockerClient()
    try:
      self.logger.debug('Looking up port %d for container %s', container_port, container)
      return client.port(container, container_port)
    except Exception as e:
      self.logger.exception(e)
      return 0