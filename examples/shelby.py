#!/usr/bin/env python2.7
# Copyright 2013 Amazon.com, Inc. or its affiliates. All Rights Reserved.

# Licensed under the Apache License, Version 2.0 (the "License").
# You may not use this file except in compliance with the License.
# A copy of the License is located at

#  http://aws.amazon.com/apache2.0

# or in the "license" file accompanying this file. This file is distributed
# on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
# express or implied. See the License for the specific language governing
# permissions and limitations under the License.

__author__ = 'dougalb'

# Imports
import sys
import argparse
import boto.ec2.autoscale
import boto.vpc
from boto.ec2.autoscale import AutoScalingGroup
from boto.ec2.autoscale import LaunchConfiguration

# Variables
KEY_NAME = 'dougalb-aws-keypair' # EC2 kaypair name
SECURITY_GROUP = 'sg-f581779a' # EC2 security group name(Classic) or Id(VPC)
PROJECT = 'lava' 
REGION = 'us-west-2'
AMI = 'ami-346ff104'
SNS_ARN = 'arn:aws:sns:us-west-2:560348900601:AS-SNS'
NOTIFICATION_TYPES = [
    'autoscaling:EC2_INSTANCE_LAUNCH', 'autoscaling:EC2_INSTANCE_TERMINATE']
USER_DATA = 'bootas=compute master=ip-172-16-0-10 resources=spot,m1_xlarge'
INSTANCES = [{'instance-type': 'm1.xlarge', 'spot-price': '0.10', 'asgs': 10}]
##             {'instance-type': 'm2.2xlarge', 'spot-price': '0.10', 'asgs': 10}]
SUBNETS = ['subnet-fa5b2d91', 'subnet-e05b2d8b', 'subnet-ff5b2d94']

#
# NOTHING FURTHER NEEDS TO BE CHANGED
#


def make_lc_name(instance):
    __name__ = [PROJECT, REGION, AMI, instance[
        'instance-type'], instance['spot-price']]
    __name__ = '-'.join(__name__)

    return __name__


def get_subnet_az(subnets=SUBNETS):
    vc = boto.vpc.connect_to_region(REGION)
    __subnets__ = vc.get_all_subnets(subnet_ids=subnets)
    __azs__ = []

    for subnet in __subnets__:
        __azs__.append(subnet.availability_zone)

    return __azs__


def check_lc(name, conn):
    __check_lc__ = conn.get_all_launch_configurations(names=[name])
    try:
        __check_lc_name__ = __check_lc__[0].name
    except IndexError:
        __check_lc_name__ = False

    return __check_lc_name__


def check_asg(gname, conn):
    __check_asg__ = conn.get_all_groups(names=[gname])
    try:
        __check_asg_name__ = __check_asg__[0].name
    except IndexError:
        __check_asg_name__ = False

    return __check_asg_name__


def create_lc_asg(instances=INSTANCES):
    # Connect to EC2
    conn = boto.ec2.autoscale.connect_to_region(REGION)

    # Get Availabilty Zones of subnets
    azs = get_subnet_az()

    # Build Autoscaling launch configurations
    launchConfigs = {}
    for instance in instances:
        name = make_lc_name(instance)
        lc = LaunchConfiguration(
            name=name, image_id=AMI, key_name=KEY_NAME, user_data=USER_DATA,
            security_groups=[
                SECURITY_GROUP], instance_type=instance[
                'instance-type'],
            instance_monitoring=False, spot_price=float(instance['spot-price']))

        if name == check_lc(name, conn):
            print("LC: %s already exists, not creating" % name)
        else:
            conn.create_launch_configuration(lc)
            if args.verbose:
                print("Created %s launch configuration" % name)

        for group in xrange(instance['asgs']):
            gname = name + '-g' + str(group)
            subnets_str=','.join(SUBNETS)
            asg = AutoScalingGroup(group_name=gname, default_cooldown=60,
                                   vpc_zone_identifier=subnets_str, availability_zones=azs,
                                   launch_config=lc, min_size=0, max_size=0,
                                   connection=conn)
            if gname == check_asg(gname, conn):
                print("ASG: %s already exists, not creating" % gname)
            else:
                conn.create_auto_scaling_group(asg)
                conn.put_notification_configuration(
                    gname, SNS_ARN, NOTIFICATION_TYPES)
                if args.verbose:
                    print("Created %s auto scaling group" % gname)


def delete_lc_asg(instances=INSTANCES):
    # Connect to EC2
    conn = boto.ec2.autoscale.connect_to_region(REGION)

    # Build Autoscaling launch configurations
    launchConfigs = {}
    for instance in instances:
        name = make_lc_name(instance)
        for group in xrange(instance['asgs']):
            gname = name + '-g' + str(group)
            if check_asg(gname, conn) == False:
                print("ASG: %s does not exist, not deleting" % gname)
            else:
                conn.delete_auto_scaling_group(gname)
                if args.verbose:
                    print("Deleted %s auto scaling group" % gname)

        if check_lc(name, conn) == False:
            print("LC: %s does not exist, not deleting" % name)
        else:
            conn.delete_launch_configuration(name)
            if args.verbose:
                print("Deleted %s launch configuration" % name)


def scale_asgs(num, type, instances=INSTANCES):
    # Connect to EC2
    conn = boto.ec2.autoscale.connect_to_region(REGION)

    if type == False:
        for instance in instances:
            name = make_lc_name(instance)
            for group in xrange(instance['asgs']):
                gname = name + '-g' + str(group)
                asg = AutoScalingGroup(group_name=gname, launch_config=name,
                                       min_size=0, max_size=num, desired_capacity=num)
                conn._update_group('UpdateAutoScalingGroup', asg)
    else:
        for instance in instances:
            if type == instance['instance-type']:
                name = make_lc_name(instance)
                for group in xrange(instance['asgs']):
                    gname = name + '-g' + str(group)
                    asg = AutoScalingGroup(
                        group_name=gname, launch_config=name,
                        min_size=0, max_size=num, desired_capacity=num)
                    conn._update_group('UpdateAutoScalingGroup', asg)


def get_all_instances():

    conn = boto.ec2.autoscale.connect_to_region(REGION)

    __temp_instances__ = []
    __instances__ = conn.get_all_autoscaling_instances()

    while True:
        __temp_instances__.extend(__instances__)
        if not __instances__.next_token:
            break

        __instances__ = conn.get_all_autoscaling_instances(
            next_token=__instances__.next_token)

    return __temp_instances__


def get_status():
    instances = get_all_instances()
    total_instances = len(instances)
    __lifecycle_state__ = []
    __availability_zones__ = []
    for instance in instances:
        __lifecycle_state__.append(instance.lifecycle_state)
        __availability_zones__.append(instance.availability_zone)

    print ("Lifecycle State:")
    for __state__ in set(__lifecycle_state__):
        print(" %s  %d" % (__state__, __lifecycle_state__.count(__state__)))

    print ("Availability Zones:")
    for __availability_zone__ in set(__availability_zones__):
        print(" %s  %d" %
              (__availability_zone__, __availability_zones__.count(__availability_zone__)))

    print("Total instances: %d" % total_instances)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Shelby is a simple tool for managing clusters built using AWS EC2, Autoscaling, SNS & SQS')
    parser.add_argument('--verbose', action='store_true',
                        help='show addtional output when runnning commands')
    parser.add_argument('--action', action='append', help='available actions are: create, scale, status and delete. '
                                                          'create - setup all required config; '
                                                          'scale - set the desired and max instances; '
                                                          'status - show a status of the instances; '
                                                          'delete - delete all created config')
    parser.add_argument('--num', action='store', type=int, help='used to provide the number of instances to scale. '
                                                                '(use 0 to terminate all instances)')
    parser.add_argument('--type', action='store', default=False, help='used with the scale action to scale '
                                                                      'specific instance types')
    parser.add_argument('-y', action='store_true')
    args = parser.parse_args()

    if args.action:
        action = args.action[0]
        if action == 'create':
            create_lc_asg()
        elif action == 'delete':
            if args.y:
                delete_lc_asg()
            else:
                print "You must add -y when deleting!"
                sys.exit(1)
        elif action == "scale":
            if args.num >= 0:
                num = args.num
                type = args.type
                scale_asgs(num, type)
            else:
                print "You must add --num X when scaling"
        elif action == "status":
            get_status()
        else:
            print "Unsupported action!"
            sys.exit(1)
    else:
        parser.print_help()
