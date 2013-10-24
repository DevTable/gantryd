def start_action(component):
  if component.isRunning():
    print 'Component ' + component.getName() + ' is already running'
    return False
    
  return component.update()
  
def stop_action(component):
  if not component.isRunning():
    print 'Component ' + component.getName() + ' is not running'
    return False

  component.stop(kill = False)
  return False
  
def kill_action(component):
  if not component.isRunning():
    print 'Component ' + component.getName() + ' is not running'
    return False

  component.stop(kill = True)
  return False
  
def update_action(component):
  return component.update()
  
def list_action(component):
  if not component.isRunning():
    print 'Component ' + component.getName() + ' is not running'
    return False

  print "%-20s %-20s %-20s %-20s" % ('CONTAINER ID', 'UPTIME', 'IMAGE ID', 'STATUS')
  
  for info in component.getContainerInformation():
    container = info[0]
    status = info[1]

    id = container['Id']
    uptime = container['Status']
    image = container['Image']
    i = (id[0:12], uptime, image, status)
    print "%-20s %-20s %-20s %-20s" % i
    
  return False

