import json
import socket

from etcdstate import EtcdState
from etcdpaths import getMachineStatePath

STATUS_RUNNING = 'running'

class MachineState(EtcdState):
  """ Helper class which allows easy getting and setting of the etcd distributed
      state of a machine.
  """
  def __init__(self, project_name, machine_id, etcd_client):
    path = getMachineStatePath(project_name, machine_id)
    super(MachineState, self).__init__(path, etcd_client)

  def registerMachine(self, component_names, ttl = 60):
    """ Registers this machine with etcd. """
    machine_state = {
      'status': STATUS_RUNNING,
      'components': component_names,
      'ip': socket.gethostbyname(socket.gethostname())
    }
    
    self.setState(machine_state, ttl = ttl)
    
  def getStatus(self):
    """ Returns the status of this machine. """
    return self.getState({'status': 'unknown'})
    
  def removeMachine(self):
    """ Removes this machine from etcd. """
    self.deleteState()