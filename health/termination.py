import urllib2

from health.healthcheck import TerminationSignal
from util import ReportLevels

class HttpTerminationSignal(TerminationSignal):
  """ A termination signal which tries to POST to an HTTP server on a known port. """
  def __init__(self, protocol, config):
    super(TerminationSignal, self).__init__()
    self.protocol = protocol
    self.config = config

  def run(self, container, report):
    container_port = self.config.getExtraField('port')
    container_ip = self.getContainerIPAddress(container)

    address = '%s://%s:%s' % (self.protocol, container_ip, container_port)
    if self.config.hasExtraField('path'):
      address += self.config.getExtraField('path')

    data = ''

    report('Posting to HTTP address in container ' + container['Id'][0:12] + ': ' + address,
           level=ReportLevels.EXTRA)
    try:
      req = urllib2.Request(address, data)
      response = urllib2.urlopen(req, timeout=2)
      response.read()
    except Exception as exc:
      self.logger.exception(exc)
      return False

    return True
