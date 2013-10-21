# gantryd

A framework built on top of [Docker](http://docker.io) that allows for easy deployment and management of project components, with a focus on:

* Easy management of components of a project across multiple machines
* Single command updating of components with **automatic draining** and **progressive rollout**
* Ability to manage components locally, when necessary (see **gantry** below)

## Overview

**gantryd** is a distributed, etcd-based system for running, updating and managing various Docker images (known as "components") across
multiple machines.

![gantryd overview](https://docs.google.com/drawings/d/1S0P8XE9H6lxUZNyQkfAXW9uYfKnXxUrzwA23oihwXlQ/pub?w=596&amp;h=349)

**gantryd** manages the running and draining of containers, automatically updating machines *progressively* on update, and *draining* the old containers
as it goes along. A container is only shutdown when *all connections* to it have terminated (or it is manually killed). This, combined with progressive
update, allows for *continuous deployment* by simply pushing a new docker image to a repository and running `update` via `gantryd.py`.

## Progressive rollout and updating

The gantryd update process is extremely useful for careful rollout of updates:

1. A user pushes a new docker image for a repo
2. A user runs `sudo gantryd.py update myprojectname -c firstcomponent secondcomponent`
3. Via etcd, the machine(s) running gantryd detect the update
4. A *single* machine (atomically) marks that it is updating
5. The machine pulls the updated image, starts the container, verifies it works (via **gantryd** health checks) and updates the local proxy to redirect traffic to that container
6. All existing containers for that component are marked as *draining* and are automatically shutdown when there are no longer any incoming connections
7. The machine marks, via etcd, that the update succeeded and the next machine takes up the update
8. On failure, all machines leave the existing containers for the component running and the status is changed in gantryd to alert about the error

## Getting Started

### Getting etcd

The latest etcd release is available as a binary at [Github][github-release].

[github-release]: https://github.com/coreos/etcd/releases/

### Cloning the source

```sh
git clone https://github.com/devtable/gantryd
```

### Setting up

All settings for gantry are contained in a JSON file named `.gantry`, placed in the same location as the Python source.

The `.gantry` file defines the various components of the project you want to manage:
```json
{
  "components": [
    {
       "name": "someexamplecomponent",
       "repo": "my/localrepo",
       "tag": "latest",
       "command": ["/usr/bin/python", "/somedir/myapplication.py"],
       "ports": [
	         {"external": 8888, "container": 8888}
       ],
       "readyChecks": [
	         { "kind": "http", "port": 8888 }
       ]
    }
  ]
}
```

| Field        | Description                                                                     | Default |
| ------------ | ------------------------------------------------------------------------------- | ------- |
| name         | The name of the component                                                       |         |
| repo         | The docker to use for the component's image                                     |         |
| tag          | The tag of the docker image to use                                              | latest  |
| command      | The command to run inside the container                                         |         |
| ports        | Mappings of container ports to external ports                                   |         |
| readyChecks  | The various checks to run to ensure the container is ready (see below for list) |         |


## gantryd

**gantryd** is a distributed tool which uses **etcd** to manage running components on a fleet of machines.

### Setting up a project

#### Creating/updating the project's configuration

To setup a gantryd project, make sure that etcd is running, and a `.gantry` file is ready.

Run the following to update the configuration for project `myprojectname` in gantryd:
```sh
sudo ./gantryd.py setconfig myprojectname .gantry
```

Response:
```sh
Configuration updated
```

#### Marking components as ready

To mark one or more components as ready for deployment, execute the following from a machine with the latest images:
```sh
sudo ./gantryd.py update myprojectname -c firstcomponent secondcomponent
```

Response:
```sh
Updating the image IDs on components
Component firstcomponent -> 4ae76210a4fe
Component secondcomponent -> 0cf0c034fc89
```

#### Running gantryd on machines

gantryd can be run on any number of machines that share an etcd. To run one (or more) components on a machine, simply run:

```sh
sudo ./gantryd.py run myprojectname -c firstcomponent secondcomponent
```

The gantryd process will block and react to all commands for those components in the future.


#### Gantryd commands

##### Updating a component across all listening machines
```sh
sudo ./gantryd.py update myprojectname -c firstcomponent secondcomponent
```

Response:
```sh
Updating the image IDs on components
Component firstcomponent -> 4ae76210a4fe
Component secondcomponent -> 0cf0c034fc89
```

##### Listing the status of all components
```sh
sudo ./gantryd.py list myprojectname
```

Response:
```sh
COMPONENT            STATUS               IMAGE ID
firstcomponent       ready                4ae76210a4fe
secondcomponent      stopped              0cf0c034fc89
```

##### Stopping a component on all machines
```sh
sudo ./gantryd.py stop myprojectname -c firstcomponent secondcomponent
```

Response:
```sh
Marking components as stopped
```

##### Killing a component on all machines
```sh
sudo ./gantryd.py kill myprojectname -c firstcomponent secondcomponent
```

Response:
```sh
Marking components as killed
```

### Gantryd health checks

Gantryd supports a number of built-in checks for verifying that a container is properly started and running.

#### http Health Check

```json
{ "kind": "http", "port": 8888 }
```

Attempts to connect and download the HTTP page located at the given port. Fails if the HTTP response is not 200.

#### tcp Health Check

```json
{ "kind": "tcp", "port": 8888 }
```

Attempts to connect to the given port via TCP. Fails if the connection cannot be established.


## gantry

**gantry** is the local version of **gantryd**, intended for starting, stopping and updating of components on a *single* machine.

### Listing all containers running on a local machine for a component
```sh
sudo ./gantry.py list firstcomponent
```

Response:
```sh
CONTAINER ID         UPTIME               IMAGE ID             STATUS              
39d59e26ee64         Up 17 seconds        my/image:latest      running
18182e07ade1         Up 2 minutes         0cf0c034fc89         draining
87b14f60b220         Up 4 minutes         26c8cb358b9d         draining
```

### Performing a *local* update of a component

*Note*: This will occur outside of the gantryd event loop, so this should *only* be used for **single-machine** or **canary** images.

```sh
sudo ./gantry.py update firstcomponent
```

Response:
```sh
Starting container 39d59e26ee64
Waiting for health checks...
Running health check: http
Checking HTTP address: http://localhost:49320
Redirecting traffic to new container
Checking container statuses...
Updating proxy...
Starting monitoring...
Monitor check started
```

### Stopping all containers running on a local machine for a component

*Note*: This will *drain* containers in a safe way, so the process will block until all containers are free from incoming connections

```sh
sudo ./gantry.py stop firstcomponent
```

Response:
```sh
Draining all containers...
Checking container statuses...
Updating proxy...
Starting monitoring...
Monitor check started
Shutting down container: 39d59e26ee64
Proxy updated
```

### Killing all containers running on a local machine for a component
```sh
sudo ./gantry.py kill firstcomponent
```

Response:
```sh
Draining all containers...
Killing container d05d73bc6c3
Checking container statuses...
Shutting down proxy...
```