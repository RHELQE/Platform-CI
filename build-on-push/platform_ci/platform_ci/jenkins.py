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
This module provides an interface to the Jenkins instance providing
Platform CI service.
"""

import os
import subprocess
import logging
import platform_ci.jjb
import platform_ci.config
import platform_ci.notifications as notifications


class PlatformJenkinsException(notifications.PlatformCIException):
    """Exception thrown on errors during communication with a Jenkins instance."""
    header = notifications.create_platform_error_header(notifications.HEADERS["JENKINS"])


# pylint: disable=too-few-public-methods
class PlatformJenkins(object):
    """Represents a Platform CI Jenkins instance.

    Provides methods for interacting with the Jenkins instance, mostly for job
    manipulation (create, update, delete) but also others. The class is
    basically a thin wrapper over a different, generic Jenkins API, extended
    to be aware of the Platform CI concepts.
    """
    @classmethod
    def get_jenkins(cls, url, template_dir=None):
        """Returns an instance for a given Jenkins URL.

        The returned instance is usually a instance of a PlatformJenkins
        subclass (this allows to switch to a different Jenkins API.
        """
        return PlatformJenkinsJavaCLI(template_dir, url)

    def __init__(self, jenkins, template_dir):
        self.jenkins_server = jenkins
        self.template_dir = template_dir


class PlatformJenkinsJavaCLI(PlatformJenkins):
    """Represents a Platform CI Jenkins instance, wrapping a Java CLI API.

    While ugly to wrap the Java CLI in Python like this, we had the best
    experience with using the Java CLI from all other Jenkins API options
    that we tried, especially related to authentication.

    If someone implements a replacement class over Python Jenkins API that
    *works*, it would probably be best to replace this class with it.
    """

    CLI = ["/usr/bin/java", "-jar", "/var/lib/jenkins/jenkins-cli.jar", "-noCertificateCheck"]

    GET_VIEW = "get-view"
    UPDATE_VIEW = "update-view"
    CREATE_VIEW = "create-view"

    VIEW_TEMPLATE = "view-template.xml"

    DELETE_JOB = "delete-job"
    BUILD_JOB = "build"
    CREATE_JOB = "create-job"
    UPDATE_JOB = "update-job"
    ENABLE_JOB = "enable-job"
    DISABLE_JOB = "disable-job"
    GET_JOB = "get-job"

    SET_DESCRIPTION = "set-build-description"

    def __init__(self, template_dir, url):
        super(PlatformJenkinsJavaCLI, self).__init__(None, template_dir)
        self.url = url
        self.cli = []

        config = platform_ci.config.PlatformCIConfig()

        if config.jenkins_cli_path:
            self.cli.extend(config.jenkins_cli_path.split())
            self.cli.append("-noCertificateCheck")
        else:
            self.cli.extend(PlatformJenkinsJavaCLI.CLI)

        self.cli.extend(["-s", url])

    def view_exists(self, view):
        """Returns true if a given view exists."""
        with open("/dev/null", "w") as devnull:
            call = subprocess.Popen(self.cli + [PlatformJenkinsJavaCLI.GET_VIEW, view], stdout=devnull, stderr=devnull)
            call.wait()
        return call.returncode == 0

    def set_view(self, view, view_xml_filename):
        """Creates a View, defined by XML in view_xml_filename.

        If the file exists, it will be update using the provided definition.

        Args:
            view: Created view name
            view_xml_filename: Path to a file containing a XML definition of a view.
        """
        if self.view_exists(view):
            command = PlatformJenkinsJavaCLI.UPDATE_VIEW
        else:
            command = PlatformJenkinsJavaCLI.CREATE_VIEW

        with open(view_xml_filename) as view_xml_file:
            view_xml = view_xml_file.read()

        call = subprocess.Popen(self.cli + [command, view], stdin=subprocess.PIPE)
        call.communicate(view_xml)
        call.wait()

    def job_exists(self, job):
        """Returns True if the given job exists."""

        with open(os.devnull, 'w') as devnull:
            result = subprocess.call(self.cli + [PlatformJenkinsJavaCLI.GET_JOB, job.name], stdout=devnull)

        return result == 0

    def delete_job(self, job):
        """Deletes a given job from Jenkins."""
        subprocess.call(self.cli + [PlatformJenkinsJavaCLI.DELETE_JOB, job.name])

    def trigger_job(self, job, parameters=None):
        """Triggers given job, providing a set of parameters to it.

        Raises:
            PlatformJenkinsException: Triggering the job failed: either the job
                does not exist, is disabled, or there was a communication
                error.
        """
        parameters = parameters or {}
        parameter_list = []
        for key in parameters:
            parameter_list.append("-p")
            parameter_list.append("%s=%s" % (key, parameters[key]))
        if subprocess.call(self.cli + [PlatformJenkinsJavaCLI.BUILD_JOB, job.name] + parameter_list) != 0:
            raise PlatformJenkinsException("Triggering job failed: " + job.name)

    def enable_job(self, job):
        """Enables given job on Jenkins.

        Raises:
            PlatformJenkinsException: Enabling the job failed: either the job
                does not exist, or there was some communication error."""
        if subprocess.call(self.cli + [PlatformJenkinsJavaCLI.ENABLE_JOB, job.name]) != 0:
            raise PlatformJenkinsException("Enabling job failed: " + job.name)

    def disable_job(self, job):
        """Disables given job on Jenkins.

        Raises:
            PlatformJenkinsException: Disabling the job failed: either the job
                does not exist, or there was some communication error.
        """
        if subprocess.call(self.cli + [PlatformJenkinsJavaCLI.DISABLE_JOB, job.name]) != 0:
            raise PlatformJenkinsException("Disabling job failed: " + job.name)

    def create_job(self, job):
        """Create a given job on Jenkins.

        Raises:
            PlatformJenkinsException: Creating the job failed: either the job
                exists already, or there was some communication error.
        """
        call = subprocess.Popen(self.cli + [PlatformJenkinsJavaCLI.CREATE_JOB, job.name], stdin=subprocess.PIPE)
        out, err = call.communicate(input=platform_ci.jjb.get_job_as_xml(job, self.template_dir, self.url))
        call.wait()
        if call.returncode != 0:
            logging.info(out)
            logging.error(err)
            raise PlatformJenkinsException("Creating job failed: " + job.name)

    def update_job(self, job):
        """Update a given job on Jenkins.

        Raises:
            PlatformJenkinsException: Updating the job failed: either the job
                does not exist, or there was some communication error.
        """
        call = subprocess.Popen(self.cli + [PlatformJenkinsJavaCLI.UPDATE_JOB, job.name], stdin=subprocess.PIPE)
        call.communicate(input=platform_ci.jjb.get_job_as_xml(job, self.template_dir, self.url))
        call.wait()
        if call.returncode != 0:
            raise PlatformJenkinsException("Updating job failed: " + job.name)

    def set_build_description(self, job_name, build, description):
        """Updates a job build description.

        Args:
            job_name: Name of a job
            build: Build number of a build of job_name
            description: Description to be set

        Raises:
            PlatformJenkinsException: Setting the description failed: either the
            job_name/build are wrong, or there was some communication problem.
        """
        try:
            subprocess.check_call(self.cli + [PlatformJenkinsJavaCLI.SET_DESCRIPTION, job_name, build, description])
        except subprocess.CalledProcessError:
            message = "Setting build description failed (job={0}, build={1}, description='{2}')".format(job_name,
                                                                                                        build,
                                                                                                        description)
            raise PlatformJenkinsException(message)

    def set_current_build_description(self, description):
        """Updates a job build description for the current build.

        This method is intended to be run in an environment where JOB_NAME
        and BUILD_NUMBER are set in the environment, such as from within the
        job build itself. If either of the environment variables is not set,
        setting the description is not attempted at all.
        """
        job_name = os.environ.get("JOB_NAME", None)
        build_id = os.environ.get("BUILD_NUMBER", None)
        if job_name is not None and build_id is not None:
            self.set_build_description(job_name, build_id, description)
