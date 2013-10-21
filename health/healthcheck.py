from util import report, fail, getDockerClient

class HealthCheck(object):
  """ Base class for all health checks. """
  def run(self, container, report):
    """ Runs the given health check on the given container, returning True if it succeeds and
        false otherwise.
    """
    return False
    
  def getLocalPort(self, container, container_port):
    """ Returns the port on the local system for the given container port or 0 if none. """
    client = getDockerClient()
    try:
      return client.port(container, container_port)
    except Exception as e:
      print e
      return 0