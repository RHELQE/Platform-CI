#!/usr/bin/python

# This script takes in a package list, a field name, and a distro.
# It then pushes logs to localhost's instance of elasticsearch
# on port 9200 for every package in the provided list that is not
# present in the name.raw bucket of localhost's elasticsearch.
# It also includes the provided distro for each said log. The field
# key for each package name is provided by the user.  Finally, it
# pushes a log depicting the percent of the packages that have coverage
# in localhost's elasticsearch instance. This script now does the same
# for the brew_name.raw field, and pushes a log for existence as well
# as nonexistence.
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

def get_pkgs(myfield):
    query = '''
    {
        "aggs" : {
            "%s" : {
                "terms" : {
                    "field": "%s", 
                    "size": 200
                }
            }
        }
    }''' % (myfield, myfield)
    local_server = httplib.HTTPConnection('localhost:9200')
    local_server.request("POST", "/ci-metrics/_search?size=0", query)
    reply = local_server.getresponse()
    json_in = reply.read()
    namesjson = json.loads(json_in)
    pkgs = []
    for name in namesjson['aggregations'][myfield]['buckets']:
        if len(name['key']) > 1:
            pkgs.append(json.dumps(name['key']).strip("\""))
    return pkgs

def num_pkgs_not_tested(myfile, distro, mykey):
    tested_pkgs = get_pkgs('name.raw')
    built_pkgs = get_pkgs('brew_name.raw')
    i = 0
    j = 0
    # Push a log with package name and distro for each package not tested/built
    with open(myfile) as f:
        for key in f.read().splitlines():
            message_out = dict()
            message_out['timestamp'] = int(time.time())*1000
            message_out['base_distro'] = distro
            if key in tested_pkgs:
                message_out[mykey.split('_', 1)[0]+'_tested'] = 'true'
                message_out[mykey.replace('_not', '_name')] = key
            else:
                i = i + 1
                message_out[mykey] = key
                message_out[mykey.split('_', 1)[0]+'_tested'] = 'false'
            if key in built_pkgs:
                message_out[mykey.split('_', 1)[0]+'_built'] = 'true'
                message_out[(mykey.replace('_tested', '') + '_built').replace('_not', '_name')] = key
            else:
                j = j + 1
                message_out[mykey.replace('_tested', '') + '_built'] = key
                message_out[mykey.split('_', 1)[0]+'_built'] = 'false'
            push_log(message_out)
    return i, j

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
    not_tested, not_built = num_pkgs_not_tested(options.myfile, options.mydistro, options.mykey)
    percent_key = options.mykey.replace('_not', '') + '_percent'
    message_out[percent_key] = (float((totalpackages - not_tested) / totalpackages * 100))
    message_out['base_distro'] = options.mydistro
    message_out['timestamp'] = int(time.time())*1000
    push_log(message_out)
    percent_key = percent_key.replace('_tested', '') + '_built'
    message_out[percent_key] = (float((totalpackages - not_built) / totalpackages * 100))
    push_log(message_out)

if __name__ == '__main__':
    main(sys.argv[1:])
