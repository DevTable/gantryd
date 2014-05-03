import docker
import json

GANTRY_METADATA_FILE = '.gantry_metadata'
cached_metadata = None

def getContainerStatus(container):
  """ Returns the status code of the given container. """
  return getContainerField(container, 'status', default = 'unknown')

def setContainerStatus(container, status):
  """ Sets the status code for the given container. """
  setContainerField(container, 'status', status)    

def getContainerComponent(container):
  """ Returns the component that owns the given container. """
  return getContainerField(container, 'component', default = 'unknown')

def setContainerComponent(container, component):
  """ Sets the component code for the given container. """
  setContainerField(container, 'component', component)    

def removeContainerMetadata(container):
  """ Removes all internal metadata for the container. """
  id = container['Id'][0:12] # Running container IDs are longer.
  metadata = getGantryMetadata()
  containers = metadata['containers']

  if id in containers:
    del containers[id]
    saveGantryMetadata(metadata)


#########################################################################

def getGantryMetadata():
  """ Attempts to load the full metadata file. If none found, returns a new empty metadata
      dict.
  """
  if cached_metadata:
    return cached_metadata
    
  try:
    with open(GANTRY_METADATA_FILE, 'r') as f:
      metadata_json = f.read()
  except IOError:
      metadata_json = None

  # Parse it as JSON.
  metadata = {'containers': {}, 'components': {}}
  if metadata_json:
    try:
      metadata = json.loads(metadata_json)
    except:
      pass
  
  if not 'containers' in metadata:
    metadata['containers'] = {}

  if not 'components' in metadata:
    metadata['components'] = {}
  
  return metadata

def saveGantryMetadata(metadata):
  """ Saves the given metadata to the metadata file. """
  cached_metadata = metadata
  
  # Create the JSON form of the information.
  metadata_json = json.dumps(metadata)
  with open(GANTRY_METADATA_FILE, 'w') as f:
    f.write(metadata_json)
  
  
#########################################################################

def getContainerMetadata(container):
  """ Returns the internal metadata object for the container. """
  id = container['Id'][0:12] # Running container IDs are longer.
  
  # Load the metadata.
  metadata = getGantryMetadata()
  
  # Find the information for the container with the given ID.
  containers = metadata['containers']
  if not id in containers:
    return {}
    
  return containers[id]

def setContainerMetadata(container, info):
  """ Sets the internal metadata object for the container. """
  
  # Load the metadata.
  metadata = getGantryMetadata()

  # Update the metadata for the container.
  id = container['Id'][0:12] # Running container IDs are longer.
  metadata['containers'][id] = info

  # Save the metadata.
  saveGantryMetadata(metadata)

def getContainerField(container, field, default):
  """ Returns the metadata field for the given container or the default value. """
  info = getContainerMetadata(container)
  if not field in info:
    return default
  return info[field]
  
def setContainerField(container, field, value):
  """ Sets the metadata field for the given container. """
  info = getContainerMetadata(container)
  info[field] = value
  setContainerMetadata(container, info)


#########################################################################

def getComponentMetadata(component_name):
  """ Returns the internal metadata object for the component. """  
  metadata = getGantryMetadata()  
  components = metadata['components']
  return components.get(component_name, {})

def setComponentMetadata(component_name, info):
  """ Sets the internal metadata object for the component. """  
  metadata = getGantryMetadata()
  metadata['components'][component_name] = info
  saveGantryMetadata(metadata)

def getComponentField(component_name, field, default):
  """ Returns the metadata field for the given component or the default value. """
  info = getComponentMetadata(component_name)
  return info.get(field, default)
  
def setComponentField(component_name, field, value):
  """ Sets the metadata field for the given component. """
  info = getComponentMetadata(component_name)
  info[field] = value
  setComponentMetadata(component_name, info)
