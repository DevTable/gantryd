def getContainerIPAddress(client, container):
  """ Returns the IP address on which the container is running. """
  container_info = client.inspect_container(container)
  return container_info['NetworkSettings']['IPAddress']
