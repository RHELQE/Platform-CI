# Copyright 2016 Red Hat Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
This module provides a very thin wrapper over the Jenkins Job Builder. It's
sole purpose is to generate instantiated job XML definitions using the JJB
'test' command.
"""

import tempfile
import os
import shutil
import subprocess


def get_job_as_xml(job, template_dir, jenkins_url=None):
    """Returns a instantiated definition of a Jenkins job in XML format.

    Args:
        job: A Jenkins Job object to be instantiated
        template_dir: A path to a directory containing job templates
        jenkins_url: A URL to the Jenkins instance which may be read
            when the XML is being created (usually to get versions
            of the plugins). If None, it will be obtained from the
            JENKINS_URL environment variable.

    Returns:
        A string with the XML definition of a Jenkins job, suitable to be
            used as an input for Jenkins API to create/update a job.

    Raises:
        KeyError: If jenkins_url is None and JENKINS_URL environment variable
            does not exist.
    """
    if jenkins_url is None:
        jenkins_url = os.environ["JENKINS_URL"]

    with JJB(template_dir, jenkins_url) as jjbuilder:
        jobxml = jjbuilder.get_job_as_xml(job)
    return jobxml


# pylint: disable=too-few-public-methods
class JJB(object):
    def __init__(self, template_dir, jenkins_url):
        self.template_dir = template_dir
        self.workdir = tempfile.mkdtemp()
        self.jenkins_url = jenkins_url
        filename = "config_file.ini"
        self.config_file = os.path.join(self.workdir, filename)

    def __enter__(self):
        for item in os.listdir(self.template_dir):
            source_path = os.path.join(self.template_dir, item)
            if os.path.isfile(source_path):
                shutil.copy(source_path, self.workdir)

        with open(self.config_file, "w") as config_file_handler:
            config_file_handler.write("[jenkins]\nurl={0}".format(self.jenkins_url))

        return self

    def __exit__(self, type_param, value, traceback):
        shutil.rmtree(self.workdir)

    def get_job_as_xml(self, job):
        with open(os.path.join(self.workdir, "%s.yaml" % job.name), "w") as job_file:
            job_file.write(job.as_yaml())

        to_execute = ["jenkins-jobs", "--conf", self.config_file, "test", self.workdir, job.name]
        jjb = subprocess.Popen(to_execute, stdout=subprocess.PIPE)
        jjb_xml = jjb.communicate()[0]
        return jjb_xml
