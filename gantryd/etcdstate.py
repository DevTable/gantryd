import json

class EtcdState(object):
  """ Base class for all helper classes which get and set state in etcd for objects.
  """
  def __init__(self, state_path, etcd_client):
    self.etcd_client = etcd_client
    self.state_path = state_path

  def getState(self, default = {}):
    """ Gets the state. """
    try:
      return json.loads(self.etcd_client.get(self.state_path).value)
    except KeyError:
      pass
    except ValueError:
      pass
      
    return default

  def replaceState(self, previous_state, new_state):
    """ Attempts to atomically replace the given previous state with a new state.
        On success, returns the new state object. On failure, returns None.
    """
    try:
      original_contents_json = json.dumps(previous_state, separators=(',',':'))
      new_contents_json = json.dumps(new_state, separators=(',',':'))
      self.etcd_client.test_and_set(self.state_path, new_contents_json, original_contents_json)
    except ValueError as e:
      return None
    
    return new_state

  def buildAndSetState(self, **kwargs):
    """ Builds state from the given args and sets the state. """
    state_obj = dict(kwargs)
    self.setState(state_obj)
    
  def setState(self, state_obj = {}, ttl = None):
    """ Sets the state to the given object. """
    self.etcd_client.set(self.state_path, json.dumps(state_obj, separators=(',',':')), ttl = ttl)
    
  def deleteState(self):
    """ Deletes the state. """
    self.etcd_client.delete()

  