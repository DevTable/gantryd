#!/usr/bin/env python

from gantryd.client import GantryDClient
import argparse
import json

ETCD_HOST = '127.0.0.1'

def run(dclient, args):
  """ Runs gantryd. """
  dclient.run(args.component)

def getconfig(dclient, args):
  """ Prints out the current project configuration stored in etcd. """
  config = None
  try:
    config = dclient.getConfigJSON()
  except:
    pass
    
  if not config:
    print 'No config found'
    return
  
  print json.dumps(json.loads(config), sort_keys=True, indent=2, separators=(',', ': '))

def setconfig(dclient, args):
  """ Sets the current project configuration stored in etcd. """
  if not args.configfile:
    print 'Missing configfile parameter'
    return
    
  with open(args.configfile, 'r') as f:
    dclient.setConfig(json.loads(f.read()))
    print 'Configuration updated'

def list_status(dclient, args):
  """ Lists the status of all components in gantryd. """
  dclient.listStatus()

def mark_updated(dclient, args):
  """ Marks a component to be updated. """
  dclient.markUpdated(args.component)

def stop(dclient, args):
  """ Marks a component to be stopped. """
  dclient.stopComponents(args.component)

def kill(dclient, args):
  """ Marks a component to be killed. """
  dclient.killComponents(args.component)

ACTIONS = {
  'run': run,
  'getconfig': getconfig,
  'setconfig': setconfig,
  'list': list_status,
  'update': mark_updated,
  'stop': stop,
  'kill': kill
}

def start():  
  # Setup the gantryd arguments.
  parser = argparse.ArgumentParser(description='gantry continuous deployment system daemon')
  parser.add_argument('action', help = 'The action to perform', choices = ACTIONS.keys())
  parser.add_argument('project', help = 'The name of the project containing the components')
  parser.add_argument('configfile', help = 'The name of the config file. Only applies to setconfig.', nargs='?')
  parser.add_argument('-c', help = 'A component to watch and run', nargs='+', type=str, dest='component')
  parser.add_argument('-etcd', help = 'The etcd endpoint to which the client should connect. Defaults to 127.0.0.1:4001', dest='etcd_host', nargs='?', const=ETCD_HOST)

  # Parse the arguments.  
  args = parser.parse_args()

  # Initialize the gantryd client.
  dclient = GantryDClient(args.etcd_host or ETCD_HOST, args.project)  

  # Run the action.
  action = ACTIONS[args.action]
  action(dclient, args)

start()