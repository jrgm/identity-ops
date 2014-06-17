#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import logging
logging.basicConfig(level=logging.INFO)

import json
import time
import os
import itertools
import argparse

AZ_MAP = {'us-west-2': ['a', 'b', 'c'],
          'us-east-1': ['a','b','d']}

VPC_ENVIRONMENT_MAP = {'prod': 'identity-prod',
                       'stage': 'identity-dev'}

def test_for_stack_existence(region,
                             environment,
                             stack_type,
                             name):
    import boto.ec2
    conn_ec2 = boto.ec2.connect_to_region(region)
    reservations = conn_ec2.get_all_instances(None, {"tag:Name" : "*-%s" % name, "tag:Env"  : stack_type})
    if len(reservations) > 0:
        logging.error('stack exists. instances found : %s' % [x for x in reservations])

def create_stack(region,
                 environment,
                 stack_type,
                 availability_zones,
                 path,
                 application=False,
                 name=None,
                 key_name=None,
                 mini_stack=False,
                 hydrate=True,
                 git_branch_or_commit='HEAD'):
    if name == None:
        # Maybe we set the stack name to the username of the user creating with a number suffix?
        import random
        name = str(random.randint(1, 9999))
    if len(name) > 4:
        raise ValueError("name must not exceed 4 characters in length. '%s' is too long" % name)

    if not key_name:
        key_name = '20130416-svcops-base-key'

    from string import Template
    import boto.ec2
    import boto.ec2.elb
    import boto.ec2.elb.healthcheck
    import boto.vpc
    import boto.iam
    import boto.ec2.cloudwatch
    import boto.ec2.cloudwatch.alarm
    import boto.ec2.autoscale
    import boto.ec2.autoscale.tag
    import boto.cloudformation

    conn_iam = boto.iam.connect_to_region('universal')
    conn_elb = boto.ec2.elb.connect_to_region(region)
    conn_vpc = boto.vpc.connect_to_region(region)
    conn_ec2 = boto.ec2.connect_to_region(region)
    conn_cw = boto.ec2.cloudwatch.connect_to_region(region)
    conn_autoscale = boto.ec2.autoscale.connect_to_region(region)
    stack = {}

    alt_cfn_regions = ['us-west-2', 'us-east-1']
    alt_cfn_regions.remove(region)
    try:
        cfn_region = region
        print('Trying to find IAM cfn stack in region: %s' % cfn_region)
        conn_cfn = boto.cloudformation.connect_to_region(cfn_region)
        iam_roles_stack_resources = conn_cfn.list_stack_resources('identity-iam-roles')
    except:
        print('Could not find IAM cfn stack in region: %s' % region)

    try:
        cfn_region = alt_cfn_regions.pop()
        print('Trying to find IAM cfn stack in region: %s' % cfn_region)
        conn_cfn = boto.cloudformation.connect_to_region(cfn_region)
        iam_roles_stack_resources = conn_cfn.list_stack_resources('identity-iam-roles')
    except:
        print('Could not find IAM cfn stack, aborting.')
        exit(1)

    # Apply recommendation from https://wiki.mozilla.org/Security/Server_Side_TLS
    policy_attributes = {"ADH-AES128-GCM-SHA256": False,
                        "ADH-AES256-GCM-SHA384": False,
                        "ADH-AES128-SHA": False,
                        "ADH-AES128-SHA256": False,
                        "ADH-AES256-SHA": False,
                        "ADH-AES256-SHA256": False,
                        "ADH-CAMELLIA128-SHA": False,
                        "ADH-CAMELLIA256-SHA": False,
                        "ADH-DES-CBC3-SHA": False,
                        "ADH-DES-CBC-SHA": False,
                        "ADH-RC4-MD5": False,
                        "ADH-SEED-SHA": False,
                        "AES128-GCM-SHA256": True,
                        "AES256-GCM-SHA384": True,
                        "AES128-SHA": True,
                        "AES128-SHA256": True,
                        "AES256-SHA": True,
                        "AES256-SHA256": True,
                        "CAMELLIA128-SHA": True,
                        "CAMELLIA256-SHA": True,
                        "DES-CBC3-MD5": False,
                        "DES-CBC3-SHA": False,
                        "DES-CBC-MD5": False,
                        "DES-CBC-SHA": False,
                        "DHE-DSS-AES128-GCM-SHA256": True,
                        "DHE-DSS-AES256-GCM-SHA384": True,
                        "DHE-DSS-AES128-SHA": True,
                        "DHE-DSS-AES128-SHA256": True,
                        "DHE-DSS-AES256-SHA": True,
                        "DHE-DSS-AES256-SHA256": True,
                        "DHE-DSS-CAMELLIA128-SHA": False,
                        "DHE-DSS-CAMELLIA256-SHA": False,
                        "DHE-DSS-SEED-SHA": False,
                        "DHE-RSA-AES128-GCM-SHA256": True,
                        "DHE-RSA-AES256-GCM-SHA384": True,
                        "DHE-RSA-AES128-SHA": True,
                        "DHE-RSA-AES128-SHA256": True,
                        "DHE-RSA-AES256-SHA": True,
                        "DHE-RSA-AES256-SHA256": True,
                        "DHE-RSA-CAMELLIA128-SHA": False,
                        "DHE-RSA-CAMELLIA256-SHA": False,
                        "DHE-RSA-SEED-SHA": False,
                        "EDH-DSS-DES-CBC3-SHA": False,
                        "EDH-DSS-DES-CBC-SHA": False,
                        "EDH-RSA-DES-CBC3-SHA": False,
                        "EDH-RSA-DES-CBC-SHA": False,
                        "EXP-ADH-DES-CBC-SHA": False,
                        "EXP-ADH-RC4-MD5": False,
                        "EXP-DES-CBC-SHA": False,
                        "EXP-EDH-DSS-DES-CBC-SHA": False,
                        "EXP-EDH-RSA-DES-CBC-SHA": False,
                        "EXP-KRB5-DES-CBC-MD5": False,
                        "EXP-KRB5-DES-CBC-SHA": False,
                        "EXP-KRB5-RC2-CBC-MD5": False,
                        "EXP-KRB5-RC2-CBC-SHA": False,
                        "EXP-KRB5-RC4-MD5": False,
                        "EXP-KRB5-RC4-SHA": False,
                        "EXP-RC2-CBC-MD5": False,
                        "EXP-RC4-MD5": False,
                        "IDEA-CBC-SHA": False,
                        "KRB5-DES-CBC3-MD5": False,
                        "KRB5-DES-CBC3-SHA": False,
                        "KRB5-DES-CBC-MD5": False,
                        "KRB5-DES-CBC-SHA": False,
                        "KRB5-RC4-MD5": False,
                        "KRB5-RC4-SHA": False,
                        "Protocol-SSLv2": False,
                        "Protocol-SSLv3": True,
                        "Protocol-TLSv1": True,
                        "Protocol-TLSv1.1": True,
                        "Protocol-TLSv1.2": True,
                        "PSK-3DES-EDE-CBC-SHA": False,
                        "PSK-AES128-CBC-SHA": False,
                        "PSK-AES256-CBC-SHA": False,
                        "PSK-RC4-SHA": False,
                        "RC2-CBC-MD5": False,
                        "RC4-MD5": False,
                        "RC4-SHA": True,
                        "SEED-SHA": False}
    policy_name = 'Mozilla-Security-Assurance-Ciphersuite-Policy-v-2-0'

    policy_attributes = {"ADH-AES128-SHA": False,
                        "ADH-AES256-SHA": False,
                        "ADH-CAMELLIA128-SHA": False,
                        "ADH-CAMELLIA256-SHA": False,
                        "ADH-DES-CBC3-SHA": False,
                        "ADH-DES-CBC-SHA": False,
                        "ADH-RC4-MD5": False,
                        "ADH-SEED-SHA": False,
                        "AES128-SHA": True,
                        "AES256-SHA": True,
                        "CAMELLIA128-SHA": True,
                        "CAMELLIA256-SHA": True,
                        "DES-CBC3-MD5": False,
                        "DES-CBC3-SHA": False,
                        "DES-CBC-MD5": False,
                        "DES-CBC-SHA": False,
                        "DHE-DSS-AES128-SHA": True,
                        "DHE-DSS-AES256-SHA": True,
                        "DHE-DSS-CAMELLIA128-SHA": False,
                        "DHE-DSS-CAMELLIA256-SHA": False,
                        "DHE-DSS-SEED-SHA": False,
                        "DHE-RSA-AES128-SHA": False,
                        "DHE-RSA-AES256-SHA": False,
                        "DHE-RSA-CAMELLIA128-SHA": False,
                        "DHE-RSA-CAMELLIA256-SHA": False,
                        "DHE-RSA-SEED-SHA": False,
                        "EDH-DSS-DES-CBC3-SHA": False,
                        "EDH-DSS-DES-CBC-SHA": False,
                        "EDH-RSA-DES-CBC3-SHA": False,
                        "EDH-RSA-DES-CBC-SHA": False,
                        "EXP-ADH-DES-CBC-SHA": False,
                        "EXP-ADH-RC4-MD5": False,
                        "EXP-DES-CBC-SHA": False,
                        "EXP-EDH-DSS-DES-CBC-SHA": False,
                        "EXP-EDH-RSA-DES-CBC-SHA": False,
                        "EXP-KRB5-DES-CBC-MD5": False,
                        "EXP-KRB5-DES-CBC-SHA": False,
                        "EXP-KRB5-RC2-CBC-MD5": False,
                        "EXP-KRB5-RC2-CBC-SHA": False,
                        "EXP-KRB5-RC4-MD5": False,
                        "EXP-KRB5-RC4-SHA": False,
                        "EXP-RC2-CBC-MD5": False,
                        "EXP-RC4-MD5": False,
                        "IDEA-CBC-SHA": False,
                        "KRB5-DES-CBC3-MD5": False,
                        "KRB5-DES-CBC3-SHA": False,
                        "KRB5-DES-CBC-MD5": False,
                        "KRB5-DES-CBC-SHA": False,
                        "KRB5-RC4-MD5": False,
                        "KRB5-RC4-SHA": False,
                        "Protocol-SSLv2": False,
                        "Protocol-SSLv3": True,
                        "Protocol-TLSv1": True,
                        "PSK-3DES-EDE-CBC-SHA": False,
                        "PSK-AES128-CBC-SHA": False,
                        "PSK-AES256-CBC-SHA": False,
                        "PSK-RC4-SHA": False,
                        "RC2-CBC-MD5": False,
                        "RC4-MD5": False,
                        "RC4-SHA": True,
                        "SEED-SHA": False}

    policy_name = 'Mozilla-Security-Assurance-Ciphersuite-Policy-v-1-2'

    ami_map = json.load(open('/etc/stack_control/ami_map.json', 'r'))

    sns_topics = {"us-west-2": "arn:aws:sns:us-west-2:351644144250:identity-alert",
                  "us-east-1": "arn:aws:sns:us-east-1:351644144250:identity-alert"}

    existing_vpcs = conn_vpc.get_all_vpcs()
    # This will throw an IndexError exception if the VPC isn't found which isn't very intuitive
    vpc = [x for x in existing_vpcs if 'Name' in x.tags and x.tags['Name'] == environment][0]
    
    stack['loadbalancer'] = []
    existing_load_balancers = conn_elb.get_all_load_balancers()
    existing_security_groups = conn_ec2.get_all_security_groups()
    existing_certs = conn_iam.get_all_server_certs(path_prefix=path)['list_server_certificates_response']['list_server_certificates_result']['server_certificate_metadata_list']
    existing_subnets = conn_vpc.get_all_subnets(filters=[('vpcId', [vpc.id])])
    existing_instance_profiles = [x for x in iam_roles_stack_resources if x.resource_type == 'AWS::IAM::InstanceProfile']
    instance_profile_map = dict([(x.logical_resource_id, x.physical_resource_id) for x in existing_instance_profiles])

    for load_balancers_params in json.load(open('/etc/stack_control/elbs_public.%s.json' % stack_type, 'r')) + json.load(open('/etc/stack_control/elbs_private.json')):
        if application and load_balancers_params['application'] != application:
            continue
        load_balancers_params['name'] = '%s-%s' % (load_balancers_params['name'], name)
        for listener in load_balancers_params['listeners']:
            if len(listener) == 4:
                # Convert the cert name to an ARN
                # listener[3] = global_data['certs'][listener[3]]['arn']
                # This thows an IndexError if it can't find the cert which isn't intuitive
                try:
                    listener[3] = [x.arn for x in existing_certs if x['server_certificate_name'] == listener[3]][0]
                except IndexError:
                    logging.error("unable to find cert %s in certs %s" % (listener[3], existing_certs))
                    raise

        # subnets = []
        # for availability_zone in vpc['availability_zones'].keys():
        #    for subnet_name in load_balancers_params['subnets']:
        #        subnets.append(vpc['availability_zones'][availability_zone]['subnets'][subnet_name].id)

        subnets = [x for x in existing_subnets if 'Name' in x.tags and environment + '-' + load_balancers_params['subnet'] in x.tags['Name']]

        security_groups = [x for x in existing_security_groups if x.name in [environment + '-' + y for y in load_balancers_params['security_groups']]]

        logging.debug('About to create load balancer %s' % load_balancers_params['name'])
        stack['loadbalancer'].append(conn_elb.create_load_balancer(
                                       name=load_balancers_params['name'],
                                       zones=None,
                                       listeners=load_balancers_params['listeners'],
                                       subnets=[x.id for x in subnets],
                                       security_groups=[x.id for x in security_groups],
                                       scheme='internal' if load_balancers_params['is_internal'] else 'internet-facing'
                                       ))
        load_balancer = stack['loadbalancer'][-1]
        logging.info('Created load balancer %s' % load_balancer.name)
        
        # TODO : tag the load_balancer

        healthcheck_params = load_balancers_params['healthcheck'] if 'healthcheck' in load_balancers_params else {
            "interval" : 30,
            "target" : "HTTP:80/__heartbeat__",
            "healthy_threshold" : 3,
            "timeout" : 5,
            "unhealthy_threshold" : 5
        }
        # healthcheck_params['access_point'] = load_balancer[name]
        load_balancer.configure_health_check(boto.ec2.elb.healthcheck.HealthCheck(**healthcheck_params))
        logging.info('Healthcheck configured on %s' % load_balancer.name)

        # set the Ciphersuite for https listeners
        https_listeners = [x[0] for x in load_balancers_params['listeners'] if x[2] == 'HTTPS']
        for listener in https_listeners:
            # Create the Ciphersuite Policy
            params = {'LoadBalancerName': load_balancers_params['name'],
                      'PolicyName': policy_name,
                      'PolicyTypeName': 'SSLNegotiationPolicyType'}
            conn_elb.build_complex_list_params(params, 
                                               [(x, "true" if policy_attributes[x] else "false") for x in policy_attributes.keys()],
                                               'PolicyAttributes.member',
                                               ('AttributeName', 'AttributeValue'))
            policy = conn_elb.get_list(action='CreateLoadBalancerPolicy', 
                                       params=params, 
                                       markers=None,
                                       verb='POST')
            logging.info('Load balancer ciper suite policy %s created for %s' % (policy_name, load_balancer.name))

            # Apply the Ciphersuite Policy to your ELB
            params = {'LoadBalancerName': load_balancers_params['name'],
                      'LoadBalancerPort': listener,
                      'PolicyNames.member.1': policy_name}
            
            result = conn_elb.get_list('SetLoadBalancerPoliciesOfListener', params, None)
            logging.info("New policy %s applied to load balancer %s" % (policy_name, load_balancers_params['name']))

        if environment == 'prod':
            # monitor the ELB
            metric = "HTTPCode_Backend_5XX"
            threshold = 6
            period = 120
            metric_alarm = boto.ec2.cloudwatch.alarm.MetricAlarm(
                name="%s %s" % (load_balancers_params['name'], metric),
                metric=metric,
                namespace="AWS/ELB",
                statistic="Average",
                comparison=">=",
                threshold=threshold,
                period=period,
                evaluation_periods=1,
                unit="Count",
                alarm_actions=[sns_topics[region]],
                dimensions={"LoadBalancerName": load_balancers_params['name']},
                description="Alarm when the rate of %s exceeds the threshold %s for %s seconds on the %s ELB" % (
                             metric, threshold, period, load_balancers_params['name']))
            conn_cw.put_metric_alarm(metric_alarm)
            logging.info("Cloudwatch alarm %s created" % ("%s %s" % (load_balancers_params['name'], metric)))
        
        stack['loadbalancer'].append(load_balancer)

    existing_load_balancers = conn_elb.get_all_load_balancers()

    stack_info = {}
    stack_info['load_balancers'] = {}
    for x in [y for y in existing_load_balancers 
              if y.vpc_id == vpc.id 
              and y.name.endswith('-%s' % name) 
              or y.name.endswith('-univ-%s' % stack_type)]:
        if x.name.endswith('-univ-%s' % stack_type):
            si_tier_name = x.name[:-len('-univ-%s' % stack_type)]
        elif x.name.endswith('-%s' % name):
            si_tier_name = x.name[:-len('-%s' % name)]
        stack_info['load_balancers'][si_tier_name] = {}
        stack_info['load_balancers'][si_tier_name]['dns_name'] = x.dns_name
        stack_info['load_balancers'][si_tier_name]['name'] = x.name

    stack_info.update({'name': name,
                       'type': stack_type,
                       'environment': environment})
    
    # auto scale

    stack['launch_configuration'] = []
    stack['autoscale_group'] = []

    # I'm going to combine launch configuration and autoscale group because I don't
    # see us having more than one autoscale group for each launch configuration

    for autoscale_params in json.load(open('/etc/stack_control/autoscale.%s.json' % stack_type, 'r')):
        if application and autoscale_params['application'] != application:
            continue
        launch_configuration_params = autoscale_params['launch_configuration']
        tier = launch_configuration_params['tier']

#         if 'AWS_CONFIG_DIR' in os.environ:
#             user_data_filename = os.path.join(os.environ['AWS_CONFIG_DIR'], 'userdata.%s.%s.json' % (stack_type, tier))
#         else:
#             user_data_filename = '/etc/stack_control/userdata.%s.%s.json' % (stack_type, tier)

        gpg_filename_suffix = {'stage': 'login.anosrep.org',
                               'prod': 'login.persona.org'}[stack_type]
        if 'AWS_CONFIG_DIR' in os.environ:
            gpg_private_key_filename = os.path.join(os.environ['AWS_CONFIG_DIR'], 
                                                    '%s@%s.priv' % (tier, gpg_filename_suffix))
        else:
            gpg_private_key_filename = '/etc/stack_control/%s@%s.priv' % (tier, gpg_filename_suffix)

        with open(gpg_private_key_filename, 'r') as f:
            gpg_private_key = f.read()
        attributes = {'tier': tier,
                      'stack': stack_info,
                      'aws_region': region,
                      'access': {'teams' : {'create' : ['team_services_ops']}}}
        launch_configuration_params['user_data'] = '''#!/bin/bash
yum --assumeyes install https://s3.amazonaws.com/mozilla-identity-us-standard/rpms/python-manage_s3_secrets-1.0.0-1.noarch.rpm https://s3.amazonaws.com/mozilla-identity-us-standard/rpms/python-combine-1.0.0-1.noarch.rpm
oldumask="`umask`" && umask 077
cat > /etc/chef/gpg_key.priv <<End-of-message
%(gpg_private_key)s
End-of-message
cat > /tmp/attributes.json <<End-of-message
%(attributes)s
End-of-message
/usr/bin/manage_s3_secrets get --gpgkey /etc/chef/gpg_key.priv %(filename)s | \
  /usr/bin/combine --json /tmp/attributes.json /dev/stdin > \
  /etc/chef/node.json
umask $oldumask
rm -f /tmp/attributes.json
''' % {'gpg_private_key': gpg_private_key ,
       'attributes': json.dumps(attributes,
                                indent=4),
       'filename': 'persona.%s.%s.json' % (tier, stack_type)}
        launch_configuration_params['user_data'] += "cd /root/identity-ops && git pull && git checkout %s\n" % git_branch_or_commit
        if hydrate:
            launch_configuration_params['user_data'] += "chef-solo -c /etc/chef/solo.rb -j /etc/chef/node.json\n"

        launch_configuration_params['name'] = '%s-%s-%s-%s' % (environment, stack_type, tier, name)
        # TODO : pull the "key_name" out of the json config
        # and set this per stack_type. prod keys for prod servers etc.

        # for testing just spin everything as t1.micro
        if 'instance_type' not in launch_configuration_params:
            launch_configuration_params['instance_type'] = 't1.micro'
        
        # I'm temporarily giving everything outbound intenret access with the "temp-outbound"
        # security group. TODO : I'll bring our resources (yum, github chef, etc) internal later and close
        # this access
        launch_configuration_params['security_groups'].append('temp-internet')

        # removing because we're blocked by aws on a max of 5 security groups for now
        # launch_configuration_params['security_groups'].append('monitorable')
        
        # launch_configuration_params['security_groups'] = [vpc['security-groups'][environment + '-' + x].id for x in launch_configuration_params['security_groups']]
        launch_configuration_params['security_groups'] = [x.id for x in existing_security_groups if x.name in [environment + '-' + y for y in launch_configuration_params['security_groups']]]

        # ami mapping
        launch_configuration_params['image_id'] = ami_map[launch_configuration_params['image_id']][region]

        # key_name
        launch_configuration_params['key_name'] = key_name

        # enable detailed monitoring
        launch_configuration_params['instance_monitoring'] = True

        # IAM role
        if 'instance_profile_logical_name' in launch_configuration_params:
            launch_configuration_params['instance_profile_name'] = instance_profile_map[launch_configuration_params['instance_profile_logical_name']]
            del(launch_configuration_params['instance_profile_logical_name'])
        else:
            launch_configuration_params['instance_profile_name'] = 'identity'

        ag_subnets = [x.id for x in existing_subnets if 'Name' in x.tags and environment + '-' + autoscale_params['subnet'] in x.tags['Name']]
        vpc_zone_identifier = ','.join(ag_subnets)

        if 'scale_method' in autoscale_params and autoscale_params['scale_method'] == 'manual':
            launch_configuration_params['security_group_ids'] = launch_configuration_params['security_groups']
            del(launch_configuration_params['security_groups'])
            launch_configuration_params['monitoring_enabled'] = launch_configuration_params['instance_monitoring']
            del(launch_configuration_params['instance_monitoring'])
            instance_name = launch_configuration_params['name']
            del(launch_configuration_params['name'])

            if 'ebs_optimized' in autoscale_params and autoscale_params['ebs_optimized']:
                launch_configuration_params['ebs_optimized'] = true
            # kernel_id? do we need to set this or is None ok?
            # monitoring_enabled
            
            current_capacity = 0
            for subnet in itertools.cycle([x for x in existing_subnets if x.id in ag_subnets]):
                launch_configuration_params['placement'] = subnet.availability_zone
                launch_configuration_params['subnet_id'] = subnet.id
                reservation = conn_ec2.run_instances(launch_configuration_params)
                logging.info("Instance %s created manually (not autoscaled)" % reservation.instances)
                current_capacity += 1
                reservation.instances[0].add_tag('Name', instance_name)
                reservation.instances[0].add_tag('App', 'identity')
                reservation.instances[0].add_tag('Env', stack_type)
                reservation.instances[0].add_tag('Stack', name)
                reservation.instances[0].add_tag('Tier', tier)
                if current_capacity >= autoscale_params['desired_capacity'] if 'desired_capacity' in autoscale_params else 1:
                    break
        else:
            del(launch_configuration_params['tier'])
            if 'ebs_optimized' in launch_configuration_params:
                del(launch_configuration_params['ebs_optimized'])  # boto doesn't yet support ebsoptimized for autoscaled gropup
            stack['launch_configuration'].append(boto.ec2.autoscale.LaunchConfiguration(**launch_configuration_params))
            launch_configuration = stack['launch_configuration'][-1]
    
            # Don't know what this returns, maybe I should use the return object from create_launch_configuration
            # instead of the instance from the LaunchConfiguration constructor
            # http://docs.aws.amazon.com/AutoScaling/latest/APIReference/API_CreateLaunchConfiguration.html
            # https://github.com/boto/boto/blob/7d1c814c4fecaa69b887e5f1b723ab1f8361cde0/boto/ec2/autoscale/__init__.py#L240
            conn_autoscale.create_launch_configuration(launch_configuration)
            logging.info("Launch configuration %s created" % launch_configuration.name)

            ag_loadbalancers = ['%s-%s' % (x, name) for x in autoscale_params['load_balancers']]
            autoscale_group = boto.ec2.autoscale.AutoScalingGroup(
                    group_name=launch_configuration_params['name'],
                    load_balancers=ag_loadbalancers,
                    availability_zones=[region + x for x in availability_zones],
                    launch_config=launch_configuration,
                    min_size=1,
                    max_size=12,
                    vpc_zone_identifier=vpc_zone_identifier,
                    desired_capacity=0,
                    connection=conn_autoscale)
            conn_autoscale.create_auto_scaling_group(autoscale_group)
            logging.info("Autoscale group %s created with launch "
                         "configuration %s with a desired capacity "
                         "of 0 bound to loadbalancers %s" % 
                         (autoscale_group.name,
                          launch_configuration.name,
                          ag_loadbalancers))
            
            stack['autoscale_group'].append(conn_autoscale.get_all_groups(names=[launch_configuration_params['name']])[0])
            autoscale_group = stack['autoscale_group'][-1]
    
            conn_autoscale.create_or_update_tags([boto.ec2.autoscale.Tag(key='Name',
                                                                         value=launch_configuration_params['name'],
                                                                         propagate_at_launch=True,
                                                                         resource_id=launch_configuration_params['name']),
                                                  boto.ec2.autoscale.Tag(key='App',
                                                                         value='identity',
                                                                         propagate_at_launch=True,
                                                                         resource_id=launch_configuration_params['name']),
                                                  boto.ec2.autoscale.Tag(key='Env',
                                                                         value=stack_type,
                                                                         propagate_at_launch=True,
                                                                         resource_id=launch_configuration_params['name']),
                                                  boto.ec2.autoscale.Tag(key='Stack',
                                                                         value=name,
                                                                         propagate_at_launch=True,
                                                                         resource_id=launch_configuration_params['name']),
                                                  boto.ec2.autoscale.Tag(key='Tier',
                                                                         value=tier,
                                                                         propagate_at_launch=True,
                                                                         resource_id=launch_configuration_params['name'])])    
            logging.info("Autoscale group %s tagged" % launch_configuration_params['name'])

            # Now we set_desired_capacity up from 0 so instances start spinning up
            if mini_stack:
                autoscale_params['desired_capacity'] = 1

            ag_desired_capacity = autoscale_params['desired_capacity'] if 'desired_capacity' in autoscale_params else 1
            conn_autoscale.set_desired_capacity(launch_configuration_params['name'],
                                                ag_desired_capacity)
            logging.info("Autoscale group %s desired capacity increased from 0 to %s" % 
                         (launch_configuration_params['name'],
                          ag_desired_capacity))

            # Let's see how it's going
            # conn_autoscale = boto.ec2.autoscale.connect_to_region(region)
            # conn_autoscale.get_all_groups(['identity-dev1-stage-admin-g1'])[0].get_activities()
            # conn_autoscale.get_all_groups(['identity-dev-stage-admin-g1'])[0].get_activities()
        
            # Associate Elastic IP with admin box?

    # stack_filename = "/home/gene/Documents/identity-stack-%s.pkl" % name
    # pickle.dump(stack, open(stack_filename, 'wb'))
    # logging.info('pickled stack to %s' % stack_filename)
    logging.info('%s : stack %s:%s created' % (time.strftime('%c'), region, name))
    return stack

def destroy_stack(region,
                  environment,
                  stack_type,
                  name):
    # Find associated ELBs
    # Find ELB associated Autoscale groups
    # find EIPs associated with proxy instances and delete them
    # destroy AG instances
    # destroy AG and Launchconfig
    # destroy ELBs

    # TODO : check DNS to see that nothing CNAMEs to an ELB with the stack name in it indicating it's in use

    import boto.ec2
    import boto.ec2.elb
    import boto.ec2.autoscale
    import boto.ec2.cloudwatch
    conn_autoscale = boto.ec2.autoscale.connect_to_region(region)
    conn_elb = boto.ec2.elb.connect_to_region(region)
    conn_ec2 = boto.ec2.connect_to_region(region)
    conn_cw = boto.ec2.cloudwatch.connect_to_region(region)
    
    existing_autoscale_groups = conn_autoscale.get_all_groups()
    existing_launch_configurations = conn_autoscale.get_all_launch_configurations()
    existing_load_balancers = conn_elb.get_all_load_balancers()
    existing_addresses = conn_ec2.get_all_addresses()

    autoscale_groups = []
    launch_configurations = []
    load_balancers = []
    alarms = []
    for autoscale_params in json.load(open('/etc/stack_control/autoscale.%s.json' % stack_type, 'r')):
        ag_name = '%s-%s-%s-%s' % (environment, stack_type, autoscale_params['launch_configuration']['tier'], name)
        ag = [x for x in existing_autoscale_groups if x.name == ag_name]
        autoscale_groups.extend(ag)
        launch_configurations.extend([x for x in existing_launch_configurations if x.name == ag_name])

    metric = "HTTPCode_Backend_5XX"

    for load_balancers_params in json.load(open('/etc/stack_control/elbs_public.%s.json' % stack_type, 'r')) + json.load(open('/etc/stack_control/elbs_private.json')):
        load_balancers_params['name'] = '%s-%s' % (load_balancers_params['name'], name)
        load_balancers.extend([x for x in existing_load_balancers if x.name == load_balancers_params['name']])
        alarms.extend(["%s %s" % (load_balancers_params['name'], metric)])

    # Delete alarms
    conn_cw.delete_alarms(alarms)
    logging.info('Alarms %s deleted' % alarms)

    
    # Disassociate EIPs and release them
    for autoscale_group in autoscale_groups:
        for address in [x for x in existing_addresses if x.instance_id in [y.instance_id for y in autoscale_group.instances]]:
            if not conn_ec2.disassociate_address(association_id=address.association_id):
                logging.error('failed to disassociate eip %s from instance %s' % (address.public_ip, address.instance_id))
            logging.info('Disassociated EIP %s from %s' % (address.public_ip, address.instance_id))
            if not conn_ec2.release_address(allocation_id=address.allocation_id):
                logging.error('failed to release eip %s' % address.public_ip)
            logging.info('Released EIP %s' % address.public_ip)

    # Shutdown all instances in the stack
    for autoscale_group in autoscale_groups:
        autoscale_group.shutdown_instances()
        logging.info('Shutting down instances for autoscale group %s' % autoscale_group.name)

    # Wait for all instances to terminate and deleting autoscale groups
    existing_autoscale_groups = conn_autoscale.get_all_groups()
    for autoscale_group in autoscale_groups:
        attempts = 0
        while True:
            attempts += 1
            remaining_live_instances = len([x.instances for x in existing_autoscale_groups if x.name == autoscale_group.name][0])
            if remaining_live_instances == 0:
                time.sleep(5)
                autoscale_group.delete()
                logging.info('Autoscale group %s deleted' % autoscale_group.name)
                break
            else:
                logging.info('waiting 10 seconds for remaining %s instances in the %s autoscale group to finish shutting down' % (remaining_live_instances, autoscale_group.name))
                time.sleep(10)
                existing_autoscale_groups = conn_autoscale.get_all_groups([x.name for x in autoscale_groups])
                if attempts > 30:
                    logging.error('unable to delete autoscale group %s after 5 minutes' % autoscale_group.name)
                    autoscale_group.get_activities()
                    autoscale_group.delete()
                    logging.info('Autoscale group %s deleted' % autoscale_group.name)
                    break

    # Delete launch configurations
    for launch_configuration in launch_configurations:
        launch_configuration.delete()
        logging.info('Launch configuration %s deleted' % launch_configuration.name)

    # Delete load balancers
    for load_balancer in load_balancers:
        load_balancer.delete()
        logging.info('Load balancer %s deleted' % load_balancer.name)
    logging.info('%s : stack %s:%s destroyed' % (time.strftime('%c'), region, name))

def get_stack(region, environment, stack_type, name):
    import pprint
    import boto.ec2
    import boto.ec2.elb
    import json
    # import boto.ec2.autoscale
    # conn_autoscale = boto.ec2.autoscale.connect_to_region(region)
    conn_elb = boto.ec2.elb.connect_to_region(region)
    #conn_ec2 = boto.ec2.connect_to_region(region)
    # existing_autoscale_groups = conn_autoscale.get_all_groups()
    # existing_launch_configurations = conn_autoscale.get_all_launch_configurations()
    existing_load_balancers = conn_elb.get_all_load_balancers()
    # existing_addresses = conn_ec2.get_all_addresses()

    output = {}
    #output['instances'] = {}
    output['load balancers'] = {}
    #reservations = conn_ec2.get_all_instances(None, {"tag:Name" : "*-%s" % name,
    #                                                 "tag:Env"  : stack_type})
    #reservations.extend(conn_ec2.get_all_instances(None, {"tag:Name" : "*-univ",
    #                                                      "tag:Env"  : stack_type}))
    #for reservation in reservations:
    #    for instance in reservation.instances:
    #        if instance.state == 'running':
    #            output['instances'][instance.id] = {'Name'               : instance.tags['Name'],
    #                                                'private_ip_address' : instance.private_ip_address}
    #            if instance.ip_address:
    #               output['bastion_ip'] = instance.ip_address
    #output['instance_ip_list'] = " ".join([output['instances'][x]['private_ip_address'] for x in output['instances'].keys()])
    for load_balancer in [x for x in existing_load_balancers if x.name[-len(name) - 1:] == "-%s" % name]:
        #lb_instances = [{'id': x.id,
        #                 'Name' : output['instances'][x.id]['Name'],
        #                 'private_ip_address' : output['instances'][x.id]['private_ip_address']} for x in load_balancer.instances]
        output['load balancers'][load_balancer.name] = {'dns_name' : load_balancer.dns_name}
                                                        #'instances': lb_instances}
    return output

def show_stack(region, environment, stack_type, name):
    output = get_stack(region, environment, stack_type, name)
    print "# Stack %s : %s : %s" % (name, region, stack_type)
    print "```"
    for x in output.keys():
        print x
        print json.dumps(output[x], sort_keys=True, indent=4, separators=(',', ': '))
    print "```"

def point_dns_to_stack(region, stack_type, application, name):
    import sys
    import os
    import json
    import boto.ec2.elb

    from dynect.DynectDNS import DynectRest  # sudo pip install https://github.com/dyninc/Dynect-API-Python-Library/zipball/master

    if stack_type == 'stage':
        zone = 'anosrep.org'
        if application == 'persona':
            elbs = {'firefoxos.anosrep.org': 'w-anosrep-org',
                    'login.anosrep.org': 'w-anosrep-org',
                    'www.anosrep.org': 'w-anosrep-org',
                    'static.login.anosrep.org': 'w-login-anosrep-org',
                    'verifier.login.anosrep.org': 'w-login-anosrep-org'}
        elif application == 'bridge-yahoo':
            elbs = {'yahoo.login.anosrep.org': 'yahoo-login-anosrep-org'}
        elif application == 'bridge-gmail':
            elbs = {'gmail.login.anosrep.org': 'gmail-login-anosrep-org'}
        elif not application:
            elbs = {'firefoxos.anosrep.org': 'w-anosrep-org',
                    'login.anosrep.org': 'w-anosrep-org',
                    'www.anosrep.org': 'w-anosrep-org',
                    'static.login.anosrep.org': 'w-login-anosrep-org',
                    'verifier.login.anosrep.org': 'w-login-anosrep-org',
                    'gmail.login.anosrep.org': 'gmail-login-anosrep-org',
                    'yahoo.login.anosrep.org': 'yahoo-login-anosrep-org'}
        else:
            raise ValueError("application value is bad : %s" % application)
    elif stack_type == 'prod':
        zone = 'persona.org'
        if application == 'persona':
            elbs = {'login.persona.org': 'persona-org',
                    'www.persona.org': 'persona-org'}
        elif application == 'bridge-yahoo':
            elbs = {'yahoo.login.persona.org': 'yahoo-login-persona-org'}
        elif application == 'bridge-gmail':
            elbs = {'gmail.login.persona.org': 'gmail-login-persona-org'}
        elif not application:
            elbs = {'login.persona.org': 'persona-org',
                    'www.persona.org': 'persona-org',
                    'gmail.login.persona.org': 'gmail-login-persona-org',
                    'yahoo.login.persona.org': 'yahoo-login-persona-org'}
        else:
            raise ValueError("application value is bad : %s" % application)
    new_names = {}

    # TODO : This doesn't work for prod because we need to inject multiple regions into traffic mangement
    
    conn_elb = boto.ec2.elb.connect_to_region(region)
    load_balancers = conn_elb.get_all_load_balancers(load_balancer_names=['%s-%s' % (x, name) for x in set(elbs.values())])
    for load_balancer in load_balancers:
        new_names['-'.join(load_balancer.name.split('-')[:-1])] = load_balancer.dns_name

    rest_iface = DynectRest()
    if 'AWS_CONFIG_DIR' in os.environ:
        user_data_filename = os.path.join(os.environ['AWS_CONFIG_DIR'], 'dynect.json')
    else:
        user_data_filename = '/etc/stack_control/dynect.json'

    with open(user_data_filename, 'r') as f:
        dynect_credentials = json.load(f)
    
    # Log in
    response = rest_iface.execute('/Session/', 'POST', dynect_credentials)
    
    if response['status'] != 'success':
      sys.exit("Incorrect credentials")
    
    for record in elbs.keys():
        # Get record_id
        uri = '/CNAMERecord/%s/%s/' % (zone, record)
        response = rest_iface.execute(uri, 'GET')
        record_id = response['data'][0].split('/')[-1]
        uri = uri + record_id + '/'
    
        # Get current record
        response = rest_iface.execute(uri, 'GET')
        old_name = response['data']['rdata']['cname']
        
        # Set new record
        new_name = new_names[elbs[record]] + '.'
        arguments = {'rdata': {'cname': new_name}}
        logging.info('calling "%s" to change the record from "%s" to "%s"' % (uri, old_name, new_name))
        response = rest_iface.execute(uri, 'PUT', arguments)
        logging.info(json.dumps(response['msgs']))

    # Publish the new zone
    response = rest_iface.execute('/Zone/%s' % zone, 'PUT', {'publish': 1})
    logging.info('new zone published with updates at serial number %s' % response['data']['serial'])

    # Log out, to be polite
    rest_iface.execute('/Session/', 'DELETE')

def collect_arguments():
    def type_stackname(stackname):
        if len(stackname) > 4:
            raise argparse.ArgumentTypeError('Stack name must not exceed 4 characters in length')
        return stackname
        
    defaults = {'region': 'us-west-2',
                'path': '/identity/',
                'environment': 'stage',
                'git': 'HEAD'}
    description = 'stack_control can be used to create, destroy and show information on Identity application stacks'
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('-p', '--path',
                        default=defaults['path'],
                        help='ARN Path prefix (default : %s)' % defaults['path'])
    parser.add_argument('-r', '--region', choices=['us-west-2', 'us-east-1'],
                        default=defaults['region'],
                        help='AWS region (default : %s)' % defaults['region'])
    parser.add_argument('-e', '--environment', choices=['stage', 'prod'],
                        default=defaults['environment'],
                        help='Environment (default : %s)' % defaults['environment'])

    parsers = {}
    subparsers = parser.add_subparsers(dest='action',
                                       help='sub-command help')
    parsers['create'] = subparsers.add_parser('create', help='create --help')
    parsers['create'].add_argument('-g', '--git', default=defaults['git'],
                help='git branch name or commit hash to instruct instances to '
                'draw from for their identity-ops chef code (default: %s)' %
                defaults['git'])
    parsers['create'].add_argument('name', type=type_stackname, help='Stack name')
    parsers['destroy'] = subparsers.add_parser('destroy', help='destroy --help')
    parsers['destroy'].add_argument('name', type=type_stackname, help='Stack name')
    parsers['show'] = subparsers.add_parser('show', help='show --help')
    parsers['show'].add_argument('name', type=type_stackname, help='Stack name')
    return parser.parse_args()
    
def main():
    args = collect_arguments()
    if args.action == 'create':
        stack = create_stack(region=args.region,
                             environment=VPC_ENVIRONMENT_MAP[args.environment],
                             stack_type=args.environment,
                             availability_zones=AZ_MAP[args.region],
                             path=args.path,
                             name=args.name,
                             git_branch_or_commit=args.git)
    elif args.action == 'destroy':
        stack = destroy_stack(region=args.region,
                             environment=VPC_ENVIRONMENT_MAP[args.environment],
                             stack_type=args.environment,
                             name=args.name)
    elif args.action == 'show':
        show_stack(region=args.region,
                   environment=VPC_ENVIRONMENT_MAP[args.environment],
                   stack_type=args.environment,
                   name=args.name)

#     point_dns_to_stack(region=region, 
#                        stack_type='stage', 
#                        application='bridge-yahoo',
#                        name='1014')

if __name__ == '__main__':
    main()
