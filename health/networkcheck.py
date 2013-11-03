import socket
import urllib2

from healthcheck import HealthCheck
from util import report, ReportLevels

class TcpCheck(HealthCheck):
  """ A health check which tries to connect to a port via TCP. """
  def __init__(self, config):
    super(TcpCheck, self).__init__()
    self.config = config
    
  def run(self, container, report):
    container_port = self.config.getExtraField('port')
    local_port = self.getLocalPort(container, container_port)
    
    report('Checking TCP port in container ' + container['Id'][0:12] + ': ' + str(local_port),
      level = ReportLevels.EXTRA)
    try:
      s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
      s.connect('127.0.0.1', local_port)
      s.close()
    except:
      return False
      
    return True
    
    
class HttpRequestCheck(HealthCheck):
  """ A health check which tries to connect to an HTTP server on a known port. """
  def __init__(self, config):
    super(HttpRequestCheck, self).__init__()
    self.cached_port = None
    self.config = config
    
  def run(self, container, report):
    container_port = self.config.getExtraField('port')
    
    # Note: We cache the port here both for speed reasons and because of a bug in
    # docker-py whereby subsequent calls to getLocalPort fail for some odd reason.
    if not self.cached_port:
      self.cached_port = self.getLocalPort(container, container_port)

    address = 'http://localhost:' + str(self.cached_port)
    if self.config.hasExtraField('path'):
      address += path
    
    report('Checking HTTP address in container ' + container['Id'][0:12] + ': ' + address,
      level = ReportLevels.EXTRA)
    try:
      response = urllib2.urlopen(address, timeout = 2)
      response.read()
    except Exception as e:
      self.logger.exception(e)
      return False
      
    return True