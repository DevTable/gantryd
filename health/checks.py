from networkcheck import TcpCheck, HttpRequestCheck
from util import report, fail, getDockerClient

# The list of registered health checks
HEALTH_CHECKS = {
  'tcp': TcpCheck,
  'http': HttpRequestCheck
}

def runHealthCheck(check_config, container, report):
  """ Runs the health check (as specified by the given config) over the given container. """
  kind = check_config.kind
  if not kind in HEALTH_CHECKS:
    fail('Unknown health check: ' + kind)
  
  instance = HEALTH_CHECKS[kind](check_config)
  return instance.run(container, report)