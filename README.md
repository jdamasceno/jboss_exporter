# JBoss Prometheus Exporter

A JBoss metrics exporter to prometheus based on python client

### Prerequisites

Tested on Python 2.7.* and JBoss EAP 6.4.x

### Installing

You can use pip to install the dependencies

```
pip install requests
```
```
pip install prometheus_client
```
```
pip install pyyaml
```

## Configuration

You need to create a file called 'config.yml' on the same folder level of the python script
A sample configuration file:

```
global:
   jboss_host: jboss_host
   jboss_port: 9990
   jboss_user: jboss_mgnt_user
   jboss_password: jboss_mgnt_passwd

datasources:
    - name: ds_name_1
      attributes: [InUseCount, ActiveCount]
    - name: ds_name_2
      attributes: [InUseCount, ActiveCount]

queues:
    - name: queue_name_1
      attributes: [message-count]
    - name: queue_name_2
      attributes: [message-count]

http_sessions:
    - app: app_name_1
      attributes: [active-sessions]
    - app: app_name_1
      attributes: [active-sessions]
```

## Authors

* **Juan Damasceno** - (https://github.com/jdamasceno)

## License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details

