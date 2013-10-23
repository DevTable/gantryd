import socket
import urllib2

from healthcheck import HealthCheck
from util import report

class TcpCheck(HealthCheck):
  """ A health check which tries to connect to a port via TCP. """
  def __init__(self, config):
    self.config = config
    
  def run(self, container, report):
    container_port = self.config.getExtraField('port')
    local_port = self.getLocalPort(container, container_port)
    
    report('Checking TCP port: ' + str(local_port))
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
    
    report('Checking HTTP address: ' + address)
    try:
      response = urllib2.urlopen(address, timeout = 2)
      response.read()
    except:
      return False
      
    return True