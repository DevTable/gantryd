from functools import partial

from networkcheck import TcpCheck, HttpRequestCheck, IncomingConnectionCheck
from termination import HttpTerminationSignal, ExecTerminationSignal
from util import report, fail, getDockerClient

# The list of registered health checks
HEALTH_CHECKS = {
  'tcp': TcpCheck,
  'http': partial(HttpRequestCheck, 'http'),
  'https': partial(HttpRequestCheck, 'https'),
  'connection': IncomingConnectionCheck,
}

def buildHealthCheck(check_config):
  """ Builds a health check to run and returns it. """
  kind = check_config.kind
  if not kind in HEALTH_CHECKS:
    fail('Unknown health check: ' + kind)

  return HEALTH_CHECKS[kind](check_config)

TERMINATION_SIGNALS = {
  'http': partial(HttpTerminationSignal, 'http'),
  'https': partial(HttpTerminationSignal, 'https'),
  'exec': ExecTerminationSignal,
}

def buildTerminationSignal(check_config):
  """ Builds a termination signal and returns it. """
  kind = check_config.kind
  if not kind in TERMINATION_SIGNALS:
    fail('Unknown termination signal kind: ' + kind)

  return TERMINATION_SIGNALS[kind](check_config)
