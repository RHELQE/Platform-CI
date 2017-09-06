#!/usr/bin/python

# This script takes in a package list, a field name, and a distro.
# It then pushes logs to localhost's instance of elasticsearch
# on port 9200 for every package in the provided list that is not
# present in the name.raw bucket of localhost's elasticsearch.
# It also includes the provided distro for each said log. The field
# key for each package name is provided by the user.  Finally, it
# pushes a log depicting the percent of the packages that have coverage
# in localhost's elasticsearch instance.
# Author: Johnny Bieren <jbieren@redhat.com>

from __future__ import division
from optparse import OptionParser
import json
import sys
import httplib
import time

def line_count(myfile):
    i = 0
    with open(myfile) as f:
        for i in enumerate(f, 1):
            pass
    return(i[0])

def num_pkgs_not_tested(myfile, distro, mykey):
    query = '''
    {
        "aggs" : {
            "name.raw" : {
                "terms" : {
                    "field": "name.raw", 
                    "size": 200
                }
            }
        }
    }'''
    i = 0
    local_server = httplib.HTTPConnection('localhost:9200')
    local_server.request("POST", "/ci-metrics/_search?size=0", query)
    reply = local_server.getresponse()
    json_in = reply.read()
    namesjson = json.loads(json_in)
    tested_pkgs = []
    for name in namesjson['aggregations']['name.raw']['buckets']:
        if len(name['key']) > 1:
            tested_pkgs.append(json.dumps(name['key']).strip("\""))
    # Push a log with package name and distro for each package not tested
    with open(myfile) as f:
        for key in f.read().splitlines():
            if key not in tested_pkgs:
                i = i + 1
                message_out = dict()
                message_out[mykey] = key
                message_out['timestamp'] = int(time.time())*1000
                message_out['base_distro'] = distro
                message_out['CI Testing Done'] = 'false'
                push_log(message_out)
    return i

def push_log(mymessage):
    output = json.dumps(mymessage, indent=4)
    local_server = httplib.HTTPConnection('localhost:9200')
    local_server.request("POST", "/ci-metrics/log/", output)
    reply = local_server.getresponse()
    data = reply.read()
    if reply.status not in [200, 201]:
        print("Failed to push log data to Elastic Search."
              " Status:%s Reason:%s" % (reply.status, reply.reason))

def main(args):
    if sys.version_info < (2,5):
        eprint("Python 2.5 or better is required.")
        sys.exit(1)

    # Parse the command line args
    usage = 'usage: %prog'
    parser = OptionParser()
    parser.add_option('-f', '--file', dest='myfile', default=None,
                      help='File in $pwd containing list of packages to compare with')
    parser.add_option('-d', '--distro', dest='mydistro', default=None,
                      help='Distro to populate base_distro with in logs')
    parser.add_option('-k', '--key', dest='mykey', default=None,
                      help='Field key name to use to store the untested package name in elasticsearch')

    options, arguments = parser.parse_args(args)

    if options.myfile is None or options.mydistro is None or options.mykey is None:
        print("You must provide a package file and a distro.")
        sys.exit(1)
    
    message_out = dict()
    totalpackages = line_count(options.myfile)
    not_tested = num_pkgs_not_tested(options.myfile, options.mydistro, options.mykey)
    percent_key = options.mykey.replace('_not', '') + '_percent'
    message_out[percent_key] = (float((totalpackages - not_tested) / totalpackages * 100))
    message_out['base_distro'] = options.mydistro
    message_out['timestamp'] = int(time.time())*1000
    push_log(message_out)

if __name__ == '__main__':
    main(sys.argv[1:])
