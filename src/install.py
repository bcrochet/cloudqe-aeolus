#!/usr/bin/python

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
#
# Description: aeolus installation in two ways
# Option 1:Install all the rpms from the last released repo and then pull all the src and compile
# Option 2:Only pull the src and compile
#
# Author: Aziza Karol <akarol@redhat.com>
# Copyright (C) 2011  Red Hat
# see file 'COPYING' for use and warranty information
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
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

import os
import sys
import optparse
import logging
import yum
import inspect

try:
    import aeoluslib
except ImportError:
    print "Unable to import aeoluslib.  Is aeoluslib in PYTHONPATH?"
    sys.exit(1)

def yum_var_subst(buf):
    '''Convenience method to substitute instances of $releasever and $basearch
    from yum's point of view.
        ex: yum_var_subst('/tmp/$basearch/$releasever') -> '/tmp/x86_64/16'
    '''

    yb = yum.YumBase()
    yb.conf
    for varname in ['releasever', 'basearch']:
        buf = buf.replace('$'+varname, yb.yumvar[varname])
    return buf

def get_supported_modules():
    '''Discover supported AeolusModule subclasses'''
    def is_aeolusmodule(object):
        '''The built-in issubclass treats classes as subclasses of themselves.
        This method does not.'''
        if inspect.isclass(object) \
           and issubclass(object, aeoluslib.AeolusModule) \
           and aeoluslib.AeolusModule in object.__bases__:
            return True
        return False

    return [mbr[0].lower() \
        for mbr in inspect.getmembers(aeoluslib, is_aeolusmodule)]

def parse_args():
    # Old method - Hard code the list of supported modules
    # component_list = ['all', 'conductor', 'configure', 'oz', 'imagefactory', 'iwhd', 'audrey',]
    component_list = ['all']
    component_list.extend(get_supported_modules())

    usage_str = '''%%prog [options] [module(s)]

Supported modules include:
 %s

Examples:
 * Install oz from git
   $ install.py --source=git --base_dir=/home oz
 * Install audrey using yum
   $ install.py --source=yum audrey
 * Install everything from git
   $ install.py --source=git --base_dir=/home all''' % (', '.join(component_list),)

    parser = optparse.OptionParser(usage=usage_str)
    source_choices = ["yum", "git"]
    parser.add_option("--source", action="store", default=None,
        type="choice", choices=source_choices,
        help="Install source to use for install (options: %s)" %
            ", ".join(source_choices))
    parser.add_option("--repofile", action="append",
        #default=['http://repos.fedorapeople.org/repos/aeolus/conductor/testing/fedora-aeolus-testing.repo'],
        default=[],
        help="Specify custom yum .repo file(s) for use with --source=yum. (default: %default)")
    parser.add_option("-p", "--base_dir", action="store", dest="base_dir",
        default=None, help="providing a base dir for installation")
    parser.add_option("--log", action="store", dest="logfile",
        default=None, help="Log output to a file")
    parser.add_option("--noclean", action="store_true", dest="noclean",
        default=False, help="Don't cleanup after completion",)
    parser.add_option("-d", "--debug", action="store_true", dest="debug",
        default=False, help="Enable debug output",)

    (opts, args) = parser.parse_args()

    # Sanitize source
    o = parser.get_option("--source")
    if opts.source not in o.choices:
        parser.error("Must provide value for %s" % o.get_opt_string())

    # Sanity --base_dir
    if opts.source == 'git':
        '''FIXME - optionally sanitize opts.base_dir'''

    elif opts.source == 'yum':
        '''FIXME - optionally sanitize opts.repofile'''

    # Sanity component list
    if len(args) <= 0:
        parser.error("No component provided")
    for a in args:
        if a not in component_list:
            parser.error("Unknown component selected: %s" % a)

    return (opts, args)

def setup_logging(debug=False, logfile=None):

    # Normal or debug?
    if debug:
        logging_format = '%(asctime)s %(levelname)s [%(filename)s:%(lineno)d] %(message)s'
        logging_level = logging.DEBUG
    else:
        #logging_format = '%(asctime)s %(levelname)s %(message)s'
        #logging_format = '(%(levelname)s) %(message)s'
        logging_format = '%(message)s'
        logging_level = logging.INFO

    # Configure root logger
    logging.basicConfig(level=logging_level,
                        format=logging_format,
                        datefmt='%Y-%d-%m %I:%M:%S')

    # HACK - the above doesn't properly set the desired level, so the
    # following fixes that
    logger = logging.getLogger()
    logger.setLevel(logging_level)

    # Optionally attach a fileHandler
    if logfile is not None:
        try:
            logger
        except NameError: # in case someone fixes basicConfig above
            logger = logging.getLogger()

        filehandler = logging.FileHandler(logfile, 'a')
        # Use format from root logger
        filehandler.setFormatter(logging.Formatter(logger.handlers[0].formatter._fmt,
                                 logger.handlers[0].formatter.datefmt))
        logger.addHandler(filehandler)

def is_requested(module, requested):
    if module in requested or 'all' in requested:
        return True
    return False

def aeolus_install(opts, requested_modules):
    # FIXME - detect whether running in SELinux enforcing
    # FIXME - remind about firewall changes?

    # If directed, enable custom repofiles
    if opts.repofile:
        aeoluslib.add_custom_repos(opts.repofile)

    # Instruct aeoluslib to not cleanup temporary files after completion
    if opts.noclean:
        aeoluslib.cleanup = False

    # Define a base_dir for all git operations
    if opts.source == 'git' and opts.base_dir:
        aeoluslib.workdir = opts.base_dir

    if False:
        '''I think this doesn't make sense ... and can go away in favor of the
        loop below'''
        # Cleanup any stale existing configuration
        conductor = aeoluslib.Conductor()
        if conductor.is_installed():
            conductor.uninstall()

        # If configure is already installed, clean it up
        configure = aeoluslib.Configure()
        if configure.is_installed():
            configure.uninstall()

        # Install fresh out of the oven
        aeoluslib.yum_install('aeolus-all')

        # Install aeolus-conductor from git
        if opts.source == 'git' and is_requested('conductor', requested_modules):
            conductor.install_from_scm()
        if opts.source == 'git' and is_requested('configure', requested_modules):
            configure.install_from_scm()

        # Enable and start aeolus services
        configure.setup()
        conductor.chkconfig('on')
        conductor.svc_restart()

    # Force specific module install/setup order
    reordered_modlist = ['conductor', 'configure']
    # Include everything else
    reordered_modlist.extend(get_supported_modules())

    # Install requested modules
    for module in reordered_modlist:
        if is_requested(module, requested_modules):
            cls_name = module.capitalize()
            if not hasattr(aeoluslib, cls_name):
                logging.error("Unable to find aeoluslib.%s" % cls_name)
                sys.exit(1)

            cls_obj = getattr(aeoluslib, cls_name)
            cls_inst = cls_obj()

            # Install the module
            if opts.source == 'yum':
                cls_inst.install()
            elif opts.source == 'git':
                cls_inst.install_from_scm()

            # Activate and start the system service (if applicable)
            if module in ['conductor', 'imagefactory', 'iwhd']:
                cls_inst.chkconfig('on')
                cls_inst.svc_restart()

            # Run custom setup
            try:
                cls_inst.setup()
            except NotImplementedError:
                pass

if __name__ == "__main__":

    # Process arguments
    (opts, requested_modules) = parse_args()

    # Setup logging
    setup_logging(opts.debug, opts.logfile)

    try:
        aeolus_install(opts, requested_modules)
    except KeyError:
        print "Exiting upon user request"
        sys.exit(1)
    finally:
        aeoluslib.remove_custom_repos(opts.repofile)
