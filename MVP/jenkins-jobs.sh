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
    pip install --user --upgrade jenkins-job-builder
    pip install --user --upgrade --index-url=http://ci-ops-jenkins-update-site.rhev-ci-vms.eng.rdu2.redhat.com/packages/simple --trusted-host ci-ops-jenkins-update-site.rhev-ci-vms.eng.rdu2.redhat.com jenkins-ci-sidekick
}


if [ $# != 1 ]
then
    echo "  To test Jenkins job definition:  $0 test"
    echo "  To create/update Jenkins jobs:   $0 update"
    echo "  Please make sure config file 'config.ini' in current dir as well."
    exit 1
fi

set -ex
upgrade_jjb
. $HOME/.bash_profile
jenkins-jobs --ignore-cache --conf config.ini $1 .
