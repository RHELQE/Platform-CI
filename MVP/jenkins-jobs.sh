#!/bin/bash

need_pip()
{
    echo "  We need 'pip' to install/update jenkins."
    echo "  Please run 'easy_install pip' as root to install it."
    exit 1
}

upgrade_jjb()
{
    which pip || need_pip
    pip install --user --upgrade pip
    pip install --user --upgrade jenkins-job-builder==1.4.0
    pip install --user --upgrade --index-url=http://ci-ops-jenkins-update-site.rhev-ci-vms.eng.rdu2.redhat.com/packages/simple --trusted-host ci-ops-jenkins-update-site.rhev-ci-vms.eng.rdu2.redhat.com jenkins-ci-sidekick
}


if [ $# != 1 ]
then
    echo "  To test Jenkins job definition:  $0 test"
    echo "  To create/update Jenkins jobs:   $0 update"
    echo "  Please make sure 'config.ini' is updated with your Jenkins credentials."
    exit 1
fi

set -ex
upgrade_jjb
jenkins-jobs --ignore-cache --conf config.ini $1 .
