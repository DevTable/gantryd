def getLocalPort(client, container, container_port):
  """ Returns the port on the local system for the given container port or 0 if none. """
  try:
    return client.port(container, container_port)
  except Exception as e:
    return 0

def getLocalPorts(container):
  """ Returns the set of ports exposed in the local networking stack for the given
      container.
  """    
  container_ports = container['Ports']
  if isinstance(container_ports, basestring):
    container_ports = [container_ports]
    
  return set([int(p.split('->')[0]) for p in container_ports if len(p) > 0])

def getContainerIPAddress(client, container):
  """ Returns the IP address on which the container is running. """
  container_info = client.inspect_container(container)
  return container_info['NetworkSettings']['IPAddress']
