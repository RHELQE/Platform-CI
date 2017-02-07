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

class Parser(object):
    """
    Parser for CI_MESSAGE
    """

    CI_TYPE = None

    def __init__(self, message_in, options):
        self.message_in = message_in
        self.options = options
        self.message_out = dict()

    def handle_simple(self, key, value, retried=False):
        self.message_out[key] = value
        return True

    def handle_simple64(self, key, value, retried=False):
        self.message_out[key] = value[:64]
        return True

    def handle_simple256(self, key, value, retried=False):
        self.message_out[key] = value[:256]
        return True

    def handle_simple1024(self, key, value, retried=False):
        self.message_out[key] = value[:1024]
        return True

    def handle_digit(self, key, value, retried=False):
        if not str(value).isdigit():
            value = '-1'
        self.message_out[key] = int(value)
        return True

    def handle_ignore(self, key, value, retried=False):
        return True

    def get_docid(self):
        raise NotImplementedError()

    @classmethod
    def check_type(cls, ci_type):
        return ci_type == cls.CI_TYPE

class BrewParser(Parser):
    CI_TYPE = "brew-taskstatechange"

    time_format = re.compile(r'(\d{4})-(0[1-9]|1[0-2])-'
                              '(0[1-9]|1[0-9]|2[0-9]|3[01]) '
                              '(0[0-9]|1[0-9]|2[0-3]):'
                              '(0[0-9]|1[0-9]|2[0-9]|3[0-9]|4[0-9]|5[0-9]):'
                              '(0[0-9]|1[0-9]|2[0-9]|3[0-9]|4[0-9]|5[0-9]).'
                              '[0-9][0-9][0-9][0-9][0-9][0-9]')

    def get_name(self):
        return os.environ.get("name", None) \
                          if self.options.name is None \
                          else self.options.name

    def get_version(self):
        return os.environ.get("version", None) \
                          if self.options.version is None \
                          else self.options.version

    def get_release(self):
        return os.environ.get("release", None) \
                          if self.options.release is None \
                          else self.options.release

    def get_nvr(self):
        return "%s-%s-%s" % (self.get_name(),
                             self.get_version(),
                             self.get_release())

    def get_docid(self):
        return "%s-%s" % (self.get_nvr(),
                           str(os.environ.get("id")))

    def handle_time(self, key, value, retried=False):
        if self.time_format.match(str(value)):
            self.message_out[key] = value.replace(" ", "T")[:-7] + "Z"

    def handle_brew_task_id(self, key, value, retried=False):
        if not str(value).isdigit():
            value = '-1'
        self.message_out['brew_task_id'] = int(value)

    def parse(self, message_out):
        self.message_out = message_out
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
                  'start_ts' : self.handle_ignore,
                  'create_ts' : self.handle_ignore,
                  'completion_ts' : self.handle_ignore,
                 }

        # Add field that shows package was built in brew for
        # visualizations in kibana
        self.message_out['Brew Built'] = 'true'
        self.message_out['scratch'] = os.environ.get("scratch", None) \
                               if self.options.scratch is None else self.options.scratch
        self.message_out['target'] = os.environ.get("target", None) \
                               if self.options.target is None else self.options.target

        pdc = PDC(self.options.pdc_server)
        self.message_out['expected_archs'] = pdc.get_archs(self.get_name(),
                                                           self.get_version(),
                                                           self.get_release())
        self.message_out['nvr'] = self.get_nvr()
        if 'info' in self.message_in:
            for key, value in self.message_in['info'].items():
                if key in fields:
                    handler = fields[key]
                    handler(key, value)
                else:
                    eprint("Unexpected key: %s" % key)
        return self.message_out

class MetricsParser(Parser):
    CI_TYPE = "ci-metricsdata"

    # ISO8601 regex.  We use this for metrics timestamps
    time_format = re.compile(r'(\d{4})-(0[1-9]|1[0-2])-(0[1-9]|1[0-9]|2[0-9]|3[01])'
                              '(|[tT\s])(0[0-9]|1[0-9]|2[0-3]):'
                              '(0[0-9]|1[0-9]|2[0-9]|3[0-9]|4[0-9]|5[0-9]):'
                              '(0[0-9]|1[0-9]|2[0-9]|3[0-9]|4[0-9]|5[0-9])Z')

    def get_docid(self):
        docid = "%s-%s" % (self.message_in.get("component"),
                           str(self.message_in.get("brew_task_id")))
        return docid

    def handle_component(self, key, value, retried=False):
        if value.count('-') < 2:
            eprint("BAD NVR: %s" % value)
            self.message_out["nvr"] = value[:256]
        return True

    def handle_brew_task_id(self, key, value, retried=False):
        if str(value).isdigit():
            self.message_out[key] = int(value)
        return True

    def handle_time(self, key, value, retried=False):
        if self.time_format.match(str(value)):
            self.message_out[key] = value
        return True

    def handle_trigger(self, key, value, retried=False):
        valid_triggers = ["manual", "git", "commit", "git push",
                          "rhpkg build", "brew build"]
        if value in valid_triggers:
            self.message_out[key] = value
        return True

    def handle_build_type(self, key, value, retried=False):
        valid_build_types = ["official", "scratch"]
        if value in valid_build_types:
            self.message_out[key] = value
        return True

    def find_next_slot(self, executor):
        slot = 1
        for key in self.message_out.keys():
            if key.startswith("%s_job_" % executor):
                slot += 1
        return slot

    def handle_tests(self, key, value, retried=False):
        required_entries = ["create_time", "completion_time" ]
        valid_executors = ["beaker", "CI-OSP", "Foreman", "RPMDiff"]

        # Only be strict the first time
        if not retried:
            for req_entry in required_entries:
                if req_entry not in self.message_out:
                    return False

        for i, tester in enumerate(value):
            executor = tester["executor"]
            next_slot = self.find_next_slot(executor)
            if executor in valid_executors:
                if "job_names" in self.message_in.keys():
                    job_name = self.message_in["job_names"]
                else:
                    job_name = "DUMMY_%s" % next_slot
                if not tester["executed"].isdigit():
                    tester["executed"] = -1
                if not tester["failed"].isdigit():
                    tester["failed"] = -1
                start = self.message_out.get("create_time",
                                             "2000-01-01T00:00:00Z")
                end = self.message_out.get("completion_time",
                                            "2000-01-01T00:00:00Z")
                time_start = time.mktime(time.strptime(start, '%Y-%m-%dT%H:%M:%SZ'))
                time_end = time.mktime(time.strptime(end, '%Y-%m-%dT%H:%M:%SZ'))
                self.message_out["%s_job_%s" %
                    (executor, next_slot)] = job_name
                self.message_out["%s_arch_%s" %
                    (executor, next_slot)] = tester["arch"]
                self.message_out["%s_tests_exec_%s" %
                    (executor, next_slot)] = int(tester["executed"])
                self.message_out["%s_tests_failed_%s" %
                    (executor, next_slot)] = int(tester["failed"])
                self.message_out["%s_time_spent_%s" %
                    (executor, next_slot)] = max(int(time_end - time_start), 0)
        return True

    def parse(self, message_out):
        self.message_out = message_out
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
                  'component' : self.handle_component,
                  'brew_task_id' : self.handle_brew_task_id,
                 }

        # Add field that shows CI Testing was done for kibana visualizations
        self.message_out['CI Testing Done'] = 'true'
        # Convert message_in dict to array of tuples.
        # Items can come in any order but some handle routines
        # need data that may not have been handled yet.
        # Those routines should return False and will be
        # moved to the end of the queue to try one more time.
        message_in_list = self.message_in.items()
        retry_list = []
        while message_in_list:
            (key, value) = message_in_list.pop(0)
            if key in fields:
                handler = fields[key]
                retried = key in retry_list
                if not handler(key, value, retried=retried):
                    message_in_list.append((key, value))
                    retry_list.append(key)
        return self.message_out

class ParserManager(object):
    def __init__(self, message_in, options):
        self.options = options
        self.message_in = message_in
        self.ci_index = options.ci_index
        self.dry_run = options.dry_run
        self.debug = options.debug
        self.parser_engine = self.choose_parser_engine()
        self.docid = self.get_docid()
        es_server = options.es_server if ':' in options.es_server \
                                      else "%s:9200" % options.es_server
        self.es_server = httplib.HTTPConnection(es_server)
        self.message_out = self.get_log()

    def choose_parser_engine(self):
        ci_type = os.environ.get("CI_TYPE", None) \
                                  if self.options.ci_type is None \
                                        else self.options.ci_type
        for parser in Parser.__subclasses__():
            if parser.check_type(ci_type):
                return parser(self.message_in, self.options)

    def get_docid(self):
        return self.parser_engine.get_docid()

    def get_log(self):
        message_out = dict()
        print("GET","/%s/log/%s?pretty" % (self.ci_index, self.docid))
        self.es_server.request("GET","/%s/log/%s?pretty" % (self.ci_index, self.docid))
        res = self.es_server.getresponse()
        old_log_json = res.read()
        if res.status == 200:
            old_log = json.loads(old_log_json)
            if "_source" in old_log:
                message_out = old_log["_source"]
            else:
                eprint("Record exists, but _source missing.")
        elif res.status == 404:
                eprint("No Previous log data.")
        else:
            eprint("Failure to connect to Elastic Search Server "
                   "status:%s reason:%s" % (res.status, res.reason))
            #sys.exit(1)
        return message_out

    def parse_message(self):
        self.message_out = self.parser_engine.parse(self.message_out)

        # It is pivotal the doc has a timestamp for storing it
        if 'timestamp' not in self.message_out:
             self.message_out['timestamp'] = (int(time.time())*1000)

    def update_log(self):

        # We use nvr+brew_task_id as our elasticsearch docid
        output = json.dumps(self.message_out, indent=4)

        if self.debug:
            print("PUT /%s/log/%s" % (self.ci_index, self.get_docid()))
            print(output)

        # Push the data to elasticsearch
        if not self.dry_run:
            self.es_server.request("PUT",
                                   "/%s/log/%s" % (self.ci_index, self.get_docid()),
                                   output)
            res = self.es_server.getresponse()
            data = res.read()
            if res.status not in [200, 201]:
                eprint("Failed to Push log data to Elastic Search."
                       " Status:%s Reason:%s" % (res.status, res.reason))
                #sys.exit(1)

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
             data = res.read()
             if res.status != 201:
                 eprint("Failed to create index. Exiting..")
                 sys.exit(1)

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
    parser.add_option('--ci-type', dest='ci_type', default=None,
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
    parser.add_option('--write-docid', dest='docid_file', default=None,
                      help="Record docid in file")
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

    message_in = os.environ.get("CI_MESSAGE", None) \
                           if options.ci_message is None else options.ci_message
    message_in = json.loads(message_in)

    try:
        parser = ParserManager(message_in, options)
    except ValueError, e:
        eprint("Failed to Initialize ParserManager: %s" % str(e))
        sys.exit(1)
    except:
        eprint("Unexpected error:", sys.exc_info()[0])
        sys.exit(1)

    parser.init_index()
    parser.parse_message()
    parser.update_log()
    if options.docid_file:
        file = open(options.docid_file, 'w')
        file.write('DOCID=' + parser.docid + '\n')
        file.close()
    
if __name__ == '__main__':
    main(sys.argv[1:])
