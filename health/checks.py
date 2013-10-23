from networkcheck import TcpCheck, HttpRequestCheck
from util import report, fail, getDockerClient

# The list of registered health checks
HEALTH_CHECKS = {
  'tcp': TcpCheck,
  'http': HttpRequestCheck
}

def buildHealthCheck(check_config):
  """ Builds a health check to run and returns it. """
  kind = check_config.kind
  if not kind in HEALTH_CHECKS:
    fail('Unknown health check: ' + kind)
  
  return HEALTH_CHECKS[kind](check_config)