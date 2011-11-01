#
# Provide common command-line interface parsing routines
#
# Copyright (C) 2011  Red Hat
# James Laska <jlaska@redhat.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import sys
import inspect
import optparse
import textwrap

command_list = ['list-requires', 'list-buildrequires',
                'install-requires', 'install-buildrequires',
                'install',
                'build',
                'ls-remote',
                'unittest']

try:
    import aeoluslib
except ImportError:
    print "Unable to import aeoluslib.  Is aeoluslib in PYTHONPATH?"
    sys.exit(1)

def is_aeolusmodule(object):
    '''The built-in issubclass treats classes as subclasses of themselves.
    This method does not.'''
    if inspect.isclass(object) \
       and issubclass(object, aeoluslib.AeolusModule) \
       and aeoluslib.AeolusModule in object.__bases__:
        return True
    return False

def get_supported_modules():
    # this is weird, but I use the class attribute (if available), otherwise we
    # just use the class name (lowercased).
    return [hasattr(mbr[1], 'name') and mbr[1].name or mbr[0].lower() \
        for mbr in inspect.getmembers(aeoluslib, is_aeolusmodule)]

def get_supported_aliases():
    '''Return a list of supported AeolusModule names'''
    # The following doesn't work in python-2.6 (or older)
    #if sys.version_info > (2, 6):
    #    return {mbr[0].lower(): mbr[1].name \
    #        for mbr in inspect.getmembers(aeoluslib, is_aeolusmodule) \
    #        if hasattr(mbr[1], 'name')}
    return dict((mbr[0].lower(), mbr[1].name) \
        for mbr in inspect.getmembers(aeoluslib, is_aeolusmodule) \
        if hasattr(mbr[1], 'name'))

def find_module(name):
    '''Find and return a class with either ...
        1) a class attribute of 'name' that matches the provided name, or
        2) a class whose name (lower-case) matches provided name
    '''
    for (objname, obj) in inspect.getmembers(aeoluslib, is_aeolusmodule):
        if (hasattr(obj, 'name') and obj.name == name) or \
           name.lower() == objname.lower():
            return obj
    return None

def parse_args(argv=sys.argv[1:]):

    # Old method - Hard code the list of supported modules
    component_list = ['all']
    component_list.extend(get_supported_modules())

    parser = optparse.OptionParser()
    parser.usage = '''%%prog [options] <command> [module(s)]

Supported commands include:
 %s

Supported modules include:
 %s

Examples:
 * Build oz from git
   $ aeolus-helper --basedir=/home build oz
 * Install audrey using yum
   $ aeolus-helper --source=yum install audrey
 * Install everything from git
   $ aeolus-helper --source=git install all''' % \
    (textwrap.fill(', '.join(command_list), parser.formatter.width, subsequent_indent=' '),
     textwrap.fill(', '.join(component_list), parser.formatter.width, subsequent_indent=' '),)

    source_choices = ["git", "yum"] # first is default
    parser.add_option("--source", action="store", default=source_choices[0],
        type="choice", choices=source_choices,
        help="Install source to use for install (default: %default, options: " + \
            ", ".join(source_choices) + ")")
    parser.add_option("--repofile", action="append",
        #default=['http://repos.fedorapeople.org/repos/aeolus/conductor/testing/fedora-aeolus-testing.repo'],
        default=[],
        help="Specify custom yum .repo file(s) for use with --source=yum. (default: %default)")
    parser.add_option("-p", "--basedir", "--base_dir", action="store",
        dest="basedir", default=None,
        help="providing a base dir for installation")
    parser.add_option("--log", action="store", dest="logfile",
        default=None, help="Log output to a file")
    parser.add_option("--no-clean", action="store_true", dest="no_clean",
        default=False, help="Don't cleanup after completion",)
    parser.add_option("-d", "--debug", action="store_true", dest="debug",)
    parser.add_option("-f", "--force-install", action="store_true", dest="rpmforce",
        default=False, help="install packages w/ rpm --force rather than yum",)

    #argv = argv[:rIndex] + argv[rIndex+1:]
    #(opts, args) = parser.parse_args(argv[:rIndex])
    (opts, args) = parser.parse_args(argv)

    # Sanitize source
    o = parser.get_option("--source")
    if opts.source not in o.choices:
        parser.error("Must provide value for %s" % o.get_opt_string())

    # Sanity --basedir
    if opts.source == 'git':
        '''FIXME - optionally sanitize opts.basedir'''

    elif opts.source == 'yum':
        '''FIXME - optionally sanitize opts.repofile'''

    # Sanitize command requested
    if len(args) <= 0 or args[0] not in command_list:
        parser.error("Unknown command provided")
    else:
        command = args[0]
        args = args[1:]

    # Sanitize component list
    if len(args) <= 0:
        parser.error("No component provided")

    component_alias_dict = get_supported_aliases()
    for a in args:
        if not (a in component_list or a in component_alias_dict.keys()):
            parser.error("Unknown component selected: %s" % a)
    # Replace any aliases with the true module name
    args = [a in component_alias_dict.keys() and component_alias_dict[a] or a \
                for a in args]

    return (opts, [command] + args)
