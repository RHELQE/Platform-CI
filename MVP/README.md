# Platform-CI MVP

## What's MVP?

Minimal Viable Product (MVP) is a minimized set of Jenkins job definition (and supporting files) on Platform CI:

  - for End-to-End workflow changes (batch update) via **Template / Default YAML**
  - for create/update/scale tests (by individuals) via **Test / Job YAML**

## How to create a CI job with MVP?

1. ####Get MVP files

  >$ git clone https://github.com/RHQE/platform-ci.git

  >$ cd platform-ci/MVP

1. ####Tweak [sample_job.yaml](/MVP/sample_job.yaml/) with your own test parameters

  - `project` - `name`/`component`

     **name** is unique for identifying your job set.

     And job trigger is watching candidate brew builds for **component** by default.

  - `shell`

     This is THE key part of your job.

     Fill in the commands you've been using for submitting tests into Beaker.

     E.g. `bkr workflow-tomorrow -f $your_taskfile` or `bkr job-submit $your_test.xml`

     (`bkr job-watch` and `bkr job-results` will watch the job and collect results when it finishes.)

  - `ownership`

     Replace those names with actual owner/co-owners of your test.

     They will receive Jenkins email notifications accordingly.

  - `node`

     By specifying this **node** parameter, you can run the `shell` commands on team/individual slave - which will be able to access team-specific test resources with keytab configured on it.

1. ####Create Jenkins job

  - Update [config.ini](/MVP/config.ini/) with your credentials on Platform Jenkins Master (PJM)

        [jenkins]
        user=
        password=
        url=https://platform-stg-jenkins.rhev-ci-vms.eng.rdu2.redhat.com/

    **user** is your username of PJM - which is same as your kerberos ID.

    **password** is an API token which can be found by via `Show API Token...` button on your user configure page. (*https://platform-stg-jenkins.rhev-ci-vms.eng.rdu2.redhat.com/user/${user}/configure*)

  - Create/Update your jobs to PJM (Finally!)

     >$ ./jenkins-jobs.sh update

  - Want a dry-run before creating jobs on PJM? (validate your job definition)

     >$ ./jenkins-jobs.sh test

1. ####Done


---
Please feel free to reach [Linqing Lu](mailto:lilu@redhat.com) or open an [issue](https://github.com/RHQE/platform-ci/issues) here if any question about this MVP.

Thanks!
