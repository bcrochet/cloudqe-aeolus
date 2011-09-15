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
import errno

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

def parse_args():
    #parser = optparse.OptionParser()
    component_list = ['all', 'conductor', 'configure', 'oz', 'imagefactory', 'iwhd', 'audrey',]
    usage_str = '''%%prog [options] <%s>

Examples:
 * Install oz from git
   $ install.py --source=git --base_dir=/home oz
 * Install audrey using yum
   $ install.py --source=yum=/home audrey
 * Install everything from git
   $ install.py --source=git --base_dir=/home all''' % (','.join(component_list),)

    parser = optparse.OptionParser(usage=usage_str)
    source_choices = ["yum", "git"]
    parser.add_option("--source", action="store", default=None,
        type="choice", choices=source_choices,
        help="Install source to use for install (options: %s)" %
            ", ".join(source_choices))
    parser.add_option("--repofile", action="append",
        default=['http://repos.fedorapeople.org/repos/aeolus/conductor/testing/fedora-aeolus-testing.repo'],
        help="Specify custom yum .repo file for use with --source=yum. (default: %default)")
    parser.add_option("-p", "--base_dir", action="store", dest="base_dir",
        default=None help="providing a base dir for installation")
    parser.add_option("--log", action="store", dest="logfile",
        default=None, help="Log output to a file")
    parser.add_option("-d", "--debug", action="store_true", dest="debug",
        default=False, help="Enable debug output",)

    (opts, args) = parser.parse_args()

    # Sanitize source
    o = parser.get_option("--source")
    if opts.source not in o.choices:
        parser.error("Must provide value for %s" % o.get_opt_string())

    # Sanity --base_dir
    if opts.source == 'git':
        if opts.base_dir is None:
            parser.error("Must provide --base_dir when using --source=git")

    elif opts.source == 'yum':
        '''FIXME - sanitize opts.repofile'''

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
    else:
        logging_format = '%(asctime)s %(levelname)s %(message)s'

    # Configure root logger
    logging.basicConfig(level=opts.debug and logging.DEBUG or logging.INFO,
                        format=logging_format,
                        datefmt='%Y-%d-%m %I:%M:%S')

    # Optionally attach a fileHandler
    if logfile is not None:
        logger = logging.getLogger()

        filehandler = logging.FileHandler(logfile, 'a')
        # Use format from root logger
        filehandler.setFormatter(logging.Formatter(logger.handlers[0].formatter._fmt,
                                 logger.handlers[0].formatter.datefmt))
        logger.addHandler(filehandler)

def is_requested(comp, requested):
    if comp in requested or 'all' in requested:
        return True
    return False

if __name__ == "__main__":

    # Process arguments
    (opts, components) = parse_args()

    # Setup logging
    setup_logging(opts.debug, opts.logfile)

    if opts.source == 'git':
        # FIXME - this needs to move into a module somewhere
        logging.debug('base_dir: %s' % opts.base_dir)
        try:
            os.makedirs('a/b/c')
        except OSError, e:
            if e.errno != errno.EEXIST:
                raise

    if opts.source == 'yum':
        print("installing from repo")
        try:
            aeoluslib.aeolus_cleanup()
        except:
            print("could not uninstall")
        aeoluslib.addrepo()
        aeoluslib.instpkg()
        aeoluslib.aeolus_configure()
        aeoluslib.check_services()
        #aeoluslib.inst_dev_pkg()
        #aeoluslib.pullsrc_compile()

    if opts.source == 'git': # and opts.dir:
        aeoluslib.aeolus_cleanup()
        aeoluslib.addrepo()
        aeoluslib.instpkg()
        aeoluslib.inst_dev_pkg()
        aeoluslib.pullsrc_compile_conductor(base_dir)
        aeoluslib.inst_frm_src_conductor()
        aeoluslib.aeolus_configure()
        aeoluslib.check_services()

    if is_requested('conductor', components): # and opts.dir:
        aeoluslib.cleanup_aeolus()
        aeoluslib.inst_dev_pkg()
        aeoluslib.pullsrc_compile_conductor(base_dir)
        aeoluslib.inst_frm_src_conductor()
        aeoluslib.aeolus_configure()
        aeoluslib.check_services()

    if is_requested('oz', components): # and opts.dir:
        aeoluslib.pullsrc_compile_Oz(base_dir)
        aeoluslib.inst_frm_src_oz()

    if is_requested('imagefactory', components): # and opts.dir:
        aeoluslib.pullsrc_compile_image_factory(base_dir)
        aeoluslib.inst_frm_src_image_factory()

    if is_requested('configure', components): # and opts.dir:
        aeoluslib.pullsrc_compile_Configure(base_dir)
        aeoluslib.inst_frm_src_configure()

    if is_requested('iwhd', components): # and opts.dir:
        aeoluslib.inst_dev_pkg_iwhd()
        aeoluslib.pullsrc_compile_iwhd(base_dir)
        aeoluslib.inst_frm_src_iwhd()

    if is_requested('audrey', components): # and opts.dir:
        aeoluslib.pullsrc_compile_audry(base_dir)
        aeoluslib.inst_frm_src_audry()
