#!/usr/bin/bash
#
# Helper script to automate downloading and running aeolus-install
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

AEOLUS_INSTALL_OPTS="--source=git --build-only"

# Determine what module we've been asked to test
if [ $# -gt 0 ]; then
    PROJECT="$@"
else
    # Should yield something like: git://github.com/clalancette/oz.git
    REMOTE_URL=$(git config --get remote.origin.url)
    # Get the basename, without calling `basename` (should yield: oz.git)
    PROJECT=${REMOTE_URL##*/}
    # Remove the trailing .git (should yield: oz)
    PROJECT=${PROJECT%%.git}
fi

if [ -z "$PROJECT" ]; then
    echo "Error: no project name supplied (or detected)"
    exit 1
fi

# Checkout test code and run test
TESTDIR=/tmp/cloudqe-aeolus

# If the test dir already exists, update it
if [ -d "$TESTDIR" ]; then
    cd "$TESTDIR" && git pull
# Otherwise, create it
else
    git clone git://github.com/RedHatQE/cloudqe-aeolus.git "$TESTDIR"
    cd "$TESTDIR"
fi

# FIXME - it would be nice to use the git checkout jenkins already did
# located in $WORKSPACE
python aeolus-install $AEOLUS_INSTALL_OPTS "$PROJECT"
exit $?
