#
# Provide a common logging configuration
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

import logging

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

