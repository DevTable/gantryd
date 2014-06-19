#!/usr/bin/env python

import argparse
import signal
import time

from actions import start_action, update_action, list_action, stop_action, kill_action
from config.GantryConfig import Configuration
from runtime.manager import RuntimeManager
from util import report, fail


ACTIONS = {
  'start': start_action,
  'update': update_action,
  'list': list_action,
  'stop': stop_action,
  'kill': kill_action
}


def loadConfig(config_file):
  """ Attempts to load and parse the given config file. """
  try:
    with open(config_file, 'r') as f:
      config_json = f.read()
  except:
    print 'Could not find config file: ' + config_file
    return None

  try:
    return Configuration.parse(config_json)
  except Exception as e:
    print 'Error parsing gantry config: ' + str(e)
    return None


def monitor(component):
  while True:
    # Sleep for 30 seconds.
    time.sleep(30)

    # Conduct the checks.
    report('Checking in on component ' + component.getName())
    if not component.isHealthy():
      report('Component ' + component.getName() + ' is not healthy. Killing and restarting')
      component.stop(kill=True)
      if not component.update():
        report('Could not restart component ' + component.getName())
        return


def run():
  # Setup the gantry arguments
  parser = argparse.ArgumentParser(description='gantry continuous deployment system')
  parser.add_argument('config_file', help='The configuration file')
  parser.add_argument('action', help='The action to perform', choices=ACTIONS.keys())
  parser.add_argument('component_name', help='The name of the component to manage')
  parser.add_argument('-m', dest='monitor', action='store_true', help='If specified and the action is "start" or "update", gantry will remain running to monitor components, auto restarting them as necessary')
  parser.add_argument('--setconfig', dest='config_overrides', action='append', help='Configuration overrides for the component')

  args = parser.parse_args()
  component_name = args.component_name
  action = args.action
  should_monitor = args.monitor
  config_file = args.config_file
  config_overrides = args.config_overrides

  # Load the config.
  config = loadConfig(config_file)
  if not config:
    return

  # Create the manager.
  manager = RuntimeManager(config)

  # Find the component
  component = manager.getComponent(component_name)
  if not component:
    raise Exception('Unknown component: ' + component_name)
    
  # Apply the config overrides (if any).
  if config_overrides:
    component.applyConfigOverrides(config_overrides)

  # Run the action with the component and config.
  result = ACTIONS[action](component)
  if result and should_monitor:
    try:
      report('Starting monitoring of component: ' + component_name)
      monitor(component)
    except KeyboardInterrupt:
      report('Terminating monitoring of component: ' + component_name)

  def cleanup_monitor(signum, frame):
    manager.join()

  # Set the signal handler and a 5-second alarm
  signal.signal(signal.SIGINT, cleanup_monitor)

  # We may have to call cleanup manually if we weren't asked to monitor
  cleanup_monitor(None, None)

if __name__ == "__main__":
  run()