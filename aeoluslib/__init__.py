#
# aeoluslib.py - library for installing and enabling aeolus* modules
#
# Copyright (C) 2011  Red Hat
# James Laska <jlaska@redhat.com>
# Aziza Karol <akarol@redhat.com>
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

import os
import subprocess
import shutil
import re
import errno
import logging
import tempfile
import shlex
import json
import urlparse, urlgrabber
from rpmUtils.miscutils import splitFilename

# Module-wide support for specifying a working directory
workdir = None

# Module-wide support to handle cleanup procedures.  When cleanup=True, after #
# completion, aeoluslib will remove any git repos and packages.  Caller is
# responsible for removing any repofiles created
cleanup = True

class AeolusModule(object):
    def __init__(self, **kwargs):
        # Module name (defaults to __class__.__name__.lower())
        if not hasattr(self, 'name') or self.name is None:
            self.name = self.__class__.__name__.lower()

        # SCM URL (only git right now)
        if not hasattr(self, 'git_url') or self.git_url is None:
            raise Exception("Module %s has no git_url defined" % self.__class__.__name__)

        # Shell command needed to build RPMs from SCM
        if not hasattr(self, 'package_cmd'):
            self.package_cmd = 'make rpms'

        # Shell command needed to run built-in unittests from SCM
        if not hasattr(self, 'unittest_cmd'):
            self.unittest_cmd = 'make test'

        # RPM BuildRequires for specific module
        if hasattr(self, 'build_requires') and isinstance(self.build_requires, str):
            self.build_requires = shlex.split(self.build_requires)
        else:
            self.build_requires = list()

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

    # NOTE: Isn't always called when object is removed (search interwebs for
    # reasons)
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

    def list_buildreqs(self):
        self._clone_from_scm()
        return self._detect_buildreqs()

    def install_buildreqs(self):
        self._clone_from_scm()
        deps = self._detect_buildreqs()
        logging.info("BuildRequires for %s: %s" % \
            (self.name, ', '.join(deps)))
        yum_install_if_needed(deps)

    def _detect_buildreqs(self):
        '''Return a list of 'BuildRequires' listed in the .spec'''
        return self._detect_dependencies('BuildRequires')

    def list_requires(self):
        self._clone_from_scm()
        return self._detect_requires()

    def install_requires(self):
        self._clone_from_scm()
        deps = self._detect_requires()
        logging.info("Requires for %s: %s" % \
            (self.name, ', '.join(deps)))
        yum_install_if_needed(deps)

    def _detect_requires(self):
        '''Return a list of 'Requires' listed in the .spec'''
        return self._detect_dependencies('Requires')

    def _detect_dependencies(self, deptype):
        '''Scan .spec file and return list of deps
        '''

        assert deptype in ['BuildRequires', 'Requires'], \
            "Unknown dependency type requested: " % deptype

        # Find any files that look like .spec files
        specfiles = list()
        for root, dirs, files in os.walk(self.workdir):
            specfiles += [os.path.join(root, spec) for spec in files \
                            if '.spec' in spec]

        if len(specfiles) <= 0:
            logging.warn("No .spec files found")

        deps = list()
        # Gather any 'BuildRequires' from the spec files
        for spec in specfiles:
            # TODO - instead of pattern matching for requirements, use
            # rpmspec.  Note, rpmspec is not included in RHEL6 at this time.
            #  rpmspec -q --requires /path/to/rpm.spec
            #  rpmspec -q --buildrequires /path/to/rpm.spec
            for br in re.findall(r'^%s:\s+(.*)$' % deptype, \
               open(spec, 'r').read(), re.MULTILINE):
                # If this is a versioned compare, only split by comma
                if re.search(r'[<>=]', br):
                    deps += re.split(r'\s*,\s*', br)
                # Otherwise, split by comma or whitespace
                else:
                    deps += re.split(r'[ ,]*', br)

        # Remove any duplicates
        return list(set(deps))

    def _install_reqs(self):
        runtime_reqs = self._detect_requires()

        if len(runtime_reqs) == 0:
            logging.warn("No Requires detected for %s" % \
                self.name)
        else:
            logging.info("Requires for %s: %s" % \
                (self.name, ', '.join(runtime_reqs)))
            yum_install_if_needed(runtime_reqs)

    def _install_buildreqs(self):

        assert isinstance(self.build_requires, list)

        logging.debug("Detecting build requirements ...")
        self.build_requires += self._detect_buildreqs()

        if len(self.build_requires) == 0:
            logging.warn("No BuildRequires detected for %s" % \
                self.name)
        else:
            logging.info("BuildRequires for %s: %s" % \
                (self.name, ', '.join(self.build_requires)))
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
        assert hasattr(self, 'git_url') and self.git_url != '', \
            "Object missing git_url"

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
                (rc, clone_log) = call('git clone %s "%s"' % (self.git_url, \
                    self.workdir))
        finally:
            # return to old directory
            if os.getcwd() != cwd:
                os.chdir(cwd)

    def unittest(self):
        # self._clone_from_scm()
        self.install_requires()
        return self._run_unittests()

    def _run_unittests(self):
        '''Runs self.unittest_cmd and returns exit code'''
        logging.info("Running unittests for %s" % self.name)
        cwd = os.getcwd()
        test_log = ''
        try:
            os.chdir(self.workdir)
            (rc, test_log) = call(self.unittest_cmd)
        finally:
            # return to old directory
            if os.getcwd() != cwd:
                os.chdir(cwd)
        return rc

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

    def build_from_scm(self):
        self._clone_from_scm()
        self._install_buildreqs()
        return self._make_rpms()

    def install_from_scm(self, force=False):
        packages = self.build_from_scm()

        # Strip out any .src.rpm files
        non_src_pkgs  = [p for p in packages if splitFilename(p)[4] != 'src']

        logging.info("Installing SCM-built packages for '%s'" % self.name)
        for pkg in non_src_pkgs:
            logging.info("... %s" % pkg)

        # Install packages
        if force:
            rpm_install(non_src_pkgs)
        else:
            yum_install(non_src_pkgs)
        # FIXME - remove packages from file-system?

    def get_remote_hash(self, branch):
        '''Return the git-hash for the most recent commit on the specified
           branch'''
        assert isinstance(branch, str), "branch argument must be a string"

        u = urlparse.urlparse(self.git_url)
        if u.scheme == 'git':
            if u.netloc == 'github.com':
                # Formulate API call
                json_url = "http://%s/api/v2/json/repos/show%s/branches" \
                    % (u.netloc, re.sub(r'\.git$', '', u.path))
                json_data = json.loads(urlgrabber.urlopen(json_url).read())
                if isinstance(json_data, dict):
                    return json_data.get('branches', {}).get(branch, 'UNKNOWN')
                else:
                    logging.error("Unknown json data format: %s" % type(json_data))
            else:
                (rc, out) = call("git ls-remote %s refs/heads/%s" % (self.git_url, branch))
                if rc == 0:
                    out = out.strip() # yank off newline char
                    return out.split()[0]
                else:
                    logging.error("Unable to query repository: %s" % u)
        else:
            logging.error("Unhandled SCM format: %s" % u.scheme)


class Conductor (AeolusModule):
    name = 'aeolus-conductor'
    git_url = 'git://github.com/aeolusproject/conductor.git'

    #def install(self):
    #    '''install package via RPM'''
    #    call('yum -y install aeolus-all')

    def setup(self):
        '''Run custom configuration after install'''
        # FIXME - are we looking for a specific result/output?
        logging.info("Running aeolus-check-services")
        cmd = '/usr/bin/aeolus-check-services'
        (rc, out) = call(cmd)

    def install(self):
        '''install some meta package deps too'''
        logging.info("Installing '%s*' using yum" % self.name)
        call('yum -y install "%s*"' % self.name)

class Configure (AeolusModule):
    name = 'aeolus-configure'
    git_url = 'git://github.com/aeolusproject/aeolus-configure.git'
    package_cmd = 'rake rpms'

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

class AeolusCli (AeolusModule):
    name = 'aeolus-cli'
    git_url = 'git://github.com/aeolusproject/aeolus-cli.git'
    package_cmd = 'rake rpms'

class Oz (AeolusModule):
    git_url = 'git://github.com/clalancette/oz.git'
    # Specify additional custom build-requirements
    build_requires = 'python-virtualenv python-pip'
    unittest_cmd = 'make clean virtualenv unittests'
    package_cmd = 'make rpm'

class Imagefactory (AeolusModule):
    git_url = 'git://github.com/aeolusproject/imagefactory.git'
    package_cmd = 'make rpm'

class Iwhd (AeolusModule):
    git_url = 'git://git.fedorahosted.org/iwhd.git'
    package_cmd = './bootstrap && ./configure && make && make rpm'

class Audrey (AeolusModule):
    #name = 'aeolus-configserver'
    git_url = 'git://github.com/aeolusproject/audrey.git'
    unittest_cmd = 'python audrey_start/test_audrey_startup.py'
    package_cmd = 'cd agent && make rpms && cd .. && ' \
                + 'cd configserver && rake rpm && cd .. && '

class Libdeltacloud (AeolusModule):
    git_url = 'git://git.fedorahosted.org/deltacloud/libdeltacloud.git'
    package_cmd = './autogen.sh && ./configure && make rpm'

class PacemakerCloud (AeolusModule):
    name = 'pacemaker-cloud'
    git_url = 'git://github.com/pacemaker-cloud/pacemaker-cloud.git'
    package_cmd = './autogen.sh && ./configure && make rpm'

# No longer required upstream
# class Condor (AeolusModule):
#     git_url = 'http://git.condorproject.org/repos/condor.git -b V7_6-branch'
#     build_requires = 'imake flex byacc postgresql-devel openssl-devel ' \
#         + 'krb5-devel "gsoap-devel >= 2.7.12-1" libvirt-devel ' \
#         + '"libdeltacloud-devel >= 0.6" libX11-devel cmake ' \
#         + '"classads-devel >= 1.0.4" '
#         #+ 'condor-classads-devel'
#     package_cmd = 'curl -O https://raw.github.com/aeolusproject/aeolus-extras/master/condor/make_condor_package_7.x.sh && ' \
#                   + 'PATH_TO_CONDOR=$PWD bash make_condor_package_7.x.sh 0dcloud'

class Katello (AeolusModule):
    git_url = 'git://git.fedorahosted.org/git/katello.git'
    # FIXME - add support for handling provides: rubygem(compass) >= 0.11.5
    package_cmd = 'cd src && tito build --rpm --test'

class Pulp (AeolusModule):
    git_url = 'git://git.fedorahosted.org/pulp.git'
    package_cmd = 'tito build --rpm --test'

class Candlepin (AeolusModule):
    git_url = 'git://git.fedorahosted.org/candlepin.git'
    package_cmd = 'cd proxy && tito build --rpm --test'

class Pythonrhsm (AeolusModule):
    name = 'python-rhsm'
    git_url = 'git://git.fedorahosted.org/candlepin.git'
    package_cmd = 'cd client/python-rhsm && tito build --rpm --test'

class Headpin (AeolusModule):
    git_url = 'git://git.fedorahosted.org/headpin.git'
    package_cmd = 'tito build --rpm --test'

class Gofer (AeolusModule):
    git_url = 'git://git.fedorahosted.org/gofer.git'
    package_cmd = 'tito build --rpm --test'

class Matahari (AeolusModule):
    git_url = 'git://github.com/matahari/matahari.git'
    package_cmd = 'make rpm'

def yum_install_if_needed(dependencies):
    '''Figure out if the provided dependency is ...
        1) already satisfied on the installed system
        2) if not, is it satisfied by a package in the configured repos?
        3) if so, install it
    '''

    assert isinstance(dependencies, list), \
        "expecting list, string provided: '%s'" % dependencies

    # make sure yum-utils are installed
    (rc, out) = call("rpm -q yum-utils", False)
    if 'is not installed' in out:
        call("yum -y install yum-utils")

    missing_pkgs = list()
    for dep in dependencies:
        # Is the dependency already satisfied on the installed system?
        (rc, out) = call("repoquery --qf '%{name}-%{version}-%{release}'" \
            + " --installed --whatprovides '%s'" % dep)
        if rc == 0 and out != '':
            # FIXME - it's possible that multiple packages will satisfy a dep
            out = out.strip()
            logging.debug('Installed package %s satisfies dependency: %s' % (out, dep))
        else:
            logging.debug('Checking yum repos to satisfy dependency: %s' % dep)
            # Is the dependency satisfied by packages in the repos?
            (rc, out) = call('yum --quiet resolvedep "%s"' % dep, raiseExc=False)
            if rc != 0:
                # FIXME - should this be considered fatal?
                logging.warn("No package satisfies dependency: %s" % dep)
            else:
                # scan output to find a match ... yes this is not ideal and
                # would be better handled through some yum API
                found = False
                for line in out.split('\n'):
                    if re.match(r'^\d+:[^\s]+$', line):
                        # expected output format from /usr/share/yum-cli/cli.py
                        # resolveDepCli() '%s:%s-%s-%s.%s' % (pkg.epoch,
                        # pkg.name, pkg.version, pkg.release, pkg.arch) strip off
                        # the 'epoch:'
                        pkg = line.split(':', 1)[1].strip()
                        missing_pkgs.append(pkg)
                        found = True
                if not found:
                    logging.warn("No package satisfies dependency: %s" % dep)

    if len(missing_pkgs) > 0:
        logging.info("Installing packages: %s" % ' '.join(missing_pkgs))
        yum_install(missing_pkgs)

def yum_install(packages, gpgcheck=False):

    assert isinstance(packages, list), \
        "expecting list, string provided: '%s'" % packages

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

def rpm_install(packages):

    assert isinstance(packages, list), \
        "expecting list, string provided: '%s'" % packages

    # FIXME - find out how to do this with yum installed ... --nodeps is bad
    if len(packages) > 0:
        call('rpm -Uvh --nodeps ' + ' '.join(packages))

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
