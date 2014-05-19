import docker
import json

from peewee import (Model, SqliteDatabase, ForeignKeyField, CharField, OperationalError,
                    sort_models_topologically, DoesNotExist)
from functools import wraps

GANTRY_METADATA_FILE = '.gantry_metadata'
cached_metadata = None


db = SqliteDatabase(GANTRY_METADATA_FILE)


class BaseModel(Model):
  class Meta:
    database = db


class Component(BaseModel):
  name = CharField(index=True)


class ComponentField(BaseModel):
  component = ForeignKeyField(Component)
  key = CharField(index=True)
  value = CharField()


class Container(BaseModel):
  docker_id = CharField(index=True)
  component = ForeignKeyField(Component, null=True)


class ContainerField(BaseModel):
  container = ForeignKeyField(Container)
  key = CharField(index=True)
  value = CharField()

  class Meta:
    database = db
    indexes = (
      # A team name must be unique within an organization
      (('container', 'key'), True),
    )


all_models = [Component, ComponentField, Container, ContainerField]


def _initialze_db():
  for model in sort_models_topologically(all_models):
    try:
      model.select().get()
    except OperationalError as exc:
      model.create_table()
    except DoesNotExist:
      pass


def db_access(to_wrap):
  @wraps(to_wrap)
  def wrapper(*args, **kwargs):
    _initialze_db()

    try:
      return to_wrap(*args, **kwargs)
    finally:
      if not db.is_closed():
        db.close()

  return wrapper


def getContainerStatus(container):
  """ Returns the status code of the given container. """
  return _getContainerField(container, 'status', default='unknown')


def setContainerStatus(container, status):
  """ Sets the status code for the given container. """
  _setContainerField(container, 'status', status)


@db_access
def getContainerComponent(container):
  """ Returns the component that owns the given container. """
  container_record = _upsertContainerRecord(container)
  return container_record.component and container_record.component.name


@db_access
def setContainerComponent(container, component_name):
  """ Sets the component code for the given container. """
  component = _upsertComponentRecord(component_name)
  container_record = _upsertContainerRecord(container)
  container_record.component = component
  container_record.save()


def _getContainerId(container_or_id):
  return container_or_id['Id'] if isinstance(container_or_id, dict) else container_or_id


@db_access
def removeContainerMetadata(container):
  found = _upsertContainerRecord(container)
  found.delete_instance(recursive=True)


def _getContainerFieldRecord(container, field):
  try:
    return (ContainerField
      .select()
      .join(Container)
      .where(Container.docker_id == container, ContainerField.key == field)
      .get())
  except ContainerField.DoesNotExist:
    return None


def _upsertContainerRecord(container):
  container_id = _getContainerId(container)
  try:
    return (Container
      .select()
      .where(Container.docker_id == container_id)
      .get())
  except Container.DoesNotExist:
    return Container.create(docker_id=container_id)


@db_access
def _getContainerField(container, field, default):
  """ Returns the metadata field for the given container or the default value. """
  container_id = _getContainerId(container)
  found = _getContainerFieldRecord(container_id, field)
  return found.value if found else default


@db_access
def _setContainerField(container, field, value):
  """ Sets the metadata field for the given container. """
  container_id = _getContainerId(container)
  found = _getContainerFieldRecord(container_id, field)
  if found is not None:
    found.value = value
    found.save()
  else:
    container_record = _upsertContainerRecord(container_id)
    ContainerField.create(container=container_record, key=field, value=value)


def _upsertComponentRecord(component):
  try:
    return (Component
      .select()
      .where(Component.name == component)
      .get())
  except Component.DoesNotExist:
    return Component.create(name=component)


def _getComponentFieldRecord(component_name, field):
  try:
    return (ComponentField
      .select()
      .join(Component)
      .where(Component.name == component_name, ComponentField.key == field)
      .get())
  except ComponentField.DoesNotExist:
    return None


@db_access
def getComponentField(component_name, field, default):
  """ Returns the metadata field for the given component or the default value. """
  found = _getComponentFieldRecord(component_name, field)
  return found.value if found else default


@db_access
def setComponentField(component_name, field, value):
  """ Sets the metadata field for the given component. """
  found = _getComponentFieldRecord(component_name, field)
  if found is not None:
    found.value = value
    found.save()
  else:
    component = _upsertComponentRecord(component_name)
    ComponentField.create(component=component, key=field, value=value)
