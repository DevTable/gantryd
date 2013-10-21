import json
import string
import copy

class CFObject(object):
  """ 
    Defines a class in which all fields marked with the CFField are automatically handled
    for configuration purposes.
  """  
  def __init__(self, name):
    # The parent of the object.
    self.parent = None
    
    # The name of the object.
    self.name = name
    
    # The cached fields for the object.
    self.fields = None
    
    # The "extra" fields on the object, if any.
    self.extra_fields = {}
  
  def getExtraField(self, name):
    """ Returns the 'extra' field with this name. """
    return self.extra_fields[name]
  
  def getRootConfig(self):
    """ Returns the root configuration object. """
    if self.parent:
      return self.parent
      
    return self
  
  @classmethod
  def parse(cls, json_data):
    """ Parses the given JSON data into an instance of this config object. """
    dictionary = json.loads(json_data)
    return cls.build(dictionary)
    
  @classmethod
  def build(cls, dictionary):
    """ Builds an instance of this config object from the given dictionary. """
    instance = cls()
    instance.extra_fields = copy.copy(dictionary)
    for name in instance.get_fields():
      if name in instance.extra_fields:
         del instance.extra_fields[name]
        
      field = instance.get_fields()[name]
      if field.is_required() and not name in dictionary:
        raise Exception('Missing required property ' + name + ' under object ' + instance.name)

      if name in dictionary:
        field.populate(instance, dictionary[name])

    return instance      

  def get_fields(self):
    """ Returns a dictionary of all CFField's defined in the CFObject """
    # Check the field cache first
    if self.fields:
      return self.fields
    
    fields = {}
    class_fields = dir(self.__class__)
    class_dict = self.__class__.__dict__
    for field_name in class_fields:
      if class_dict.has_key(field_name):
        field = class_dict[field_name]
        if field.__class__ == CFField:
          name = CFField.get_name(field)
          fields[name] = field
    self.fields = fields
    return fields


class CFField(object):
  """ A field representing a property in the configuration object """
  def __init__(self, name):
    # The name of the field in the config.
    self.name = name

    # The current value of the field.
    self.value = None
    
    # The type of the field. Defaults to string.
    self.field_kind = str
    
    # If this field is a list, the kind of its elements.
    self.list_kind = None
    
    # The default value for the field. If none, the field is required.
    self.default_value = None
    
  def __get__(self, instance, owner):
    return self.get_value(instance)

  def __set__(self, instance, value):
    self.update(instance, value)
        
  def kind(self, kind):
    """ Sets the kind of the field. """
    self.field_kind = kind
    return self

  def default(self, value):
    """ Sets the default value for the field. """
    self.default_value = value
    return self

  def list_of(self, kind):
    """ Sets that this field is a list of some kind of values. """
    self.field_kind = list
    self.list_kind = kind
    return self

  def is_required(self):
    return self.default_value is None

  def get_name(self):
    """ Returns the name of the field """
    return self.name
    
  def populate(self, instance, primitive):
    """ Attempts to populate this list from the given primitive value. """
    if self.field_kind == list:
      if not isinstance(primitive, list):
        raise Exception('Expected list for field ' + self.name)
      
      list_value = []
      for p in primitive:
        c_value = self.get_converted_value(instance, p, self.list_kind)
        if not isinstance(c_value, self.list_kind):
          raise Exception('Expected items of kind ' + str(self.list_kind) + ' in ' + self.name)
        list_value.append(c_value)
        
      self.update(instance, list_value)
      return
      
    self.update(instance, self.get_converted_value(instance, primitive, self.field_kind))
  
  def get_converted_value(self, instance, primitive, kind):      
    # Class types.
    if issubclass(kind, CFObject):
      if not isinstance(primitive, dict):
        raise Exception('Expected dictionary for field ' + self.name)
      
      built = kind.build(primitive)
      built.parent = instance;
      return built
      
    # Otherwise, convert to from a string.
    return kind(primitive)
    
  def internal_data(self, instance):
    internal_name = self.name + '_data'
    if internal_name not in instance.__dict__:
      instance.__dict__[internal_name] = {'data': None}
    return instance.__dict__[internal_name]

  def get_value(self, instance):
    """ Returns the value of the field for the given instance """
    value = self.internal_data(instance)['data'];
    if value is None and self.default_value is not None:
      return self.default_value
      
    return value

  def set_value(self, instance, value):
    """ Sets the value of the field for the given instance """
    self.__set__(instance, value)
    
  def update(self, instance, value):
    """ Updates the value of the field """
    self.internal_data(instance)['data'] = value