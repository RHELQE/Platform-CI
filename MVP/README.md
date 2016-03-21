# Platform-CI MVP

## What's MVP?

Minimal Viable Product (MVP) is a set of Jenkins job definition (and supporting files) for creating jobs on Platform CI as easy as possible:

  - for workflow changes (batch update) via **Template / Default YAML**
  - for create/update/scale tests by individuals via **Test / Job YAML**

## How to create a CI job with MVP?

1. ####Get MVP files

  >$ git clone https://github.com/RHQE/platform-ci.git

  >$ cd platform-ci/MVP

1. ####Modify [sample_job.yaml](/sample_job.yaml/) with your own tests *(skip this step if you just want a taste of creating job)*

  - `ownership`
  
     Replace those names with actual owner/co-owners of your test.
     They will receive Jenkins email notifications accordingly.
  
  - `project` - `name`/`component`
     
     **name** is unique as identification of the job set.
     And job trigger will watch brew builds for **component**.

  - `shell`
     
     This is THE key part of your job.
     Fill in shell commands you've been using for submitting automation jobs in Beaker.
     
     E.g. download/clone test metadata from team repo and run `bkr workflow-tomorrow` or `bkr job-submit`
     
     (Keep the last two lines `bkr job-watch` and `bkr job-results`. They'll collect test results when jobs end.)

1. ####Create or update your jobs
     
  - Create/Update your jobs to Platform Jenkins master (Finally!)

     >$ ./jenkins-jobs.sh update`

  - Want a dry-run before creating jobs? (test your test is a good habit)

     >$ ./jenkins-jobs.sh test`

## Optional yet Recommended

- ####Update [config.ini](/config.ini/) with your own Jenkins credential

        [jenkins]
        user=
        password=
        url=https://platform-stg-jenkins.rhev-ci-vms.eng.rdu2.redhat.com/

  **user** is actuall your RH kerb ID.

  **password** is a static API token can be found by via `Show API Token...` button on your Jenkins user config page.
  (from top right corner of Jenkins homepage - or via this URL: *https://platform-stg-jenkins.rhev-ci-vms.eng.rdu2.redhat.com/user/__${user}__/configure*)

- ####Run jobs on your own Jenkins slave

