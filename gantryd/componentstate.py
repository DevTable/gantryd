import json
from etcdstate import EtcdState
from etcdpaths import getComponentStatePath

READY_STATUS = 'ready'
STOPPED_STATUS = 'stopped'
KILLED_STATUS = 'killed'
PULL_FAIL = 'pullfail'

IMAGE_ID = 'imageid'

class ComponentState(EtcdState):
  """ Helper class which allows easy getting and setting of the etcd distributed
      state of a component.
  """
  def __init__(self, project_name, component, etcd_client):
    path = getComponentStatePath(project_name, component)
    super(ComponentState, self).__init__(path, etcd_client)

  @staticmethod
  def getStatusOf(state):
    """ Returns the status field in the given state object. """
    return state['status'] if 'status' in state else 'unknown'

  @staticmethod
  def getImageIdOf(state):
    """ Returns the image ID field in the given state object or empty string if None. """
    return state[IMAGE_ID] if IMAGE_ID in state else ''

  def getStatus(self):
    """ Returns the status of the component. """
    return self.getState(default={'status': 'unknown'}).status

  def setStatus(self, status, **kwargs):
    """ Sets the status of the component. """
    state = dict(kwargs)
    state['status'] = status
    self.setState(state)

  def setReadyStatus(self, imageid):
    """ Sets the status of the component to 'ready', with the given imageid. """
    self.setStatus(READY_STATUS, imageid=imageid)

  def setUpdatingStatus(self, status, machine_id, original_state):
    """ Attempts to set the status of the component to being updated by the given machine.
        Returns the updated state on success and None otherwise.
    """
    state = {}
    state['status'] = status
    state['machine'] = machine_id
    return self.replaceState(original_state, state)
