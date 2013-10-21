import docker

client = docker.Client()

def report(msg):
  """ Reports a message to the console. """
  print msg
  
def fail(reason):
  """ Fails due to some unexpected error. """
  raise Exception(reason)
  
def getDockerClient():
  """ Returns the docker client. """
  return client