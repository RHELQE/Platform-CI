#!/usr/bin/env python
from __future__ import print_function
import sys
import os
import json
import re
import time
import numbers
import dateutil.parser as dp
import httplib
import unittest
from optparse import OptionParser

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

class PDC:
    def __init__(self, pdc_server):
        self.pdc_server = None
        if pdc_server is not None:
            self.pdc_server = httplib.HTTPSConnection(pdc_server)

    def get_archs(self, name, version, release):
        expected_archs = ''
        if self.pdc_server is not None:
            # Look up package by NVR in the PDC
            self.pdc_server.request("GET","/rest_api/v1/rpms/?name=^%s$"
                                          "&version=^%s$&release=^%s$" % 
                                           (name, version, release))
            res = self.pdc_server.getresponse()
            if res.status != 200:
                eprint("Failed to find %s-%s-%s in PDC" %
                                               (name, version, release))
            pdc_message = res.read()
            pdc_parsed = json.loads(pdc_message)
            # If results isnt there, NVR was not in PDC
            # Can add else and sys.exit later
            # This adds the archs we expect to test for this nvr
            if 'results' in pdc_parsed:
                 for id in pdc_parsed['results']:
                      if id['arch'] != 'src':
                           expected_archs = expected_archs + id['arch'] + ' '
                 expected_archs = expected_archs[:-1]
        return expected_archs

class CIHandler:
    def __init__(self, es_server=None, pdc_server=None,
                 ci_index=None, ci_type=None, ci_message=None,
                 scratch=None, name=None, version = None,
                 release=None, target=None, dry_run=False,
                 debug=False):
        es_server = es_server if ':' in es_server else "%s:9200" % es_server
        self.es_server = httplib.HTTPConnection(es_server)
        self.pdc_server = pdc_server
        self.ci_index = ci_index
        self.ci_type = os.environ.get("CI_TYPE", None) \
                               if ci_type is None else ci_type
        ci_message = os.environ.get("CI_MESSAGE", None) \
                               if ci_message is None else ci_message
        self.ci_message = json.loads(ci_message)
        self.scratch = os.environ.get("scratch", None) \
                               if scratch is None else scratch
        self.name = os.environ.get("name", None) \
                               if name is None else name
        self.version = os.environ.get("version", None) \
                               if version is None else version
        self.release = os.environ.get("release", None) \
                               if release is None else release
        self.target = os.environ.get("target", None) \
                               if target is None else target
        self.dry_run = dry_run
        self.debug = debug
        self.output = dict()

    def init_index(self):
        # This template is for elasticsearch and allows timestamp to be your time field
        # It also adds the .raw fields so you can use the fields to create visualizations in kibana
        indextemplate = '''
        {
            "mappings": {
                "log": {
                    "properties": {
                        "timestamp": {
                            "type": "date"
                        }
                    }, 
                    "dynamic_templates": [
                        {
                            "message_field": {
                                "match_mapping_type": "string", 
                                "mapping": {
                                    "index": "analyzed", 
                                    "type": "string", 
                                    "omit_norms": true
                                }, 
                                "match": "message"
                            }
                        }, 
                        {
                            "string_fields": {
                                "match_mapping_type": "string", 
                                "mapping": {
                                    "index": "analyzed", 
                                    "type": "string", 
                                    "fielddata": {
                                        "format": "disabled"
                                    }, 
                                    "fields": {
                                        "raw": {
                                            "index": "not_analyzed", 
                                            "type": "string", 
                                            "doc_values": true
                                        }
                                    }, 
                                    "omit_norms": true
                                }, 
                                "match": "*"
                            }
                        }
                    ]
                }
            }
        }'''

        self.es_server.request("GET","/_cat/indices?v")
        res = self.es_server.getresponse()
        if res.status != 200:
            eprint("Failed to get list of indexes. Exiting..")
            sys.exit(1)
        indexes = res.read()
        # If the index is not on the host yet put it there
        if not self.dry_run and self.ci_index not in indexes:
             self.es_server.request("PUT", "/%s?pretty" % self.ci_index,
                                    indextemplate)
             res = self.es_server.getresponse()
             if res.status != 201:
                 eprint("Failed to create index. Exiting..")
                 sys.exit(1)

    def process(self):
        parser = None
        if self.ci_type == 'brew-taskstatechange':
            parser = BrewParser()
            parser.parse(self.ci_message)
            self.output = parser.message
            self.output['nvr'] = "%s-%s-%s" % (self.name,
                                               self.version,
                                               self.release)

            # Add field that shows package was built in brew for
            # visualizations in kibana
            self.output['Brew Built'] = 'true'
            if self.scratch:
                self.output['scratch'] = self.scratch
            if self.target:
                self.output['target'] = self.target
            pdc = PDC(self.pdc_server)
            self.output['expected_archs'] = pdc.get_archs(self.name,
                                                          self.version,
                                                          self.release)
            # It is pivotal the doc has a timestamp for storing it
            if 'timestamp' not in self.output.keys():
                 self.output['timestamp'] = (int(time.time())*1000)

        elif self.ci_type == 'ci-metricsdata':
            if "component" in self.ci_message:
                component = MetricsParser.handle_component(self.ci_message["component"])
            if "brew_task_id" in self.ci_message:
                brew_task_id = MetricsParser.handle_brew_task_id(self.ci_message["brew_task_id"])
            message = dict()
            docid = "%s-%s" % (component, brew_task_id)

            self.es_server.request("GET","/%s/log/%s?pretty" % (self.ci_index, docid))
            res = self.es_server.getresponse()
            if res.status == 200:
                old_log_json = res.read()
                old_log = json.loads(old_log_json)
                if "_source" in old_log:
                    message = old_log["_source"]
                else:
                    eprint("No Previous log data.")
            else:
                eprint("Failure to connect to Elastic Search Server"
                       "status:%s reason:%s" % (res.status, res.reason))
                sys.exit(1)

            parser = MetricsParser(message)
            parser.parse(self.ci_message)
            self.output = parser.message
            # Add field that shows CI Testing was done for kibana visualizations
            self.output['CI Testing Done'] = 'true'
        else:
            eprint("Unknown ci_type:%s" % self.ci_type)
            sys.exit(1)

        # We use nvr+brew_task_id as our elasticsearch docid
        output = json.dumps(self.output, indent=4)

        if self.debug:
            print("PUT /%s/log/%s" % (self.ci_index, parser.get_docid()))
            print(output)

        # Push the data to elasticsearch
        if not self.dry_run:
            self.es_server.request("PUT",
                                   "/%s/log/%s" % (self.ci_index, parser.get_docid()),
                                   output)
            res = self.es_server.getresponse()
            if res.status != 201:
                eprint("Failed to Push log data to Elastic Search."
                       " Status:%s Reason:%s" % (res.status, res.reason))
                sys.exit(1)

class Parser:
    """
    Parser for CI_MESSAGE
    """

    def __init__(self):
        self.message = dict()

    def get_docid(self):
        docid = ""
        if "nvr" in self.message and "brew_task_id" in self.message:
            docid = "%s-%s" % (self.message['nvr'], str(self.message['brew_task_id']))
        return docid

    def handle_simple(self, key, value, ci_message=None):
        self.message[key] = value

    def handle_simple64(self, key, value, ci_message=None):
        self.message[key] = value[:64]

    def handle_simple256(self, key, value, ci_message=None):
        self.message[key] = value[:256]

    def handle_simple1024(self, key, value, ci_message=None):
        self.message[key] = value[:1024]

    def handle_digit(self, key, value, ci_message=None):
        if not str(value).isdigit():
            value = '-1'
        self.message[key] = int(value)

    def handle_ignore(self, key, value, ci_message=None):
        pass

class BrewParser(Parser):
    brew_time_format = re.compile(r'(\d{4})-(0[1-9]|1[0-2])-'
                                   '(0[1-9]|1[0-9]|2[0-9]|3[01]) '
                                   '(0[0-9]|1[0-9]|2[0-3]):'
                                   '(0[0-9]|1[0-9]|2[0-9]|3[0-9]|4[0-9]|5[0-9]):'
                                   '(0[0-9]|1[0-9]|2[0-9]|3[0-9]|4[0-9]|5[0-9]).'
                                   '[0-9][0-9][0-9][0-9][0-9][0-9]')
    def handle_time(self, key, value, ci_message=None):
        if self.brew_time_format.match(str(value)):
            value = value.replace(" ", "T")[:-7] + "Z"
        else:
            value = 'TIME_NOT_VALID'
        self.message[key] = value

    def handle_brew_task_id(self, key, value, ci_message=None):
        if not str(value).isdigit():
            value = '-1'
        self.message['brew_task_id'] = int(value)

    def parse(self, ci_message):
        fields = {'weight' : self.handle_simple,
                  'parent' : self.handle_simple,
                  'channel_id' : self.handle_digit,
                  'request' : self.handle_ignore,
                  'start_time' : self.handle_time,
                  'waiting' : self.handle_simple,
                  'awaited' : self.handle_simple,
                  'label' : self.handle_simple,
                  'priority' : self.handle_digit,
                  'completion_time' : self.handle_time,
                  'state' : self.handle_digit,
                  'create_time' : self.handle_time,
                  'owner' : self.handle_simple,
                  'host_id' : self.handle_digit,
                  'method' : self.handle_simple,
                  'arch' : self.handle_simple,
                  'id' : self.handle_brew_task_id,
                  'result' : self.handle_simple,
                 }

        if ci_message and 'info' in ci_message:
            for key, value in ci_message['info'].items():
                if key in fields:
                    handler = fields[key]
                    handler(key, value)
                else:
                    eprint("Unexpected key: %s" % key)

class MetricsParser(Parser):

    def __init__(self, message=dict()):
        self.message = message
        
    # ISO8601 regex.  We use this for metrics timestamps
    iso8601 = re.compile(r'(\d{{4}})-(0[1-9]|1[0-2])-(0[1-9]|1[0-9]|2[0-9]|3[01])'
                          '(|[tT\s])(0[0-9]|1[0-9]|2[0-3]):'
                          '(0[0-9]|1[0-9]|2[0-9]|3[0-9]|4[0-9]|5[0-9]):'
                          '(0[0-9]|1[0-9]|2[0-9]|3[0-9]|4[0-9]|5[0-9])Z')

    @classmethod
    def handle_component(cls, value):
        if value.count('-') < 2:
            eprint("BAD NVR: %s" % value)
            return False
        else:
            return value[:256]

    @classmethod
    def handle_brew_task_id(cls, value):
        if str(value).isdigit():
            return value
        else:
            return False

    def handle_time(self, key, value, ci_message=None):
        if not self.iso8601.match(str(value)):
            value = 'TIME_NOT_ISO8601'
        self.message[key] = value

    def handle_trigger(self, key, value, ci_message=None):
        valid_triggers = ["manual", "git", "commit", "git push",
                          "rhpkg build", "brew build"]
        if value in valid_triggers:
            self.message[key] = value

    def handle_build_type(self, key, value, ci_message=None):
        valid_build_types = ["official", "scratch"]
        if value in valid_build_types:
            self.message[key] = value

    def find_next_slot(self, executor):
        slot = 1
        for key in self.message.keys():
            if key.startswith("%s_job_" % executor):
                slot += 1
        return slot

    def handle_tests(self, key, value, ci_message=None):
        valid_executors = ["beaker", "ciosp"]
        for i, tester in enumerate(value):
            executor = tester["executor"]
            next_slot = self.find_next_slot(executor)
            if executor in valid_executors:
                if "job_names" in ci_message.keys():
                    job_name = ci_message["job_names"]
                else:
                    job_name = "DUMMY_%s" % next_slot
                if not tester["executed"].isdigit():
                    tester["executed"] = -1
                if not tester["failed"].isdigit():
                    tester["failed"] = -1
                self.message["%s_job_%s" %
                    (executor, next_slot)] = job_name
                self.message["%s_arch_%s" %
                    (executor, next_slot)] = tester["arch"]
                self.message["%s_tests_exec_%s" %
                    (executor, next_slot)] = int(tester["executed"])
                self.message["%s_tests_failed_%s" %
                    (executor, next_slot)] = int(tester["failed"])

    def parse(self, ci_message):
        fields = {'trigger' : self.handle_trigger,
                  'tests' : self.handle_tests,
                  'jenkins_job_url' : self.handle_simple,
                  'base_distro' : self.handle_simple256,
                  'compose_id' : self.handle_digit,
                  'create_time' : self.handle_time,
                  'completion_time' : self.handle_time,
                  'CI_infra_failure' : self.handle_simple,
                  'CI_infra_failure_desc' : self.handle_simple1024,
                  'job_names' : self.handle_simple256,
                  'CI_tier' : self.handle_digit,
                  'build_type' : self.handle_build_type,
                  'owner' : self.handle_simple64,
                  'content-length' : self.handle_simple,
                  'destination' : self.handle_simple,
                  'expires' : self.handle_simple,
                  'xunit_links' : self.handle_simple,
                  'jenkins_build_url' : self.handle_simple,
                 }

        for key, value in ci_message.items():
            if key in fields:
                handler = fields[key]
                handler(key, value, ci_message=ci_message)

class ParseCIMetricTests(unittest.TestCase):
    def test_ci_message(self):
        ci_message = """
                        CI_MESSAGE={
                          "create_time": "",
                          "tests": [{"executor": "beaker", "arch": "", "executed": "60", "failed": "5"}],
                          "CI_tier": "1",
                          "owner": "",
                          "build_type": "",
                          "base_distro": "",
                          "completion_time": "",
                          "component": "kernel-3.10.0-547.el7",
                          "jenkins_job_url": "https://platform-stg-jenkins.rhev-ci-vms.eng.rdu2.redhat.com/job/kernel-general-rhel-kmod/",
                          "jenkins_build_url": "https://platform-stg-jenkins.rhev-ci-vms.eng.rdu2.redhat.com/job/kernel-general-rhel-kmod/272/",
                          "brew_task_id": "12388882",
                          "job_names": "kernel-general-rhel-kmod",
                          "xunit_links": ""
                        }
                     """

class ParseBrewTests(unittest.TestCase):
    def test_ci_message(self):
        ci_message = """
                        CI_MESSAGE={
                          "info" : {
                            "weight" : 0.2,
                            "parent" : null,
                            "channel_id" : 11,
                            "request" : [ "git://pkgs.devel.redhat.com/rpms/rubygem-listen?#1b2b703f6dee462008410ec22d4733667e04f349", "rhscl-2.4-rh-ror50-rhel-7-candidate", { } ],
                            "start_time" : "2017-01-19 14:25:47.326395",
                            "start_ts" : 1.4848359473264E9,
                            "waiting" : false,
                            "awaited" : null,
                            "label" : null,
                            "priority" : 20,
                            "completion_time" : "2017-01-19 14:33:43.34485",
                            "state" : 2,
                            "create_time" : "2017-01-19 14:25:45.150925",
                            "create_ts" : 1.48483594515092E9,
                            "owner" : "jaruga",
                            "host_id" : 90,
                            "method" : "build",
                            "completion_ts" : 1.48483642334485E9,
                            "arch" : "noarch",
                            "id" : 12399412,
                            "result" : null
                          },
                          "attribute" : "state",
                          "old" : "OPEN",
                          "new" : "CLOSED",
                          "rpms" : {
                            "noarch" : [ "rh-ror50-rubygem-listen-3.1.5-1.el7.noarch.rpm", "rh-ror50-rubygem-listen-3.1.5-1.el7.src.rpm", "rh-ror50-rubygem-listen-doc-3.1.5-1.el7.noarch.rpm" ]
                          }
                        }
                     """

def main(args):
    if sys.version_info < (2,5):
        eprint("Python 2.5 or better is required.")
        sys.exit(1)

    # Parse the command line args
    usage = 'usage: %prog'
    parser = OptionParser()
    parser.add_option('-e', '--elastic', dest='es_server', default=None,
                      help='Elastic Search Server to use')
    parser.add_option('-p', '--pdc', dest='pdc_server', default=None,
                      help='PDC server to use')
    parser.add_option('--ci-index', dest='ci_index', default="ci-metrics",
                      help='Specify the index being processed')
    parser.add_option('--ci_type', dest='ci_type', default=None,
                      help='Specify ci_type, default will use CI_TYPE from env')
    parser.add_option('--ci_message', dest='ci_message', default=None,
                      help='Specify ci_message, default will use CI_MESSAGE from env')
    parser.add_option('--scratch', dest='scratch', default=None,
                      help='Specify if scratch build, default will use scratch from env')
    parser.add_option('--name', dest='name', default=None,
                      help='Specify name, default will use name from env')
    parser.add_option('--version', dest='version', default=None,
                      help='Specify version, default will use version from env')
    parser.add_option('--release', dest='release', default=None,
                      help='Specify release, default will use release from env')
    parser.add_option('--target', dest='target', default=None,
                      help='Specify target, default will use target from env')
    parser.add_option('-u', '--unittests', dest='unittests', action='store_true',
                      help='Run unittests')
    parser.add_option('-d', '--dry-run', dest='dry_run', action='store_true',
                      help="Don't actually do anything")
    parser.add_option('-v', '--debug', dest='debug', action='store_true',
                      help="Debug output")

    options, arguments = parser.parse_args(args)

    if options.es_server is None:
        eprint("You must specify a Elastic Search Server")
        sys.exit(1)
    try:
        ci_handler = CIHandler(es_server = options.es_server,
                               pdc_server = options.pdc_server,
                               ci_index = options.ci_index,
                               ci_type = options.ci_type,
                               ci_message = options.ci_message,
                               scratch = options.scratch,
                               name = options.name,
                               version = options.version,
                               release = options.release,
                               target = options.target,
                               dry_run = options.dry_run,
                               debug = options.debug)
    except ValueError, e:
        eprint("Failed to Initialize CIHandler: %s" % str(e))
        sys.exit(1)
    ci_handler.init_index()
    ci_handler.process()
    
if __name__ == '__main__':
    main(sys.argv[1:])
