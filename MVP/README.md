# Platform-CI MVP

## What's MVP?

Minimal Viable Product (MVP) is a minimized set of Jenkins job definition (and supporting files) on Platform CI:

  - for End-to-End workflow changes (batch update) via **Template / Default YAML**
  - for create/update/scale tests (by individuals) via **Test / Job YAML**

It contains only the neccessary CI elements for creating a job in stable and scalable way.

So it's also expected to be a common ground for teams to start with. And contribution would be highly appreciated.

## How to create a CI job with MVP?

1. ####Get MVP files

  >$ git clone https://github.com/RHQE/platform-ci.git

  >$ cd platform-ci/MVP

1. ####Tweak [sample_job.yaml](/MVP/sample_job.yaml/) with your own test parameters

    *Job YAMLs store parameters which are specific for your testing jobs. It's recommended to maintain them in your team git repo.*

    *Each job YAML file may contain one or more sets of job defintion, and multiple job YAML files can be saved in same folder. They work together with the template YAML to provide detailed configurations for creating/updating Jenkins jobs.*

  - `project` - `name`/`component`

     **name** is unique for identifying your job set.

     And job trigger is watching candidate brew builds for **component** by default.

  - `shell`

     This is THE key part of your job.

     Fill in the commands you've been using for submitting tests into Beaker.

     E.g. `bkr workflow-tomorrow -f $your_taskfile` or `bkr job-submit $your_test.xml`

     (`bkr job-watch` and `bkr job-results` will watch the job and collect results when it finishes.)

  - `ownership`

     Replace the name with actual owner of those tests.

     Owner will receive Jenkins email notifications accordingly.

  - `node`

     By specifying this **node** parameter, you can run the `shell` commands on team/individual slave - which will be able to access team-specific test resources with keytab configured on it.

1. ####Create Jenkins job

  - Update [config.ini](/MVP/config.ini/) with your credentials on Platform Jenkins Master (PJM). It's requried for next step.

    **user** is your username of PJM - same as your kerberos ID.

    **password** is an API token which can be found by clicking `Show API Token...` button on your user configure page. (*https://platform-stg-jenkins.rhev-ci-vms.eng.rdu2.redhat.com/user/${user}/configure*)

  - Create/Update your jobs to PJM (Finally!)

    There is a simple script [jenkins-jobs.sh](/MVP/jenkins-jobs.sh/) to help you with this step.

    It is basically a wrapper of [Jenkins Job Builder](http://ci.openstack.org/jenkins-job-builder/) along with necessary plugins.

     >$ ./jenkins-jobs.sh update

  - Or, you want a dry-run before actually creating jobs on PJM?

     >$ ./jenkins-jobs.sh test

  - [Alternative choice](https://platform-stg-jenkins.rhev-ci-vms.eng.rdu2.redhat.com/job/Platform-CI-MVP-Job-Builder/build) to create/update jobs in case without a terminal.

1. ####Done


## Other references that may help

  - A quick [video demo](http://lacrosse.redhat.com/lilu/CI_MVP_1.ogv) for starting with MVP on PJM.

  - If you met [SSL issue](https://github.com/RHQE/platform-ci/issues/4), please check out this [internal doc](https://docs.engineering.redhat.com/display/CI/Jenkins+CLI+Authentication) and install necessary cert.
  

---
Please feel free open an [issue](https://github.com/RHQE/platform-ci/issues) here if any question about this MVP.

Thanks!
