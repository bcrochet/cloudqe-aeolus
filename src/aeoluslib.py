#!/usr/bin/env python
#
# aeoluslib.py - Helper library for installing and enabling aeolus*
#
# Copyright (C) 2011  Red Hat
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; version 2 only
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA
#
# Author(s): Aziza Karol <akarol@redhat.com>
#            James Laska <jlaska@redhat.com>
#

import os
import subprocess
import shutil
import re
import errno
import logging
import tempfile
import shlex
from rpmUtils.miscutils import splitFilename

# Module-wide support for specifying a working directory
workdir = None

# Module-wide support to handle cleanup procedures.  When cleanup=True, after #
# completion, aeoluslib will remove any git repos and packages.  Caller is
# responsible for removing any repofiles created
cleanup = True

class AeolusModule(object):
    # Module name (defaults to __class__.__name__.lower())
    name = None
    # SCM URL (only git right now)
    git_url = None
    # Shell command needed to build RPMs from SCM
    package_cmd = 'make rpms'
    # RPM BuildRequires for specific module
    build_requires = None

    def __init__(self, **kwargs):
        if hasattr(self, 'name') and self.name is None:
            self.name = self.__class__.__name__.lower()

        # Define a work directory for any checkouts or temp files
        if kwargs.has_key('workdir'):
            self.workdir = os.path.join(kwargs.get('workdir'), self.name)
            makedirs(self.workdir)
        elif workdir is not None:
            self.workdir = os.path.join(workdir, self.name)
            makedirs(self.workdir)
        else:
            self.workdir = tempfile.mkdtemp(suffix='.%s' % self.name)

    def setup(self):
        raise NotImplementedError("Not implemented by derived class")

    # NOTE: Isn't always called when object is removed (search interwebs for reasons)
    def __del__(self):
        '''perform cleanup if desired (default)'''
        if cleanup:
            self._cleanup()

    def _cleanup(self):
        '''Remove self.workdir'''
        if hasattr(self, 'workdir') and os.path.isdir(self.workdir):
            try:
                shutil.rmtree(self.workdir)
            except OSError, e:
                print e

    def _install_buildreqs(self):
        if self.build_requires is None or \
           self.build_requires == '':
            logging.debug("No build requires provided, detecting...")

            # Find any files that look like .spec files
            specfiles = list()
            for root, dirs, files in os.walk(self.workdir):
                specfiles += [os.path.join(root, spec) for spec in files \
                                if '.spec' in spec]

            # Gather any 'BuildRequires' from the spec files
            build_requires = list()
            for spec in specfiles:
                build_requires += re.findall(r'^BuildRequires:\s*([^\n, ]*)',
                    open(spec, 'r').read(), re.MULTILINE)

            if len(build_requires) > 0:
                self.build_requires = ' '.join(build_requires)
            else:
                logging.warn("Unable to detect buildrequires for '%s'" % \
                    self.name)

        logging.info("Installing BuildRequires for %s: %s" % (self.name, self.build_requires))

        yum_install_if_needed(self.build_requires)

    def is_installed(self):
        '''install package via RPM'''
        logging.info("Checking if %s is installed" % self.name)
        (rc, out) = call('rpm --quiet -q %s' % self.name, raiseExc=False)
        return rc == 0  # 0=pass

    def uninstall(self):
        '''uninstall rpm package'''
        logging.info("Uninstalling %s using yum" % self.name)
        (rc, out) = call('yum -y remove %s' % self.name)
        return rc == 0  # 0=pass

    def install(self):
        '''install package via RPM'''
        logging.info("Installing %s using yum" % self.name)
        call('yum -y install %s' % self.name)

    def chkconfig(self, cmd, serviceName=None):
        '''Unsing chkconfig, enable the service on boot'''
        if serviceName is None:
            serviceName = self.name
        logging.info("Enabling system service %s" % serviceName)
        if cmd.lower() not in ['on', 'off']:
            raise Exception("Unknown chkconfig command: %s" % cmd)
        call('chkconfig %s %s' % (serviceName, cmd))

    def _svc_cmd(self, target, serviceName=None):
        '''Using servic, start the service'''
        if serviceName is None:
            serviceName = self.name
        logging.info("Changing service state: %s -> %s" % (serviceName, target))
        call('service %s %s' % (serviceName, target))

    def svc_start(self, serviceName=None):
        self._svc_cmd('start', serviceName)

    def svc_restart(self, serviceName=None):
        self._svc_cmd('restart', serviceName)

    def svc_stop(self, serviceName=None):
        self._svc_cmd('stop', serviceName)

    def _clone_from_scm(self):
        '''checkout package from version control'''
        if not hasattr(self, 'git_url') or self.git_url is None:
            raise Exception("Module has no self.git_url defined")

        cwd = os.getcwd()
        try:
            # Already cloned?
            if os.path.isdir(os.path.join(self.workdir, '.git')):
                os.chdir(self.workdir)
                logging.info("Updating existing %s checkout at %s" % \
                    (self.name, self.workdir))
                (rc, pull_log) = call('git pull')
            else:
                logging.info("Checking out %s from %s into %s" % (self.name, \
                    self.git_url, self.workdir))
                (rc, clone_log) = call('git clone %s %s' % (self.git_url, \
                    self.workdir))
        finally:
            # return to old directory
            if os.getcwd() != cwd:
                os.chdir(cwd)
        self.cloned = True

    def _make_rpms(self):
        '''Runs self.package_cmd and returns a list of built packages'''
        logging.info("Building %s RPM packages" % self.name)

        cwd = os.getcwd()
        build_log = ''
        try:
            os.chdir(self.workdir)
            (rc, build_log) = call(self.package_cmd)
        finally:
            # return to old directory
            if os.getcwd() != cwd:
                os.chdir(cwd)

        # Return a list of package paths (includes src.rpm)
        packages_built = re.findall("^Wrote:\s*(.*\.rpm)$", build_log, re.MULTILINE)
        if len(packages_built) == 0:
            raise Exception("Failed to build packages, consult build log")

        for pkg in packages_built:
            logging.info("... %s" % pkg)

        return packages_built

    def install_from_scm(self):
        # FIXME - prepare custom f15 repo?
        self._clone_from_scm()
        self._install_buildreqs()
        packages = self._make_rpms()

        # Strip out any .src.rpm files
        non_src_pkgs  = [p for p in packages if splitFilename(p)[4] != 'src']
        logging.info("Installing SCM-built packages for '%s'" % self.name)
        for pkg in non_src_pkgs:
            logging.info("... %s" % pkg)
        yum_install(non_src_pkgs)
        # FIXME - remove packages from file-system?

class Conductor (AeolusModule):
    name = 'aeolus-conductor'
    git_url = 'git://git.fedorahosted.org/git/aeolus/conductor.git'
    build_requires = 'condor-classads-devel git rest-devel rpm-build ruby-devel zip'

    #def install(self):
    #    '''install package via RPM'''
    #    call('yum -y install aeolus-all')

    def setup(self):
        '''Run custom configuration after install'''
        # FIXME - are we looking for a specific result/output from
        logging.info("Running aeolus-check-services")
        cmd = '/usr/bin/aeolus-check-services'
        (rc, out) = call(cmd)

class Configure (AeolusModule):
    name = 'aeolus-configure'
    git_url = 'git://git.fedorahosted.org/git/aeolus/configure.git'

    def uninstall(self):
        cmd = '/usr/sbin/aeolus-cleanup'
        logging.info("Running '%s'" % cmd)
        if os.path.isfile(cmd):
            (rc, out) = call(cmd + ' -v')

        # Call parent to remove package
        AeolusModule.uninstall(self)

    def setup(self):
        '''Run custom configuration after install'''
        logging.info("Running aeolus-configure")
        cmd = 'aeolus-configure'
        (rc, out) = call(cmd)

class Oz (AeolusModule):
    git_url = 'git://github.com/clalancette/oz.git'
    build_requires = 'gcc git make rpm-build'
    package_cmd = 'make rpm'

class Imagefactory (AeolusModule):
    git_url = 'git://github.com/aeolusproject/imagefactory.git'
    build_requires = 'gcc git make rpm-build'
    package_cmd = 'make rpm'

class Iwhd (AeolusModule):
    git_url = 'git://git.fedorahosted.org/iwhd.git'
    #build_requires = 'jansson-devel libmicrohttpd-devel hail-devel gc-devel ' \
    #    + 'git gperf mongodb-devel help2man mongodb-server libcurl-devel ' \
    #    + 'libuuid-devel'
    package_cmd = './bootstrap && ./configure && make && make rpm'

class Audrey (AeolusModule):
    git_url = 'git://github.com/clalancette/audrey.git -b config-server'
    package_cmd = 'cd configserver && rake rpm'

class Libdeltacloud (AeolusModule):
    git_url = 'git://git.fedorahosted.org/deltacloud/libdeltacloud.git'
    package_cmd = './autogen.sh && ./configure && make rpm'

# Qpid not required, since already packaged in Fedora
# FIXME - not pulled from GIT, uses existing package
class Qpid (AeolusModule):
    build_requires = 'boost-devel e2fsprogs-devel pkgconfig gcc-c++ ' \
        + 'make autoconf automake ruby libtool help2man doxygen graphviz ' \
        + 'corosynclib-devel clusterlib-devel cyrus-sasl-devel ' \
        + 'nss-devel nspr-devel xqilla-devel xerces-c-devel ' \
        + 'ruby ruby-devel swig libibverbs-devel librdmacm-devel ' \
        + 'libaio-devel'

# FIXME - incomplete
class Condor (AeolusModule):
    git_url = 'http://git.condorproject.org/repos/condor.git -b V7_6-branch'
    build_requires = 'coredumper coredumper-devel git qpid-cpp-server-devel ' \
        + 'wget'
    package_cmd = ['curl https://raw.github.com/aeolusproject/aeolus-extras/master/condor/make_condor_package_7.x.sh',
                   'PATH_TO_CONDOR=FIXME make_condor_package_7.x.sh 0dcloud',]

class Katello (AeolusModule):
    git_url = 'git://git.fedorahosted.org/git/katello.git'
    # FIXME - add support for handling provides: rubygem(compass) >= 0.11.5
    build_requires = 'tito coreutils findutils sed rubygems rubygem-rake ' \
        + 'rubygem-gettext rubygem-jammit rubygem-compass ' \
        + 'rubygem-compass-960-plugin'
    package_cmd = 'cd src && tito build --rpm --test'

class Pulp (AeolusModule):
    git_url = 'git://git.fedorahosted.org/pulp.git'
    build_requires = 'python-devel python-setuptools python-nose ' \
        + 'rpm-python make checkpolicy selinux-policy hardlink '
    package_cmd = 'tito build --rpm --test'

class Candlepin (AeolusModule):
    git_url = 'git://git.fedorahosted.org/candlepin.git'
    build_requires = 'ruby rubygems ruby-devel gcc perl-Locale-Msgfmt ' \
        + 'tomcat6 java-1.6.0-openjdk-devel tito'
    package_cmd = 'tito build --rpm --test'

def yum_install_if_needed(packages):

    # convert to a list
    if isinstance(packages, str):
        packages = shlex.split(packages)

    # Using shlex.split allows for package deps with spaces
    missing_pkgs = list()
    for pkg in packages:
        (rc, out) = call('rpm -q %s' % pkg, raiseExc=False)
        if rc != 0:
            missing_pkgs.append(pkg)

    yum_install(missing_pkgs)

def yum_install(packages, gpgcheck=False):

    # convert to a list
    if isinstance(packages, str):
        packages = shlex.split(packages)

    if len(packages) > 0:
        yum_opts = gpgcheck and ' ' or '--nogpgcheck'
        call('yum install %s -y %s' % (yum_opts, ' '.join(packages)))

        # Convert any packages to nvr (not file path)
        package_nvrs = [p for p in packages if not
            os.path.isfile(p)]
        package_nvrs += [str2NVR(p) for p in packages if
            os.path.isfile(p)]

        # Yum doesn't tell us whether things installed or not ... ask rpm
        (rc, out) = call('rpm --quiet -q %s' % ' '.join(package_nvrs),
            raiseExc=False)
        if rc != 0:
            raise Exception("Some build dependencies could not be installed")

def str2NVR(s):
    '''Convenience method to convert an rpm filename to just NVR'''
    (n,v,r,e,a) = splitFilename(os.path.basename(s))
    return '%s-%s-%s' % (n,v,r)

def makedirs(path):
    try:
        os.makedirs(path)
    except OSError, e:
        if e.errno == errno.EEXIST:
            pass

def call(cmd, raiseExc=True):
    logging.debug(cmd)
    p = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT)
    (pout, perr) = p.communicate()
    logging.debug("rc: %s" %  p.returncode)
    logging.debug("output: %s" %  pout)
    if p.returncode != 0 and raiseExc:
        raise Exception("Command failed, rc=%s\n%s" % (p.returncode, pout))
    return (p.returncode, pout)

def add_custom_repos(repofiles):
    '''Download the provided list of yum repository files to
    /etc/yum.repos.d/'''
    if isinstance(repofiles, str):
        repofiles = [repofiles]
    for repofile in repofiles:
        cmd = "curl -o /etc/yum.repos.d/%s %s" % (os.path.basename(repofile),
            repofile)
        logging.info("Adding repo %s " % repofile)
        (rc, out) = call(cmd)

def remove_custom_repos(repofiles):
    '''Remove provided repofiles provided (if aeoluslib.cleanup = True
    (default)'''
    if not cleanup:
        return

    if isinstance(repofiles, str):
        repofiles = [repofiles]
    for repofile in repofiles:
        repofile = os.path.join('/etc/yum.repos.d', os.path.basename(repofile))
        if os.path.isfile(repofile):
            logging.info("Removing file %s " % repofile)
            os.remove(repofile)
