# gantryd

A framework built on top of [Docker](http://docker.io) that allows for easy deployment and management of project components, with a focus on:

* Easy management of components of a project across multiple machines
* Single command updating of components with **automatic draining** and **progressive rollout**
* Ability to manage components locally, when necessary (see **gantry** below)

## Overview

**gantryd** is a distributed, etcd-based system for running, updating, monitoring and managing various Docker images (known as "components") across
multiple machines.

![gantryd overview](https://docs.google.com/drawings/d/1S0P8XE9H6lxUZNyQkfAXW9uYfKnXxUrzwA23oihwXlQ/pub?w=596&amp;h=349)

**gantryd** manages the running, monitoring and draining of containers, automatically updating machines *progressively* on update, and *draining* the old containers
as it goes along. A container is only shutdown when *all connections* to it have terminated (or it is manually killed). This, combined with progressive
update, allows for *continuous deployment* by simply pushing a new docker image to a repository and running `update` via `gantryd.py`.

**gantryd** also automatically monitors the containers of a component, running checks periodically to ensure they are healthy. If a container goes bad, a new one is automatically started in its place, with traffic being moved over.

## Getting Started

### Getting etcd

The latest etcd release is available as a binary at [Github][github-release].
Installation instructions can be found at [Etcd README][etcd-readme].

[github-release]: https://github.com/coreos/etcd/releases/
[etcd-readme]: https://github.com/coreos/etcd/blob/master/README.md


### Cloning the source

```sh
git clone https://github.com/DevTable/gantryd.git
```

### Installing dependencies

#### Debian or Ubuntu
```sh
# Install apt-get dependencies.
cat requirements.system | xargs sudo apt-get install -y

# Install python dependencies.
sudo pip install -r requirements.txt
```

#### RHEL or Centos
```sh
# Install yum dependencies.
cat requirements.system.rhel | xargs sudo yum install -y

# Install python dependencies.
sudo pip install -r requirements.txt
```

### Setting up

All settings for gantryd are defined in a JSON format. A project's configuration is stored in etcd but is set initially from a local file (see `setconfig` below).

The configuration defines the various components of the project you want to manage:
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
       ],
       "healthChecks": [
         { "kind": "http", "port": 8888, "path": "/some/path" }
       ],
       "volumesFrom": [
         "somedatacontainer"
       ],
       "bindings": [
         { "external": "/an/external/path", "volume": "/some/container/path"}
       ],
       "defineComponentLinks": [
         { "port": 8888, "name": "mycoolserver", "kind": "tcp" }
       ],
       "requireComponentLinks": [
         { "name": "anotherserver", "alias": "serveralias" }
       ],
       "environmentVariables": [
         { "name": "FOO", "value": "somevalue" }
       ]
    }
  ]
}
```

| Field                 | Description                                                                       | Default     |
| --------------------- | --------------------------------------------------------------------------------- | ----------- |
| name                  | The name of the component                                                         |             |
| repo                  | The docker image to use for the component                                         |             |
| tag                   | The tag of the docker image to use                                                | latest      |
| user                  | The user under which to run the command in the container                          | (in image)  |
| command               | The command to run inside the container                                           | (in image)  |
| ports                 | Mappings of container ports to external ports                                     |             |
| readyChecks           | The various checks to run to ensure the container is ready (see below for list)   |             |
| healthChecks          | The various checks to run to ensure the container is healthy (see below for list) |             |
| terminationSignals    | Signals which should be sent to a specific container when it should be shut down  |             |
| terminationChecks     | The various checks to run to ensure that the container is ready to be shut down   | connections |
| volumesFrom           | Container(s), by name, whose volume(s) should be mounted into the container       |             |
| bindings              | Mapping between external hosts paths and the corresponding container volumes      |             |
| defineComponentLinks  | Defines the component links exported by this component                            |             |
| requireComponentLinks | Defines the component links imported/required by this component                   |             |
| readyTimeout          | Timeout in milliseconds that we will wait for a container to pass a ready check   | 10,000      |
| environmentVariables  | Environment variables to set when running the component's containers              |             |
| privileged            | Whether the container should run in privileged mode                               | False       |

### Terminology

**Project**: Namespace that contains configuration for a set of components, as well as any metadata associated
when those components are running. For example: 'frontend', 'backend', 'someproduct'.

**Component**: A named component that runs a specific docker image in a container. For example: 'elasticsearch', 'mongodb'.

**Component Link**: Similar to a Docker link: An exposed port by one *component* that is imported by one or more other 
components. Unlike a Docker link, a component link is managed by gantry and automatically updated via the proxy just link
normal exposed ports. When a component link is required/imported by a container, the following environment variables are
added into the containers for that component:

| Environment Variable              | Example Name                        | Example Value                                     |
| --------------------------------- | ----------------------------------- | ------------------------------------------------- |
| {ALIAS}_CLINK                     | SERVERALIAS_CLINK                   | tcp://172.17.42.1:53852                           |
| {ALIAS}\_CLINK\_{PORT}\_{KIND}       | SERVERALIAS_CLINK_8888_TCP          | tcp://172.17.42.1:53852                           |
| {ALIAS}\_CLINK\_{PORT}\_{KIND}\_PROTO | SERVERALIAS_CLINK_8888_TCP_PROTO    | tcp                                               |
| {ALIAS}\_CLINK\_{PORT}\_{KIND}\_ADDR  | SERVERALIAS_CLINK_8888_TCP_ADDR     | 172.17.42.1                                       |
| {ALIAS}\_CLINK\_{PORT}\_{KIND}\_PORT  | SERVERALIAS_CLINK_8888_TCP_PORT     | 53852                                             |


### Setting up a project

- [Gantryd commands](#gantryd-commands) - distributed management
- [Gantry commands](#gantry-commands) - local management

### <a name="gantryd"></a>Gantryd commands

#### Creating/updating the project's configuration

To setup a gantryd project, make sure that etcd is running, and gantry configuration is avaliable in some file.

Run the following to update the configuration for project `myprojectname` in gantryd:
```sh
sudo ./gantryd.py setconfig myprojectname myconfigfile
```

Response:
```sh
Configuration updated
```

#### Setup components by 'updating' them

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

This sets the status of the components to 'ready' and associates them with the image IDs listed. Once run, any followup
`gantryd run` commands on this machine (or any other machines in the etcd cluster) will update and start those components
with those images.

#### Running components on machine(s)

Once components have been marked as ready, they can be run by executing `gantryd run` on one or more machines:

```sh
sudo ./gantryd.py run myprojectname -c firstcomponent secondcomponent
```

This command will start a daemon (and block), starting the components and monitoring them, until it is shutdown.

#### Updating a component across all listening machines

To tell components to update themselves in response to an image change, execute:

```sh
sudo ./gantryd.py update myprojectname -c firstcomponent secondcomponent
```

Response:
```sh
Updating the image IDs on components
Component firstcomponent -> 4ae76210a4fe
Component secondcomponent -> 0cf0c034fc89
```

The first machine running the gantryd daemon will start the update within 30 seconds.

### Listing the status of all components
```sh
sudo ./gantryd.py list myprojectname
```

Response:
```sh
COMPONENT            STATUS               IMAGE ID
firstcomponent       ready                4ae76210a4fe
secondcomponent      stopped              0cf0c034fc89
```

#### Stopping a component on all machines

To tell components to stop themselves on all machines, execute:

```sh
sudo ./gantryd.py stop myprojectname -c firstcomponent secondcomponent
```

Response:
```sh
Marking components as stopped
```

All components specified will start the shutdown process within 30 seconds.

#### Killing a component on all machines

To order components to kill themselves immediately on all machines, execute:

```sh
sudo ./gantryd.py kill myprojectname -c firstcomponent secondcomponent
```

Response:
```sh
Marking components as killed
```

All components specified will be killed within 30 seconds.


### Gantryd health checks

Gantryd supports a number of built-in checks for verifying that a container is properly started, running and healthy.

#### http Health Check

```json
{ "kind": "http", "port": 8888, "path": "/somepath" }
```

Attempts to connect and download the HTTP page located at the given port and path. Fails if the HTTP response is not 2XX. 

Note that "path" is **optional**.

#### tcp Health Check

```json
{ "kind": "tcp", "port": 8888 }
```

Attempts to connect to the given port via TCP. Fails if the connection cannot be established.


###<a name="gantry"></a>Gantry commands

**gantry** is the **local** version of gantry, intended for starting, stopping and updating of components on a **single** machine. Please note that you don't need etcd to be installed (or running) to use **gantry**.

#### Listing all containers running on a local machine for a component
```sh
sudo ./gantry.py myconfigfile list firstcomponent
```

Response:
```sh
CONTAINER ID         UPTIME               IMAGE ID             STATUS              
39d59e26ee64         Up 17 seconds        my/image:latest      running
18182e07ade1         Up 2 minutes         0cf0c034fc89         draining
87b14f60b220         Up 4 minutes         26c8cb358b9d         draining
```

#### Performing a *local* update of a component

*Note*: This will occur outside of the gantryd event loop, so this should *only* be used for **single machine** or **canary** images.

```sh
sudo ./gantry.py myconfigfile update firstcomponent
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

*Note*: If the `-m` flag is specified, then gantry will remain running and actively monitor the component's container, restarting it automatically if it becomes unhealthy.

#### Stopping all containers running on a local machine for a component

*Note*: This will *drain* containers in a safe way, so the process will block until all containers are free from incoming connections

```sh
sudo ./gantry.py myconfigfile stop firstcomponent
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

#### Killing all containers running on a local machine for a component
```sh
sudo ./gantry.py myconfigfile kill firstcomponent
```

Response:
```sh
Draining all containers...
Killing container d05d73bc6c3
Checking container statuses...
Shutting down proxy...
```
