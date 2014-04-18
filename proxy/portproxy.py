import subprocess
import logging
import psutil

from uuid import uuid4
from jinja2 import Environment, FileSystemLoader

TEMPLATE_FOLDER = 'proxy'

HAPROXY = 'haproxy'
HAPROXY_TEMPLATE = 'haproxy.tmpl'
HAPROXY_PID_FILE = '/var/run/haproxy-private.pid'
HAPROXY_CONFIG_FILE = 'haproxy.conf'

CLOSE_WAIT = 'CLOSE_WAIT'

class Proxy(object):
  def __init__(self):
    # Logging.
    self.logger = logging.getLogger(__name__)

    # The registered routes, by external port number.
    self._port_routes = {}

    jinja_options = {
        "loader": FileSystemLoader(TEMPLATE_FOLDER),
    }

    env = Environment(**jinja_options)
    self._template = env.get_template(HAPROXY_TEMPLATE)

  def get_connections(self):
    """ Returns the connection information for all proxy processes. """
    self.logger.debug('Getting proxy connections')
    connections = []
    for proc in psutil.process_iter():
      if proc.is_running() and proc.name() == HAPROXY:
        connections.extend([conn for conn in proc.get_connections() if conn.status != CLOSE_WAIT])
        
    return connections

  def clear_routes(self):
    """ Clears all routes found in the proxy. """
    self._port_routes = {}
  
  def add_route(self, route):
    """ Adds a route to the proxy (but does not commit the changes). """
    self._port_routes[route.host_port] = route

  def remove_route(self, route_id):
    """ Removes a route from the proxy (but does not commit the changes). """
    del self._port_routes[removed.host_port]

  def shutdown(self):
    """ Shuts down the proxy entirely. """
    subprocess.call('./shutdown-haproxy.sh', shell=True, close_fds=True)

  def commit(self):
    """ Commits the changes made to the proxy. """
    self.logger.debug("Restarting haproxy with new rules.")

    # If the port routes are empty, add a dummy mapping to the proxy.
    if len(self._port_routes.values()) == 0:
      self.add_route(Route(False, 65535, '127.0.0.2', 65534, is_fake = True))
      
    # Write out the config.
    rendered = self._template.render({'port_routes': self._port_routes})
    with open(HAPROXY_CONFIG_FILE, 'w') as config_file:
      config_file.write(rendered)
      
    # Restart haproxy
    subprocess.call('./restart-haproxy.sh', shell=True, close_fds=True)


class Route(object):
  """ A single route proxied. """
  def __init__(self, is_http, host_port, container_ip, container_port, is_fake = False):
    self.id = str(uuid4())
    self.is_fake = is_fake
    self.is_http = is_http
    self.host_port = host_port
    self.container_ip = container_ip
    self.container_port = container_port
