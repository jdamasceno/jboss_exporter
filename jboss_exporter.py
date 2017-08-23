#!/usr/bin/env python
import yaml
import io
import requests
import json
import re
import time
#try:
import urllib2
#except:
  # Python 3
#  import urllib.request as urllib2

from prometheus_client import start_http_server
from prometheus_client.core import GaugeMetricFamily, REGISTRY
import random
import optparse
import os
from requests.auth import HTTPDigestAuth

try:
    import json
except ImportError:
    try:
        import simplejson as json
    except ImportError, e:
        print e

with open("config.yml", 'r') as stream:
   data_loaded = yaml.load(stream)

jboss_mngmt_host = data_loaded['global']['jboss_host']
jboss_mngmt_port = data_loaded['global']['jboss_port']
jboss_mngmt_usr = data_loaded['global']['jboss_user']
jboss_mngmt_passwd = data_loaded['global']['jboss_password']
jboss_host = data_loaded['global']['jboss_host']

class JbossCollector(object):

  def collect(self):
    # The build statuses we want to export about.
    # The metrics we want to export.
    try:

        self._prometheus_metrics = {}

        if data_loaded.get('datasources', None) is not None:
           self._prometheus_metrics['jboss_datasource'] = GaugeMetricFamily('jboss_datasource',
                 'JBoss Datasource Connections', labels=["name", "attribute"])
           for ds in data_loaded['datasources']:
              add_metric_datasource(self._prometheus_metrics['jboss_datasource'], ds['name'], ds['attributes'])

        if data_loaded.get('queues', None) is not None:
           self._prometheus_metrics['jboss_queue'] = GaugeMetricFamily('jboss_queue',
                 'JBoss Queue', labels=["name", "attribute"])
           for queue in data_loaded['queues']:
              add_metric_queue(self._prometheus_metrics['jboss_queue'], queue.get('server', 'default'), queue['name'], queue['attributes'])

        if data_loaded.get('http_sessions', None) is not None:
           self._prometheus_metrics['jboss_http_sessions'] = GaugeMetricFamily('jboss_http_sessions',
                 'JBoss HTTP Sessions', labels=["app"])
           for session in data_loaded['http_sessions']:
              add_metric_http_session(self._prometheus_metrics['jboss_http_sessions'], session['app'], session['attributes'])

        if data_loaded.get('memory_heap', None) is not None:
           self._prometheus_metrics['jboss_memory_heap'] = GaugeMetricFamily('jboss_memory_heap',
                 'JBoss Memory', labels=["attribute"])
           for mem in data_loaded['memory_heap']:
              add_metric_memory(self._prometheus_metrics['jboss_memory_heap'], mem['attributes'], True)

        self._prometheus_metrics['jboss_status'] = GaugeMetricFamily('jboss_status',
                 'JBoss Status', labels=[])
        add_metric_jboss_status(self._prometheus_metrics['jboss_status'])

    except Exception as e:
        print e

    for metric in self._prometheus_metrics.values():
       yield metric

def add_metric_memory(metrics, attribute, is_heap_memory):

    stat = check_memory_usage(jboss_host, jboss_mngmt_port, jboss_mngmt_usr,jboss_mngmt_passwd, is_heap_memory)

    print stat

    for attr in attribute:
       metrics.add_metric([attr], (float(stat[attr]) / (1024 * 1024)))

def add_metric_jboss_status(metrics):

    jboss_status = check_server_status(jboss_host, jboss_mngmt_port, jboss_mngmt_usr, jboss_mngmt_passwd)

    if jboss_status is None:
        metrics.add_metric([], 0)
    else:
        metrics.add_metric([], 1)

def add_metric_datasource(metrics, ds_name, ds_attribute):

    stat = get_datasource_stats(jboss_host, jboss_mngmt_port, jboss_mngmt_usr,jboss_mngmt_passwd, False, ds_name)

    for attr in ds_attribute:
       metrics.add_metric([ds_name, attr], float(stat[attr]) )

def add_metric_http_session(metrics, app, session_attr):

    stat = get_http_sessions(app)

    for attr in session_attr:
       metrics.add_metric([app, attr], float(stat[attr]))

def add_metric_queue(metrics, hornetq_server, name, attribute):

    stat = check_queue_depth(jboss_host, jboss_mngmt_port, jboss_mngmt_usr,jboss_mngmt_passwd, hornetq_server, name)

    for attr in attribute:
       metrics.add_metric([name, attr], float(stat[attr]))

#
# TODO: Document
#
def optional_arg(arg_default):
    def func(option, opt_str, value, parser):
        if parser.rargs and not parser.rargs[0].startswith('-'):
            val = parser.rargs[0]
            parser.rargs.pop(0)
        else:
            val = arg_default
        setattr(parser.values, option.dest, val)
    return func

def numeric_type(param):
    """
    Checks parameter type
    True for float; int or null data; false otherwise

    :param param: input param to check
    """
    if ((type(param) == float or type(param) == int or param == None)):
        return True
    return False


def get_digest_auth_json(host, port, uri, user, password, payload):
    """
    HTTP GET with Digest Authentication. Returns JSON result.
    Base URI of http://{host}:{port}/management is used

    :param host: JBossAS hostname
    :param port: JBossAS HTTP Management Port
    :param uri: URL fragment
    :param user: management username
    :param password: password
    :param payload: JSON payload
    """
    try:
        url = base_url(host, port) + uri
        res = requests.get(url, params=payload, auth=HTTPDigestAuth(user, password))
        data = res.json()

        try:
            outcome = data['outcome']
            if outcome == "failed":
                print "CRITICAL - Unexpected value : %s" % data
        except KeyError: pass

        return data
    except Exception, e:
        # The server could be down; make this CRITICAL.
        print "CRITICAL - JbossAS Error:", e

def post_digest_auth_json(host, port, uri, user, password, payload):
    """
    HTTP POST with Digest Authentication. Returns JSON result.
    Base URI of http://{host}:{port}/management is used

    :param host: JBossAS hostname
    :param port: JBossAS HTTP Management Port
    :param uri: URL fragment
    :param user: management username
    :param password: password
    :param payload: JSON payload
    """
    try:
        url = base_url(host, port) + uri
        headers = {'content-type': 'application/json'}
        res = requests.post(url, data=json.dumps(payload), headers=headers, auth=HTTPDigestAuth(user, password))
        data = res.json()

        try:
            outcome = data['outcome']
            if outcome == "failed":
                print "CRITICAL - Unexpected value : %s" % data
        except KeyError: pass

        return data
    except Exception, e:
        # The server could be down; make this CRITICAL.
        print "CRITICAL - JbossAS Error:", e

def base_url(host, port):
    """
    Provides base URL for HTTP Management API

    :param host: JBossAS hostname
    :param port: JBossAS HTTP Management Port
    """
    url = "http://{host}:{port}/management".format(host=host, port=port)
    return url

def check_server_status(host, port, user, passwd):
    try:

        payload = {'operation': 'read-attribute', 'name': 'server-state'}
        res = post_digest_auth_json(host, port, "", user, passwd, payload)

        if res['result'] == "running":
            return 1
        else:
            return None

        return res
    except Exception, e:
        return handle_general_critical(e)


def get_http_sessions(app):
    try:

        payload = {'include-runtime': 'true', 'recursive':'true'}
        url = "/deployment/" + app + ".war/subsystem/web"

        data = get_digest_auth_json(jboss_host, jboss_mngmt_port, url, jboss_mngmt_usr, jboss_mngmt_passwd, payload)

        return data
    except Exception, e:
        return handle_general_critical(e)

def get_memory_usage(host, port, user, passwd, is_heap):
    try:
        payload = {'include-runtime': 'true'}
        url = "/core-service/platform-mbean/type/memory"

        data = get_digest_auth_json(host, port, url, user, passwd, payload)

        print data

        if is_heap:
            data = data['heap-memory-usage']
        else:
            data = data['non-heap-memory-usage']


        return data
    except Exception, e:
        return handle_general_critical(e)

def check_memory_usage(host, port, user, passwd, attr):

    try:
        data = get_memory_usage(host, port, user, passwd, True)

#        percent = round((float(used_heap * 100) / max_heap), 2)

        return data
    except Exception, e:
        return handle_general_critical(e)

def check_non_heap_usage(host, port, user, passwd, warning, critical, perf_data):
    warning = warning or 80
    critical = critical or 90

    try:
        used_heap = get_memory_usage(host, port, user, passwd, False, 'used')

        if used_heap is None:
            return used_heap

        max_heap = get_memory_usage(host, port, user, passwd, False, 'max')

        if max_heap is None:
            return max_heap

        percent = round((float(used_heap * 100) / max_heap), 2)

        message = "Non Heap Memory Utilization %sMB of %sMB" % (used_heap, max_heap)
        message += performance_data(perf_data, [("%.2f%%" % percent, "non_heap_usage", warning, critical)])

        return check_levels(percent, warning, critical, message)
    except Exception, e:
        return handle_general_critical(e)

def get_memory_pool_usage(host, port, user, passwd, pool_name, memory_value):
    try:
        payload = {'include-runtime': 'true', 'recursive':'true'}
        url = "/core-service/platform-mbean/type/memory-pool"

        data = get_digest_auth_json(host, port, url, user, passwd, payload)
        usage = data['name'][pool_name]['usage'][memory_value] / (1024 * 1024)

        return usage
    except Exception, e:
        return handle_general_critical(e)


def check_eden_space_usage(host, port, user, passwd, memory_pool, warning, critical, perf_data):
    warning = warning or 80
    critical = critical or 90

    try:
        used_heap = get_memory_pool_usage(host, port, user, passwd, memory_pool, 'used')
        max_heap = get_memory_pool_usage(host, port, user, passwd, memory_pool, 'max')
        percent = round((float(used_heap * 100) / max_heap), 2)

        message = "Eden_Space Utilization %sMB of %sMB" % (used_heap, max_heap)
        message += performance_data(perf_data, [("%.2f%%" % percent, "eden_space_usage", warning, critical)])

        return check_levels(percent, warning, critical, message)
    except Exception, e:
        return handle_general_critical(e)

def check_old_gen_usage(host, port, user, passwd, memory_pool, warning, critical, perf_data):
    warning = warning or 80
    critical = critical or 90

    try:
        used_heap = get_memory_pool_usage(host, port, user, passwd, memory_pool, 'used')
        max_heap = get_memory_pool_usage(host, port, user, passwd, memory_pool, 'max')
        percent = round((float(used_heap * 100) / max_heap), 2)

        message = "Old_Gen Utilization %sMB of %sMB" % (used_heap, max_heap)
        message += performance_data(perf_data, [("%.2f%%" % percent, "old_gen_usage", warning, critical)])

        return check_levels(percent, warning, critical, message)
    except Exception, e:
        return handle_general_critical(e)

def check_perm_gen_usage(host, port, user, passwd, memory_pool, warning, critical, perf_data):
    warning = warning or 90
    critical = critical or 95

    try:
        used_heap = get_memory_pool_usage(host, port, user, passwd, memory_pool, 'used')
        max_heap = get_memory_pool_usage(host, port, user, passwd, memory_pool, 'max')
        percent = round((float(used_heap * 100) / max_heap), 2)

        message = "Perm_Gen Utilization %sMB of %sMB" % (used_heap, max_heap)
        message += performance_data(perf_data, [("%.2f%%" % percent, "perm_gen_usage", warning, critical)])

        return check_levels(percent, warning, critical, message)
    except Exception, e:
        return handle_general_critical(e)

def check_code_cache_usage(host, port, user, passwd, memory_pool, warning, critical, perf_data):
    warning = warning or 90
    critical = critical or 95

    try:
    	if memory_pool == None:
    		memory_pool = 'Code_Cache'

        used_heap = get_memory_pool_usage(host, port, user, passwd, memory_pool, 'used')
        max_heap = get_memory_pool_usage(host, port, user, passwd, memory_pool, 'max')
        percent = round((float(used_heap * 100) / max_heap), 2)

        message = "Code_Cache Utilization %sMB of %sMB" % (used_heap, max_heap)
        message += performance_data(perf_data, [("%.2f%%" % percent, "code_cache_usage", warning, critical)])

        return check_levels(percent, warning, critical, message)
    except Exception, e:
        return handle_general_critical(e)

def check_gctime(host, port, user, passwd, memory_pool, warning, critical, perf_data):
    # Make sure you configure right values for your application
    warning = warning or 500
    critical = critical or 1000

    try:
        payload = {'include-runtime': 'true', 'recursive':'true'}
        url = "/core-service/platform-mbean/type/garbage-collector"
        res = get_digest_auth_json(host, port, url, user, passwd, payload)
        gc_time = res['name'][memory_pool]['collection-time']
        gc_count = res['name'][memory_pool]['collection-count']

        avg_gc_time = 0

        if gc_count > 0:
            avg_gc_time = float(gc_time / gc_count)

        message = "GC '%s' total-time=%dms count=%s avg-time=%.2fms" % (memory_pool, gc_time, gc_count, avg_gc_time)
        message += performance_data(perf_data, [("%.2fms" % avg_gc_time, "gctime", warning, critical)])

        return check_levels(avg_gc_time, warning, critical, message)
    except Exception, e:
        return handle_general_critical(e)


def check_threading(host, port, user, passwd, thread_stat_type, warning, critical, perf_data):
    warning = warning or 100
    critical = critical or 200

    try:
        if thread_stat_type not in ['thread-count', 'peak-thread-count', 'total-started-thread-count', 'daemon-thread-count']:
            return handle_general_critical("The thread statistics value type of '%s' is not valid" % thread_stat_type)

        payload = {'include-runtime': 'true'}
        url = "/core-service/platform-mbean/type/threading"

        data = get_digest_auth_json(host, port, url, user, passwd, payload)
        data = data[thread_stat_type]

        message = "Threading Statistics '%s':%s " % (thread_stat_type, data)
        message += performance_data(perf_data, [(data, "threading", warning, critical)])

        return check_levels(data, warning, critical, message)
    except Exception, e:
        return handle_general_critical(e)


def check_queue_depth(host, port, user, passwd, horneq_server, queue_name):

    try:
        if queue_name is None:
            return handle_general_critical("The queue name '%s' is not valid" % queue_name)

        payload = {'include-runtime': 'true', 'recursive':'true'}
        url = "/subsystem/messaging/hornetq-server/" + horneq_server + "/jms-queue/" + queue_name

        data = get_digest_auth_json(host, port, url, user, passwd, payload)

        return data
    except Exception, e:
        return handle_general_critical(e)

def get_datasource_stats(host, port, user, passwd, is_xa, ds_name):
    try:
        if ds_name is None:
            return handle_general_critical("The ds_name name '%s' is not valid" % ds_name)

        payload = {'include-runtime': 'true', 'recursive':'true'}
        if is_xa:
            url = "/subsystem/datasources/xa-data-source/" + ds_name + "/statistics/pool/"
        else:
            url = "/subsystem/datasources/data-source/" + ds_name + "/statistics/pool/"

        return get_digest_auth_json(host, port, url, user, passwd, payload)
    except Exception, e:
        return handle_general_critical(e)


def check_non_xa_datasource(host, port, user, passwd, ds_name, warning, critical, perf_data):
    warning = warning or 0
    critical = critical or 10

    try:
        data = get_datasource_stats(host, port, user, passwd, False, ds_name)

        message = "DataSource %s %s" % (ds_stat_type, data)
        message += performance_data(perf_data, [(data, "datasource", warning, critical)])
        return check_levels(data, warning, critical, message)
    except Exception, e:
        return handle_general_critical(e)

def check_xa_datasource(host, port, user, passwd, ds_name, warning, critical, perf_data):
    warning = warning or 0
    critical = critical or 10

    try:
        data = get_datasource_stats(host, port, user, passwd, True, ds_name)

        message = "XA DataSource %s %s" % (ds_stat_type, data)
        message += performance_data(perf_data, [(data, "xa_datasource", warning, critical)])
        return check_levels(data, warning, critical, message)
    except Exception, e:
        return handle_general_critical(e)

def build_file_name(host, action):
    # done this way so it will work when run independently and from shell
    module_name = re.match('(.*//*)*(.*)\..*', __file__).group(2)
    return "/tmp/" + module_name + "_data/" + host + "-" + action + ".data"


def ensure_dir(f):
    d = os.path.dirname(f)
    if not os.path.exists(d):
        os.makedirs(d)

def handle_general_warning(e):
    """

    :param e: exception
    """
    if isinstance(e, SystemExit):
        return e
    elif isinstance(e, ValueError):
        print "WARNING - General JbossAS Error:", e
    else:
        print "WARNING - General JbossAS warning:", e
    return None


def handle_general_critical(e):

    print "CRITICAL - General JbossAS Error:", e

    return None


def write_values(file_name, string):
    f = None
    try:
        f = open(file_name, 'w')
    except IOError, e:
        # try creating
        if (e.errno == 2):
            ensure_dir(file_name)
            f = open(file_name, 'w')
        else:
            raise IOError(e)
    f.write(string)
    f.close()
    return 0

def read_values(file_name):
    data = None
    try:
        f = open(file_name, 'r')
        data = f.read()
        f.close()
        return 0, data
    except IOError, e:
        if (e.errno == 2):
            # no previous data
            return 1, ''
    except Exception, e:
        return 2, None


def calc_delta(old, new):
    delta = []
    if (len(old) != len(new)):
        raise Exception("unequal number of parameters")
    for i in range(0, len(old)):
        val = float(new[i]) - float(old[i])
        if val < 0:
            val = new[i]
        delta.append(val)
    return 0, delta

def maintain_delta(new_vals, host, action):
    file_name = build_file_name(host, action)
    err, data = read_values(file_name)
    old_vals = data.split(';')
    new_vals = [str(int(time.time()))] + new_vals
    delta = None
    try:
        err, delta = calc_delta(old_vals, new_vals)
    except:
        err = 2
    write_res = write_values(file_name, ";" . join(str(x) for x in new_vals))
    return err + write_res, delta


if __name__ == "__main__":
  REGISTRY.register(JbossCollector())
  start_http_server(9091)
  while True: time.sleep(1)
