#!/usr/bin/env python
# Copyright 2013 Amazon.com, Inc. or its affiliates. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License").
# You may not use this file except in compliance with the License.
# A copy of the License is located at

#  http://aws.amazon.com/apache2.0

# or in the "license" file accompanying this file. This file is distributed
# on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
# express or implied. See the License for the specific language governing
# permissions and limitations under the License.

import boto
import json
import time
import os
import cPickle as pickle
import subprocess as sub
from boto.sqs.message import RawMessage

# Define region and queue below
region = 'us-east-1'
sqsqueue = 'SQS-Queue-Name'
##

conn = boto.connect_sqs()
conn = boto.sqs.connect_to_region(region)

# Define an SQS queue to poll below
q = conn.get_queue(sqsqueue)
q.set_message_class(RawMessage)

if not os.path.isfile('data.pkl'):
    output = open('data.pkl', 'wb')
    data = {}
    pickle.dump(data, output)
    output.close()

while 1:

    results = q.get_messages(10)

    pkl_file = open('data.pkl', 'rb')
    data = pickle.load(pkl_file)
    pkl_file.close()

    while len(results) > 0:

        for result in results:
            message = json.loads(result.get_body())
            message_attrs = json.loads(message['Message'])
            eventType = message_attrs['Event']

            if eventType == 'autoscaling:TEST_NOTIFICATION':
                q.delete_message(result)

            if eventType != 'autoscaling:TEST_NOTIFICATION':
                instanceId = message_attrs['EC2InstanceId']
                if eventType == 'autoscaling:EC2_INSTANCE_LAUNCH':
                    print eventType, instanceId

                    ec2 = boto.connect_ec2()
                    ec2 = boto.ec2.connect_to_region(region)

                    hostname = ec2.get_all_instances(instance_ids=instanceId)[
                        0].instances[0].private_dns_name.split('.')[:1]
                    hostname = hostname[0]

                    data[instanceId] = hostname

                    command = '/opt/openlava-2.1/bin/lsaddhost'
                    arg1 = '-t'
                    arg2 = 'linux'
                    arg3 = '-m'
                    arg4 = 'IntelI5'

                    try:
                        sub.check_call(
                            [command, arg1, arg2, arg3, arg4, hostname])
                    except sub.CalledProcessError:
                        print ("Failed to add %s\n" % hostname)

                    q.delete_message(result)

                elif eventType == 'autoscaling:EC2_INSTANCE_TERMINATE':
                    print eventType, instanceId

                    try:
                        hostname = data[instanceId]

                        command = '/opt/openlava-2.1/bin/lsrmhost'
                        try:
                            sub.check_call([command, hostname])
                        except sub.CalledProcessError:
                            print ("Failed to remove %s\n" % hostname)

                        del data[instanceId]

                    except KeyError:
                        print ("Did not find %s in the metadb\n" % instanceId)

                    q.delete_message(result)

        results = q.get_messages(10)

    pkl_file = open('data.pkl', 'wb')
    pickle.dump(data, pkl_file)
    pkl_file.close()

    time.sleep(30)
