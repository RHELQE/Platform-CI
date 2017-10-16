# CI Metrics

CI Metrics is a solution to simplify and automate CI metrics data collection.

The solution consists of:

 * ELK instance

 * CI Metrics data listener Jenkins job

 * Jenkins jobs with enabled CI publisher

```
		   +----------+
		   |   ELK    |                                   +--------------------+
		   | instance |                                   |     Jenkins 1      |
		   +----+-----+                   +---------------+   with test jobs   |
				^                         |               | using CI publisher |
				|                         |               +--------------------+
				|                         |
		+-------+---------+               v               +--------------------+
		|  Jenkins with   |      +--------+-------+       |     Jenkins 2      |
		| CI Metrics data +<-----+ CI Message Bus +<------+   with test jobs   |
		|  listener job   |      +--------+-------+       | using CI publisher |
		+-----------------+               ^               +--------------------+
										  |
										  |               +--------------------+
										  |               |     Jenkins 3      |
										  +---------------+   with test jobs   |
														  | using CI publisher |
														  +--------------------+
```

The ELK instance is the data store for storing metrics exported from Jenkins jobs with enabled CI publisher. The exported data from Jenkins jobs is harvested via CI Metrics data listener Jenkins job and stored into the ELK instance.

If you want to install your own ELK instance follow the steps in the section ELK instance.

If you do not want to install you own ELK instance skip the sections *ELK instance* and *CI Metrics data listener Jenkins job* sections.


## ELK instance

### What is ELK

ELK is a combination of Elasticsearch, Logstash and Kibana. Elasticsearch is a non relational database. Logstash collects and pushes logs to the Elasticsearch database. Kibana then takes the data and visualizes it in graphical form and it also makes it possible to query the data.

Note that in current design Logstash is not used and the data is directly stored from the CI Metrics data listener Jenkins job into Elasticsearch.

### How to install ELK for CI metrics

Note that the solution requires an RHEL 7 or Centos 7 system. To install an ELK instance on your localhost use the provided Ansible yaml file.


1. ####Add EPEL repository

  See [https://fedoraproject.org/wiki/EPEL] for installation instructions


1. ####Install git and ansible

  >$ yum -y install git ansible


1. ####Get CI Metrics files

  >$ git clone https://github.com/RHQE/platform-ci.git

  >$ cd platform-ci/ci-metrics


1. ####Run ansible to install ELK

  >$ ansible-playbook install_elk.yaml


1. ####Verify that ELK instance works

    Access the port 80 on your localhost via your web browser and you should see the Kibana configuration page.

  [http://localhost]


## ELK Listener Jenkins job

ELK Listener job listens on the CI message bus for messages matching this JMS selector:

```
(CI_TYPE = 'brew-taskstatechange' AND method = 'build' AND scratch = FALSE) OR (CI_TYPE = 'ci-metricsdata')

```

These messages are stored directly into the ELK instance.

The ELK Listener job requires:

  - an existing ELK instance

  - an existing PDC instance - see https://github.com/product-definition-center/

  - a keytab for authentication to PDC via keberos

### Installation of ELK Listener job

1. ####Get CI Metrics files

  >$ git clone https://github.com/RHQE/platform-ci.git

  >$ cd platform-ci/ci-metrics

1. ####Tweak [ci_listener.yaml](/ci-metrics/ci_listener.yaml)

    Edit the file and:

    - replace LINKTO_ELK_SERVER with url to an ELK instance

    - replace LINKTO_PDC to with url to a PDC instance

    Also make sure the environment variables KEYTAB and PRINCIPAL are defined in your Jenkins environment with details about your kerberos principal and keytab.

1. ####Enable CI publisher for your Jenkins Job

    To enable the job, run `jenkins-jobs` from the Jenkins Job Builder on the file ci_listener.yaml.

  >$ jenkins-jobs update ci_listener.yaml


## Jenkins jobs with enabled CI publisher

This section describes how to enable CI publisher for publishing CI metrics data from your jobs.

The message types are defined in this document [https://url.corp.redhat.com/ci-metrics-message-types].

The possible items of the message are defined in this document [https://url.corp.redhat.com/ci-metrics]

### Howto enable CI publisher in your jobs in JJB yaml

1. #### Make sure to inject the required variables that will be used by the CI publisher in the post build action

    For example you can use the [EnvInject](https://wiki.jenkins-ci.org/display/JENKINS/EnvInject+Plugin) plugin to achieve this.

1. #### Enable CI publisher for your Jenkins Job

    Add into your publisher section *ci-publisher* definition like the one below. Make sure to correctly define the *message-type* and all the relevant items in your message.

```
    publishers:
      - ci-publisher:
          message-type: 'Tier1TestingDone'
          message-properties: |
            CI_TYPE=ci-metricsdata
          message-content: |
            {{
                "create_time": "$CREATE_TIME",
                "trigger": "brew build",
                "tests": $TESTS,
                "CI_tier": "$CI_TIER",
                "owner": "$OWNER",
                "build_type": "$BUILD",
                "base_distro": "$BASE_DISTRO",
                "completion_time": "$COMPLETION_TIME",
                "component": "$name-$version-$release",
                "jenkins_job_url": "$JOB_URL",
                "jenkins_build_url": "$BUILD_URL",
                "brew_task_id": "$id",
                "job_name": "$JOB_NAME",
                "team": "$TEAM_NAME",
                "recipients": "someuser"
            }}
```

    You can also check [jjb_metrics_snippets.txt](/ci-metrics/jjb_metrics_snippets.txt) for an example of a job which uses CI publisher.

---
Please feel free open an [issue](https://github.com/RHQE/platform-ci/issues) if you encounter issues following this README.
