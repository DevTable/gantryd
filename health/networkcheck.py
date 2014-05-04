import socket
import urllib2

from health.healthcheck import HealthCheck
from util import ReportLevels

class TcpCheck(HealthCheck):
  """ A health check which tries to connect to a port via TCP. """
  def __init__(self, config):
    super(TcpCheck, self).__init__()
    self.config = config
    
  def run(self, container, report):
    container_port = self.config.getExtraField('port')
    container_ip = self.getContainerIPAddress(container)

    report('Checking TCP port in container ' + container['Id'][0:12] + ': ' + str(container_port),
      level = ReportLevels.EXTRA)
    try:
      sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
      sock.connect((container_ip, container_port))
      sock.close()
    except Exception as e:
      print e
      return False
      
    return True
    
    
class HttpRequestCheck(HealthCheck):
  """ A health check which tries to connect to an HTTP server on a known port. """
  def __init__(self, protocol, config):
    super(HttpRequestCheck, self).__init__()
    self.protocol = protocol
    self.config = config
    
  def run(self, container, report):
    container_port = self.config.getExtraField('port')
    container_ip = self.getContainerIPAddress(container)
    
    address = '%s://%s:%s' % (self.protocol, container_ip, container_port)
    if self.config.hasExtraField('path'):
      address += self.config.getExtraField('path')
    
    report('Checking HTTP address in container ' + container['Id'][0:12] + ': ' + address,
      level = ReportLevels.EXTRA)
    try:
      response = urllib2.urlopen(address, timeout = 2)
      response.read()
    except Exception as exc:
      self.logger.exception(exc)
      return False
      
    return True
