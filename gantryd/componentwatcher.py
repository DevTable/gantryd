import time
import threading
import json
import logging

from gantryd.componentstate import ComponentState, STOPPED_STATUS, KILLED_STATUS, READY_STATUS, PULL_FAIL
from util import report, fail, getDockerClient, ReportLevels

CHECK_SLEEP_TIME = 30 # 30 seconds
CHECK_SHORT_SLEEP_TIME = 10 # 10 seconds
MONITOR_SLEEP_TIME = 30 # 30 seconds

class ComponentWatcher(object):
  """ Helper class which watches a specific component's status in etcd and
      manages the update/stop/kill process (if necessary). Also watches the
      component itself once started, and ensures that it remains running (restarting
      it if it failed).
  """
  def __init__(self, component, project_name, machine_id, etcd_client):
    self.component = component
    self.project_name = project_name
    self.machine_id = machine_id
    self.is_running = False

    # Logging.
    self.logger = logging.getLogger(__name__)

    # Setup the state helper for the component.
    self.state = ComponentState(project_name, component, etcd_client)

    # Setup the watcher thread.
    self.watcher_thread = threading.Thread(target=self.waitForCommand, args=[])
    self.watcher_thread.daemon = True

    # Setup the monitor thread.
    self.monitor_thread = threading.Thread(target=self.monitorComponent, args=[])
    self.monitor_thread.daemon = True

    # Setup an event to ping the monitor thread when it should restart checking in
    # on the component.
    self.monitor_event = threading.Event()

    # Setup a lock to prevent multiple threads from trying to (re)start a container.
    self.update_lock = threading.Lock()

  def start(self):
    """ Starts the watcher. """
    self.watcher_thread.start()
    self.monitor_thread.start()

  def monitorComponent(self):
    """ Monitors a component by pinging it every MONITOR_SLEEP_TIME seconds or so. If a component
        fails, then the system will try to restart it. If that fails, the component is marked
        as dead.
    """
    while True:
      # Wait for the component to be running.
      self.monitor_event.wait()

      # Sleep MONITOR_SLEEP_TIME seconds.
      time.sleep(MONITOR_SLEEP_TIME)

      # Check the component.
      report('Checking in on component', project=self.project_name, component=self.component,
             level=ReportLevels.BACKGROUND)

      if not self.component.isHealthy():
        self.logger.debug('Component %s is not healty', self.component.getName())
        with self.update_lock:
          # Just to be sure...
          if not self.is_running:
            continue

          # Ensure that the component is still ready.
          state = self.state.getState()
          current_status = ComponentState.getStatusOf(state)
          if current_status == READY_STATUS:
            report('Component ' + self.component.getName() + ' is not healthy. Restarting...',
                   project=self.project_name, component=self.component)

            if not self.component.update():
              report('Could not restart component ' + self.component.getName(),
                     project=self.project_name, component=self.component,
                     level=ReportLevels.IMPORTANT)
              self.monitor_event.clear()
              continue

  def waitForCommand(self):
    """ Waits for an command notification on the component in etcd. If one is received,
        processes it by attempting to update the component.
    """
    is_initial_loop = True
    sleep_time = 0
    while True:
      # Sleep and then check again.
      time.sleep(sleep_time)
      sleep_time = CHECK_SLEEP_TIME

      # Check the component's status.
      self.logger.debug('Checking state for component %s', self.component.getName())
      state = self.state.getState()
      self.logger.debug('Found state %s for component %s', state, self.component.getName())

      # Determine whether we should give initial status messages.
      was_initial_loop = is_initial_loop
      is_initial_loop = False

      # Take actions based on the status requested.
      current_status = ComponentState.getStatusOf(state)
      sleep_time = self.handleStatus(current_status, state, was_initial_loop)

  def handleStatus(self, current_status, state, was_initial_check):
    """ Handles the various status states for the component, returning the
        amount of time after which to retry lookup up the state or -1 for
        terminated.
    """
    if current_status == STOPPED_STATUS:
      return self.handleStopped(was_initial_check)
    elif current_status == KILLED_STATUS:
      return self.handleKilled(was_initial_check)
    elif current_status == READY_STATUS or current_status == PULL_FAIL:
      with self.update_lock:
        return self.handleReady(state, was_initial_check)

    return CHECK_SLEEP_TIME

  def handleStopped(self, was_initial_check):
    """ Handles when the component has been marked to be stopped. """
    self.monitor_event.clear()

    if was_initial_check:
      report('Component %s is marked as stopped' % self.component.getName(),
             project=self.project_name, component=self.component)

    self.is_running = False
    self.component.stop(kill=False)
    return CHECK_SLEEP_TIME

  def handleKilled(self, was_initial_check):
    """ Handles when the component has been marked to be killed. """
    self.monitor_event.clear()

    if was_initial_check:
      report('Component %s is marked as killed' % self.component.getName(),
             project=self.project_name, component=self.component)

    self.is_running = False
    self.component.stop(kill=True)
    return CHECK_SLEEP_TIME

  def handleReady(self, state, was_initial_check):
    """ Handles when the component has been marked as ready. """

    # If the status is ready, we update the component if:
    #   - The ID of the component's image does not match that found in the status.
    #   - The process is not running.
    imageid = ComponentState.getImageIdOf(state)
    imageid_different = imageid != self.component.getImageId()
    should_update = not self.is_running or imageid_different

    if should_update:
      self.is_running = False
      self.monitor_event.clear()

      # We need to update this machine's copy. First, do a test and set to ensure that
      # we are the only machine allowed to update. If the test and set fails, we'll
      # try again in 10s.
      if imageid_different:
        report('Detected pushed update for component ' + self.component.getName(),
               project=self.project_name, component=self.component)
      else:
        report('Component %s is not running; starting' % self.component.getName(),
               project=self.project_name, component=self.component)

      result = self.state.setUpdatingStatus('updating', self.machine_id, state)
      if not result:
        # The exchange failed. Sleep CHECK_SHORT_SLEEP_TIME seconds and try again.
        report('Could not grab update lock. Will try again in %s seconds' % CHECK_SHORT_SLEEP_TIME,
               project=self.project_name, component=self.component)
        return CHECK_SHORT_SLEEP_TIME

      # Start the update by pulling the repo for the component.
      if imageid_different:
        report('Pulling the image for component ' + self.component.getName())
        if not self.component.pullRepo():
          # The pull failed.
          report('Pull failed of image %s for component %s' % (imageid[0:12],
                                                               self.component.getName()),
                 project=self.project_name, component=self.component, level=ReportLevels.IMPORTANT)
          self.state.setUpdatingStatus('pullfail', self.machine_id, result)
          return CHECK_SLEEP_TIME

      # Run the update on the component and wait for it to finish.
      if imageid_different:
        report('Starting update for component ' + self.component.getName(),
               project=self.project_name, component=self.component)

      if not self.component.update():
        # The update failed.
        self.state.setUpdatingStatus('updatefail', self.machine_id, result)
        return CHECK_SLEEP_TIME

      # Otherwise, the update has succeeded. Mark the component as ready, so another
      # gantryd can start its update.
      if imageid_different:
        report('Update completed for component ' + self.component.getName(),
               project=self.project_name, component=self.component)
      else:
        report('Component ' + self.component.getName() + ' is now running',
               project=self.project_name, component=self.component)

      self.state.setReadyStatus(self.component.getImageId())
      self.is_running = True
      self.monitor_event.set()

    return CHECK_SLEEP_TIME
