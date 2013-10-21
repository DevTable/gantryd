#!/usr/bin/env python

import argparse
from actions import start_action, update_action, list_action, stop_action, kill_action
from config.GantryConfig import Configuration
from runtime.manager import RuntimeManager

CONFIG_FILE = '.gantry'

ACTIONS = {
  'start': start_action,
  'update': update_action,
  'list': list_action,
  'stop': stop_action,
  'kill': kill_action
}

def run(config):  
  # Setup the gantry arguments
  parser = argparse.ArgumentParser(description='gantry continuous deployment system')
  parser.add_argument('action', help = 'The action to perform', choices = ACTIONS.keys())
  parser.add_argument('component_name', help = 'The name of the component to manage')
  
  args = parser.parse_args()
  component_name = args.component_name
  action = args.action
  
  # Create the manager.
  manager = RuntimeManager(config)
  
  # Find the component
  component = manager.getComponent(component_name)
  if not component:
    raise Exception('Unknown component: ' + component_name)

  # Run the action with the component and config.
  ACTIONS[action](component)


def loadConfig():
  try:
    with open(CONFIG_FILE, 'r') as f:
      config_json = f.read()
  except:
    print 'Could not find .gantry'
    return None
    
  return Configuration.parse(config_json)
  try:
    return Configuration.parse(config_json)
  except Exception as e:
    print 'Error parsing gantry config: ' + str(e)
    return None
    
    
config = loadConfig()
if config:
  run(config)