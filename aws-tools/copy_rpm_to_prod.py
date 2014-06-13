#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import boto
import boto.s3.key
import os.path
import sys

if len(sys.argv) <= 1:
  print "Pass the rpm you want to copy"
  sys.exit(1)

conn_s3 = boto.connect_s3()
bucket = conn_s3.get_bucket('net.mozaws.ops.rpmrepo')
bucket.copy_key('6/x86_64/%s' % os.path.basename(sys.argv[1]),
                'net.mozaws.ops.rpmrepo-stage',
                '6/x86_64/%s' % os.path.basename(sys.argv[1]))
