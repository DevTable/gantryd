import time
import threading
import json

from gantryd.componentstate import ComponentState, STOPPED_STATUS, KILLED_STATUS, READY_STATUS
from util import report, fail, getDockerClient

CHECK_SLEEP_TIME = 30 # 30 seconds
CHECK_SHORT_SLEEP_TIME = 10 # 10 seconds

class ComponentWatcher(object):
  """ Helper class which watches a specific component's status in etcd and
      manages the update/stop/kill process (if necessary).
  """
  def __init__(self, component, project_name, machine_id, etcd_client):
    self.component = component
    self.machine_id = machine_id    
    self.is_running = False

    # Setup the state helper for the component.
    self.state = ComponentState(project_name, component, etcd_client)

    # Setup the watcher thread.
    self.watcher_thread = threading.Thread(target = self.waitForCommand, args = [])
    self.watcher_thread.daemon = True

  def start(self):
    """ Starts the watcher. """
    self.watcher_thread.start()

  def waitForCommand(self):
    """ Waits for an command notification on the component in etcd. If one is received,
        processes it by attempting to update the component.
    """
    sleep_time = 0
    while True:
      # Sleep and then check again.
      time.sleep(sleep_time)
      sleep_time = CHECK_SLEEP_TIME
      
      # Check the component's status.
      state = self.state.getState()

      # Take actions based on the status requested.           
      current_status = ComponentState.getStatusOf(state)
      if current_status == STOPPED_STATUS:
        self.is_running = False
        self.component.stop(kill = False)
        continue
      elif current_status == KILLED_STATUS:
        self.is_running = False
        self.component.stop(kill = True)
        continue
      
      # If the status is ready, we update the component if:
      #   - The ID of the component's image does not match that found in the status.
      #   - The process is not running.
      imageid = ComponentState.getImageIdOf(state)
      should_update = not self.is_running or imageid != self.component.getImageId()
      
      if current_status == READY_STATUS and should_update:
        # We need to update this machine's copy. First, do a test and set to ensure that
        # we are the only machine allowed to update. If the test and set fails, we'll
        # try again in 10s.
        report('Update pushed for component ' + self.component.getName())
        result = self.state.setUpdatingStatus('updating', self.machine_id, state)
        if not result:
          # The exchange failed. Sleep CHECK_SHORT_SLEEP_TIME seconds and try again.
          report('Exchange failed. Sleeping ' + str(CHECK_SHORT_SLEEP_TIME) + ' seconds')          
          sleep_time = CHECK_SHORT_SLEEP_TIME
          continue
        
        # Start the update by pulling the repo for the component.
        report('Pulling the image for component ' + self.component.getName())
        if not self.component.pullRepo():
          # The pull failed.
          report('Pull failed of image ' + imageid[0:12] + ' for component ' + self.component.getName())
          self.state.setUpdatingStatus('pullfail', self.machine_id, result)
          sleep_time = CHECK_SLEEP_TIME
          continue
          
        # Run the update on the component and wait for it to finish.
        report('Starting update for component ' + self.component.getName())
        if not self.component.update():
          # The update failed.
          self.state.setUpdatingStatus('updatefail', self.machine_id, result)
          sleep_time = CHECK_SLEEP_TIME
          continue
        
        # Otherwise, the update has succeeded. Mark the component as ready, so another
        # gantryd can start its update.
        report('Update completed for component ' + self.component.getName())
        self.state.setReadyStatus(self.component.getImageId())
        self.is_running = True